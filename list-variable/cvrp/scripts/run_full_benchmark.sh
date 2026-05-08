#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

VENV_ACTIVATE="${REPO_ROOT}/.venv/bin/activate"
TIMEFOLD_POM="${REPO_ROOT}/src/cvrp_bench/solver/timefold_java/pom.xml"
SOLVERFORGE_DIR="${REPO_ROOT}/src/cvrp_bench/solver/solverforge"

if [[ ! -f "${VENV_ACTIVATE}" ]]; then
    echo "Missing virtualenv activation script: ${VENV_ACTIVATE}" >&2
    exit 1
fi

if ! command -v mvn >/dev/null 2>&1; then
    echo "Missing required command: mvn" >&2
    exit 1
fi

if ! command -v maturin >/dev/null 2>&1; then
    echo "Missing required command: maturin" >&2
    exit 1
fi

cd "${REPO_ROOT}"
source "${VENV_ACTIVATE}"

echo "Building Timefold Java fat JAR..."
mvn -f "${TIMEFOLD_POM}" package -q

echo "Building local SolverForge extension..."
cd "${SOLVERFORGE_DIR}"
maturin develop --release --locked

echo "Running full benchmark..."
cd "${REPO_ROOT}"
PYTHONPATH=src python scripts/run_benchmark.py
