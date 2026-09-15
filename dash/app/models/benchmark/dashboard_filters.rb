module Benchmark
  class DashboardFilters
    ALL = "all"
    FEASIBILITY_STATES = %w[all feasible infeasible errors].freeze

    attr_reader :run_kind,
      :benchmark_name,
      :dataset_set,
      :time_limit_seconds,
      :solver,
      :feasibility,
      :instance_query,
      :min_instance_size,
      :max_instance_size

    def initialize(params, options)
      @run_kind = pick(params[:run_kind], options.run_kinds, default: default_run_kind(options.run_kinds))
      @benchmark_name = pick(params[:benchmark_name], options.benchmark_names, default: ALL)
      @dataset_set = pick(params[:dataset_set], options.dataset_sets, default: ALL)
      @time_limit_seconds = pick(params[:time_limit_seconds], options.time_limits.map(&:to_s), default: ALL)
      @solver = pick(params[:solver], options.solvers, default: ALL)
      @feasibility = pick(params[:feasibility], FEASIBILITY_STATES, default: ALL)
      @instance_query = params[:instance_query].to_s.strip
      @min_instance_size = integer_param(params[:min_instance_size])
      @max_instance_size = integer_param(params[:max_instance_size])
    end

    def all_time_limits?
      time_limit_seconds == ALL
    end

    def all_solvers?
      solver == ALL
    end

    def all_feasibility?
      feasibility == ALL
    end

    def time_limit_value
      return if all_time_limits?

      time_limit_seconds.to_i
    end

    def to_query
      {
        run_kind: run_kind,
        benchmark_name: benchmark_name,
        dataset_set: dataset_set,
        time_limit_seconds: time_limit_seconds,
        solver: solver,
        feasibility: feasibility,
        instance_query: instance_query,
        min_instance_size: min_instance_size,
        max_instance_size: max_instance_size
      }
    end

    private

    def pick(value, allowed, default:)
      candidate = value.presence || default
      return candidate if candidate == ALL || allowed.include?(candidate)

      default
    end

    def default_run_kind(run_kinds)
      return "candidate" if run_kinds.include?("candidate")

      run_kinds.first || ALL
    end

    def integer_param(value)
      return if value.blank?

      Integer(value, exception: false)
    end
  end
end
