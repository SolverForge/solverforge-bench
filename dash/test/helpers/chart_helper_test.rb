require "test_helper"

class ChartHelperTest < ActionView::TestCase
  include ChartHelper

  Point = Struct.new(:avg_quality_ratio, :avg_cost, :result_count, :feasible_count)

  test "quality ratio charts do not fall back to incompatible cost values" do
    point = Point.new(nil, 42.0, 1, 1)

    assert_nil send(:metric_value, point, :quality_ratio)
    assert_equal 42.0, send(:metric_value, point, :cost)
  end

  test "quality ratio charts use the reference-relative value" do
    point = Point.new(1.08, 420.0, 1, 1)

    assert_equal 1.08, send(:metric_value, point, :quality_ratio)
  end
end
