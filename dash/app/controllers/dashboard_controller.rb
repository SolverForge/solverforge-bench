class DashboardController < ApplicationController
  def index
    @snapshot = Benchmark::DashboardSnapshot.new(params)
  rescue ActiveRecord::ActiveRecordError, PG::Error => error
    @dashboard_error = error
  end
end
