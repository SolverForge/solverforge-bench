module Benchmark
  class LatestRun < Record
    self.table_name = "latest_benchmark_runs"
    self.primary_key = "id"
  end
end
