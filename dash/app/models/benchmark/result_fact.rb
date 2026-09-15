module Benchmark
  class ResultFact < Record
    self.table_name = "benchmark_result_facts"

    # A result fact is one solver's outcome for one benchmark instance in one
    # run. This table is the complete history, so it is the source for charts
    # and activity that intentionally span several completed runs.
    scope :completed, -> { where(run_status: "completed") }
  end
end
