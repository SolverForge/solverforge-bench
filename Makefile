.PHONY: bench-cvrp bench-cvrp-quick bench-solverforge bench-solverforge-quick validate-cvrp bench-employee-scheduling bench-employee-scheduling-quick bench-employee-scheduling-solverforge-quick validate-employee-scheduling normalize-results

bench-cvrp:
	$(MAKE) -C list-variable/cvrp bench

bench-cvrp-quick:
	$(MAKE) -C list-variable/cvrp bench-quick

bench-solverforge:
	$(MAKE) -C list-variable/cvrp bench-solverforge

bench-solverforge-quick:
	$(MAKE) -C list-variable/cvrp bench-solverforge-quick

validate-cvrp:
	$(MAKE) -C list-variable/cvrp validate

bench-employee-scheduling:
	$(MAKE) -C scalar-variable/employee-scheduling bench

bench-employee-scheduling-quick:
	$(MAKE) -C scalar-variable/employee-scheduling bench-quick

bench-employee-scheduling-solverforge-quick:
	$(MAKE) -C scalar-variable/employee-scheduling bench-solverforge-quick

validate-employee-scheduling:
	$(MAKE) -C scalar-variable/employee-scheduling validate

normalize-results:
	test -n "$(INPUT)"
	test -n "$(OUTPUT)"
	python3 scripts/normalize_results.py --input "$(INPUT)" --output "$(OUTPUT)" $(ARGS)
