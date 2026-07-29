#!/usr/bin/env python3.14
"""Report whether historical canonical nightlies satisfy today's public contract."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from typing import Any

import psycopg
from psycopg.rows import dict_row


DEFAULT_DATABASE_URL = (
    os.environ.get("BENCH_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql://postgres@localhost/solverforge_bench"
)

LEGACY_AUDIT_QUERY = """
    SELECT
        runs.id::text AS run_id,
        runs.benchmark_name,
        runs.run_kind,
        runs.nightly,
        runs.completed_at,
        runs.git_commit,
        runs.git_dirty,
        runs.result_count,
        runs.expected_result_count,
        runs.expected_matrix_sha256,
        runs.observed_matrix_sha256,
        audit.publication_ready,
        audit.publication_failures,
        audit.all_fair_start_valid,
        audit.solver_provenance_valid,
        audit.expected_catalog_count,
        audit.actual_result_count,
        audit.missing_result_count,
        audit.unexpected_result_count
    FROM benchmark_runs AS runs
    JOIN benchmark_run_publication_audit AS audit
      ON audit.run_id = runs.id
    WHERE runs.nightly IS TRUE
      AND runs.run_kind = 'candidate'
      AND EXISTS (
          SELECT 1
          FROM benchmark_result_facts AS canonical
          WHERE canonical.run_id = runs.id
            AND canonical.dataset_set = 'canonical'
      )
      AND NOT EXISTS (
          SELECT 1
          FROM benchmark_result_facts AS noncanonical
          WHERE noncanonical.run_id = runs.id
            AND noncanonical.dataset_set IS DISTINCT FROM 'canonical'
      )
    ORDER BY runs.completed_at DESC NULLS LAST, runs.id DESC
"""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with psycopg.connect(args.database_url, row_factory=dict_row) as connection:
        rows = fetch_legacy_rows(connection)

    decisions = [decision_for_row(row) for row in rows]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "nightly": True,
            "run_kind": "candidate",
            "dataset_set": "canonical",
            "mutates_warehouse": False,
        },
        "summary": {
            "audited": len(decisions),
            "publishable": sum(
                decision["decision"] == "publishable" for decision in decisions
            ),
            "retained_private": sum(
                decision["decision"] == "retain_private" for decision in decisions
            ),
        },
        "runs": decisions,
    }
    json.dump(report, sys.stdout, indent=2, sort_keys=True, default=json_value)
    sys.stdout.write("\n")
    return 0


def fetch_legacy_rows(connection: Any) -> list[dict[str, Any]]:
    connection.execute("SET TRANSACTION READ ONLY")
    return connection.execute(LEGACY_AUDIT_QUERY).fetchall()


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only re-audit of historical canonical nightlies. Missing "
            "matrix or runtime-artifact evidence is reported, never rebuilt."
        )
    )
    parser.add_argument(
        "--database-url",
        default=DEFAULT_DATABASE_URL,
        help="PostgreSQL benchmark warehouse URL.",
    )
    return parser.parse_args(argv)


def decision_for_row(row: dict[str, Any]) -> dict[str, Any]:
    publication_ready = bool(row["publication_ready"])
    reasons = list(row.get("publication_failures") or [])
    if not publication_ready:
        if (
            row.get("expected_result_count") is None
            or row.get("expected_matrix_sha256") is None
            or not row.get("expected_catalog_count")
        ):
            reasons.append("legacy_predeclared_matrix_evidence_absent")
        if not row.get("solver_provenance_valid"):
            reasons.append("legacy_runtime_artifact_identity_absent")

    return {
        "run_id": row["run_id"],
        "benchmark_name": row["benchmark_name"],
        "completed_at": row.get("completed_at"),
        "git_commit": row.get("git_commit"),
        "result_count": row.get("result_count"),
        "decision": "publishable" if publication_ready else "retain_private",
        "reasons": sorted(set(reasons)),
        "evidence": {
            "all_fair_start_valid": bool(row.get("all_fair_start_valid")),
            "solver_provenance_valid": bool(row.get("solver_provenance_valid")),
            "expected_result_count": row.get("expected_result_count"),
            "expected_catalog_count": row.get("expected_catalog_count"),
            "actual_result_count": row.get("actual_result_count"),
            "missing_result_count": row.get("missing_result_count"),
            "unexpected_result_count": row.get("unexpected_result_count"),
            "expected_matrix_sha256": row.get("expected_matrix_sha256"),
            "observed_matrix_sha256": row.get("observed_matrix_sha256"),
        },
    }


def json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
