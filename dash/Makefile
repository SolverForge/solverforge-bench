# SolverForge Dashboard Makefile
# Rails dashboard workflow for the benchmark warehouse.

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
APP_NAME := SolverForge Benchmark Dashboard
RAILS_VERSION := $(shell bin/rails -v 2>/dev/null | awk '{print $$2}')
RUBY_VERSION := $(shell ruby -e 'print RUBY_VERSION')

# ============== Runtime Configuration ==============
BIND_HOST ?= 127.0.0.1
PORT ?= 3001
RAILS_ENV ?= development
BENCH_DATABASE_URL ?= postgresql://postgres@localhost/solverforge_bench

BUNDLE ?= bundle
RAILS ?= bin/rails
RUBOCOP ?= bin/rubocop
BRAKEMAN ?= bin/brakeman
BUNDLER_AUDIT ?= bin/bundler-audit
IMPORTMAP ?= bin/importmap
PSQL ?= psql

# ============== Phony Targets ==============
.PHONY: \
	banner help version status setup install server dev console routes \
	db-prepare db-reset warehouse-check smoke test lint security audit ci-local \
	clean logs-clear tmp-clear

# ============== Default Target ==============
.DEFAULT_GOAL := help

# ============== Banner ==============
banner:
	@printf -- "$(EMERALD)$(BOLD)  ____        _                _____\n"
	@printf -- " / ___|  ___ | |_   _____ _ __|  ___|__  _ __ __ _  ___\n"
	@printf -- " \\___ \\\\ / _ \\\\| \\\\ \\\\ / / _ \\\\ '__| |_ / _ \\\\| '__/ _\` |/ _ \\\\\n"
	@printf -- "  ___) | (_) | |\\\\ V /  __/ |  |  _| (_) | | | (_| |  __/\n"
	@printf -- " |____/ \\\\___/|_| \\_/ \\___|_|  |_|  \\___/|_|  \\__, |\\___|\n"
	@printf -- "                                             |___/$(RESET)\n"
	@printf -- "  $(GRAY)Rails $(RAILS_VERSION) / Ruby $(RUBY_VERSION)$(RESET) $(EMERALD)Dashboard Build System$(RESET)\n\n"

help: banner
	@printf "$(CYAN)$(BOLD)Available targets$(RESET)\n"
	@printf "  $(YELLOW)setup$(RESET)             Install gems and prepare local Rails metadata DB\n"
	@printf "  $(YELLOW)server$(RESET)            Run Rails on $(BIND_HOST):$(PORT)\n"
	@printf "  $(YELLOW)test$(RESET)              Run Rails tests\n"
	@printf "  $(YELLOW)lint$(RESET)              Run RuboCop\n"
	@printf "  $(YELLOW)security$(RESET)          Run bundler-audit, importmap audit, and Brakeman\n"
	@printf "  $(YELLOW)ci-local$(RESET)          Run the Rails CI script from bin/ci\n"
	@printf "  $(YELLOW)warehouse-check$(RESET)   Check the PostgreSQL benchmark warehouse connection\n"
	@printf "  $(YELLOW)smoke$(RESET)             Load a dashboard snapshot against the warehouse\n"
	@printf "  $(YELLOW)db-prepare$(RESET)        Prepare the Rails metadata database\n"
	@printf "  $(YELLOW)db-reset$(RESET)          Reset the Rails metadata database\n"
	@printf "  $(YELLOW)console$(RESET)           Open Rails console\n"
	@printf "  $(YELLOW)routes$(RESET)            Print Rails routes\n"
	@printf "  $(YELLOW)clean$(RESET)             Clear Rails logs and temporary files\n\n"
	@printf "$(GRAY)Config: BIND_HOST=$(BIND_HOST) PORT=$(PORT) RAILS_ENV=$(RAILS_ENV) BENCH_DATABASE_URL=$(BENCH_DATABASE_URL)$(RESET)\n"

# ============== Project Info ==============
version: banner
	@printf "$(CYAN)Rails:$(RESET) $(YELLOW)$(RAILS_VERSION)$(RESET)\n"
	@printf "$(CYAN)Ruby:$(RESET)  $(YELLOW)$(RUBY_VERSION)$(RESET)\n"

status: banner
	@printf "$(PROGRESS) Checking bundle...\n"
	@$(BUNDLE) check && printf "$(GREEN)$(CHECK) Bundle complete$(RESET)\n" || (printf "$(RED)$(CROSS) Bundle incomplete$(RESET)\n" && exit 1)
	@printf "$(PROGRESS) Checking Rails executable...\n"
	@$(RAILS) -v
	@printf "$(PROGRESS) Checking warehouse URL...\n"
	@printf "$(GRAY)%s$(RESET)\n" "$(BENCH_DATABASE_URL)"

