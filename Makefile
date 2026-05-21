# SolverForge Bench Makefile
# Benchmark build and validation workflow.

# ============== Colors & Symbols ==============
GREEN := \033[92m
EMERALD := \033[38;2;16;185;129m
CYAN := \033[96m
YELLOW := \033[93m
RED := \033[91m
GRAY := \033[90m
BOLD := \033[1m
RESET := \033[0m

CHECK := OK
CROSS := FAIL
ARROW := =>
PROGRESS := ..

# ============== Project Metadata ==============
VERSION := $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)

HOST_PYTHON ?= python3.14
VENV ?= $(CURDIR)/.venv
PYTHON ?= $(VENV)/bin/python3
PIP ?= $(VENV)/bin/pip
DATABASE_URL ?= $(if $(BENCH_DATABASE_URL),$(BENCH_DATABASE_URL),postgresql://postgres@localhost/solverforge_bench)
SQLX ?= sqlx
DB_RESET_FLAGS ?= -y -f
BENCH_ARGS ?=
BENCH_CONFIG ?=
NIGHTLY_ARGS ?=
BENCH_CONFIG_ARG = $(if $(BENCH_CONFIG),--config "$(BENCH_CONFIG)",)
NIGHTLY_CONFIG_ARG = $(if $(findstring --config,$(NIGHTLY_ARGS)),,$(if $(BENCH_CONFIG),--config "$(BENCH_CONFIG)",--config "benchmark.nightly.example.toml"))
BENCH_DB_ARGS := --postgres-url "$(DATABASE_URL)"
BENCH_PYTHONPATH := src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src
BENCH_ENV := OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=$(BENCH_PYTHONPATH)
BENCH_CPU ?= 0
PINNED_BENCH := taskset -c $(BENCH_CPU) env $(BENCH_ENV)

CVRP_ROOT := list-variable/cvrp
CVRP_SOLVERFORGE_DIR := $(CVRP_ROOT)/src/cvrp_bench/solver/solverforge
CVRP_TIMEFOLD_POM := $(CVRP_ROOT)/src/cvrp_bench/solver/timefold/pom.xml
CVRP_ORTOOLS_DIR := $(CVRP_ROOT)/src/cvrp_bench/solver/ortools
CVRP_RUSTVRP_DIR := $(CVRP_ROOT)/src/cvrp_bench/solver/rustvrp
CVRP_VROOM_DIR := $(CVRP_ROOT)/src/cvrp_bench/solver/vroom

EMPLOYEE_ROOT := scalar-variable/employee-scheduling
EMPLOYEE_SOLVERFORGE_DIR := $(EMPLOYEE_ROOT)/src/employee_scheduling_bench/solver/solverforge_nrp
EMPLOYEE_TIMEFOLD_POM := $(EMPLOYEE_ROOT)/src/employee_scheduling_bench/solver/timefold/pom.xml
EMPLOYEE_ORTOOLS_DIR := $(EMPLOYEE_ROOT)/src/employee_scheduling_bench/solver/ortools
ORTOOLS_VERSION ?= 9.15.6755
ORTOOLS_ARCHIVE ?= or-tools_amd64_opensuse-leap_cpp_v$(ORTOOLS_VERSION).tar.gz
ORTOOLS_URL ?= https://github.com/google/or-tools/releases/download/v9.15/$(ORTOOLS_ARCHIVE)
ORTOOLS_ROOT ?= $(CURDIR)/build/ortools/or-tools_x86_64_openSUSE-15.6_cpp_v$(ORTOOLS_VERSION)
VROOM_VERSION ?= 1.15.0
VROOM_REPO ?= https://github.com/VROOM-Project/vroom.git
VROOM_SOURCE_DIR := $(CURDIR)/build/vroom/vroom-$(VROOM_VERSION)
VROOM_BINARY := $(VROOM_SOURCE_DIR)/bin/vroom
JAVA_HOME_FOR_MAVEN ?= $(shell dirname "$$(dirname "$$(readlink -f "$$(command -v java)")")")
MAVEN_ENV := JAVA_HOME="$(JAVA_HOME_FOR_MAVEN)" PATH="$(JAVA_HOME_FOR_MAVEN)/bin:$(PATH)"

.PHONY: \
	banner venv install-python-deps build-cvrp build-cvrp-python-deps build-cvrp-solverforge build-cvrp-timefold build-cvrp-ortools build-cvrp-rustvrp build-cvrp-vroom \
	build-employee-scheduling build-employee-scheduling-solverforge build-employee-scheduling-timefold build-employee-scheduling-ortools \
	bench-cvrp bench-cvrp-db bench-cvrp-quick bench-cvrp-quick-db \
	bench-cvrp-solverforge bench-cvrp-solverforge-db \
	bench-cvrp-solverforge-quick bench-cvrp-solverforge-quick-db \
	bench-employee-scheduling bench-employee-scheduling-db \
	bench-employee-scheduling-quick bench-employee-scheduling-quick-db \
	bench-employee-scheduling-solverforge bench-employee-scheduling-solverforge-db \
	bench-employee-scheduling-solverforge-quick bench-employee-scheduling-solverforge-quick-db \
	bench-nightly-db \
	validate-cvrp validate-employee-scheduling validate-employee-model-parity \
	db-check db-create db-migrate db-reset normalize-results

# ============== Default Target ==============
.DEFAULT_GOAL := venv

# ============== Banner ==============
banner:
	@printf -- "$(EMERALD)$(BOLD)  ____        _                _____\n"
	@printf -- " / ___|  ___ | |_   _____ _ __|  ___|__  _ __ __ _  ___\n"
	@printf -- " \\___ \\\\ / _ \\\\| \\\\ \\\\ / / _ \\\\ '__| |_ / _ \\\\| '__/ _\` |/ _ \\\\\n"
	@printf -- "  ___) | (_) | |\\\\ V /  __/ |  |  _| (_) | | | (_| |  __/\n"
	@printf -- " |____/ \\\\___/|_| \\_/ \\___|_|  |_|  \\___/|_|  \\__, |\\___|\n"
	@printf -- "                                             |___/$(RESET)\n"
	@printf -- "  $(GRAY)v$(VERSION)$(RESET) $(EMERALD)Benchmark Build System$(RESET)\n\n"

venv:
	@if [ -x "$(PYTHON)" ]; then \
		current="$$("$(PYTHON)" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"; \
		expected="$$("$(HOST_PYTHON)" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"; \
		if [ "$$current" != "$$expected" ]; then \
			rm -rf "$(VENV)"; \
		fi; \
	fi
	@if [ ! -x "$(PYTHON)" ]; then \
		"$(HOST_PYTHON)" -m venv "$(VENV)"; \
	fi

install-python-deps: banner venv
	PIP_DISABLE_PIP_VERSION_CHECK=1 "$(PIP)" install -e .

db-check: banner
	psql "$(DATABASE_URL)" -c "select current_user, current_database(), version();"

db-create: banner
	$(SQLX) database create --database-url "$(DATABASE_URL)"

db-migrate: db-create
	$(SQLX) migrate run --source migrations --database-url "$(DATABASE_URL)"

db-reset: banner
	$(SQLX) database reset --source migrations --database-url "$(DATABASE_URL)" $(DB_RESET_FLAGS)

$(ORTOOLS_ROOT)/lib64/cmake/ortools/ortoolsConfig.cmake:
	mkdir -p build/ortools
	curl -L --fail --retry 3 -o build/ortools/$(ORTOOLS_ARCHIVE) "$(ORTOOLS_URL)"
	tar -xzf build/ortools/$(ORTOOLS_ARCHIVE) -C build/ortools

$(VROOM_SOURCE_DIR)/src/makefile:
	mkdir -p build/vroom
	git clone --depth 1 --branch v$(VROOM_VERSION) --recurse-submodules --shallow-submodules "$(VROOM_REPO)" "$(VROOM_SOURCE_DIR)"

$(VROOM_BINARY): $(VROOM_SOURCE_DIR)/src/makefile
	$(MAKE) -C "$(VROOM_SOURCE_DIR)/src" USE_ROUTING=false ../bin/vroom

build-cvrp: banner install-python-deps build-cvrp-timefold build-cvrp-solverforge build-cvrp-ortools build-cvrp-rustvrp build-cvrp-vroom

build-cvrp-python-deps: install-python-deps

build-cvrp-timefold: banner
	$(MAVEN_ENV) mvn -f $(CVRP_TIMEFOLD_POM) package -q

build-cvrp-ortools: banner $(ORTOOLS_ROOT)/lib64/cmake/ortools/ortoolsConfig.cmake
	cmake -S $(CVRP_ORTOOLS_DIR) -B build/cvrp-ortools -DCMAKE_PREFIX_PATH="$(ORTOOLS_ROOT)" -DORTOOLS_ROOT="$(ORTOOLS_ROOT)"
	cmake --build build/cvrp-ortools --parallel
	mkdir -p $(CVRP_ORTOOLS_DIR)/target
	cp build/cvrp-ortools/cvrp_ortools $(CVRP_ORTOOLS_DIR)/target/

build-cvrp-rustvrp: banner
	cd $(CVRP_RUSTVRP_DIR) && cargo build --release --locked
	cp $(CVRP_RUSTVRP_DIR)/target/release/cvrp_rustvrp $(CVRP_RUSTVRP_DIR)/target/

build-cvrp-vroom: banner $(VROOM_BINARY)
	mkdir -p $(CVRP_VROOM_DIR)/target
	cp $(VROOM_BINARY) $(CVRP_VROOM_DIR)/target/cvrp_vroom

build-cvrp-solverforge: banner install-python-deps
	cd $(CVRP_SOLVERFORGE_DIR) && PIP_DISABLE_PIP_VERSION_CHECK=1 maturin develop --release --locked --pip-path "$(PIP)"

bench-cvrp: build-cvrp
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) $(BENCH_ARGS)

bench-cvrp-db: build-cvrp db-migrate
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-cvrp-quick: build-cvrp
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --run-kind quick --num-instances 3 --time-limits 1 10 $(BENCH_ARGS)

bench-cvrp-quick-db: build-cvrp db-migrate
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --run-kind quick --num-instances 3 --time-limits 1 10 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-cvrp-solverforge: build-cvrp-solverforge
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --solver solverforge $(BENCH_ARGS)

bench-cvrp-solverforge-db: build-cvrp-solverforge db-migrate
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --solver solverforge $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-cvrp-solverforge-quick: build-cvrp-solverforge
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --run-kind quick --solver solverforge --num-instances 3 --time-limits 1 10 $(BENCH_ARGS)

bench-cvrp-solverforge-quick-db: build-cvrp-solverforge db-migrate
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --run-kind quick --solver solverforge --num-instances 3 --time-limits 1 10 $(BENCH_DB_ARGS) $(BENCH_ARGS)

validate-cvrp: banner
	cd $(CVRP_ROOT) && PYTHONPATH=src "$(PYTHON)" scripts/validate_all.py

build-employee-scheduling: banner install-python-deps build-employee-scheduling-timefold build-employee-scheduling-solverforge build-employee-scheduling-ortools

build-employee-scheduling-timefold: banner
	$(MAVEN_ENV) mvn -f $(EMPLOYEE_TIMEFOLD_POM) package -q

build-employee-scheduling-ortools: banner $(ORTOOLS_ROOT)/lib64/cmake/ortools/ortoolsConfig.cmake
	cmake -S $(EMPLOYEE_ORTOOLS_DIR) -B build/employee-scheduling-ortools -DCMAKE_PREFIX_PATH="$(ORTOOLS_ROOT)" -DORTOOLS_ROOT="$(ORTOOLS_ROOT)"
	cmake --build build/employee-scheduling-ortools --parallel
	mkdir -p $(EMPLOYEE_ORTOOLS_DIR)/target
	cp build/employee-scheduling-ortools/employee_scheduling_ortools $(EMPLOYEE_ORTOOLS_DIR)/target/

build-employee-scheduling-solverforge: banner install-python-deps
	cd $(EMPLOYEE_SOLVERFORGE_DIR) && maturin build --release --locked -i "$(PYTHON)"
	PIP_DISABLE_PIP_VERSION_CHECK=1 "$(PIP)" install --force-reinstall $$(ls -t $(EMPLOYEE_SOLVERFORGE_DIR)/target/wheels/*.whl | head -1)

bench-employee-scheduling: build-employee-scheduling
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --dataset-set canonical --time-limits 1 10 60 $(BENCH_ARGS)

bench-employee-scheduling-db: build-employee-scheduling db-migrate
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --dataset-set canonical --time-limits 1 10 60 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-employee-scheduling-quick: build-employee-scheduling
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --datasets n005w4 --time-limits 1 10 $(BENCH_ARGS)

bench-employee-scheduling-quick-db: build-employee-scheduling db-migrate
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --datasets n005w4 --time-limits 1 10 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-employee-scheduling-solverforge: build-employee-scheduling-solverforge
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --solver solverforge --dataset-set canonical --time-limits 1 10 60 $(BENCH_ARGS)

bench-employee-scheduling-solverforge-db: build-employee-scheduling-solverforge db-migrate
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --solver solverforge --dataset-set canonical --time-limits 1 10 60 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-employee-scheduling-solverforge-quick: build-employee-scheduling-solverforge
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --solver solverforge --datasets n005w4 --time-limits 1 10 $(BENCH_ARGS)

bench-employee-scheduling-solverforge-quick-db: build-employee-scheduling-solverforge db-migrate
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --solver solverforge --datasets n005w4 --time-limits 1 10 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-nightly-db: build-cvrp build-employee-scheduling db-migrate
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(NIGHTLY_CONFIG_ARG) $(BENCH_DB_ARGS) $(NIGHTLY_ARGS)
	$(PINNED_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(NIGHTLY_CONFIG_ARG) $(BENCH_DB_ARGS) $(NIGHTLY_ARGS)

validate-employee-scheduling: banner
	cd $(EMPLOYEE_ROOT) && PYTHONPATH=../../src:../../list-variable/cvrp/src:src "$(PYTHON)" scripts/validate_all.py

validate-employee-model-parity: banner
	cd $(EMPLOYEE_ROOT) && PYTHONPATH=../../src:../../list-variable/cvrp/src:src "$(PYTHON)" scripts/verify_model_parity.py

normalize-results: banner
	test -n "$(INPUT)"
	test -n "$(OUTPUT)"
	"$(PYTHON)" scripts/normalize_results.py --input "$(INPUT)" --output "$(OUTPUT)" $(ARGS)
