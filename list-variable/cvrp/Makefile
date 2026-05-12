PYTHON ?= $(CURDIR)/.venv/bin/python3
ROOT := ../..

.PHONY: build build-solverforge build-timefold-java bench bench-quick bench-solverforge bench-solverforge-quick validate full

build:
	$(MAKE) -C $(ROOT) build-cvrp

build-timefold-java:
	$(MAKE) -C $(ROOT) build-cvrp-timefold-java

build-solverforge:
	$(MAKE) -C $(ROOT) build-cvrp-solverforge

bench:
	$(MAKE) -C $(ROOT) bench-cvrp CVRP_PYTHON=$(PYTHON)

bench-quick:
	$(MAKE) -C $(ROOT) bench-cvrp-quick CVRP_PYTHON=$(PYTHON)

bench-solverforge:
	$(MAKE) -C $(ROOT) bench-cvrp-solverforge CVRP_PYTHON=$(PYTHON)

bench-solverforge-quick:
	$(MAKE) -C $(ROOT) bench-cvrp-solverforge-quick CVRP_PYTHON=$(PYTHON)

validate:
	$(MAKE) -C $(ROOT) validate-cvrp CVRP_PYTHON=$(PYTHON)

full:
	$(MAKE) -C $(ROOT) bench-cvrp CVRP_PYTHON=$(PYTHON)
