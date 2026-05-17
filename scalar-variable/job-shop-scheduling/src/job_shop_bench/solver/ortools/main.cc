#include <algorithm>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <iterator>
#include <map>
#include <numeric>
#include <sstream>
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
#include "ortools/sat/cp_model.h"
#include "ortools/sat/cp_model.pb.h"
#include "ortools/sat/cp_model_solver.h"
#include "ortools/sat/model.h"
#include "ortools/sat/sat_parameters.pb.h"

namespace json = boost::json;
namespace sat = operations_research::sat;

namespace {

struct Operation {
  int job_id;
  int op_index;
  int machine_id;
  int duration;
};

struct OperationVars {
  sat::IntVar start;
  sat::IntVar end;
  sat::IntervalVar interval;
};

struct InstancePayload {
  int num_jobs;
  int num_machines;
  std::vector<Operation> operations;
};

int AsInt(const json::value& value) {
  if (value.is_int64()) {
    return static_cast<int>(value.as_int64());
  }
  if (value.is_uint64()) {
    return static_cast<int>(value.as_uint64());
  }
  throw std::runtime_error("expected integer JSON value");
}

const json::array& ArrayAt(const json::object& object, const char* key) {
  return object.at(key).as_array();
}

InstancePayload ParsePayload(const std::string& input) {
  const json::object root = json::parse(input).as_object();
  InstancePayload payload;
  payload.num_jobs = AsInt(root.at("num_jobs"));
  payload.num_machines = AsInt(root.at("num_machines"));
  for (const json::value& value : ArrayAt(root, "operations")) {
    const json::object op = value.as_object();
    payload.operations.push_back(Operation{
        .job_id = AsInt(op.at("job_id")),
        .op_index = AsInt(op.at("op_index")),
        .machine_id = AsInt(op.at("machine_id")),
        .duration = AsInt(op.at("duration")),
    });
  }
  return payload;
}

std::string OpName(const Operation& op) {
  return "j" + std::to_string(op.job_id) + "_o" + std::to_string(op.op_index);
}

json::object Solve(const InstancePayload& payload, double time_limit) {
  const int horizon = std::max(
      1, std::accumulate(payload.operations.begin(), payload.operations.end(), 0,
                         [](int total, const Operation& op) {
                           return total + op.duration;
                         }));

  sat::CpModelBuilder model;
  std::vector<OperationVars> vars;
  vars.reserve(payload.operations.size());
  std::map<std::pair<int, int>, int> by_job_step;
  std::vector<std::vector<sat::IntervalVar>> intervals_by_machine(
      payload.num_machines);
  std::vector<sat::IntVar> ends;
  ends.reserve(payload.operations.size());

  for (int idx = 0; idx < static_cast<int>(payload.operations.size()); ++idx) {
    const Operation& op = payload.operations[idx];
    if (op.machine_id < 0 || op.machine_id >= payload.num_machines) {
      throw std::runtime_error("operation machine id is out of range");
    }
    const std::string name = OpName(op);
    sat::IntVar start =
        model.NewIntVar(operations_research::Domain(0, horizon))
            .WithName(name + "_start");
    sat::IntVar end = model.NewIntVar(operations_research::Domain(0, horizon))
                          .WithName(name + "_end");
    sat::IntervalVar interval =
        model.NewIntervalVar(start, op.duration, end).WithName(name);
    vars.push_back(OperationVars{start, end, interval});
    by_job_step[{op.job_id, op.op_index}] = idx;
    intervals_by_machine[op.machine_id].push_back(interval);
    ends.push_back(end);
  }

  for (int job_id = 0; job_id < payload.num_jobs; ++job_id) {
    for (int op_index = 0;; ++op_index) {
      auto current = by_job_step.find({job_id, op_index});
      auto next = by_job_step.find({job_id, op_index + 1});
      if (current == by_job_step.end() || next == by_job_step.end()) {
        break;
      }
      model.AddGreaterOrEqual(vars[next->second].start, vars[current->second].end);
    }
  }

  for (const auto& machine_intervals : intervals_by_machine) {
    model.AddNoOverlap(machine_intervals);
  }

  sat::IntVar makespan =
      model.NewIntVar(operations_research::Domain(0, horizon)).WithName("makespan");
  model.AddMaxEquality(makespan, ends);
  model.Minimize(makespan);

  sat::Model solver_model;
  sat::SatParameters parameters;
  parameters.set_max_time_in_seconds(std::max(0.1, time_limit));
  parameters.set_num_search_workers(1);
  parameters.set_random_seed(1);
  parameters.set_log_search_progress(false);
  solver_model.Add(sat::NewSatParameters(parameters));

  const sat::CpSolverResponse response =
      sat::SolveCpModel(model.Build(), &solver_model);
  if (response.status() != sat::CpSolverStatus::OPTIMAL &&
      response.status() != sat::CpSolverStatus::FEASIBLE) {
    throw std::runtime_error("OR-Tools CP-SAT found no feasible solution");
  }

  json::array operations;
  for (int idx = 0; idx < static_cast<int>(payload.operations.size()); ++idx) {
    const Operation& op = payload.operations[idx];
    json::object out;
    out["job_id"] = op.job_id;
    out["op_index"] = op.op_index;
    out["machine_id"] = op.machine_id;
    out["start"] = static_cast<int>(sat::SolutionIntegerValue(response, vars[idx].start));
    out["duration"] = op.duration;
    operations.push_back(out);
  }

  json::object output;
  output["operations"] = operations;
  output["reported_makespan"] =
      static_cast<int>(sat::SolutionIntegerValue(response, makespan));
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
      throw std::runtime_error(
          "usage: job_shop_scheduling_ortools <time_limit_seconds>");
    }
    const double time_limit = std::stod(argv[1]);
    const std::string input((std::istreambuf_iterator<char>(std::cin)),
                            std::istreambuf_iterator<char>());
    std::cout << json::serialize(Solve(ParsePayload(input), time_limit)) << '\n';
    return EXIT_SUCCESS;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return EXIT_FAILURE;
  }
}
