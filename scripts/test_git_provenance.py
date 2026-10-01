#!/usr/bin/env python3.14
"""Regression tests for recorded run provenance.

`git_dirty` is a publication gate: `benchmark_run_publication_audit` requires
`git_dirty IS FALSE` before a run may be shown publicly. The flag must therefore
mean "the harness that produced these numbers is not the identified commit",
not "the checkout contains a file git does not track". Local output and scratch
directories keep the old meaning and would strand every future run in the
warehouse as unpublishable.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from solverforge_bench.postgres import WorktreeProvenance, worktree_provenance


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(repo: Path) -> None:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "bench@example.invalid")
    _git(repo, "config", "user.name", "Bench Test")
    (repo / "src").mkdir()
    (repo / "src" / "harness.py").write_text("VALUE = 1\n")
    (repo / "list-variable").mkdir()
    (repo / "list-variable" / "adapter.py").write_text("VALUE = 1\n")
    (repo / ".gitignore").write_text("build/\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial")


class WorktreeProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        _init_repo(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def assert_pristine(self, provenance: WorktreeProvenance) -> None:
        self.assertFalse(provenance.dirty)
        self.assertEqual(provenance.dirty_paths, ())

    def test_clean_checkout_is_pristine(self) -> None:
        self.assert_pristine(worktree_provenance(self.repo))

    def test_modified_harness_source_is_dirty(self) -> None:
        (self.repo / "src" / "harness.py").write_text("VALUE = 2\n")
        provenance = worktree_provenance(self.repo)
        self.assertTrue(provenance.dirty)
        self.assertIn("src/harness.py", provenance.dirty_paths)

    def test_staged_harness_source_is_dirty(self) -> None:
        (self.repo / "src" / "harness.py").write_text("VALUE = 2\n")
        _git(self.repo, "add", "src/harness.py")
        self.assertTrue(worktree_provenance(self.repo).dirty)

    def test_deleted_harness_source_is_dirty(self) -> None:
        (self.repo / "src" / "harness.py").unlink()
        self.assertTrue(worktree_provenance(self.repo).dirty)

    def test_untracked_harness_source_is_dirty(self) -> None:
        (self.repo / "src" / "local_override.py").write_text("VALUE = 3\n")
        provenance = worktree_provenance(self.repo)
        self.assertTrue(provenance.dirty)
        self.assertIn("src/local_override.py", provenance.dirty_paths)

    def test_untracked_problem_adapter_is_dirty(self) -> None:
        (self.repo / "list-variable" / "local_adapter.py").write_text("VALUE = 3\n")
        provenance = worktree_provenance(self.repo)
        self.assertTrue(provenance.dirty)
        self.assertIn("list-variable/local_adapter.py", provenance.dirty_paths)

    def test_untracked_output_directory_is_pristine(self) -> None:
        exports = self.repo / "exports"
        exports.mkdir()
        (exports / "cvrp_run-248bd693_latest-versions.csv").write_text("cost\n1\n")
        provenance = worktree_provenance(self.repo)
        self.assert_pristine(provenance)
        self.assertIn(
            "exports/cvrp_run-248bd693_latest-versions.csv", provenance.untracked_paths
        )

    def test_untracked_root_scratch_file_is_pristine(self) -> None:
        (self.repo / "NOTES.md").write_text("scratch\n")
        provenance = worktree_provenance(self.repo)
        self.assert_pristine(provenance)
        self.assertIn("NOTES.md", provenance.untracked_paths)

    def test_ignored_build_output_is_pristine_and_unrecorded(self) -> None:
        (self.repo / "build").mkdir()
        (self.repo / "build" / "artifact.bin").write_bytes(b"\x00")
        provenance = worktree_provenance(self.repo)
        self.assert_pristine(provenance)
        self.assertEqual(provenance.untracked_paths, ())

    def test_no_git_repository_is_not_dirty(self) -> None:
        outside = Path(self._tmp.name) / "no-repo"
        outside.mkdir()
        provenance = worktree_provenance(outside)
        self.assertFalse(provenance.dirty)


if __name__ == "__main__":
    unittest.main()
