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
SOLVERFORGE_PY_REQUIREMENT := solverforge==0.8.1
DATABASE_URL ?= $(if $(BENCH_DATABASE_URL),$(BENCH_DATABASE_URL),postgresql://postgres@localhost/solverforge_bench)
SQLX ?= sqlx
DB_RESET_FLAGS ?= -y -f
BENCH_ARGS ?=
BENCH_CONFIG ?=
NIGHTLY_ARGS ?=
GUARDRAIL_ARGS ?=
SOLVERFORGE_PY_GUARDRAIL_ARGS ?=
SOLVERFORGE_PY_GUARDRAIL_OUTPUT_DIR ?= build/solverforge-py-guardrails
BENCH_CONFIG_ARG = $(if $(BENCH_CONFIG),--config "$(BENCH_CONFIG)",)
NIGHTLY_CONFIG_ARG = $(if $(findstring --config,$(NIGHTLY_ARGS)),,$(if $(BENCH_CONFIG),--config "$(BENCH_CONFIG)",--config "benchmark.nightly.example.toml"))
BENCH_DB_ARGS := --postgres-url "$(DATABASE_URL)"
BENCH_PYTHONPATH := src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src:huge-scale/hospital-scale/src:huge-scale/delivery-scale/src
BENCH_CPU ?=
CVRP_BENCH_CPU ?= $(if $(BENCH_CPU),$(BENCH_CPU),0)
EMPLOYEE_BENCH_CPU ?= $(if $(BENCH_CPU),$(BENCH_CPU),1)
JOBSHOP_BENCH_CPU ?= $(if $(BENCH_CPU),$(BENCH_CPU),2)
HOSPITAL_SCALE_BENCH_CPU ?= $(if $(BENCH_CPU),$(BENCH_CPU),3)
DELIVERY_SCALE_BENCH_CPU ?= $(if $(BENCH_CPU),$(BENCH_CPU),4)
BENCH_LOCK_DIR ?= /tmp
CVRP_BENCH_LOCK ?= $(BENCH_LOCK_DIR)/solverforge-bench-cpu-$(CVRP_BENCH_CPU).lock
EMPLOYEE_BENCH_LOCK ?= $(BENCH_LOCK_DIR)/solverforge-bench-cpu-$(EMPLOYEE_BENCH_CPU).lock
JOBSHOP_BENCH_LOCK ?= $(BENCH_LOCK_DIR)/solverforge-bench-cpu-$(JOBSHOP_BENCH_CPU).lock
HOSPITAL_SCALE_BENCH_LOCK ?= $(BENCH_LOCK_DIR)/solverforge-bench-cpu-$(HOSPITAL_SCALE_BENCH_CPU).lock
DELIVERY_SCALE_BENCH_LOCK ?= $(BENCH_LOCK_DIR)/solverforge-bench-cpu-$(DELIVERY_SCALE_BENCH_CPU).lock
BENCH_ENV_COMMON := OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=$(BENCH_PYTHONPATH)
PINNED_CVRP_BENCH := taskset -c $(CVRP_BENCH_CPU) env $(BENCH_ENV_COMMON) BENCH_CPU=$(CVRP_BENCH_CPU) BENCH_LOCK=$(CVRP_BENCH_LOCK)
PINNED_EMPLOYEE_BENCH := taskset -c $(EMPLOYEE_BENCH_CPU) env $(BENCH_ENV_COMMON) BENCH_CPU=$(EMPLOYEE_BENCH_CPU) BENCH_LOCK=$(EMPLOYEE_BENCH_LOCK)
PINNED_JOBSHOP_BENCH := taskset -c $(JOBSHOP_BENCH_CPU) env $(BENCH_ENV_COMMON) BENCH_CPU=$(JOBSHOP_BENCH_CPU) BENCH_LOCK=$(JOBSHOP_BENCH_LOCK)
PINNED_HOSPITAL_SCALE_BENCH := taskset -c $(HOSPITAL_SCALE_BENCH_CPU) env $(BENCH_ENV_COMMON) BENCH_CPU=$(HOSPITAL_SCALE_BENCH_CPU) BENCH_LOCK=$(HOSPITAL_SCALE_BENCH_LOCK)
PINNED_DELIVERY_SCALE_BENCH := taskset -c $(DELIVERY_SCALE_BENCH_CPU) env $(BENCH_ENV_COMMON) BENCH_CPU=$(DELIVERY_SCALE_BENCH_CPU) BENCH_LOCK=$(DELIVERY_SCALE_BENCH_LOCK)
# The thread study pins every thread count, 1 included, to the same CPU set:
# one logical CPU per physical core by default, so threads never share a core.
THREAD_STUDY_CPUS ?= 4,6,8,10
THREAD_STUDY_CONFIG ?= benchmark.thread-study.toml
THREAD_STUDY_DIR ?= build/thread-study
THREAD_STUDY_LOCK ?= $(BENCH_LOCK_DIR)/solverforge-bench-thread-study.lock
PINNED_THREAD_STUDY := taskset -c $(THREAD_STUDY_CPUS) env $(BENCH_ENV_COMMON) BENCH_CPU=$(THREAD_STUDY_CPUS) BENCH_LOCK=$(THREAD_STUDY_LOCK)

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
JOBSHOP_ROOT := scalar-variable/job-shop-scheduling
JOBSHOP_SOLVERFORGE_DIR := $(JOBSHOP_ROOT)/src/job_shop_bench/solver/solverforge_jssp
JOBSHOP_TIMEFOLD_POM := $(JOBSHOP_ROOT)/src/job_shop_bench/solver/timefold/pom.xml
JOBSHOP_ORTOOLS_DIR := $(JOBSHOP_ROOT)/src/job_shop_bench/solver/ortools
HOSPITAL_SCALE_ROOT := huge-scale/hospital-scale
HOSPITAL_SCALE_SOLVERFORGE_DIR := $(HOSPITAL_SCALE_ROOT)/src/hospital_scale_bench/solver/solverforge_hospital
HOSPITAL_SCALE_TIMEFOLD_POM := $(HOSPITAL_SCALE_ROOT)/src/hospital_scale_bench/solver/timefold/pom.xml
HOSPITAL_SCALE_ORTOOLS_DIR := $(HOSPITAL_SCALE_ROOT)/src/hospital_scale_bench/solver/ortools
DELIVERY_SCALE_ROOT := huge-scale/delivery-scale
DELIVERY_SCALE_SOLVERFORGE_DIR := $(DELIVERY_SCALE_ROOT)/src/delivery_scale_bench/solver/solverforge_deliveries
DELIVERY_SCALE_TIMEFOLD_POM := $(DELIVERY_SCALE_ROOT)/src/delivery_scale_bench/solver/timefold/pom.xml
DELIVERY_SCALE_ORTOOLS_DIR := $(DELIVERY_SCALE_ROOT)/src/delivery_scale_bench/solver/ortools
DASH_ROOT := dash
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
	help banner venv install-python-deps build-cvrp build-cvrp-python-deps build-cvrp-solverforge build-cvrp-timefold build-cvrp-ortools build-cvrp-rustvrp build-cvrp-vroom \
	build-employee-scheduling build-employee-scheduling-solverforge build-employee-scheduling-timefold build-employee-scheduling-ortools \
	build-job-shop-scheduling build-job-shop-scheduling-solverforge build-job-shop-scheduling-timefold build-job-shop-scheduling-ortools \
	bench-cvrp bench-cvrp-db bench-cvrp-quick bench-cvrp-quick-db \
	bench-cvrp-solverforge bench-cvrp-solverforge-db \
	bench-cvrp-solverforge-quick bench-cvrp-solverforge-quick-db \
	bench-employee-scheduling bench-employee-scheduling-db \
	bench-employee-scheduling-quick bench-employee-scheduling-quick-db \
	bench-employee-scheduling-solverforge bench-employee-scheduling-solverforge-db \
	bench-employee-scheduling-solverforge-quick bench-employee-scheduling-solverforge-quick-db \
	bench-job-shop-scheduling bench-job-shop-scheduling-db \
	bench-job-shop-scheduling-quick bench-job-shop-scheduling-quick-db \
	bench-job-shop-scheduling-solverforge bench-job-shop-scheduling-solverforge-db \
	bench-job-shop-scheduling-solverforge-quick bench-job-shop-scheduling-solverforge-quick-db \
	build-hospital-scale build-hospital-scale-solverforge build-hospital-scale-timefold build-hospital-scale-ortools \
	bench-hospital-scale bench-hospital-scale-db bench-hospital-scale-quick bench-hospital-scale-quick-db \
	build-delivery-scale build-delivery-scale-solverforge build-delivery-scale-timefold build-delivery-scale-ortools \
	bench-delivery-scale bench-delivery-scale-db bench-delivery-scale-quick bench-delivery-scale-quick-db \
	bench-nightly-db \
	reaudit-legacy-publication \
	verify-benchmark-contracts verify-reference-catalogs load-reference-catalogs verify-fair-start verify-fair-start-rows verify-solverforge-config-parity verify-stock-solverforge-guardrails \
	verify-solverforge-py-guardrail-contract verify-solverforge-py-smoke verify-solverforge-py-comparison verify-solverforge-py-release \
	validate-cvrp validate-employee-scheduling validate-employee-model-parity validate-job-shop-scheduling \
	validate-hospital-scale validate-hospital-scale-model-parity \
	validate-delivery-scale validate-delivery-scale-model-parity \
	thread-study thread-study-report \
	db-check db-create db-migrate db-reset normalize-results \
	dash-setup dash-server dash-warehouse-check dash-smoke dash-test

# ============== Default Target ==============
.DEFAULT_GOAL := help

# $(call status,message) prints a progress line.
status = @printf -- "$(CYAN)$(ARROW)$(RESET) %s\n" "$(1)"

# $(call help_item,target,description) prints one help row.
help_item = printf -- "  $(GREEN)%-48s$(RESET) %s\n" "$(1)" "$(2)"
help_section = printf -- "\n$(CYAN)$(BOLD)%s$(RESET)\n" "$(1)"

help: banner
	@$(call help_section,Setup)
	@$(call help_item,install-python-deps,Create or refresh the root .venv)
	@$(call help_item,venv,Create the root .venv only)
	@$(call help_section,CVRP)
	@$(call help_item,validate-cvrp,Validate bundled .vrp/.sol pairs)
	@$(call help_item,build-cvrp,Build all CVRP solver integrations)
	@$(call help_item,bench-cvrp-quick[-db],Quick CVRP sample run)
	@$(call help_item,bench-cvrp-solverforge-quick[-db],SolverForge-only CVRP smoke run)
	@$(call help_item,bench-cvrp[-db],Full CVRP suite)
	@$(call help_section,Employee scheduling)
	@$(call help_item,validate-employee-scheduling,Validate INRC2 datasets)
	@$(call help_item,validate-employee-model-parity,Check validator/solver model parity)
	@$(call help_item,build-employee-scheduling,Build all employee solver integrations)
	@$(call help_item,bench-employee-scheduling-quick[-db],Quick INRC2 sample run)
	@$(call help_item,bench-employee-scheduling-solverforge-quick[-db],SolverForge-only smoke run)
	@$(call help_item,bench-employee-scheduling[-db],Full employee-scheduling suite)
	@$(call help_section,Job-shop scheduling)
	@$(call help_item,validate-job-shop-scheduling,Validate JSPLIB manifest and parser)
	@$(call help_item,build-job-shop-scheduling,Build all JSSP solver integrations)
	@$(call help_item,bench-job-shop-scheduling-quick[-db],Quick JSPLIB run)
	@$(call help_item,bench-job-shop-scheduling-solverforge-quick[-db],SolverForge-only smoke run)
	@$(call help_item,bench-job-shop-scheduling[-db],Full job-shop suite)
	@$(call help_section,Huge-scale)
	@$(call help_item,validate-hospital-scale[-model-parity],Check hospital corpus / model parity)
	@$(call help_item,build-hospital-scale,Build hospital-scale integrations)
	@$(call help_item,bench-hospital-scale[-quick][-db],Hospital-scale run (300s budget))
	@$(call help_item,validate-delivery-scale[-model-parity],Check delivery corpus / model parity)
	@$(call help_item,build-delivery-scale,Build delivery-scale integrations)
	@$(call help_item,bench-delivery-scale[-quick][-db],Delivery-scale run (300s budget))
	@$(call help_section,Nightly and studies)
	@$(call help_item,bench-nightly-db,Build everything and persist all suites)
	@$(call help_item,thread-study,SolverForge 1/2/4 move-thread study)
	@$(call help_item,thread-study-report,Regenerate the thread-study report)
	@$(call help_section,Verification gates)
	@$(call help_item,verify-benchmark-contracts,Harness contract tests)
	@$(call help_item,verify-fair-start,Static fair-start check)
	@$(call help_item,verify-fair-start-rows RUN_ID=<uuid>,Fair-start check on persisted rows)
	@$(call help_item,verify-solverforge-config-parity,Native/Python config parity)
	@$(call help_item,verify-reference-catalogs,Reference catalogs reproduce from source)
	@$(call help_item,verify-stock-solverforge-guardrails,Stock SolverForge guardrails)
	@$(call help_item,verify-solverforge-py-guardrail-contract,solverforge-py guardrail contract)
	@$(call help_item,verify-solverforge-py-smoke,solverforge-py smoke gate)
	@$(call help_item,verify-solverforge-py-comparison,solverforge-py comparison gate)
	@$(call help_item,verify-solverforge-py-release,solverforge-py release gate)
	@$(call help_section,Warehouse)
	@$(call help_item,db-check / db-create / db-migrate / db-reset,Manage the PostgreSQL warehouse)
	@$(call help_item,load-reference-catalogs,Load reference catalogs into the warehouse)
	@$(call help_item,reaudit-legacy-publication,Re-audit legacy publishable runs)
	@$(call help_item,normalize-results INPUT=... OUTPUT=...,Normalize result CSVs via Polars)
	@$(call help_section,Dashboard)
	@$(call help_item,dash-setup / dash-server,Set up / serve the Rails dashboard)
	@$(call help_item,dash-warehouse-check / dash-smoke / dash-test,Dashboard checks)
	@printf -- "\n$(GRAY)Variables: BENCH_ARGS  BENCH_CONFIG  NIGHTLY_ARGS  BENCH_CPU  DATABASE_URL$(RESET)\n\n"

# ============== Banner ==============
banner:
	@printf -- "$(EMERALD)$(BOLD)  ____        _                _____\n"
	@printf -- " / ___|  ___ | |_   _____ _ __|  ___|__  _ __ __ _  ___\n"
	@printf -- " \\___ \\\\ / _ \\\\| \\\\ \\\\ / / _ \\\\ '__| |_ / _ \\\\| '__/ _\` |/ _ \\\\\n"
	@printf -- "  ___) | (_) | |\\\\ V /  __/ |  |  _| (_) | | | (_| |  __/\n"
	@printf -- " |____/ \\\\___/|_| \\_/ \\___|_|  |_|  \\___/|_|  \\__, |\\___|\n"
	@printf -- "                                             |___/$(RESET)\n"
	@printf -- "  $(GRAY)v$(VERSION)$(RESET) $(EMERALD)Benchmark Build System$(RESET)\n\n"

verify-fair-start: banner venv
	"$(PYTHON)" scripts/verify_fair_start.py

verify-benchmark-contracts: banner venv
	PYTHONPATH=$(BENCH_PYTHONPATH) "$(PYTHON)" scripts/test_benchmark_contracts.py
	PYTHONPATH=$(BENCH_PYTHONPATH) "$(PYTHON)" scripts/test_thread_study.py
	PYTHONPATH=$(BENCH_PYTHONPATH) "$(PYTHON)" scripts/test_solver_output_contracts.py
	PYTHONPATH=scripts "$(PYTHON)" scripts/test_verify_stock_solverforge_guardrails.py
	PYTHONPATH=. "$(PYTHON)" scripts/test_reaudit_legacy_publication.py
	PYTHONPATH=src "$(PYTHON)" scripts/test_git_provenance.py
	PYTHONPATH=$(BENCH_PYTHONPATH) "$(PYTHON)" scripts/test_reference_catalog.py
	PYTHONPATH=$(BENCH_PYTHONPATH) "$(PYTHON)" scripts/test_reference_catalogs_contract.py
	PYTHONPATH=$(BENCH_PYTHONPATH) "$(PYTHON)" scripts/test_warehouse_references.py
	PYTHONPATH=$(BENCH_PYTHONPATH) "$(PYTHON)" scripts/test_warehouse_pins.py

verify-reference-catalogs: banner venv
	$(call status,Verifying reference catalogs reproduce from their pinned sources)
	PYTHONPATH=$(BENCH_PYTHONPATH) "$(PYTHON)" scripts/generate_reference_catalog.py jssp --check
	PYTHONPATH=$(BENCH_PYTHONPATH) "$(PYTHON)" scripts/generate_reference_catalog.py cvrp --check
	PYTHONPATH=$(BENCH_PYTHONPATH) "$(PYTHON)" scripts/generate_reference_catalog.py employee --check

load-reference-catalogs: banner venv
	$(call status,Loading official reference catalogs into the warehouse)
	"$(PYTHON)" scripts/load_reference_catalog.py --database-url "$(DATABASE_URL)"

verify-fair-start-rows: banner venv
	@test -n "$(RUN_ID)" || (echo "RUN_ID is required" >&2; exit 2)
	"$(PYTHON)" scripts/verify_fair_start.py --run-id "$(RUN_ID)" --database-url "$(DATABASE_URL)"

reaudit-legacy-publication: banner venv
	"$(PYTHON)" scripts/reaudit_legacy_publication.py --database-url "$(DATABASE_URL)"

verify-solverforge-config-parity: banner venv
	"$(PYTHON)" scripts/verify_solverforge_config_parity.py

verify-solverforge-py-guardrail-contract: banner venv
	"$(PYTHON)" scripts/test_verify_solverforge_py_guardrails.py

verify-stock-solverforge-guardrails: banner venv verify-fair-start verify-solverforge-config-parity build-job-shop-scheduling build-cvrp-solverforge build-employee-scheduling-solverforge
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/verify_stock_solverforge_guardrails.py $(GUARDRAIL_ARGS)

verify-solverforge-py-smoke: banner install-python-deps verify-fair-start verify-solverforge-config-parity verify-solverforge-py-guardrail-contract build-cvrp-solverforge build-employee-scheduling-solverforge build-job-shop-scheduling-solverforge
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/verify_solverforge_py_guardrails.py --mode smoke --output-dir "$(SOLVERFORGE_PY_GUARDRAIL_OUTPUT_DIR)" $(SOLVERFORGE_PY_GUARDRAIL_ARGS)

verify-solverforge-py-comparison: banner install-python-deps verify-fair-start verify-solverforge-config-parity verify-solverforge-py-guardrail-contract build-cvrp-solverforge build-employee-scheduling-solverforge build-job-shop-scheduling-solverforge
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/verify_solverforge_py_guardrails.py --mode comparison --output-dir "$(SOLVERFORGE_PY_GUARDRAIL_OUTPUT_DIR)" $(SOLVERFORGE_PY_GUARDRAIL_ARGS)

verify-solverforge-py-release: banner install-python-deps verify-benchmark-contracts verify-fair-start verify-solverforge-config-parity \
	verify-solverforge-py-guardrail-contract \
	validate-cvrp validate-employee-scheduling validate-employee-model-parity \
	validate-job-shop-scheduling build-cvrp-solverforge \
	build-employee-scheduling-solverforge build-job-shop-scheduling-solverforge
	"$(PYTHON)" -m compileall -q src list-variable/cvrp/src scalar-variable/employee-scheduling/src scalar-variable/job-shop-scheduling/src huge-scale/hospital-scale/src huge-scale/delivery-scale/src scripts
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/verify_solverforge_py_guardrails.py --mode release --output-dir "$(SOLVERFORGE_PY_GUARDRAIL_OUTPUT_DIR)" $(SOLVERFORGE_PY_GUARDRAIL_ARGS)

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
	PIP_DISABLE_PIP_VERSION_CHECK=1 "$(PIP)" install --force-reinstall --no-deps --only-binary=:all: "$(SOLVERFORGE_PY_REQUIREMENT)"
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

build-cvrp-solverforge: banner install-python-deps verify-solverforge-config-parity
	cd $(CVRP_SOLVERFORGE_DIR) && PIP_DISABLE_PIP_VERSION_CHECK=1 maturin develop --release --locked --pip-path "$(PIP)"

bench-cvrp: build-cvrp
	$(PINNED_CVRP_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) $(BENCH_ARGS)

bench-cvrp-db: build-cvrp db-migrate
	$(PINNED_CVRP_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-cvrp-quick: build-cvrp
	$(PINNED_CVRP_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --run-kind quick --num-instances 3 --time-limits 1 10 $(BENCH_ARGS)

bench-cvrp-quick-db: build-cvrp db-migrate
	$(PINNED_CVRP_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --run-kind quick --num-instances 3 --time-limits 1 10 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-cvrp-solverforge: build-cvrp-solverforge
	$(PINNED_CVRP_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --solver solverforge $(BENCH_ARGS)

bench-cvrp-solverforge-db: build-cvrp-solverforge db-migrate
	$(PINNED_CVRP_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --solver solverforge $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-cvrp-solverforge-quick: build-cvrp-solverforge
	$(PINNED_CVRP_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --run-kind quick --solver solverforge --num-instances 3 --time-limits 1 10 $(BENCH_ARGS)

bench-cvrp-solverforge-quick-db: build-cvrp-solverforge db-migrate
	$(PINNED_CVRP_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(BENCH_CONFIG_ARG) --run-kind quick --solver solverforge --num-instances 3 --time-limits 1 10 $(BENCH_DB_ARGS) $(BENCH_ARGS)

# ============== Thread Study ==============
# Native SolverForge against itself across move-thread counts. Results stay in
# local CSVs and a markdown report; they never enter the warehouse rankings.
thread-study: build-cvrp-solverforge build-employee-scheduling-solverforge
	mkdir -p $(THREAD_STUDY_DIR)
	$(PINNED_THREAD_STUDY) "$(PYTHON)" scripts/run_benchmark.py cvrp --config "$(THREAD_STUDY_CONFIG)" --output $(THREAD_STUDY_DIR)/cvrp.csv $(BENCH_ARGS)
	$(PINNED_THREAD_STUDY) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling --config "$(THREAD_STUDY_CONFIG)" --output $(THREAD_STUDY_DIR)/employee-scheduling.csv $(BENCH_ARGS)
	$(MAKE) thread-study-report

thread-study-report: banner
	PYTHONPATH=$(BENCH_PYTHONPATH) "$(PYTHON)" scripts/thread_study_report.py $(THREAD_STUDY_DIR)/*.csv --output $(THREAD_STUDY_DIR)/report.md

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

build-employee-scheduling-solverforge: banner install-python-deps verify-solverforge-config-parity
	cd $(EMPLOYEE_SOLVERFORGE_DIR) && maturin build --release --locked -i "$(PYTHON)"
	PIP_DISABLE_PIP_VERSION_CHECK=1 "$(PIP)" install --force-reinstall $$(ls -t $(EMPLOYEE_SOLVERFORGE_DIR)/target/wheels/*.whl | head -1)

bench-employee-scheduling: build-employee-scheduling
	$(PINNED_EMPLOYEE_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --dataset-set canonical --time-limits 1 10 60 $(BENCH_ARGS)

bench-employee-scheduling-db: build-employee-scheduling db-migrate
	$(PINNED_EMPLOYEE_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --dataset-set canonical --time-limits 1 10 60 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-employee-scheduling-quick: build-employee-scheduling
	$(PINNED_EMPLOYEE_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --datasets n005w4 --time-limits 1 10 $(BENCH_ARGS)

bench-employee-scheduling-quick-db: build-employee-scheduling db-migrate
	$(PINNED_EMPLOYEE_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --datasets n005w4 --time-limits 1 10 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-employee-scheduling-solverforge: build-employee-scheduling-solverforge
	$(PINNED_EMPLOYEE_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --solver solverforge --dataset-set canonical --time-limits 1 10 60 $(BENCH_ARGS)

bench-employee-scheduling-solverforge-db: build-employee-scheduling-solverforge db-migrate
	$(PINNED_EMPLOYEE_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --solver solverforge --dataset-set canonical --time-limits 1 10 60 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-employee-scheduling-solverforge-quick: build-employee-scheduling-solverforge
	$(PINNED_EMPLOYEE_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --solver solverforge --datasets n005w4 --time-limits 1 10 $(BENCH_ARGS)

bench-employee-scheduling-solverforge-quick-db: build-employee-scheduling-solverforge db-migrate
	$(PINNED_EMPLOYEE_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --solver solverforge --datasets n005w4 --time-limits 1 10 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-nightly-db: build-cvrp build-employee-scheduling build-job-shop-scheduling build-hospital-scale build-delivery-scale db-migrate
	$(PINNED_CVRP_BENCH) "$(PYTHON)" scripts/run_benchmark.py cvrp $(NIGHTLY_CONFIG_ARG) $(BENCH_DB_ARGS) $(NIGHTLY_ARGS) & \
	cvrp_pid=$$!; \
	$(PINNED_EMPLOYEE_BENCH) "$(PYTHON)" scripts/run_benchmark.py employee-scheduling $(NIGHTLY_CONFIG_ARG) $(BENCH_DB_ARGS) $(NIGHTLY_ARGS) & \
	employee_pid=$$!; \
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/run_benchmark.py job-shop-scheduling $(NIGHTLY_CONFIG_ARG) $(BENCH_DB_ARGS) $(NIGHTLY_ARGS) & \
	jobshop_pid=$$!; \
	$(PINNED_HOSPITAL_SCALE_BENCH) "$(PYTHON)" scripts/run_benchmark.py hospital-scale $(NIGHTLY_CONFIG_ARG) $(BENCH_DB_ARGS) $(NIGHTLY_ARGS) & \
	hospital_scale_pid=$$!; \
	$(PINNED_DELIVERY_SCALE_BENCH) "$(PYTHON)" scripts/run_benchmark.py delivery-scale $(NIGHTLY_CONFIG_ARG) $(BENCH_DB_ARGS) $(NIGHTLY_ARGS) & \
	delivery_scale_pid=$$!; \
	status=0; \
	wait $$cvrp_pid || status=$$?; \
	wait $$employee_pid || status=$$?; \
	wait $$jobshop_pid || status=$$?; \
	wait $$hospital_scale_pid || status=$$?; \
	wait $$delivery_scale_pid || status=$$?; \
	exit $$status

validate-employee-scheduling: banner
	cd $(EMPLOYEE_ROOT) && PYTHONPATH=../../src:../../list-variable/cvrp/src:src "$(PYTHON)" scripts/validate_all.py

validate-employee-model-parity: banner
	cd $(EMPLOYEE_ROOT) && PYTHONPATH=../../src:../../list-variable/cvrp/src:src "$(PYTHON)" scripts/verify_model_parity.py

normalize-results: banner
	test -n "$(INPUT)"
	test -n "$(OUTPUT)"
	"$(PYTHON)" scripts/normalize_results.py --input "$(INPUT)" --output "$(OUTPUT)" $(ARGS)


build-job-shop-scheduling: banner install-python-deps build-job-shop-scheduling-solverforge build-job-shop-scheduling-timefold build-job-shop-scheduling-ortools

build-job-shop-scheduling-solverforge: banner install-python-deps verify-solverforge-config-parity
	cd $(JOBSHOP_SOLVERFORGE_DIR) && maturin build --release --locked -i "$(PYTHON)"
	PIP_DISABLE_PIP_VERSION_CHECK=1 "$(PIP)" install --force-reinstall $$(ls -t $(JOBSHOP_SOLVERFORGE_DIR)/target/wheels/*.whl | head -1)

build-job-shop-scheduling-timefold: banner
	$(MAVEN_ENV) mvn -f $(JOBSHOP_TIMEFOLD_POM) package -q

build-job-shop-scheduling-ortools: banner $(ORTOOLS_ROOT)/lib64/cmake/ortools/ortoolsConfig.cmake
	cmake -S $(JOBSHOP_ORTOOLS_DIR) -B build/job-shop-scheduling-ortools -DCMAKE_PREFIX_PATH="$(ORTOOLS_ROOT)" -DORTOOLS_ROOT="$(ORTOOLS_ROOT)"
	cmake --build build/job-shop-scheduling-ortools --parallel
	mkdir -p $(JOBSHOP_ORTOOLS_DIR)/target
	cp build/job-shop-scheduling-ortools/job_shop_scheduling_ortools $(JOBSHOP_ORTOOLS_DIR)/target/

bench-job-shop-scheduling: build-job-shop-scheduling
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/run_benchmark.py job-shop-scheduling $(BENCH_CONFIG_ARG) --dataset-set canonical --time-limits 1 10 60 $(BENCH_ARGS)

bench-job-shop-scheduling-db: build-job-shop-scheduling db-migrate
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/run_benchmark.py job-shop-scheduling $(BENCH_CONFIG_ARG) --dataset-set canonical --time-limits 1 10 60 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-job-shop-scheduling-quick: build-job-shop-scheduling
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/run_benchmark.py job-shop-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --dataset-set quick --time-limits 1 10 $(BENCH_ARGS)

bench-job-shop-scheduling-quick-db: build-job-shop-scheduling db-migrate
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/run_benchmark.py job-shop-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --dataset-set quick --time-limits 1 10 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-job-shop-scheduling-solverforge: build-job-shop-scheduling-solverforge
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/run_benchmark.py job-shop-scheduling $(BENCH_CONFIG_ARG) --solver solverforge --dataset-set canonical --time-limits 1 10 60 $(BENCH_ARGS)

bench-job-shop-scheduling-solverforge-db: build-job-shop-scheduling-solverforge db-migrate
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/run_benchmark.py job-shop-scheduling $(BENCH_CONFIG_ARG) --solver solverforge --dataset-set canonical --time-limits 1 10 60 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-job-shop-scheduling-solverforge-quick: build-job-shop-scheduling-solverforge
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/run_benchmark.py job-shop-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --solver solverforge --dataset-set quick --time-limits 1 10 $(BENCH_ARGS)

bench-job-shop-scheduling-solverforge-quick-db: build-job-shop-scheduling-solverforge db-migrate
	$(PINNED_JOBSHOP_BENCH) "$(PYTHON)" scripts/run_benchmark.py job-shop-scheduling $(BENCH_CONFIG_ARG) --run-kind quick --solver solverforge --dataset-set quick --time-limits 1 10 $(BENCH_DB_ARGS) $(BENCH_ARGS)

validate-job-shop-scheduling: banner
	cd $(JOBSHOP_ROOT) && PYTHONPATH=../../src:src "$(PYTHON)" scripts/validate_all.py

build-hospital-scale: banner install-python-deps build-hospital-scale-solverforge build-hospital-scale-timefold build-hospital-scale-ortools

build-hospital-scale-solverforge: banner install-python-deps
	cd $(HOSPITAL_SCALE_SOLVERFORGE_DIR) && maturin build --release --locked -i "$(PYTHON)"
	PIP_DISABLE_PIP_VERSION_CHECK=1 "$(PIP)" install --force-reinstall $$(ls -t $(HOSPITAL_SCALE_SOLVERFORGE_DIR)/target/wheels/*.whl | head -1)

build-hospital-scale-timefold: banner
	$(MAVEN_ENV) mvn -f $(HOSPITAL_SCALE_TIMEFOLD_POM) package -q

build-hospital-scale-ortools: banner $(ORTOOLS_ROOT)/lib64/cmake/ortools/ortoolsConfig.cmake
	cmake -S $(HOSPITAL_SCALE_ORTOOLS_DIR) -B build/hospital-scale-ortools -DCMAKE_PREFIX_PATH="$(ORTOOLS_ROOT)" -DORTOOLS_ROOT="$(ORTOOLS_ROOT)"
	cmake --build build/hospital-scale-ortools --parallel
	mkdir -p $(HOSPITAL_SCALE_ORTOOLS_DIR)/target
	cp build/hospital-scale-ortools/hospital_scale_ortools $(HOSPITAL_SCALE_ORTOOLS_DIR)/target/

bench-hospital-scale: build-hospital-scale
	$(PINNED_HOSPITAL_SCALE_BENCH) "$(PYTHON)" scripts/run_benchmark.py hospital-scale $(BENCH_CONFIG_ARG) --dataset-set canonical --time-limits 300 $(BENCH_ARGS)

bench-hospital-scale-db: build-hospital-scale db-migrate
	$(PINNED_HOSPITAL_SCALE_BENCH) "$(PYTHON)" scripts/run_benchmark.py hospital-scale $(BENCH_CONFIG_ARG) --dataset-set canonical --time-limits 300 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-hospital-scale-quick: build-hospital-scale
	$(PINNED_HOSPITAL_SCALE_BENCH) "$(PYTHON)" scripts/run_benchmark.py hospital-scale $(BENCH_CONFIG_ARG) --run-kind quick --dataset-set quick --time-limits 300 $(BENCH_ARGS)

bench-hospital-scale-quick-db: build-hospital-scale db-migrate
	$(PINNED_HOSPITAL_SCALE_BENCH) "$(PYTHON)" scripts/run_benchmark.py hospital-scale $(BENCH_CONFIG_ARG) --run-kind quick --dataset-set quick --time-limits 300 $(BENCH_DB_ARGS) $(BENCH_ARGS)

validate-hospital-scale: banner
	PYTHONPATH=src:$(HOSPITAL_SCALE_ROOT)/src "$(PYTHON)" $(HOSPITAL_SCALE_ROOT)/scripts/generate_instances.py --check
	PYTHONPATH=src:$(HOSPITAL_SCALE_ROOT)/src "$(PYTHON)" $(HOSPITAL_SCALE_ROOT)/scripts/validate_all.py

validate-hospital-scale-model-parity: banner
	PYTHONPATH=src:$(HOSPITAL_SCALE_ROOT)/src "$(PYTHON)" $(HOSPITAL_SCALE_ROOT)/scripts/verify_model_parity.py

build-delivery-scale: banner install-python-deps build-delivery-scale-solverforge build-delivery-scale-timefold build-delivery-scale-ortools

build-delivery-scale-solverforge: banner install-python-deps
	cd $(DELIVERY_SCALE_SOLVERFORGE_DIR) && maturin build --release --locked -i "$(PYTHON)"
	PIP_DISABLE_PIP_VERSION_CHECK=1 "$(PIP)" install --force-reinstall $$(ls -t $(DELIVERY_SCALE_SOLVERFORGE_DIR)/target/wheels/*.whl | head -1)

build-delivery-scale-timefold: banner
	$(MAVEN_ENV) mvn -f $(DELIVERY_SCALE_TIMEFOLD_POM) package -q

build-delivery-scale-ortools: banner $(ORTOOLS_ROOT)/lib64/cmake/ortools/ortoolsConfig.cmake
	cmake -S $(DELIVERY_SCALE_ORTOOLS_DIR) -B build/delivery-scale-ortools -DCMAKE_PREFIX_PATH="$(ORTOOLS_ROOT)" -DORTOOLS_ROOT="$(ORTOOLS_ROOT)"
	cmake --build build/delivery-scale-ortools --parallel
	mkdir -p $(DELIVERY_SCALE_ORTOOLS_DIR)/target
	cp build/delivery-scale-ortools/delivery_scale_ortools $(DELIVERY_SCALE_ORTOOLS_DIR)/target/

bench-delivery-scale: build-delivery-scale
	$(PINNED_DELIVERY_SCALE_BENCH) "$(PYTHON)" scripts/run_benchmark.py delivery-scale $(BENCH_CONFIG_ARG) --dataset-set canonical --time-limits 300 $(BENCH_ARGS)

bench-delivery-scale-db: build-delivery-scale db-migrate
	$(PINNED_DELIVERY_SCALE_BENCH) "$(PYTHON)" scripts/run_benchmark.py delivery-scale $(BENCH_CONFIG_ARG) --dataset-set canonical --time-limits 300 $(BENCH_DB_ARGS) $(BENCH_ARGS)

bench-delivery-scale-quick: build-delivery-scale
	$(PINNED_DELIVERY_SCALE_BENCH) "$(PYTHON)" scripts/run_benchmark.py delivery-scale $(BENCH_CONFIG_ARG) --run-kind quick --dataset-set quick --time-limits 300 $(BENCH_ARGS)

bench-delivery-scale-quick-db: build-delivery-scale db-migrate
	$(PINNED_DELIVERY_SCALE_BENCH) "$(PYTHON)" scripts/run_benchmark.py delivery-scale $(BENCH_CONFIG_ARG) --run-kind quick --dataset-set quick --time-limits 300 $(BENCH_DB_ARGS) $(BENCH_ARGS)

validate-delivery-scale: banner
	PYTHONPATH=src:$(DELIVERY_SCALE_ROOT)/src "$(PYTHON)" $(DELIVERY_SCALE_ROOT)/scripts/generate_instances.py --check
	PYTHONPATH=src:$(DELIVERY_SCALE_ROOT)/src "$(PYTHON)" $(DELIVERY_SCALE_ROOT)/scripts/validate_all.py

validate-delivery-scale-model-parity: banner
	PYTHONPATH=src:$(DELIVERY_SCALE_ROOT)/src "$(PYTHON)" $(DELIVERY_SCALE_ROOT)/scripts/verify_model_parity.py

# ============== Dashboard ==============
# Read-only Rails dashboard over the benchmark warehouse. Rails keeps its own
# framework metadata in dash/storage SQLite files; it never writes benchmark
# rows and never runs warehouse migrations.

dash-setup: banner
	"$(MAKE)" -C $(DASH_ROOT) BENCH_DATABASE_URL="$(DATABASE_URL)" setup

dash-server: banner
	"$(MAKE)" -C $(DASH_ROOT) BENCH_DATABASE_URL="$(DATABASE_URL)" server

dash-warehouse-check: banner
	"$(MAKE)" -C $(DASH_ROOT) BENCH_DATABASE_URL="$(DATABASE_URL)" warehouse-check

dash-smoke: banner
	"$(MAKE)" -C $(DASH_ROOT) BENCH_DATABASE_URL="$(DATABASE_URL)" smoke

dash-test: banner
	"$(MAKE)" -C $(DASH_ROOT) BENCH_DATABASE_URL="$(DATABASE_URL)" test
