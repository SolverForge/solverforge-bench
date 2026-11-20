#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <utility>
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

// Mirrors the SolverForge and Timefold models: an unplaced delivery costs this
// much, so the search only drops a stop it cannot fit anywhere. Any dropped
// stop makes the plan a failed invocation in the Python wrapper.
constexpr int64_t UNASSIGNED_DELIVERY_HARD = 1'000'000;

// Node 0 is the depot; delivery i is node i + 1.
struct DeliveryInstance {
  double speed_mps;
  int64_t departure_time;
  int vehicle_count;
  int64_t capacity;
  std::vector<int64_t> xs;
  std::vector<int64_t> ys;
  std::vector<int64_t> demands;
  std::vector<int64_t> min_starts;
  std::vector<int64_t> max_ends;
  std::vector<int64_t> services;
};

int64_t AsInt(const json::value& value) {
  if (value.is_int64()) {
    return value.as_int64();
  }
  if (value.is_uint64()) {
    return static_cast<int64_t>(value.as_uint64());
  }
  throw std::runtime_error("expected integer JSON value");
}

double AsDouble(const json::value& value) {
  if (value.is_double()) {
    return value.as_double();
  }
  return static_cast<double>(AsInt(value));
}

std::vector<int64_t> IntArray(const json::object& root, const char* key) {
  std::vector<int64_t> values;
  for (const json::value& value : root.at(key).as_array()) {
    values.push_back(AsInt(value));
  }
  return values;
}

DeliveryInstance ParseInput(const std::string& input) {
  const json::object root = json::parse(input).as_object();
  DeliveryInstance instance;
  instance.speed_mps = AsDouble(root.at("speed_mps"));
  instance.departure_time = AsInt(root.at("departure_time"));
  instance.vehicle_count = static_cast<int>(AsInt(root.at("vehicle_count")));
  instance.capacity = AsInt(root.at("capacity"));
  const json::array& depot = root.at("depot").as_array();
  instance.xs.push_back(AsInt(depot.at(0)));
  instance.ys.push_back(AsInt(depot.at(1)));
  instance.demands.push_back(0);
  instance.min_starts.push_back(0);
  instance.max_ends.push_back(0);
  instance.services.push_back(0);
  const std::pair<const char*, std::vector<int64_t>*> columns[] = {
      {"xs", &instance.xs},
      {"ys", &instance.ys},
      {"demands", &instance.demands},
      {"min_starts", &instance.min_starts},
      {"max_ends", &instance.max_ends},
      {"services", &instance.services},
  };
  for (const auto& [key, target] : columns) {
    const std::vector<int64_t> values = IntArray(root, key);
    target->insert(target->end(), values.begin(), values.end());
  }
  const size_t nodes = instance.xs.size();
  for (const std::vector<int64_t>* column :
       {&instance.ys, &instance.demands, &instance.min_starts, &instance.max_ends,
        &instance.services}) {
    if (column->size() != nodes) {
      throw std::runtime_error("delivery columns differ in length");
    }
  }
  if (instance.vehicle_count < 1) {
    throw std::runtime_error("vehicle_count must be positive");
  }
  return instance;
}

// The validator's rule: Euclidean metres over speed_mps, rounded half up.
int64_t TravelSeconds(const DeliveryInstance& instance, int from, int to) {
  const int64_t dx = instance.xs[from] - instance.xs[to];
  const int64_t dy = instance.ys[from] - instance.ys[to];
  return static_cast<int64_t>(std::floor(std::sqrt(static_cast<double>(dx * dx + dy * dy)) / instance.speed_mps + 0.5));
}

json::object FairStartWitness() {
  json::object witness;
  witness["routing_assignment_hint_present"] = false;
  witness["adapter_hint_count"] = 0;
  witness["preliminary_solve_count"] = 0;
  witness["fallback_solution_enabled"] = false;
  witness["preassigned_scalar_variables"] = 0;
  witness["prefilled_list_variables"] = 0;
  return witness;
}

