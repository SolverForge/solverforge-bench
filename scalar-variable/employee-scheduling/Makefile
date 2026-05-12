PYTHON ?= python3.12
ROOT := ../..

.PHONY: build build-solverforge build-timefold-java bench bench-quick bench-solverforge bench-solverforge-quick validate validate-model-parity

build:
	$(MAKE) -C $(ROOT) build-employee-scheduling PYTHON=$(PYTHON)

build-timefold-java:
	$(MAKE) -C $(ROOT) build-employee-scheduling-timefold-java

build-solverforge:
	$(MAKE) -C $(ROOT) build-employee-scheduling-solverforge PYTHON=$(PYTHON)

bench:
	$(MAKE) -C $(ROOT) bench-employee-scheduling PYTHON=$(PYTHON)

bench-quick:
	$(MAKE) -C $(ROOT) bench-employee-scheduling-quick PYTHON=$(PYTHON)

bench-solverforge:
	$(MAKE) -C $(ROOT) bench-employee-scheduling-solverforge PYTHON=$(PYTHON)

bench-solverforge-quick:
	$(MAKE) -C $(ROOT) bench-employee-scheduling-solverforge-quick PYTHON=$(PYTHON)

validate:
	$(MAKE) -C $(ROOT) validate-employee-scheduling PYTHON=$(PYTHON)

validate-model-parity:
	$(MAKE) -C $(ROOT) validate-employee-model-parity PYTHON=$(PYTHON)
