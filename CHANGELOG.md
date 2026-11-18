# Changelog

All notable changes to this project will be documented in this file.
## [0.1.7](https://github.com/SolverForge/solverforge-bench/compare/v0.1.6...v0.1.7) (2026-11-18)


### Features

* **huge-scale:** add the delivery-scale routing benchmark ([11ed2f9](https://github.com/SolverForge/solverforge-bench/commit/11ed2f9048e5f4baa3b9770951e6c9884b6ddbf0))
* **huge-scale:** add the hospital-scale rostering benchmark ([62e2c90](https://github.com/SolverForge/solverforge-bench/commit/62e2c903eab2af4777a8193055c70cb05728a64f))


### Bug Fixes

* **guardrails:** treat a reference solver without a schedule as a result ([9111abd](https://github.com/SolverForge/solverforge-bench/commit/9111abd9db6f480235621e8b2c472374beb31af5)), closes [#3](https://github.com/SolverForge/solverforge-bench/issues/3)
* **jssp:** report Timefold's incomplete schedule as a missing incumbent ([769a1bf](https://github.com/SolverForge/solverforge-bench/commit/769a1bfe02038d576f0007a2358ea02af3748c15))


### Documentation

* align native SolverForge pin guidance with 0.24.0 ([f1e027d](https://github.com/SolverForge/solverforge-bench/commit/f1e027d26821ccc82bea6f57c1e7e2d327101c6b))
* align native SolverForge pin guidance with 0.25.0 ([712a302](https://github.com/SolverForge/solverforge-bench/commit/712a30205590f8aad81ce42bf360a281cd152f0f))
* align native SolverForge pin guidance with 0.25.1 ([b43bf2f](https://github.com/SolverForge/solverforge-bench/commit/b43bf2f69a5ba5e5d99dd043bdb8beafee205323))
* align native SolverForge pin guidance with 0.26.0 ([ac853ef](https://github.com/SolverForge/solverforge-bench/commit/ac853ef0382052f2c4ec580638fde4e2ab95ff57)), closes [#7](https://github.com/SolverForge/solverforge-bench/issues/7)
* align native SolverForge pin guidance with 0.26.1 ([c36cedd](https://github.com/SolverForge/solverforge-bench/commit/c36cedd2f2c1f3a12f52ece6b19ff9952f5fa1f6)), closes [#9](https://github.com/SolverForge/solverforge-bench/issues/9)
* align solver pin guidance with SolverForge 0.31.2 and Timefold 2.8.0 ([af50304](https://github.com/SolverForge/solverforge-bench/commit/af5030474e3eac1fed88111983be0af32acf3fc1))
* document the huge-scale benchmark category ([37ce849](https://github.com/SolverForge/solverforge-bench/commit/37ce8493728c67865f9ccde4b9897a77cd76e30d))


## [0.1.6](https://github.com/SolverForge/solverforge-bench/compare/v0.1.5...v0.1.6) (2026-10-31)


### Features

* **cvrp:** select CVRPLIB-X instances by name ([b3b7dbd](https://github.com/SolverForge/solverforge-bench/commit/b3b7dbd1c5effb2680e6a68725f5cf56bb5d20dc))
* **provenance:** resolve git-locked cargo dependencies to their commit ([367d4f5](https://github.com/SolverForge/solverforge-bench/commit/367d4f571e0801b21cf12a77797cea70c29b47a1))
* **solverforge:** run the native adapters with a move-thread count ([0d9db8c](https://github.com/SolverForge/solverforge-bench/commit/0d9db8cce4b0894068f41e085002d65967db056c))
* **thread-study:** compare native SolverForge with itself across move threads ([af140cf](https://github.com/SolverForge/solverforge-bench/commit/af140cf45f441651169bdd461532844447011a9c))
* **thread-study:** read search figures from local-search phase records ([c238848](https://github.com/SolverForge/solverforge-bench/commit/c238848d053e33d71311ba76496003dbbdb00670))
* **thread-study:** report the single-threaded share of time spent evaluating ([4495ecd](https://github.com/SolverForge/solverforge-bench/commit/4495ecdecaf9d5af26d7f4a09bb468d9bf2014d3))


### Tests

* **provenance:** pin runtime provenance for git-locked cargo dependencies ([595d276](https://github.com/SolverForge/solverforge-bench/commit/595d2769348becf0a5f37b20ef07ccc1a662679d))


### Documentation

* align solver pin guidance with the latest releases ([eb6ca36](https://github.com/SolverForge/solverforge-bench/commit/eb6ca36f3cc96f10e13085a2f0807d315d1e8283))
* describe the thread-study evaluation-share column ([4178473](https://github.com/SolverForge/solverforge-bench/commit/4178473068278888993f02e2c85bc1d31d98ac0d))


## [0.1.5](https://github.com/SolverForge/solverforge-bench/compare/v0.1.4...v0.1.5) (2026-10-18)


### Documentation

* align solver pin guidance with the latest releases ([86846f2](https://github.com/SolverForge/solverforge-bench/commit/86846f2818b320c9fa1bb87d77cf95d60f5135e6))


## [0.1.4](https://github.com/SolverForge/solverforge-bench/compare/v0.1.3...v0.1.4) (2026-10-15)


### Bug Fixes

* **jssp:** declare the fixed operation owner as a solution field ([2908484](https://github.com/SolverForge/solverforge-bench/commit/29084845dc6328f2e4509e25a494d151b26ec68b))
* **jssp:** order zero-duration operations before equal-start intervals ([9fc4d93](https://github.com/SolverForge/solverforge-bench/commit/9fc4d9348cbff680585e0c1e9764b3bb1e87df1a))


### Tests

* **jssp:** compare machine validation with exhaustive pairwise oracle ([6cd89ca](https://github.com/SolverForge/solverforge-bench/commit/6cd89cacd214abd1237b1cb8e28691128b0bfcfa))
* **jssp:** reproduce zero-duration boundary validation failure ([48bf30d](https://github.com/SolverForge/solverforge-bench/commit/48bf30ddb7773befc911ae56de0e51e131b90af4))


### Documentation

* align native SolverForge pin guidance with 0.20.4 ([df3f58e](https://github.com/SolverForge/solverforge-bench/commit/df3f58e4e68a5b3d086e38be0d2fcf1f69250461))
* align native SolverForge pin guidance with 0.20.4 in AGENTS.md ([a6b5d1b](https://github.com/SolverForge/solverforge-bench/commit/a6b5d1b02751040d79f5b15e3d16eb6291dde55a))
* align native SolverForge pin guidance with 0.21.0 ([22fe4c6](https://github.com/SolverForge/solverforge-bench/commit/22fe4c611fc33a65e40cda28b9752e4e9c956f7f))
* align native SolverForge pin guidance with 0.21.2 ([b896787](https://github.com/SolverForge/solverforge-bench/commit/b896787eb6d74ce52bc707aee549c3744c950750))


## [0.1.3](https://github.com/SolverForge/solverforge-bench/compare/v0.1.2...v0.1.3) (2026-10-11)


### Features

* **cvrp:** drop vroom and rustvrp from the default benchmark matrix 46fffcf
* **solvers:** add HiGHS adapters for CVRP, employee scheduling, and JSSP e35bdfa
* **solvers:** register highs in the employee and job-shop solver registries 21bc19c


### Bug Fixes

* **guardrails:** anchor the employee feasibility probe to the published tuples 2eb747d

## [0.1.2](https://github.com/SolverForge/solverforge-bench/compare/v0.1.1...v0.1.2) (2026-10-06)


### Features

* **bench:** make the published reference tuples runnable 7d8a336
* **bench:** pin the competition's validated INRC-II results b278a6f
* **employee:** grade the tuples the competition published results for d37aa42


### Bug Fixes

* **build:** keep the packaging discovery out of solver build trees 38cd823
* **cvrp:** adapt the pyvrp wrapper to the 0.14.0 API a3c634f
* **references:** keep the workbook importer consistent with the catalog f40ab98
* **references:** resolve employee catalog entries against the enumerable cases 1aec532
* **warehouse:** drop reference rows the catalogs no longer carry 38ccc9d

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