# ============== Setup & Development ==============
setup: banner
	@printf "$(ARROW) $(BOLD)Setting up dashboard dependencies and Rails metadata DB...$(RESET)\n"
	bin/setup --skip-server
	@printf "$(GREEN)$(CHECK) Setup complete$(RESET)\n"

install: banner
	@printf "$(ARROW) $(BOLD)Installing gems...$(RESET)\n"
	$(BUNDLE) install
	@printf "$(GREEN)$(CHECK) Gems installed$(RESET)\n"

server: banner
	@printf "$(ARROW) $(BOLD)Starting Rails server on http://$(BIND_HOST):$(PORT)$(RESET)\n"
	BENCH_DATABASE_URL="$(BENCH_DATABASE_URL)" RAILS_ENV="$(RAILS_ENV)" $(RAILS) server -b "$(BIND_HOST)" -p "$(PORT)"

dev: server

console: banner
	BENCH_DATABASE_URL="$(BENCH_DATABASE_URL)" RAILS_ENV="$(RAILS_ENV)" $(RAILS) console

routes: banner
	$(RAILS) routes

# ============== Rails Metadata Database ==============
db-prepare: banner
	@printf "$(ARROW) $(BOLD)Preparing Rails metadata database...$(RESET)\n"
	RAILS_ENV="$(RAILS_ENV)" $(RAILS) db:prepare
	@printf "$(GREEN)$(CHECK) Rails metadata database prepared$(RESET)\n"

db-reset: banner
	@printf "$(YELLOW)Resetting only the Rails metadata database, not the benchmark warehouse.$(RESET)\n"
	RAILS_ENV="$(RAILS_ENV)" $(RAILS) db:reset
	@printf "$(GREEN)$(CHECK) Rails metadata database reset$(RESET)\n"

# ============== Benchmark Warehouse ==============
warehouse-check: banner
	@printf "$(ARROW) $(BOLD)Checking benchmark warehouse connection...$(RESET)\n"
	$(PSQL) "$(BENCH_DATABASE_URL)" -c "select current_database(), count(*) as runs from benchmark_runs;"
	@printf "$(GREEN)$(CHECK) Benchmark warehouse reachable$(RESET)\n"

smoke: banner warehouse-check
	@printf "$(ARROW) $(BOLD)Loading dashboard snapshot...$(RESET)\n"
	@BENCH_DATABASE_URL="$(BENCH_DATABASE_URL)" RAILS_ENV="$(RAILS_ENV)" $(RAILS) runner 'snapshot = Benchmark::DashboardSnapshot.new({}); summary = snapshot.summary; puts "#{summary.benchmark_count.to_i} benchmarks, #{summary.solver_count.to_i} solvers, #{summary.instance_count.to_i} instances"'
	@printf "$(GREEN)$(CHECK) Dashboard snapshot loaded$(RESET)\n"

# ============== Tests & Checks ==============
test: banner
	@printf "$(ARROW) $(BOLD)Running Rails tests...$(RESET)\n"
	$(RAILS) test
	@printf "$(GREEN)$(CHECK) Rails tests passed$(RESET)\n"

lint: banner
	@printf "$(ARROW) $(BOLD)Running RuboCop...$(RESET)\n"
	$(RUBOCOP)
	@printf "$(GREEN)$(CHECK) RuboCop passed$(RESET)\n"

security: banner
	@printf "$(PROGRESS) Running bundler-audit...\n"
	$(BUNDLER_AUDIT)
	@printf "$(PROGRESS) Running importmap audit...\n"
	$(IMPORTMAP) audit
	@printf "$(PROGRESS) Running Brakeman...\n"
	$(BRAKEMAN) --quiet --no-pager --exit-on-warn --exit-on-error
	@printf "$(GREEN)$(CHECK) Security checks passed$(RESET)\n"

audit: security

ci-local: banner
	@printf "$(ARROW) $(BOLD)Running local CI...$(RESET)\n"
	bin/ci
	@printf "$(GREEN)$(CHECK) Local CI passed$(RESET)\n"

# ============== Maintenance ==============
logs-clear:
	$(RAILS) log:clear

tmp-clear:
	$(RAILS) tmp:clear

clean: banner logs-clear tmp-clear
	@printf "$(GREEN)$(CHECK) Rails logs and temporary files cleared$(RESET)\n"
