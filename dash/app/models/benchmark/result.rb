module Benchmark
  class Result < Record
    self.table_name = "benchmark_results"

    belongs_to :run, class_name: "Benchmark::Run", foreign_key: :run_id, inverse_of: :results
    belongs_to :solver_version,
      class_name: "Benchmark::SolverVersion",
      foreign_key: :solver_version_id,
      inverse_of: :results
  end
end
