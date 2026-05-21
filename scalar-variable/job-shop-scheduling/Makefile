ROOT := ../..
PYTHON ?= $(abspath $(ROOT))/.venv/bin/python3

.PHONY: build build-solverforge build-timefold build-ortools bench bench-db bench-quick bench-quick-db bench-solverforge bench-solverforge-db bench-solverforge-quick bench-solverforge-quick-db validate full full-db

build:
	$(MAKE) -C $(ROOT) build-job-shop-scheduling PYTHON=$(PYTHON)

build-timefold:
	$(MAKE) -C $(ROOT) build-job-shop-scheduling-timefold

build-ortools:
	$(MAKE) -C $(ROOT) build-job-shop-scheduling-ortools

build-solverforge:
	$(MAKE) -C $(ROOT) build-job-shop-scheduling-solverforge PYTHON=$(PYTHON)

bench:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling PYTHON=$(PYTHON)

bench-db:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling-db PYTHON=$(PYTHON)

bench-quick:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling-quick PYTHON=$(PYTHON)

bench-quick-db:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling-quick-db PYTHON=$(PYTHON)

bench-solverforge:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling-solverforge PYTHON=$(PYTHON)

bench-solverforge-db:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling-solverforge-db PYTHON=$(PYTHON)

bench-solverforge-quick:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling-solverforge-quick PYTHON=$(PYTHON)

bench-solverforge-quick-db:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling-solverforge-quick-db PYTHON=$(PYTHON)

validate:
	$(MAKE) -C $(ROOT) validate-job-shop-scheduling PYTHON=$(PYTHON)

full:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling PYTHON=$(PYTHON)

full-db:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling-db PYTHON=$(PYTHON)
