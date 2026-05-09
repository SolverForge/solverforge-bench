SOLVERFORGE_DIR := src/employee_scheduling_bench/solver/solverforge_nrp
TIMEFOLD_POM := src/employee_scheduling_bench/solver/timefold_java/pom.xml
PYTHON ?= python3.12
BENCH_CMD := taskset -c 0 env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src $(PYTHON) scripts/run_benchmark.py
VALIDATE_CMD := PYTHONPATH=src $(PYTHON) scripts/validate_all.py

.PHONY: build build-solverforge build-timefold-java bench bench-quick bench-solverforge bench-solverforge-quick validate

build: build-timefold-java build-solverforge

build-solverforge:
	cd $(SOLVERFORGE_DIR) && maturin build --release --locked -i $(PYTHON)
	PIP_DISABLE_PIP_VERSION_CHECK=1 $(PYTHON) -m pip install --user --force-reinstall $$(ls -t $(SOLVERFORGE_DIR)/target/wheels/*.whl | head -1)

build-timefold-java:
	mvn -f $(TIMEFOLD_POM) package -q

bench: build
	$(BENCH_CMD) --dataset-set canonical --time-limits 1 10 60

bench-quick: build
	$(BENCH_CMD) --datasets n005w4 --time-limits 1 10

bench-solverforge: build-solverforge
	$(BENCH_CMD) --solver solverforge --dataset-set canonical --time-limits 1 10 60

bench-solverforge-quick: build-solverforge
	$(BENCH_CMD) --solver solverforge --datasets n005w4 --time-limits 1 10

validate:
	$(VALIDATE_CMD)
