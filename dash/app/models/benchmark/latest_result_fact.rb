module Benchmark
  class LatestResultFact < ResultFact
    # This warehouse-owned view joins result facts to `latest_benchmark_runs`.
    # Unlike picking the newest row for each solver/instance independently, it
    # only exposes rows from complete runs selected as a whole. Dashboard KPIs
    # and standings use it whenever they describe the dashboard's "current"
    # snapshot.
    self.table_name = "latest_benchmark_result_facts"
  end
end
