ROOT := ../..
PYTHON ?= $(abspath $(ROOT))/.venv/bin/python3

.PHONY: build build-solverforge build-timefold build-ortools build-rustvrp build-vroom bench bench-quick bench-solverforge bench-solverforge-quick validate full

build:
	$(MAKE) -C $(ROOT) build-cvrp

build-timefold:
	$(MAKE) -C $(ROOT) build-cvrp-timefold

build-ortools:
	$(MAKE) -C $(ROOT) build-cvrp-ortools

build-rustvrp:
	$(MAKE) -C $(ROOT) build-cvrp-rustvrp

build-vroom:
	$(MAKE) -C $(ROOT) build-cvrp-vroom

build-solverforge:
	$(MAKE) -C $(ROOT) build-cvrp-solverforge

bench:
	$(MAKE) -C $(ROOT) bench-cvrp PYTHON=$(PYTHON)

bench-quick:
	$(MAKE) -C $(ROOT) bench-cvrp-quick PYTHON=$(PYTHON)

bench-solverforge:
	$(MAKE) -C $(ROOT) bench-cvrp-solverforge PYTHON=$(PYTHON)

bench-solverforge-quick:
	$(MAKE) -C $(ROOT) bench-cvrp-solverforge-quick PYTHON=$(PYTHON)

validate:
	$(MAKE) -C $(ROOT) validate-cvrp PYTHON=$(PYTHON)

full:
	$(MAKE) -C $(ROOT) bench-cvrp PYTHON=$(PYTHON)
