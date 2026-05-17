ROOT := ../..
PYTHON ?= $(abspath $(ROOT))/.venv/bin/python3

.PHONY: build build-solverforge build-timefold build-ortools bench bench-quick bench-solverforge bench-solverforge-quick validate full

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

bench-quick:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling-quick PYTHON=$(PYTHON)

bench-solverforge:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling-solverforge PYTHON=$(PYTHON)

bench-solverforge-quick:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling-solverforge-quick PYTHON=$(PYTHON)

validate:
	$(MAKE) -C $(ROOT) validate-job-shop-scheduling PYTHON=$(PYTHON)

full:
	$(MAKE) -C $(ROOT) bench-job-shop-scheduling PYTHON=$(PYTHON)
