#!/usr/bin/env python3.14
"""Prove the warehouse pins each run's reference catalog and instances.

Every check runs inside one transaction that is rolled back, so the warehouse is
left exactly as it was. A test that cannot reach the warehouse is skipped
loudly; a reachable warehouse without the pinning migration fails, because a
gate that passes when it cannot see the thing it checks is not a gate.
"""

from __future__ import annotations

import os
import sys
import unittest
import uuid
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from solverforge_bench.pins import (  # noqa: E402
    record_run_instances,
    reference_catalog_snapshot,
    sync_reference_catalog,
)

DATABASE_URL = os.environ.get(
    "BENCH_DATABASE_URL", "postgresql://postgres@localhost/solverforge_bench"
)

HASH_A = "a" * 64
HASH_B = "b" * 64


class _Rollback(Exception):
    pass


class WarehousePinningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            import psycopg
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"psycopg unavailable: {exc}") from exc
        try:
            cls.conn = psycopg.connect(
                DATABASE_URL,
                autocommit=True,
                options="-c default_transaction_read_only=off",
            )
        except psycopg.OperationalError as exc:
            raise unittest.SkipTest(f"warehouse unreachable: {exc}") from exc
        with cls.conn.cursor() as cur:
            cur.execute("SELECT to_regproc('benchmark_sync_reference_catalog')")
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise AssertionError(
                    "the warehouse lacks the pinning migration; run make db-migrate"
                )
        cls.snapshot = reference_catalog_snapshot(ROOT)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.conn.close()

    def run_rolled_back(self, body) -> None:
        """Run ``body`` in a transaction and always roll it back."""
        try:
            with self.conn.transaction():
                body(self.conn)
                raise _Rollback
        except _Rollback:
            pass

    def _open_run(self, conn, *, instances: list[str]) -> uuid.UUID:
        digest = sync_reference_catalog(conn, self.snapshot)
        run_id = uuid.uuid4()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO benchmark_runs (
                    id, run_kind, run_stamp, benchmark_name, benchmark_category,
                    output_path, artifact_dir, solvers, time_limits_seconds,
                    repo_root, git_dirty, python_version, expected_result_count,
                    expected_matrix_sha256, reference_catalog_sha256
                )
                VALUES (%s, 'quick', 'pin-test', 'job-shop-scheduling', 'test',
                        'out.csv', 'artifacts', ARRAY['s'], ARRAY[1], '/repo',
                        false, 'test', %s, %s, %s)
                """,
                (run_id, len(instances), HASH_A, digest),
            )
            for instance in instances:
                cur.execute(
                    """
                    INSERT INTO benchmark_run_matrix_entries (
                        run_id, dataset, dataset_set, instance, solver,
                        time_limit_seconds
                    ) VALUES (%s, 'JSPLIB', 'quick', %s, 's', 1)
                    """,
                    (run_id, instance),
                )
        return run_id

    def _records(self, *pairs: tuple[str, str]) -> list[dict]:
        return [
            {
                "dataset": "JSPLIB",
                "dataset_set": "quick",
                "instance": instance,
                "instance_size": 36,
                "input_sha256": digest,
            }
            for instance, digest in pairs
        ]

    def test_sync_is_idempotent_and_matches_the_committed_catalog(self) -> None:
        def body(conn):
            first = sync_reference_catalog(conn, self.snapshot)
            second = sync_reference_catalog(conn, self.snapshot)
            self.assertEqual(first, second)
            self.assertRegex(first, "^[0-9a-f]{64}$")
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT benchmark_name, dataset, instance, reference_cost, "
                    "reference_kind, source_name, source_revision "
                    "FROM benchmark_reference_catalog"
                )
                stored = set(cur.fetchall())
                cur.execute(
                    "SELECT entry_count FROM benchmark_reference_catalog_versions "
                    "WHERE sha256 = %s",
                    (first,),
                )
                self.assertEqual(cur.fetchone()[0], len(self.snapshot.entries))
            committed = {
                (
                    e["benchmark_name"],
                    e["dataset"],
                    e["instance"],
                    e["reference_cost"],
                    e["reference_kind"],
                    e["source_name"],
                    e["source_revision"],
                )
                for e in self.snapshot.entries
            }
            self.assertEqual(stored, committed)

        self.run_rolled_back(body)

    def test_a_changed_catalog_is_a_new_version_and_drops_removed_values(self) -> None:
        def body(conn):
            original = sync_reference_catalog(conn, self.snapshot)
            entries = list(self.snapshot.entries)
            dropped = entries.pop()
            changed = dict(entries[0], reference_cost=entries[0]["reference_cost"] + 1)
            entries[0] = changed
            altered = type(self.snapshot)(
                entries=tuple(entries), sources=self.snapshot.sources
            )
            digest = sync_reference_catalog(conn, altered)
            self.assertNotEqual(digest, original)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM benchmark_reference_catalog "
                    "WHERE benchmark_name = %s AND instance = %s",
                    (dropped["benchmark_name"], dropped["instance"]),
                )
                self.assertEqual(cur.fetchone()[0], 0)
                cur.execute(
                    "SELECT reference_cost FROM benchmark_reference_catalog "
                    "WHERE benchmark_name = %s AND instance = %s",
                    (changed["benchmark_name"], changed["instance"]),
                )
                self.assertEqual(cur.fetchone()[0], changed["reference_cost"])
                cur.execute(
                    "SELECT count(*) FROM benchmark_reference_catalog_versions "
                    "WHERE sha256 IN (%s, %s)",
                    (original, digest),
                )
                self.assertEqual(cur.fetchone()[0], 2)

        self.run_rolled_back(body)

    def test_a_catalog_that_repeats_an_instance_is_refused(self) -> None:
        import psycopg

        def body(conn):
            entries = self.snapshot.entries + (self.snapshot.entries[0],)
            repeated = type(self.snapshot)(
                entries=entries, sources=self.snapshot.sources
            )
            with self.assertRaises(psycopg.errors.RaiseException):
                with conn.transaction():
                    sync_reference_catalog(conn, repeated)

        self.run_rolled_back(body)

    def test_a_run_cannot_open_without_a_catalog_version(self) -> None:
        import psycopg

        def body(conn):
            with self.assertRaises(psycopg.errors.CheckViolation):
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO benchmark_runs (
                            id, run_kind, run_stamp, benchmark_name,
                            benchmark_category, output_path, artifact_dir, solvers,
                            time_limits_seconds, repo_root, git_dirty, python_version
                        )
                        VALUES (%s, 'quick', 'pin-test', 'job-shop-scheduling',
                                'test', 'o', 'a', ARRAY['s'], ARRAY[1], '/r',
                                false, 't')
                        """,
                        (uuid.uuid4(),),
                    )

        self.run_rolled_back(body)

    def test_run_instances_must_equal_the_matrix(self) -> None:
        import psycopg

        def body(conn):
            run_id = self._open_run(conn, instances=["ft06", "la01"])
            with self.assertRaises(psycopg.errors.RaiseException):
                with conn.transaction():
                    record_run_instances(conn, run_id, self._records(("ft06", HASH_A)))
            with self.assertRaises(psycopg.errors.RaiseException):
                with conn.transaction():
                    record_run_instances(
                        conn,
                        run_id,
                        self._records(
                            ("ft06", HASH_A), ("la01", HASH_A), ("la02", HASH_A)
                        ),
                    )
            recorded = record_run_instances(
                conn, run_id, self._records(("ft06", HASH_A), ("la01", HASH_B))
            )
            self.assertEqual(recorded, 2)

        self.run_rolled_back(body)

    def test_a_changed_instance_shows_as_a_second_version(self) -> None:
        def body(conn):
            first = self._open_run(conn, instances=["pin-test-instance"])
            record_run_instances(
                conn, first, self._records(("pin-test-instance", HASH_A))
            )
            second = self._open_run(conn, instances=["pin-test-instance"])
            record_run_instances(
                conn, second, self._records(("pin-test-instance", HASH_B))
            )
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT input_sha256, changed, run_count "
                    "FROM benchmark_instance_versions "
                    "WHERE instance = 'pin-test-instance' ORDER BY input_sha256"
                )
                self.assertEqual(cur.fetchall(), [(HASH_A, True, 1), (HASH_B, True, 1)])

        self.run_rolled_back(body)

    def test_a_result_for_an_unpinned_instance_is_refused(self) -> None:
        import psycopg

        def body(conn):
            run_id = self._open_run(conn, instances=["ft06"])
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO benchmark_results (
                            run_id, row_index, benchmark_name, benchmark_category,
                            dataset, dataset_set, instance, solver,
                            time_limit_seconds, actual_time_seconds
                        ) VALUES (%s, 0, 'job-shop-scheduling', 'test', 'JSPLIB',
                                  'quick', 'ft06', 's', 1, 1.0)
                        """,
                        (run_id,),
                    )

        self.run_rolled_back(body)

    def test_publication_requires_pins_only_from_pinned_runs(self) -> None:
        def body(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM benchmark_run_publication_audit "
                    "WHERE NOT input_pinning_required "
                    "  AND publication_failures && ARRAY["
                    "    'reference_catalog_unpinned', 'instances_unpinned',"
                    "    'reference_cost_mismatch']::text[]"
                )
                self.assertEqual(cur.fetchone()[0], 0)
            run_id = self._open_run(conn, instances=["ft06"])
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT publication_failures FROM benchmark_run_publication_audit "
                    "WHERE run_id = %s",
                    (run_id,),
                )
                self.assertIn("instances_unpinned", cur.fetchone()[0])
            record_run_instances(conn, run_id, self._records(("ft06", HASH_A)))
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT publication_failures FROM benchmark_run_publication_audit "
                    "WHERE run_id = %s",
                    (run_id,),
                )
                failures = cur.fetchone()[0]
            self.assertNotIn("instances_unpinned", failures)
            self.assertNotIn("reference_catalog_unpinned", failures)

        self.run_rolled_back(body)

    def test_a_reference_that_disagrees_with_the_pinned_catalog_blocks_publication(
        self,
    ) -> None:
        def body(conn):
            run_id = self._open_run(conn, instances=["ft06"])
            record_run_instances(conn, run_id, self._records(("ft06", HASH_A)))
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO benchmark_solver_versions "
                    "(run_id, solver, solver_version, version_source) "
                    "VALUES (%s, 's', '1', 'test') RETURNING id",
                    (run_id,),
                )
                version_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO benchmark_results (
                        run_id, row_index, benchmark_name, benchmark_category,
                        dataset, dataset_set, instance, solver, solver_version_id,
                        time_limit_seconds, actual_time_seconds, overshoot_seconds,
                        overshoot_ratio, wall_time_over_limit,
                        watchdog_limit_seconds, watchdog_killed, row_payload,
                        fair_start_valid, fair_start_error, reference_cost
                    ) VALUES (%s, 0, 'job-shop-scheduling', 'test', 'JSPLIB',
                              'quick', 'ft06', 's', %s, 1, 1.0, 0, 0, false, 10,
                              false, '{}', false, 'test row', 1.0)
                    """,
                    (run_id, version_id),
                )
                cur.execute(
                    "SELECT reference_cost_mismatch_count, publication_failures "
                    "FROM benchmark_run_publication_audit WHERE run_id = %s",
                    (run_id,),
                )
                count, failures = cur.fetchone()
            self.assertEqual(count, 1)
            self.assertIn("reference_cost_mismatch", failures)

        self.run_rolled_back(body)

    def test_a_witness_hash_that_disagrees_with_the_pinned_instance_blocks_publication(
        self,
    ) -> None:
        from psycopg.types.json import Jsonb

        def body(conn):
            run_id = self._open_run(conn, instances=["ft06"])
            record_run_instances(conn, run_id, self._records(("ft06", HASH_A)))
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO benchmark_solver_versions "
                    "(run_id, solver, solver_version, version_source) "
                    "VALUES (%s, 's', '1', 'test') RETURNING id",
                    (run_id,),
                )
                version_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO benchmark_results (
                        run_id, row_index, benchmark_name, benchmark_category,
                        dataset, dataset_set, instance, solver, solver_version_id,
                        time_limit_seconds, actual_time_seconds, overshoot_seconds,
                        overshoot_ratio, wall_time_over_limit,
                        watchdog_limit_seconds, watchdog_killed, row_payload,
                        fair_start_valid, fair_start_witness
                    ) VALUES (%s, 0, 'job-shop-scheduling', 'test', 'JSPLIB',
                              'quick', 'ft06', 's', %s, 1, 1.0, 0, 0, false, 10,
                              false, '{}', true, %s)
                    """,
                    (run_id, version_id, Jsonb({"solver_input_hash": HASH_B})),
                )
                cur.execute(
                    "SELECT instance_hash_mismatch_count, publication_failures "
                    "FROM benchmark_run_publication_audit WHERE run_id = %s",
                    (run_id,),
                )
                count, failures = cur.fetchone()
            self.assertEqual(count, 1)
            self.assertIn("instance_hash_mismatch", failures)

        self.run_rolled_back(body)


if __name__ == "__main__":
    unittest.main()
