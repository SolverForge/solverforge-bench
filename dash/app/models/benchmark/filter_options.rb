module Benchmark
  class FilterOptions
    attr_reader :run_kinds, :benchmark_names, :dataset_sets, :time_limits, :solvers, :size_bounds

    def self.load
      # Filter choices must come from the same current snapshot that the
      # dashboard displays. Otherwise a user could select a value that exists
      # only in old history and receive an apparently empty current dashboard.
      scope = LatestResultFact.completed

      new(
        run_kinds: scope.distinct.order(:run_kind).pluck(:run_kind),
        benchmark_names: scope.distinct.order(:benchmark_name).pluck(:benchmark_name),
        dataset_sets: scope.distinct.order(:dataset_set).pluck(:dataset_set),
        time_limits: scope.distinct.order(:time_limit_seconds).pluck(:time_limit_seconds),
        solvers: scope.distinct.order(:solver).pluck(:solver),
        size_bounds: scope.pick(Arel.sql("MIN(instance_size)"), Arel.sql("MAX(instance_size)"))
      )
    end

    def initialize(run_kinds:, benchmark_names:, dataset_sets:, time_limits:, solvers:, size_bounds:)
      @run_kinds = run_kinds
      @benchmark_names = benchmark_names
      @dataset_sets = dataset_sets
      @time_limits = time_limits
      @solvers = solvers
      @size_bounds = size_bounds || [ nil, nil ]
    end
  end
end
