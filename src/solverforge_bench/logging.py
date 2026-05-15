"""Shared logging support for benchmark runs and solver subprocesses."""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from types import TracebackType


def configure_run_logging(
    *,
    level: str,
    log_file: Path,
) -> None:
    """Configure process-level benchmark logging."""

    log_file.parent.mkdir(parents=True, exist_ok=True)
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Unknown log level: {level}")

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logging.basicConfig(
        level=numeric_level,
        handlers=[stream_handler, file_handler],
        force=True,
    )


def run_log_path(*, args, benchmark_name: str) -> Path:
    run_name = f"{_safe_name(benchmark_name)}_{args.run_stamp}"
    if getattr(args, "log_file", None):
        return Path(args.log_file)
    if getattr(args, "log_dir", None):
        log_dir = Path(args.log_dir) / run_name
    else:
        repo_root = Path(getattr(args, "repo_root", Path.cwd()))
        log_dir = repo_root / "logs" / run_name
    return log_dir / f"{run_name}.log"


def solver_capture_dir(
    *,
    log_path: Path,
    benchmark_name: str,
    run_stamp: str,
    explicit_log_file: bool,
) -> Path:
    run_name = f"{_safe_name(benchmark_name)}_{run_stamp}"
    log_stem = _safe_name(log_path.stem)
    if not explicit_log_file and log_stem == run_name:
        return log_path.parent / "solvers"
    if log_stem == run_name:
        return log_path.parent / run_name / "solvers"
    return log_path.parent / f"{log_stem}_{run_name}" / "solvers"


def solver_output_paths(
    *,
    log_dir: Path,
    instance_name: str,
    solver_name: str,
    time_limit_seconds: int,
) -> tuple[Path, Path]:
    stem = "__".join(
        [
            _safe_name(instance_name),
            _safe_name(solver_name),
            f"{time_limit_seconds}s",
        ]
    )
    return log_dir / f"{stem}.stdout.log", log_dir / f"{stem}.stderr.log"


def capture_output(
    *,
    stdout_path: Path | None,
    stderr_path: Path | None,
    show_output: bool,
) -> AbstractContextManager[None]:
    if show_output and stdout_path is None and stderr_path is None:
        return nullcontext()
    if not show_output:
        stdout_path = stdout_path or Path(os.devnull)
        stderr_path = stderr_path or Path(os.devnull)
    return _FdOutputCapture(
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        show_output=show_output,
    )


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return safe or "unnamed"


class _FdOutputCapture(AbstractContextManager[None]):
    def __init__(
        self,
        *,
        stdout_path: Path | None,
        stderr_path: Path | None,
        show_output: bool,
    ):
        self._stdout_path = stdout_path
        self._stderr_path = stderr_path
        self._show_output = show_output
        self._captures: list[_StreamCapture] = []

    def __enter__(self) -> None:
        _flush_standard_streams()
        if self._stdout_path is not None:
            self._captures.append(
                _StreamCapture(
                    fd=1,
                    path=self._stdout_path,
                    show_output=self._show_output,
                )
            )
        if self._stderr_path is not None:
            self._captures.append(
                _StreamCapture(
                    fd=2,
                    path=self._stderr_path,
                    show_output=self._show_output,
                )
            )
        for capture in self._captures:
            capture.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _flush_standard_streams()
        for capture in reversed(self._captures):
            capture.stop()


def _flush_standard_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass


class _StreamCapture:
    def __init__(self, *, fd: int, path: Path, show_output: bool):
        self._fd = fd
        self._path = path
        self._show_output = show_output
        self._saved_fd: int | None = None
        self._file = None
        self._read_fd: int | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._path != Path(os.devnull):
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._saved_fd = os.dup(self._fd)
        self._file = self._path.open("wb", buffering=0)
        if not self._show_output:
            os.dup2(self._file.fileno(), self._fd)
            return

        read_fd, write_fd = os.pipe()
        self._read_fd = read_fd
        self._thread = threading.Thread(
            target=self._tee_pipe,
            args=(read_fd, self._saved_fd, self._file.fileno()),
            daemon=True,
        )
        self._thread.start()
        os.dup2(write_fd, self._fd)
        os.close(write_fd)

    def stop(self) -> None:
        if self._saved_fd is not None:
            os.dup2(self._saved_fd, self._fd)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._read_fd is not None:
            try:
                os.close(self._read_fd)
            except OSError:
                pass
        if self._saved_fd is not None:
            os.close(self._saved_fd)
        if self._file is not None:
            self._file.close()

    def _tee_pipe(self, read_fd: int, console_fd: int, file_fd: int) -> None:
        while True:
            try:
                chunk = os.read(read_fd, 65536)
            except OSError:
                return
            if not chunk:
                return
            os.write(file_fd, chunk)
            os.write(console_fd, chunk)
