require "test_helper"

module Benchmark
  class SnapshotScopeTest < ActiveSupport::TestCase
    test "current facts use the warehouse current-snapshot view" do
      # This checks query construction without needing fixture rows in the
      # external warehouse. The view is responsible for selecting complete
      # runs as a unit, which is the invariant this dashboard must preserve.
      snapshot = DashboardSnapshot.allocate
      snapshot.define_singleton_method(:apply_filters) { |scope| scope }

      scope = snapshot.send(:filtered_latest)

      assert_equal "latest_benchmark_result_facts", scope.table_name
      assert_includes scope.to_sql, '"latest_benchmark_result_facts"'
    end

    test "recent runs are completed parents of the filtered historical facts" do
      # Recent Runs starts with result facts because the request can filter by
      # facts-only attributes such as solver, feasibility, and instance size.
      # The run query then remains efficient: PostgreSQL receives one `IN`
      # subquery instead of Rails materializing every matching run ID.
      snapshot = DashboardSnapshot.allocate
      snapshot.instance_variable_set(
        :@filtered_history,
        ResultFact.completed.where(solver: "solver-a")
      )

      scope = snapshot.send(:recent_runs_scope)
      sql = scope.to_sql

      assert_includes sql, '"benchmark_runs"."status" = \'completed\''
      assert_includes sql, '"benchmark_result_facts"."solver" = \'solver-a\''
      assert_match(/"benchmark_runs"\."id" IN \(SELECT DISTINCT "benchmark_result_facts"\."run_id"/, sql)
    end

    test "current solver summaries keep benchmark domains in their grouping" do
      snapshot = DashboardSnapshot.allocate
      snapshot.define_singleton_method(:apply_filters) { |scope| scope }

      sql = snapshot.send(:solver_summaries).to_sql

      assert_includes sql, '"latest_benchmark_result_facts"."benchmark_name"'
      assert_match(/GROUP BY .*"latest_benchmark_result_facts"\."benchmark_name".*"latest_benchmark_result_facts"\."solver"/, sql)
    end

    test "historical points keep benchmark domains in their grouping" do
      snapshot = DashboardSnapshot.allocate
      snapshot.define_singleton_method(:apply_filters) { |scope| scope }
      snapshot.define_singleton_method(:focus_time_limit) { 60 }

      sql = snapshot.send(:overtime_points).to_sql

      assert_match(/GROUP BY .*"benchmark_result_facts"\."benchmark_name".*"benchmark_result_facts"\."run_id"/, sql)
    end
  end
end
