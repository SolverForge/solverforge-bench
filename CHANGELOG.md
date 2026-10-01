# Changelog

All notable changes to this project will be documented in this file. See [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) for commit guidelines.

## 0.1.1 (2026-10-01)


### Features

* add job-shop scheduling benchmark implementation a292468
* align employee scheduling quality tracking with CVRP f1ef7ff
* **bench:** add shared benchmark framework bd2b1d5
* **bench:** align SolverForge adapter policies ccd0dd0
* **bench:** centralize benchmark harness contracts 16c6c0d
* **bench:** compare solverforge-py by default 70ecd3d
* **bench:** enforce runtime fair-start witnesses b6f5474
* **bench:** pin each problem's official reference values 3626960
* **bench:** record official job-shop references 4d803cb
* **bench:** resolve every problem's reference from a pinned catalog cb20de3
* **cvrp:** add list-variable benchmark 396d07f
* **cvrp:** add opt-in solverforge-py adapter ec2afad
* **cvrp:** align SolverForge adapter with route API d998108
* **cvrp:** broaden SolverForge list neighborhoods fd68467
* **dash:** import benchmark dashboard as read-only monolith component 22c56cb
* **dwh:** carry official references into the warehouse for every problem 97a8613
* **employee-scheduling:** add INRC-II benchmark 33351f0
* **employee-scheduling:** share SolverForge constraint streams e279b73
* **employee:** add opt-in solverforge-py adapter f86b639
* **job-shop:** add three production solver adapters a5ab5d3
* **job-shop:** bundle canonical JSPLIB corpus c8f251b
* **job-shop:** expose JSPLIB bound metadata 96943e3
* **job-shop:** model schedules as machine sequences fd68995
* **jssp:** add opt-in solverforge-py adapter 09d731c


### Bug Fixes

* **adapters:** reject incomplete solver output 88dcf8e
* align CVRP SolverForge adapter with 0.17.1 hooks 6204565
* **bench:** attribute a run to its commit without local output 5714ec2
* **bench:** classify incomplete SolverForge construction 42542b0
* **bench:** gate JSSP win guardrail fbbc7c0
* **benchmarks:** attest publishable run integrity f5eb8b8
* **bench:** persist NULL validation_error for clean evaluations aa5808f
* **bench:** record postgres run completion 5017a36
* **bench:** redact database URLs from run metadata ad0b047
* **bench:** run benchmark suites on separate cores 861d944
* **cvrp:** classify native OR-Tools no-solution exits b927cf3
* **cvrp:** sort smoke instances by numeric size e0771ef
* **employee-scheduling:** align solverforge score reporting 71c1eee
* **employee-scheduling:** allow unknown reference costs in parity check 2674371, closes #1 #1
* **employee-scheduling:** keep solverforge rows for validation 8389617
* **employee-scheduling:** remove OR-Tools seeded fallback 9d726cb
* **employee-scheduling:** restore CP-SAT default search portfolio d9b3b4a
* **employee-scheduling:** use upstream assignment topology e44ade4
* **employee:** enforce Python nurse assignment domains 677d921
* **employee:** repair OR-Tools staffing outcomes 2e374df
* **employee:** restore honest canonical comparisons c26b775
* **fair-start:** keep input hashing out of timed runs 1004fa8
* **fair-start:** preserve employee native witness on no solution cc5aad3
* **fair-start:** preserve native witness evidence 0f43787
* **job-shop:** preserve native fields in normalization 3061c07
* **job-shop:** serialize schedule payloads across harness ab26a22
* **job-shop:** use stock precedence scoring 2b8c0b3
* **make:** expose job-shop database wrappers 53f53e4
* **make:** wire job-shop benchmark wrappers dfe97e2
* preserve child queue messages during watchdog waits 3e73496
* **results:** keep normalized CSV witness serializable 840a0bb
* **warehouse:** backfill official job-shop metrics 6145916
