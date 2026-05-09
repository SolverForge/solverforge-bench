PYTHON ?= $(CURDIR)/.venv/bin/python3
SOLVERFORGE_DIR := src/cvrp_bench/solver/solverforge
TIMEFOLD_POM := src/cvrp_bench/solver/timefold_java/pom.xml
BENCH_CMD := taskset -c 0 env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src $(PYTHON) scripts/run_benchmark.py
VALIDATE_CMD := PYTHONPATH=src $(PYTHON) scripts/validate_all.py

.PHONY: build build-solverforge build-timefold-java bench bench-quick bench-solverforge bench-solverforge-quick validate full

build: build-timefold-java build-solverforge

build-timefold-java:
	mvn -f $(TIMEFOLD_POM) package -q

build-solverforge:
	cd $(SOLVERFORGE_DIR) && PIP_DISABLE_PIP_VERSION_CHECK=1 maturin develop --release --locked

bench: build
	$(BENCH_CMD)

bench-quick: build
	$(BENCH_CMD) --num-instances 3 --time-limits 1 10

bench-solverforge: build-solverforge
	$(BENCH_CMD) --solver solverforge

bench-solverforge-quick: build-solverforge
	$(BENCH_CMD) --solver solverforge --num-instances 3 --time-limits 1 10

validate:
	$(VALIDATE_CMD)

full:
	./scripts/run_full_benchmark.sh
