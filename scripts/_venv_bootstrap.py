"""Bootstrap executable benchmark scripts into the repository virtualenv."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def ensure_repo_venv(repo_root: Path) -> None:
    repo_root = repo_root.resolve()
    venv_root = repo_root / ".venv"
    venv_python = venv_root / "bin" / "python3"
    if not venv_python.exists():
        raise SystemExit(
            f"Repository virtualenv not found at {venv_root}. "
            "Run `make install-python-deps` from the repository root."
        )

    if Path(sys.prefix).resolve() == venv_root:
        return

    os.execv(str(venv_python), [str(venv_python), *sys.argv])
