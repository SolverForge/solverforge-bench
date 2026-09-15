require "test_helper"

class DashboardControllerTest < ActionDispatch::IntegrationTest
  test "renders the results dashboard" do
    get root_url

    assert_response :success
    assert_select "h1", "Benchmarks"
  end
end
