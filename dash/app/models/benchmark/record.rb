module Benchmark
  class Record < ActiveRecord::Base
    self.abstract_class = true

    establish_connection(
      if Rails.env.production?
        ENV.fetch("BENCH_DATABASE_URL")
      else
        ENV.fetch("BENCH_DATABASE_URL", "postgresql://postgres@localhost/solverforge_bench")
      end
    )

    def readonly?
      true
    end

    before_destroy do
      raise ActiveRecord::ReadOnlyRecord
    end
  end
end
