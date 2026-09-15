module Benchmark
  class Run < Record
    self.table_name = "benchmark_runs"
    self.primary_key = "id"

    has_many :results, class_name: "Benchmark::Result", foreign_key: :run_id, inverse_of: :run
    has_many :solver_versions, class_name: "Benchmark::SolverVersion", foreign_key: :run_id, inverse_of: :run

    scope :completed, -> { where(status: "completed") }
    scope :recent_first, -> { order(Arel.sql("completed_at DESC NULLS LAST"), created_at: :desc) }
  end
end
