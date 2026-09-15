module Benchmark
  class DashboardSnapshot
    CompetitionCard = Data.define(:label, :value, :note, :solver)
    MetricProfile = Data.define(:benchmark_name, :label, :description, :metric)
    RecentRunsPage = Data.define(:entries, :current_page, :per_page, :total_count) do
      def total_pages
        [ (total_count.to_f / per_page).ceil, 1 ].max
      end

      def first_item
        return 0 if total_count.zero?

        ((current_page - 1) * per_page) + 1
      end

      def last_item
        [ first_item + entries.size - 1, total_count ].min
      end

      def summary_label
        return "0 runs" if total_count.zero?

        "#{first_item}-#{last_item} of #{total_count} runs"
      end

      def previous_page
        current_page - 1 if current_page > 1
      end

      def next_page
        current_page + 1 if current_page < total_pages
      end
    end

    RECENT_RUNS_PER_PAGE = 8
    METRIC_PROFILES = {
      "cvrp" => [ "Cost / reference", "CVRPLIB reference cost ratio", :quality_ratio ],
      "employee-scheduling" => [ "Validator cost", "No exact official reference in this corpus", :cost ],
      "job-shop-scheduling" => [ "Makespan / reference", "Official JSPLIB best-known reference ratio", :quality_ratio ]
    }.freeze

    attr_reader :options, :filters

    def initialize(params)
      @params = params
      @options = FilterOptions.load
      @filters = DashboardFilters.new(params, options)
    end

    def summary
      @summary ||= filtered_latest.select(
        "COUNT(*) AS result_count",
        "COUNT(DISTINCT run_id) AS run_count",
        "COUNT(DISTINCT benchmark_name) AS benchmark_count",
        "COUNT(DISTINCT solver) AS solver_count",
        "COUNT(DISTINCT instance) AS instance_count",
        "COUNT(*) FILTER (WHERE hard_feasible IS TRUE) AS feasible_count",
        "COUNT(*) FILTER (WHERE NULLIF(run_error, '') IS NOT NULL OR NULLIF(validation_error, '') IS NOT NULL) AS error_count"
      ).take
    end

    def competition_cards
      @competition_cards ||= begin
        leader, runner_up = standings.first(2)
        clean_solvers = standings.count { |row| row.ranked_rows.to_i.positive? && row.feasible_count.to_i == row.ranked_rows.to_i }

        [
          CompetitionCard.new(
            label: "Top solver",
            value: leader ? leader.solver : "n/a",
            note: leader ? "#{leader.feasible_count.to_i} feasible · #{leader.wins.to_i} top results" : "No scored results",
            solver: leader&.solver
          ),
          CompetitionCard.new(
            label: "Cases scored",
            value: whole_count(race_count),
            note: "#{whole_count(summary.result_count)} solver entries in this slice",
            solver: nil
          ),
          CompetitionCard.new(
            label: "Next solver",
            value: runner_up ? runner_up.solver : "n/a",
            note: runner_up ? "#{runner_up.feasible_count.to_i} feasible · #{runner_up.wins.to_i} top results" : "No second solver",
            solver: runner_up&.solver
          ),
          CompetitionCard.new(
            label: "Full feasibility",
            value: clean_solvers.to_s,
            note: "Solvers hard-feasible on every scored entry",
            solver: nil
          )
        ]
      end
    end

    def solver_summaries
      @solver_summaries ||= filtered_latest
        .select(
          "benchmark_name",
          "solver",
          "COUNT(*) AS result_count",
          "COUNT(*) FILTER (WHERE hard_feasible IS TRUE) AS feasible_count",
          "COUNT(*) FILTER (WHERE NULLIF(run_error, '') IS NOT NULL OR NULLIF(validation_error, '') IS NOT NULL) AS error_count",
          "AVG(cost) AS avg_cost",
          "AVG(quality_ratio) AS avg_quality_ratio",
          "AVG(actual_time_seconds) AS avg_actual_time_seconds"
        )
        .group(:benchmark_name, :solver)
        .order(:benchmark_name, :solver)
    end

    def solver_summaries_by_benchmark
      @solver_summaries_by_benchmark ||= solver_summaries.group_by(&:benchmark_name)
    end

    def metric_profiles
      @metric_profiles ||= solver_summaries_by_benchmark.keys.sort.map do |benchmark_name|
        label, description, metric = METRIC_PROFILES.fetch(
          benchmark_name,
          [ "Cost", "Benchmark cost; no configured reference metric", :cost ]
        )
        MetricProfile.new(benchmark_name, label, description, metric)
      end
    end

    def quality_metric_value(row, benchmark_name)
      metric_profile(benchmark_name).metric == :cost ? row.avg_cost : row.avg_quality_ratio
    end

    def standings
      @standings ||= ranked_results
        .select(
          "solver",
          "COUNT(*) AS ranked_rows",
          "COUNT(*) FILTER (WHERE solver_rank = 1) AS wins",
          "COUNT(*) FILTER (WHERE solver_rank <= 3) AS podiums",
          "COUNT(*) FILTER (WHERE hard_feasible IS TRUE) AS feasible_count",
          "AVG(solver_rank) AS avg_rank",
          "AVG(quality_ratio) AS avg_quality_ratio",
          "AVG(actual_time_seconds) AS avg_actual_time_seconds"
        )
        .group(:solver)
        .order(Arel.sql("COUNT(*) FILTER (WHERE hard_feasible IS TRUE) DESC"), Arel.sql("COUNT(*) FILTER (WHERE solver_rank = 1) DESC"), Arel.sql("AVG(solver_rank) ASC"), :solver)
    end

    def time_limit_summaries
      @time_limit_summaries ||= filtered_latest
        .select(
          "solver",
          "time_limit_seconds",
          "COUNT(*) AS result_count",
          "COUNT(*) FILTER (WHERE hard_feasible IS TRUE) AS feasible_count",
          "AVG(cost) AS avg_cost",
          "AVG(quality_ratio) AS avg_quality_ratio",
          "AVG(actual_time_seconds) AS avg_actual_time_seconds"
        )
        .group(:solver, :time_limit_seconds)
        .order(:time_limit_seconds, :solver)
    end

    def leaderboard
      @leaderboard ||= ranked_results
        .select(
          "solver",
          "time_limit_seconds",
          "COUNT(*) AS ranked_rows",
          "COUNT(*) FILTER (WHERE hard_feasible IS TRUE) AS feasible_count",
          "COUNT(*) FILTER (WHERE solver_rank = 1) AS wins",
          "COUNT(*) FILTER (WHERE solver_rank <= 3) AS podiums",
          "AVG(solver_rank) AS avg_rank"
        )
        .group(:solver, :time_limit_seconds)
        .order(:time_limit_seconds, Arel.sql("COUNT(*) FILTER (WHERE hard_feasible IS TRUE) DESC"), Arel.sql("COUNT(*) FILTER (WHERE solver_rank = 1) DESC"), Arel.sql("AVG(solver_rank) ASC"), :solver)
    end

    def overtime_points
      @overtime_points ||= filtered_history
        .where(time_limit_seconds: focus_time_limit)
        .where.not(run_completed_at: nil)
        .select(
          "benchmark_name",
          "run_id",
          "run_completed_at AS occurred_at",
          "solver",
          "COUNT(*) AS result_count",
          "COUNT(*) FILTER (WHERE hard_feasible IS TRUE) AS feasible_count",
          "AVG(cost) AS avg_cost",
          "AVG(quality_ratio) AS avg_quality_ratio"
        )
        .group(:benchmark_name, :run_id, :run_completed_at, :solver)
        .order(:benchmark_name, :run_completed_at, :solver)
    end

    def overtime_points_by_benchmark
      @overtime_points_by_benchmark ||= overtime_points.to_a.group_by(&:benchmark_name)
    end

    def recent_runs
      recent_runs_page.entries
    end

    def recent_runs_page
      @recent_runs_page ||= begin
        total_count = recent_runs_scope.count
        total_pages = [ (total_count.to_f / RECENT_RUNS_PER_PAGE).ceil, 1 ].max
        current_page = [ requested_recent_runs_page, total_pages ].min
        entries = recent_runs_scope
          .limit(RECENT_RUNS_PER_PAGE)
          .offset((current_page - 1) * RECENT_RUNS_PER_PAGE)

        RecentRunsPage.new(
          entries: entries,
          current_page: current_page,
          per_page: RECENT_RUNS_PER_PAGE,
          total_count: total_count
        )
      end
    end

    def solver_versions
      @solver_versions ||= filtered_latest
        .where("NULLIF(solver_version, '') IS NOT NULL")
        .select(
          "solver",
          "solver_version",
          "MIN(solver_version_source) AS version_source",
          "COUNT(DISTINCT run_id) AS run_count",
          "COUNT(DISTINCT solver_version_source) AS source_count"
        )
        .group(:solver, :solver_version)
        .order(:solver, :solver_version)
    end

    def focus_time_limit
      return filters.time_limit_value unless filters.all_time_limits?

      options.time_limits.max
    end

    def race_count
      @race_count ||= filtered_latest.pick(
        Arel.sql("COUNT(DISTINCT (benchmark_name, dataset_set, instance, time_limit_seconds))")
      ).to_i
    end

    private

    def filtered_latest
      # "Current" is defined by the warehouse view, not by a Ruby query that
      # chooses the latest row for every individual solver and instance. The
      # latter can blend a partial new run with rows from an older run, which
      # makes one set of standings describe several incompatible snapshots.
      @filtered_latest ||= apply_filters(LatestResultFact.completed)
    end

    def filtered_history
      # Historical panels deliberately use the full completed fact history.
      # Applying the same request filters here lets the activity panel describe
      # precisely the slice selected in the rest of the dashboard.
      @filtered_history ||= apply_filters(ResultFact.completed)
    end

    def recent_runs_scope
      # Runs do not have every filterable result attribute (such as solver or
      # instance size). First find matching completed facts, then use their
      # run IDs to select the parent runs. SQL `IN (subquery)` avoids loading
      # the IDs into Ruby and keeps the count and paginated entries consistent.
      @recent_runs_scope ||= Run.completed
        .where(id: filtered_history.select(:run_id).distinct)
        .recent_first
    end

    def requested_recent_runs_page
      [ Integer(@params[:recent_runs_page], exception: false).to_i, 1 ].max
    end

    def ranked_results
      @ranked_results ||= begin
        ranked_sql = filtered_latest
          .select(
            "solver",
            "time_limit_seconds",
            "hard_feasible",
            "quality_ratio",
            "actual_time_seconds",
            "DENSE_RANK() OVER (" \
              "PARTITION BY benchmark_name, dataset_set, instance, time_limit_seconds " \
              "ORDER BY CASE WHEN hard_feasible IS TRUE THEN 0 ELSE 1 END, cost ASC NULLS LAST" \
            ") AS solver_rank"
          )
          .to_sql

        ResultFact.from("(#{ranked_sql}) benchmark_result_facts")
      end
    end

    def metric_profile(benchmark_name)
      metric_profiles.find { |profile| profile.benchmark_name == benchmark_name } ||
        MetricProfile.new(benchmark_name, "Cost", "Benchmark cost; no configured reference metric", :cost)
    end

    def apply_filters(scope)
      scope = scope.where(run_kind: filters.run_kind) unless filters.run_kind == DashboardFilters::ALL
      scope = scope.where(benchmark_name: filters.benchmark_name) unless filters.benchmark_name == DashboardFilters::ALL
      scope = scope.where(dataset_set: filters.dataset_set) unless filters.dataset_set == DashboardFilters::ALL
      scope = scope.where(time_limit_seconds: filters.time_limit_value) unless filters.all_time_limits?
      scope = scope.where(solver: filters.solver) unless filters.all_solvers?
      scope = apply_feasibility_filter(scope)
      scope = scope.where("instance ILIKE ?", "%#{filters.instance_query}%") if filters.instance_query.present?
      scope = scope.where("instance_size >= ?", filters.min_instance_size) if filters.min_instance_size
      scope = scope.where("instance_size <= ?", filters.max_instance_size) if filters.max_instance_size
      scope
    end

    def apply_feasibility_filter(scope)
      case filters.feasibility
      when "feasible"
        scope.where(hard_feasible: true)
      when "infeasible"
        scope.where("hard_feasible IS NOT TRUE")
      when "errors"
        scope.where("NULLIF(run_error, '') IS NOT NULL OR NULLIF(validation_error, '') IS NOT NULL")
      else
        scope
      end
    end

    def format_rank(value)
      format("%.2f", value.to_f)
    end

    def whole_count(value)
      value.to_i.to_fs(:delimited)
    end
  end
end
