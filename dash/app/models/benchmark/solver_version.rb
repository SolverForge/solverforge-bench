module Benchmark
  class SolverVersion < Record
    self.table_name = "benchmark_solver_versions"

    belongs_to :run, class_name: "Benchmark::Run", foreign_key: :run_id, inverse_of: :solver_versions
    has_many :results,
      class_name: "Benchmark::Result",
      foreign_key: :solver_version_id,
      inverse_of: :solver_version
  end
end
