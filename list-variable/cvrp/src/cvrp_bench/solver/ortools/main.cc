#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

#include "absl/base/log_severity.h"
#include "absl/log/globals.h"
#include "boost/json.hpp"
#include "boost/json/src.hpp"
#include "ortools/base/init_google.h"
#include "ortools/base/version.h"
#include "ortools/constraint_solver/constraint_solver.h"
#include "ortools/constraint_solver/routing.h"
#include "ortools/constraint_solver/routing_enums.pb.h"
#include "ortools/constraint_solver/routing_index_manager.h"
#include "ortools/constraint_solver/routing_parameters.h"

namespace json = boost::json;

namespace {

struct CvrpInstance {
  int64_t capacity;
  std::vector<int64_t> demand;
  std::vector<std::vector<int64_t>> edge_weight;
};

int64_t AsInt(const json::value& value) {
  if (value.is_int64()) {
    return value.as_int64();
  }
  if (value.is_uint64()) {
    return static_cast<int64_t>(value.as_uint64());
  }
  if (value.is_double()) {
    return static_cast<int64_t>(std::llround(value.as_double()));
  }
  throw std::runtime_error("expected numeric JSON value");
}

CvrpInstance ParseInput(const std::string& input) {
  const json::object root = json::parse(input).as_object();
  CvrpInstance instance;
  instance.capacity = AsInt(root.at("capacity"));

  for (const json::value& demand : root.at("demand").as_array()) {
    instance.demand.push_back(AsInt(demand));
  }
  for (const json::value& row_value : root.at("edge_weight").as_array()) {
    std::vector<int64_t> row;
    for (const json::value& distance : row_value.as_array()) {
      row.push_back(AsInt(distance));
    }
    instance.edge_weight.push_back(std::move(row));
  }

  if (instance.edge_weight.size() != instance.demand.size()) {
    throw std::runtime_error("edge_weight row count does not match demand size");
  }
  for (const std::vector<int64_t>& row : instance.edge_weight) {
    if (row.size() != instance.demand.size()) {
      throw std::runtime_error("edge_weight matrix must be square");
    }
  }
  return instance;
}

json::object Solve(const CvrpInstance& instance, int time_limit_seconds) {
  const int num_nodes = static_cast<int>(instance.demand.size());
  const int num_vehicles = num_nodes;
  const operations_research::RoutingIndexManager::NodeIndex depot{0};
  operations_research::RoutingIndexManager manager(num_nodes, num_vehicles, depot);
  operations_research::RoutingModel routing(manager);

  const int transit_callback_index = routing.RegisterTransitCallback(
      [&instance, &manager](int64_t from_index, int64_t to_index) -> int64_t {
        const int from_node = manager.IndexToNode(from_index).value();
        const int to_node = manager.IndexToNode(to_index).value();
        return instance.edge_weight[from_node][to_node];
      });
  routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index);

  const int demand_callback_index = routing.RegisterUnaryTransitCallback(
      [&instance, &manager](int64_t from_index) -> int64_t {
        const int from_node = manager.IndexToNode(from_index).value();
        return instance.demand[from_node];
      });
  routing.AddDimensionWithVehicleCapacity(
      demand_callback_index,
      int64_t{0},
      std::vector<int64_t>(num_vehicles, instance.capacity),
      true,
      "Capacity");

  operations_research::RoutingSearchParameters search_parameters =
      operations_research::DefaultRoutingSearchParameters();
  search_parameters.set_first_solution_strategy(
      operations_research::FirstSolutionStrategy::PATH_CHEAPEST_ARC);
  search_parameters.set_local_search_metaheuristic(
      operations_research::LocalSearchMetaheuristic::GUIDED_LOCAL_SEARCH);
  search_parameters.mutable_time_limit()->set_seconds(time_limit_seconds);

  const operations_research::Assignment* solution =
      routing.SolveWithParameters(search_parameters);
  if (solution == nullptr) {
    throw std::runtime_error("OR-Tools found no CVRP solution");
  }

  json::array routes;
  for (int vehicle_id = 0; vehicle_id < num_vehicles; ++vehicle_id) {
    if (!routing.IsVehicleUsed(*solution, vehicle_id)) {
      continue;
    }
    json::array route;
    int64_t index = routing.Start(vehicle_id);
    while (!routing.IsEnd(index)) {
      const int node_index = manager.IndexToNode(index).value();
      if (node_index != 0) {
        route.emplace_back(node_index);
      }
      index = solution->Value(routing.NextVar(index));
    }
    routes.emplace_back(std::move(route));
  }

  json::object output;
  output["cost"] = solution->ObjectiveValue();
  output["routes"] = std::move(routes);
  return output;
}

}  // namespace

int main(int argc, char* argv[]) {
  if (argc == 2 && std::string(argv[1]) == "--version") {
    std::cout << operations_research::OrToolsMajorVersion() << "."
              << operations_research::OrToolsMinorVersion() << "."
              << operations_research::OrToolsPatchVersion() << '\n';
    return EXIT_SUCCESS;
  }
  InitGoogle(argv[0], &argc, &argv, true);
  absl::SetStderrThreshold(absl::LogSeverityAtLeast::kError);

  try {
    if (argc != 2) {
      throw std::runtime_error("usage: cvrp_ortools <time_limit_seconds>");
    }
    const int time_limit_seconds = std::stoi(argv[1]);
    const std::string input((std::istreambuf_iterator<char>(std::cin)),
                            std::istreambuf_iterator<char>());
    const CvrpInstance instance = ParseInput(input);
    std::cout << json::serialize(Solve(instance, time_limit_seconds)) << '\n';
    return EXIT_SUCCESS;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return EXIT_FAILURE;
  }
}
