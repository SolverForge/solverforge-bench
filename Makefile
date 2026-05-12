PYTHON ?= python3.12
CVRP_PYTHON ?= $(CURDIR)/list-variable/cvrp/.venv/bin/python3
CVRP_PIP ?= $(CURDIR)/list-variable/cvrp/.venv/bin/pip
DATABASE_URL ?= postgresql://postgres@localhost/solverforge_bench
SQLX ?= sqlx
BENCH_ARGS ?=
BENCH_PYTHONPATH := src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src
BENCH_ENV := OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=$(BENCH_PYTHONPATH)
PINNED_BENCH := taskset -c 0 env $(BENCH_ENV)

CVRP_ROOT := list-variable/cvrp
CVRP_SOLVERFORGE_DIR := $(CVRP_ROOT)/src/cvrp_bench/solver/solverforge
CVRP_TIMEFOLD_POM := $(CVRP_ROOT)/src/cvrp_bench/solver/timefold_java/pom.xml

EMPLOYEE_ROOT := scalar-variable/employee-scheduling
EMPLOYEE_SOLVERFORGE_DIR := $(EMPLOYEE_ROOT)/src/employee_scheduling_bench/solver/solverforge_nrp
EMPLOYEE_TIMEFOLD_POM := $(EMPLOYEE_ROOT)/src/employee_scheduling_bench/solver/timefold_java/pom.xml

.PHONY: \
	build-cvrp build-cvrp-solverforge build-cvrp-timefold-java \
	build-employee-scheduling build-employee-scheduling-solverforge build-employee-scheduling-timefold-java \
	bench-cvrp bench-cvrp-quick bench-cvrp-solverforge bench-cvrp-solverforge-quick \
	bench-employee-scheduling bench-employee-scheduling-quick \
	bench-employee-scheduling-solverforge bench-employee-scheduling-solverforge-quick \
	validate-cvrp validate-employee-scheduling validate-employee-model-parity \
	db-check db-create db-migrate normalize-results

db-check:
	psql -h localhost -U postgres -d postgres -c "select current_user, current_database(), version();"

db-create:
	psql -h localhost -U postgres -d postgres -tc "select 1 from pg_database where datname = 'solverforge_bench'" | grep -q 1 || createdb -h localhost -U postgres solverforge_bench

db-migrate: db-create
	$(SQLX) migrate run --source migrations --database-url "$(DATABASE_URL)"

build-cvrp: build-cvrp-timefold-java build-cvrp-solverforge

build-cvrp-timefold-java:
	mvn -f $(CVRP_TIMEFOLD_POM) package -q

build-cvrp-solverforge:
	cd $(CVRP_SOLVERFORGE_DIR) && PIP_DISABLE_PIP_VERSION_CHECK=1 maturin develop --release --locked --pip-path $(CVRP_PIP)

bench-cvrp: build-cvrp
	$(PINNED_BENCH) $(CVRP_PYTHON) scripts/run_benchmark.py cvrp $(BENCH_ARGS)

bench-cvrp-quick: build-cvrp
	$(PINNED_BENCH) $(CVRP_PYTHON) scripts/run_benchmark.py cvrp --run-kind quick --num-instances 3 --time-limits 1 10 $(BENCH_ARGS)

bench-cvrp-solverforge: build-cvrp-solverforge
	$(PINNED_BENCH) $(CVRP_PYTHON) scripts/run_benchmark.py cvrp --solver solverforge $(BENCH_ARGS)

bench-cvrp-solverforge-quick: build-cvrp-solverforge
	$(PINNED_BENCH) $(CVRP_PYTHON) scripts/run_benchmark.py cvrp --run-kind quick --solver solverforge --num-instances 3 --time-limits 1 10 $(BENCH_ARGS)

validate-cvrp:
	cd $(CVRP_ROOT) && PYTHONPATH=src $(CVRP_PYTHON) scripts/validate_all.py

build-employee-scheduling: build-employee-scheduling-timefold-java build-employee-scheduling-solverforge

build-employee-scheduling-timefold-java:
	mvn -f $(EMPLOYEE_TIMEFOLD_POM) package -q

build-employee-scheduling-solverforge:
	cd $(EMPLOYEE_SOLVERFORGE_DIR) && maturin build --release --locked -i $(PYTHON)
	PIP_DISABLE_PIP_VERSION_CHECK=1 $(PYTHON) -m pip install --user --force-reinstall $$(ls -t $(EMPLOYEE_SOLVERFORGE_DIR)/target/wheels/*.whl | head -1)

bench-employee-scheduling: build-employee-scheduling
	$(PINNED_BENCH) $(PYTHON) scripts/run_benchmark.py employee-scheduling --dataset-set canonical --time-limits 1 10 60 $(BENCH_ARGS)

bench-employee-scheduling-quick: build-employee-scheduling
	$(PINNED_BENCH) $(PYTHON) scripts/run_benchmark.py employee-scheduling --run-kind quick --datasets n005w4 --time-limits 1 10 $(BENCH_ARGS)

bench-employee-scheduling-solverforge: build-employee-scheduling-solverforge
	$(PINNED_BENCH) $(PYTHON) scripts/run_benchmark.py employee-scheduling --solver solverforge --dataset-set canonical --time-limits 1 10 60 $(BENCH_ARGS)

bench-employee-scheduling-solverforge-quick: build-employee-scheduling-solverforge
	$(PINNED_BENCH) $(PYTHON) scripts/run_benchmark.py employee-scheduling --run-kind quick --solver solverforge --datasets n005w4 --time-limits 1 10 $(BENCH_ARGS)

validate-employee-scheduling:
	cd $(EMPLOYEE_ROOT) && PYTHONPATH=../../src:../../list-variable/cvrp/src:src $(PYTHON) scripts/validate_all.py

validate-employee-model-parity:
	cd $(EMPLOYEE_ROOT) && PYTHONPATH=../../src:../../list-variable/cvrp/src:src $(PYTHON) scripts/verify_model_parity.py

normalize-results:
	test -n "$(INPUT)"
	test -n "$(OUTPUT)"
	python3 scripts/normalize_results.py --input "$(INPUT)" --output "$(OUTPUT)" $(ARGS)