json::object Solve(const DeliveryInstance& instance, int time_limit_seconds) {
  const int num_nodes = static_cast<int>(instance.xs.size());
  const int num_vehicles = instance.vehicle_count;
  const operations_research::RoutingIndexManager::NodeIndex depot{0};
  operations_research::RoutingIndexManager manager(num_nodes, num_vehicles, depot);
  operations_research::RoutingModel routing(manager);

  const int travel_callback_index = routing.RegisterTransitCallback(
      [&instance, &manager](int64_t from_index, int64_t to_index) -> int64_t {
        return TravelSeconds(instance, manager.IndexToNode(from_index).value(),
                             manager.IndexToNode(to_index).value());
      });
  routing.SetArcCostEvaluatorOfAllVehicles(travel_callback_index);

  const int demand_callback_index = routing.RegisterUnaryTransitCallback(
      [&instance, &manager](int64_t from_index) -> int64_t {
        return instance.demands[manager.IndexToNode(from_index).value()];
      });
  routing.AddDimensionWithVehicleCapacity(
      demand_callback_index, int64_t{0},
      std::vector<int64_t>(num_vehicles, instance.capacity), true, "Capacity");

  // Cumul at a delivery is its service start: travel plus the service at the
  // node being left, with slack absorbing any wait for min_start.
  const int time_callback_index = routing.RegisterTransitCallback(
      [&instance, &manager](int64_t from_index, int64_t to_index) -> int64_t {
        const int from_node = manager.IndexToNode(from_index).value();
        return instance.services[from_node] +
               TravelSeconds(instance, from_node, manager.IndexToNode(to_index).value());
      });
  int64_t horizon = instance.departure_time;
  for (int node = 1; node < num_nodes; ++node) {
    horizon = std::max(horizon, instance.max_ends[node] + TravelSeconds(instance, node, 0));
  }
  routing.AddDimension(time_callback_index, horizon, horizon, false, "Time");
  const operations_research::RoutingDimension& time = routing.GetDimensionOrDie("Time");
  for (int node = 1; node < num_nodes; ++node) {
    const int64_t index = manager.NodeToIndex(operations_research::RoutingIndexManager::NodeIndex{node});
    // Service must end by max_end, so it must start by max_end - service.
    time.CumulVar(index)->SetRange(instance.min_starts[node],
                                   instance.max_ends[node] - instance.services[node]);
    routing.AddDisjunction({index}, UNASSIGNED_DELIVERY_HARD);
  }
  for (int vehicle = 0; vehicle < num_vehicles; ++vehicle) {
    time.CumulVar(routing.Start(vehicle))
        ->SetRange(instance.departure_time, instance.departure_time);
  }

  operations_research::RoutingSearchParameters search_parameters =
      operations_research::DefaultRoutingSearchParameters();
  // OR-Tools' insertion construction for time-window routing; path-cheapest-arc
  // strands stops it cannot place on a fixed fleet with tight windows.
  search_parameters.set_first_solution_strategy(
      operations_research::FirstSolutionStrategy::PARALLEL_CHEAPEST_INSERTION);
  search_parameters.set_local_search_metaheuristic(
      operations_research::LocalSearchMetaheuristic::GUIDED_LOCAL_SEARCH);
  search_parameters.mutable_time_limit()->set_seconds(time_limit_seconds);

  const json::object fair_start_witness = FairStartWitness();
  const operations_research::Assignment* solution =
      routing.SolveWithParameters(search_parameters);
  if (solution == nullptr) {
    throw std::runtime_error("OR-Tools found no delivery-scale solution");
  }

  json::array routes;
  int64_t fresh_cost = 0;
  for (int vehicle_id = 0; vehicle_id < num_vehicles; ++vehicle_id) {
    if (!routing.IsVehicleUsed(*solution, vehicle_id)) {
      continue;
    }
    json::array route;
    int previous = 0;
    int64_t index = solution->Value(routing.NextVar(routing.Start(vehicle_id)));
    while (!routing.IsEnd(index)) {
      const int node = manager.IndexToNode(index).value();
      route.emplace_back(node - 1);
      fresh_cost += TravelSeconds(instance, previous, node);
      previous = node;
      index = solution->Value(routing.NextVar(index));
    }
    fresh_cost += TravelSeconds(instance, previous, 0);
    routes.emplace_back(std::move(route));
  }

  json::object output;
  output["routes"] = std::move(routes);
  output["reported_cost"] = solution->ObjectiveValue();
  output["fresh_cost"] = fresh_cost;
  output["fair_start_witness"] = fair_start_witness;
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
      throw std::runtime_error("usage: delivery_scale_ortools <time_limit_seconds>");
    }
    const int time_limit_seconds = std::stoi(argv[1]);
    const std::string input((std::istreambuf_iterator<char>(std::cin)),
                            std::istreambuf_iterator<char>());
    const DeliveryInstance instance = ParseInput(input);
    std::cout << json::serialize(Solve(instance, time_limit_seconds)) << '\n';
    return EXIT_SUCCESS;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return EXIT_FAILURE;
  }
}
