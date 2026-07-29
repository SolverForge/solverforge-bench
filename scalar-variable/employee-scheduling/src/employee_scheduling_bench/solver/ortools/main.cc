#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <iterator>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
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
#include "ortools/util/sorted_interval_list.h"

namespace json = boost::json;
namespace sat = operations_research::sat;

namespace {

constexpr int64_t kAnyShiftType = std::numeric_limits<int64_t>::max();
constexpr const char *kDays[] = {"Mon", "Tue", "Wed", "Thu",
                                 "Fri", "Sat", "Sun"};

struct Nurse {
  int contract_idx;
  std::set<int> skills;
};

struct Contract {
  int min_assignments;
  int max_assignments;
  int min_consecutive_working;
  int max_consecutive_working;
  int min_consecutive_off;
  int max_consecutive_off;
  int max_working_weekends;
  bool complete_weekends;
};

struct ShiftType {
  int min_consecutive;
  int max_consecutive;
};

struct Shift {
  int week;
  int day;
  int shift_type_idx;
  int skill_idx;
  bool is_minimum;
};

struct NurseHistory {
  int nurse_idx;
  int num_assignments;
  int num_working_weekends;
  int last_shift_type_idx;
  int num_consecutive_assignments;
  int num_consecutive_working;
  int num_consecutive_off;
};

struct ShiftOffRequest {
  int nurse_idx;
  int global_day;
  int64_t shift_type_idx;
};

struct InstancePayload {
  std::vector<Nurse> nurses;
  std::vector<Contract> contracts;
  std::vector<ShiftType> shift_types;
  std::unordered_map<int, std::set<int>> forbidden_successors;
  std::vector<ShiftOffRequest> shift_off_requests;
  std::vector<NurseHistory> histories;
  std::vector<Shift> shifts;
  int num_weeks;
  std::vector<std::string> skill_names;
  std::vector<std::string> shift_type_names;
  std::vector<std::string> nurse_names;
};

struct AssignmentVar {
  int coverage_idx;
  int nurse_idx;
  sat::BoolVar var;
};

struct CoverageRequirement {
  int week;
  int day;
  int shift_type_idx;
  int skill_idx;
  int minimum;
  int optimal;
};

struct SolveResult {
  json::object output;
  bool feasible;
};

int64_t AsInt(const json::value &value) {
  if (value.is_int64()) {
    return value.as_int64();
  }
  if (value.is_uint64()) {
    return static_cast<int64_t>(value.as_uint64());
  }
  throw std::runtime_error("expected integer JSON value");
}

bool AsBool(const json::value &value) {
  if (value.is_bool()) {
    return value.as_bool();
  }
  return AsInt(value) != 0;
}

std::string AsString(const json::value &value) {
  return std::string(value.as_string().c_str());
}

const json::array &ArrayAt(const json::object &object, const char *key) {
  return object.at(key).as_array();
}

int GlobalDay(int week, int day) { return week * 7 + day; }

int64_t Key(int coverage_idx, int nurse_idx, int num_nurses) {
  return static_cast<int64_t>(coverage_idx) * num_nurses + nurse_idx;
}

int KeyCoverage(int64_t key, int num_nurses) {
  return static_cast<int>(key / num_nurses);
}

int KeyNurse(int64_t key, int num_nurses) {
  return static_cast<int>(key % num_nurses);
}

sat::LinearExpr BoolSum(const std::vector<sat::BoolVar> &vars) {
  if (vars.empty()) {
    return sat::LinearExpr(0);
  }
  return sat::LinearExpr::Sum(vars);
}

sat::LinearExpr IntSum(const std::vector<sat::IntVar> &vars) {
  if (vars.empty()) {
    return sat::LinearExpr(0);
  }
  return sat::LinearExpr::Sum(vars);
}

json::object FairStartWitness(const sat::CpModelProto &proto) {
  json::object witness;
  witness["cp_sat_solution_hint_vars"] = proto.solution_hint().vars_size();
  witness["cp_sat_solution_hint_values"] = proto.solution_hint().values_size();
  witness["adapter_hint_count"] = 0;
  witness["preliminary_solve_count"] = 0;
  witness["fallback_solution_enabled"] = false;
  witness["preassigned_scalar_variables"] = 0;
  witness["prefilled_list_variables"] = 0;
  return witness;
}

void AddObjectiveTerm(sat::LinearExpr *objective, sat::BoolVar var,
                      int64_t weight) {
  *objective += sat::LinearExpr::Term(var, weight);
}

void AddObjectiveTerm(sat::LinearExpr *objective, sat::IntVar var,
                      int64_t weight) {
  *objective += sat::LinearExpr::Term(var, weight);
}

int ClosedBoundsCost(int length, int min_length, int max_length, int weight) {
  if (length == 0) {
    return 0;
  }
  int cost = 0;
  if (length < min_length) {
    cost += weight * (min_length - length);
  }
  if (length > max_length) {
    cost += weight * (length - max_length);
  }
  return cost;
}

int MaxBoundCost(int length, int max_length, int weight) {
  if (length > max_length) {
    return weight * (length - max_length);
  }
  return 0;
}

sat::BoolVar AndLiteral(sat::CpModelBuilder *model,
                        const std::vector<sat::BoolVar> &literals,
                        const std::string &name) {
  sat::BoolVar combined = model->NewBoolVar().WithName(name);
  std::vector<sat::BoolVar> clauses;
  clauses.reserve(literals.size() + 1);
  for (sat::BoolVar literal : literals) {
    model->AddImplication(combined, literal);
    clauses.push_back(literal.Not());
  }
  clauses.push_back(combined);
  model->AddBoolOr(clauses);
  return combined;
}

void AddRunLengthCosts(sat::CpModelBuilder *model,
                       const std::vector<sat::BoolVar> &active_by_day,
                       bool history_active, int history_length, int min_length,
                       int max_length, int weight, const std::string &name,
                       sat::LinearExpr *objective) {
  if (active_by_day.empty()) {
    return;
  }

  const int max_possible_length =
      static_cast<int>(active_by_day.size()) + std::max(0, history_length);
  int64_t max_closed_cost = 0;
  int64_t max_end_cost = 0;
  for (int length = 0; length <= max_possible_length; ++length) {
    max_closed_cost = std::max<int64_t>(
        max_closed_cost,
        std::max<int64_t>(0,
                          std::max<int64_t>((min_length - length) * weight,
                                            (length - max_length) * weight)));
    max_end_cost = std::max<int64_t>(max_end_cost,
                                     MaxBoundCost(length, max_length, weight));
  }

  std::vector<sat::IntVar> run_lengths;
  run_lengths.reserve(active_by_day.size());
  for (int day = 0; day < static_cast<int>(active_by_day.size()); ++day) {
    sat::IntVar run_length =
        model->NewIntVar(operations_research::Domain(0, max_possible_length))
            .WithName(name + "_run_len_d" + std::to_string(day));
    sat::BoolVar active = active_by_day[day];
    if (day == 0) {
      const int active_length = history_active ? history_length + 1 : 1;
      model->AddEquality(run_length, active_length).OnlyEnforceIf(active);
      model->AddEquality(run_length, 0).OnlyEnforceIf(active.Not());
    } else {
      sat::BoolVar previous_active = active_by_day[day - 1];
      sat::IntVar previous_run_length = run_lengths.back();
      model->AddEquality(run_length, 0).OnlyEnforceIf(active.Not());
      {
        std::vector<sat::BoolVar> enforcement = {active, previous_active.Not()};
        model->AddEquality(run_length, 1).OnlyEnforceIf(enforcement);
      }
      {
        std::vector<sat::BoolVar> enforcement = {active, previous_active};
        model->AddEquality(run_length, previous_run_length + 1)
            .OnlyEnforceIf(enforcement);
      }
    }
    run_lengths.push_back(run_length);
  }

  if (history_active && history_length > 0) {
    const int immediate_cost =
        ClosedBoundsCost(history_length, min_length, max_length, weight);
    if (immediate_cost != 0) {
      AddObjectiveTerm(objective, active_by_day[0].Not(), immediate_cost);
    }
  }

  for (int day = 1; day < static_cast<int>(active_by_day.size()); ++day) {
    sat::BoolVar closes =
        AndLiteral(model, {active_by_day[day - 1], active_by_day[day].Not()},
                   name + "_closes_before_d" + std::to_string(day));
    sat::IntVar penalty =
        model->NewIntVar(operations_research::Domain(0, max_closed_cost))
            .WithName(name + "_closed_penalty_d" + std::to_string(day));
    sat::LinearExpr under_minimum(min_length * weight);
    under_minimum += sat::LinearExpr::Term(run_lengths[day - 1], -weight);
    sat::LinearExpr over_maximum(-max_length * weight);
    over_maximum += sat::LinearExpr::Term(run_lengths[day - 1], weight);
    model->AddGreaterOrEqual(penalty, under_minimum).OnlyEnforceIf(closes);
    model->AddGreaterOrEqual(penalty, over_maximum).OnlyEnforceIf(closes);
    model->AddEquality(penalty, 0).OnlyEnforceIf(closes.Not());
    *objective += penalty;
  }

  sat::IntVar end_penalty =
      model->NewIntVar(operations_research::Domain(0, max_end_cost))
          .WithName(name + "_end_penalty");
  sat::LinearExpr end_over_maximum(-max_length * weight);
  end_over_maximum += sat::LinearExpr::Term(run_lengths.back(), weight);
  model->AddGreaterOrEqual(end_penalty, end_over_maximum)
      .OnlyEnforceIf(active_by_day.back());
  model->AddEquality(end_penalty, 0).OnlyEnforceIf(active_by_day.back().Not());
  *objective += end_penalty;
}

InstancePayload ParsePayload(const std::string &input) {
  const json::object root = json::parse(input).as_object();
  InstancePayload payload;

  for (const json::value &item : ArrayAt(root, "nurses")) {
    const json::object &object = item.as_object();
    Nurse nurse;
    nurse.contract_idx = static_cast<int>(AsInt(object.at("contract_idx")));
    for (const json::value &skill : object.at("skills").as_array()) {
      nurse.skills.insert(static_cast<int>(AsInt(skill)));
    }
    payload.nurses.push_back(std::move(nurse));
  }

  for (const json::value &item : ArrayAt(root, "contracts")) {
    const json::object &object = item.as_object();
    payload.contracts.push_back({
        static_cast<int>(AsInt(object.at("min_assignments"))),
        static_cast<int>(AsInt(object.at("max_assignments"))),
        static_cast<int>(AsInt(object.at("min_consecutive_working"))),
        static_cast<int>(AsInt(object.at("max_consecutive_working"))),
        static_cast<int>(AsInt(object.at("min_consecutive_off"))),
        static_cast<int>(AsInt(object.at("max_consecutive_off"))),
        static_cast<int>(AsInt(object.at("max_working_weekends"))),
        AsBool(object.at("complete_weekends")),
    });
  }

  for (const json::value &item : ArrayAt(root, "shift_types")) {
    const json::object &object = item.as_object();
    payload.shift_types.push_back({
        static_cast<int>(AsInt(object.at("min_consecutive"))),
        static_cast<int>(AsInt(object.at("max_consecutive"))),
    });
  }

  for (const json::value &item : ArrayAt(root, "forbidden")) {
    const json::object &object = item.as_object();
    const int preceding = static_cast<int>(AsInt(object.at("preceding")));
    for (const json::value &successor : object.at("succeeding").as_array()) {
      payload.forbidden_successors[preceding].insert(
          static_cast<int>(AsInt(successor)));
    }
  }

  for (const json::value &item : ArrayAt(root, "shift_off_requests")) {
    const json::object &object = item.as_object();
    int64_t shift_type_idx = AsInt(object.at("shift_type_idx"));
    if (shift_type_idx < 0) {
      shift_type_idx = kAnyShiftType;
    }
    payload.shift_off_requests.push_back({
        static_cast<int>(AsInt(object.at("nurse_idx"))),
        static_cast<int>(AsInt(object.at("global_day"))),
        shift_type_idx,
    });
  }

  for (const json::value &item : ArrayAt(root, "nurse_history")) {
    const json::object &object = item.as_object();
    int last_shift_type_idx = -1;
    if (!object.at("last_shift_type_idx").is_null()) {
      last_shift_type_idx =
          static_cast<int>(AsInt(object.at("last_shift_type_idx")));
    }
    payload.histories.push_back({
        static_cast<int>(AsInt(object.at("nurse_idx"))),
        static_cast<int>(AsInt(object.at("num_assignments"))),
        static_cast<int>(AsInt(object.at("num_working_weekends"))),
        last_shift_type_idx,
        static_cast<int>(AsInt(object.at("num_consecutive_assignments"))),
        static_cast<int>(AsInt(object.at("num_consecutive_working"))),
        static_cast<int>(AsInt(object.at("num_consecutive_off"))),
    });
  }
  std::sort(payload.histories.begin(), payload.histories.end(),
            [](const NurseHistory &left, const NurseHistory &right) {
              return left.nurse_idx < right.nurse_idx;
            });

  for (const json::value &item : ArrayAt(root, "shifts")) {
    const json::object &object = item.as_object();
    payload.shifts.push_back({
        static_cast<int>(AsInt(object.at("week"))),
        static_cast<int>(AsInt(object.at("day"))),
        static_cast<int>(AsInt(object.at("shift_type_idx"))),
        static_cast<int>(AsInt(object.at("skill_idx"))),
        AsBool(object.at("is_minimum")),
    });
  }

  payload.num_weeks = static_cast<int>(AsInt(root.at("num_weeks")));
  for (const json::value &item : ArrayAt(root, "skill_names")) {
    payload.skill_names.push_back(AsString(item));
  }
  for (const json::value &item : ArrayAt(root, "shift_type_names")) {
    payload.shift_type_names.push_back(AsString(item));
  }
  for (const json::value &item : ArrayAt(root, "nurse_names")) {
    payload.nurse_names.push_back(AsString(item));
  }

  return payload;
}

bool IsForbiddenSuccessor(const InstancePayload &payload, int preceding,
                          int succeeding) {
  if (preceding < 0) {
    return false;
  }
  const auto found = payload.forbidden_successors.find(preceding);
  if (found == payload.forbidden_successors.end()) {
    return false;
  }
  return found->second.find(succeeding) != found->second.end();
}

std::vector<CoverageRequirement>
BuildCoverageRequirements(const InstancePayload &payload) {
  using CoverageKey = std::tuple<int, int, int, int>;
  std::map<CoverageKey, std::pair<int, int>> counts;
  for (const Shift &shift : payload.shifts) {
    auto &[minimum, optimal] =
        counts[{shift.week, shift.day, shift.shift_type_idx, shift.skill_idx}];
    ++optimal;
    if (shift.is_minimum) {
      ++minimum;
    }
  }

  std::vector<CoverageRequirement> requirements;
  requirements.reserve(counts.size());
  for (const auto &[key, counts_for_key] : counts) {
    const auto &[week, day, shift_type_idx, skill_idx] = key;
    const auto &[minimum, optimal] = counts_for_key;
    if (minimum < 0 || optimal <= 0 || minimum > optimal) {
      throw std::runtime_error("invalid employee coverage requirement");
    }
    requirements.push_back(
        {week, day, shift_type_idx, skill_idx, minimum, optimal});
  }
  return requirements;
}

const char *CpSatStatusName(sat::CpSolverStatus status) {
  switch (status) {
  case sat::CpSolverStatus::UNKNOWN:
    return "UNKNOWN";
  case sat::CpSolverStatus::MODEL_INVALID:
    return "MODEL_INVALID";
  case sat::CpSolverStatus::FEASIBLE:
    return "FEASIBLE";
  case sat::CpSolverStatus::INFEASIBLE:
    return "INFEASIBLE";
  case sat::CpSolverStatus::OPTIMAL:
    return "OPTIMAL";
  }
  return "UNRECOGNIZED";
}

void AddSolverMetadata(json::object *output,
                       const sat::CpSolverResponse &response,
                       const sat::CpModelProto &proto) {
  output->emplace("native_solver_status", CpSatStatusName(response.status()));
  output->emplace("cp_sat_wall_time_seconds", response.wall_time());
  output->emplace("cp_sat_user_time_seconds", response.user_time());
  output->emplace("cp_sat_num_conflicts", response.num_conflicts());
  output->emplace("cp_sat_num_branches", response.num_branches());
  output->emplace("cp_sat_model_variables", proto.variables_size());
  output->emplace("cp_sat_model_constraints", proto.constraints_size());
  if (response.status() == sat::CpSolverStatus::OPTIMAL ||
      response.status() == sat::CpSolverStatus::FEASIBLE) {
    output->emplace("cp_sat_objective", response.objective_value());
    output->emplace("cp_sat_best_bound", response.best_objective_bound());
  }
}

json::object
SolutionJson(const InstancePayload &payload,
             const std::vector<CoverageRequirement> &coverage_requirements,
             const std::unordered_set<int64_t> &assignment_keys,
             std::optional<double> objective) {
  const int num_nurses = static_cast<int>(payload.nurses.size());
  std::vector<int64_t> sorted_keys(assignment_keys.begin(),
                                   assignment_keys.end());
  std::sort(sorted_keys.begin(), sorted_keys.end());

  json::array weeks;
  for (int week = 0; week < payload.num_weeks; ++week) {
    weeks.emplace_back(json::array());
  }

  for (int64_t key : sorted_keys) {
    const int coverage_idx = KeyCoverage(key, num_nurses);
    const int nurse_idx = KeyNurse(key, num_nurses);
    const CoverageRequirement &coverage = coverage_requirements[coverage_idx];
    json::object assignment;
    assignment["nurse"] = payload.nurse_names[nurse_idx];
    assignment["day"] = kDays[coverage.day];
    assignment["shiftType"] = payload.shift_type_names[coverage.shift_type_idx];
    assignment["skill"] = payload.skill_names[coverage.skill_idx];
    weeks[coverage.week].as_array().emplace_back(std::move(assignment));
  }

  json::object output;
  output["assignments"] = std::move(weeks);
  if (objective.has_value()) {
    output["objective"] = static_cast<int64_t>(std::llround(*objective));
  }
  return output;
}

SolveResult Solve(const InstancePayload &payload, double time_limit) {
  sat::CpModelBuilder model;
  const int num_nurses = static_cast<int>(payload.nurses.size());
  const int total_days = payload.num_weeks * 7;
  const std::vector<CoverageRequirement> coverage_requirements =
      BuildCoverageRequirements(payload);

  sat::LinearExpr objective(0);
  std::vector<AssignmentVar> assignment_vars;
  std::vector<std::vector<sat::BoolVar>> vars_by_nurse(num_nurses);
  std::vector<std::vector<std::vector<sat::BoolVar>>> vars_by_nurse_day(
      num_nurses, std::vector<std::vector<sat::BoolVar>>(total_days));
  std::vector<std::vector<std::vector<std::vector<sat::BoolVar>>>>
      vars_by_nurse_day_shift_type(
          num_nurses, std::vector<std::vector<std::vector<sat::BoolVar>>>(
                          total_days, std::vector<std::vector<sat::BoolVar>>(
                                          payload.shift_types.size())));

  for (int coverage_idx = 0;
       coverage_idx < static_cast<int>(coverage_requirements.size());
       ++coverage_idx) {
    const CoverageRequirement &coverage = coverage_requirements[coverage_idx];
    const int global_day = GlobalDay(coverage.week, coverage.day);
    std::vector<sat::BoolVar> candidates;
    for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
      const Nurse &nurse = payload.nurses[nurse_idx];
      if (nurse.skills.find(coverage.skill_idx) == nurse.skills.end()) {
        continue;
      }
      const int history_last_shift =
          payload.histories[nurse_idx].last_shift_type_idx;
      if (global_day == 0 && IsForbiddenSuccessor(payload, history_last_shift,
                                                  coverage.shift_type_idx)) {
        continue;
      }
      sat::BoolVar var = model.NewBoolVar().WithName(
          "assign_c" + std::to_string(coverage_idx) + "_n" +
          std::to_string(nurse_idx));
      candidates.push_back(var);
      assignment_vars.push_back({coverage_idx, nurse_idx, var});
      vars_by_nurse[nurse_idx].push_back(var);
      vars_by_nurse_day[nurse_idx][global_day].push_back(var);
      vars_by_nurse_day_shift_type[nurse_idx][global_day]
                                  [coverage.shift_type_idx]
                                      .push_back(var);

      int request_count = 0;
      for (const ShiftOffRequest &request : payload.shift_off_requests) {
        if (request.nurse_idx == nurse_idx &&
            request.global_day == global_day &&
            (request.shift_type_idx == kAnyShiftType ||
             request.shift_type_idx == coverage.shift_type_idx)) {
          request_count += 1;
        }
      }
      if (request_count != 0) {
        AddObjectiveTerm(&objective, var, request_count * 10);
      }
    }

    const sat::LinearExpr assigned = BoolSum(candidates);
    model.AddGreaterOrEqual(assigned, coverage.minimum);
    model.AddLessOrEqual(assigned, coverage.optimal);
    sat::IntVar uncovered =
        model.NewIntVar(operations_research::Domain(0, coverage.optimal))
            .WithName("optimal_uncovered_c" + std::to_string(coverage_idx));
    model.AddEquality(uncovered + assigned, coverage.optimal);
    AddObjectiveTerm(&objective, uncovered, 30);
  }

  std::vector<std::vector<sat::BoolVar>> work_by_nurse_day(
      num_nurses, std::vector<sat::BoolVar>(total_days));
  std::vector<std::vector<std::vector<sat::BoolVar>>> shift_type_by_nurse_day(
      num_nurses,
      std::vector<std::vector<sat::BoolVar>>(
          total_days, std::vector<sat::BoolVar>(payload.shift_types.size())));
  for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
    for (int day = 0; day < total_days; ++day) {
      sat::BoolVar work = model.NewBoolVar().WithName(
          "work_n" + std::to_string(nurse_idx) + "_d" + std::to_string(day));
      model.AddEquality(work, BoolSum(vars_by_nurse_day[nurse_idx][day]));
      work_by_nurse_day[nurse_idx][day] = work;

      for (int shift_type_idx = 0;
           shift_type_idx < static_cast<int>(payload.shift_types.size());
           ++shift_type_idx) {
        sat::BoolVar works_type = model.NewBoolVar().WithName(
            "work_n" + std::to_string(nurse_idx) + "_d" + std::to_string(day) +
            "_st" + std::to_string(shift_type_idx));
        model.AddEquality(
            works_type,
            BoolSum(
                vars_by_nurse_day_shift_type[nurse_idx][day][shift_type_idx]));
        shift_type_by_nurse_day[nurse_idx][day][shift_type_idx] = works_type;
      }
    }
  }

  for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
    for (int day = 0; day < total_days; ++day) {
      model.AddLessOrEqual(BoolSum(vars_by_nurse_day[nurse_idx][day]), 1);
    }
    for (int day = 0; day < total_days - 1; ++day) {
      for (const auto &[preceding, successors] : payload.forbidden_successors) {
        for (int succeeding : successors) {
          model.AddLessOrEqual(
              shift_type_by_nurse_day[nurse_idx][day][preceding] +
                  shift_type_by_nurse_day[nurse_idx][day + 1][succeeding],
              1);
        }
      }
    }
  }

  for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
    const Nurse &nurse = payload.nurses[nurse_idx];
    const Contract &contract = payload.contracts[nurse.contract_idx];
    const NurseHistory &history = payload.histories[nurse_idx];
    const int total_assignment_upper = history.num_assignments + total_days;

    const sat::LinearExpr assignment_count = BoolSum(vars_by_nurse[nurse_idx]);
    sat::IntVar under_assignments =
        model.NewIntVar(operations_research::Domain(0, total_assignment_upper))
            .WithName("under_assignments_n" + std::to_string(nurse_idx));
    model.AddGreaterOrEqual(under_assignments, contract.min_assignments -
                                                   history.num_assignments -
                                                   assignment_count);
    AddObjectiveTerm(&objective, under_assignments, 20);

    sat::IntVar over_assignments =
        model.NewIntVar(operations_research::Domain(0, total_assignment_upper))
            .WithName("over_assignments_n" + std::to_string(nurse_idx));
    model.AddGreaterOrEqual(over_assignments, history.num_assignments +
                                                  assignment_count -
                                                  contract.max_assignments);
    AddObjectiveTerm(&objective, over_assignments, 20);

    const std::vector<sat::BoolVar> &work_sequence =
        work_by_nurse_day[nurse_idx];
    AddRunLengthCosts(&model, work_sequence, history.last_shift_type_idx >= 0,
                      history.num_consecutive_working,
                      contract.min_consecutive_working,
                      contract.max_consecutive_working, 30,
                      "work_n" + std::to_string(nurse_idx), &objective);

    std::vector<sat::BoolVar> off_sequence;
    off_sequence.reserve(work_sequence.size());
    for (sat::BoolVar work : work_sequence) {
      off_sequence.push_back(work.Not());
    }
    AddRunLengthCosts(&model, off_sequence, history.last_shift_type_idx < 0,
                      history.num_consecutive_off, contract.min_consecutive_off,
                      contract.max_consecutive_off, 30,
                      "off_n" + std::to_string(nurse_idx), &objective);

    for (int shift_type_idx = 0;
         shift_type_idx < static_cast<int>(payload.shift_types.size());
         ++shift_type_idx) {
      std::vector<sat::BoolVar> type_sequence;
      type_sequence.reserve(total_days);
      for (int day = 0; day < total_days; ++day) {
        type_sequence.push_back(
            shift_type_by_nurse_day[nurse_idx][day][shift_type_idx]);
      }
      const ShiftType &shift_type = payload.shift_types[shift_type_idx];
      AddRunLengthCosts(
          &model, type_sequence, history.last_shift_type_idx == shift_type_idx,
          history.num_consecutive_assignments, shift_type.min_consecutive,
          shift_type.max_consecutive, 15,
          "shift_type_n" + std::to_string(nurse_idx) + "_st" +
              std::to_string(shift_type_idx),
          &objective);
    }

    std::vector<sat::BoolVar> weekend_terms;
    weekend_terms.reserve(payload.num_weeks);
    for (int week = 0; week < payload.num_weeks; ++week) {
      sat::BoolVar saturday = work_by_nurse_day[nurse_idx][week * 7 + 5];
      sat::BoolVar sunday = work_by_nurse_day[nurse_idx][week * 7 + 6];
      sat::BoolVar weekend =
          model.NewBoolVar().WithName("weekend_n" + std::to_string(nurse_idx) +
                                      "_w" + std::to_string(week));
      model.AddMaxEquality(weekend, {saturday, sunday});
      weekend_terms.push_back(weekend);

      if (contract.complete_weekends) {
        sat::BoolVar incomplete = model.NewBoolVar().WithName(
            "incomplete_weekend_n" + std::to_string(nurse_idx) + "_w" +
            std::to_string(week));
        model.AddAbsEquality(incomplete, saturday - sunday);
        AddObjectiveTerm(&objective, incomplete, 30);
      }
    }

    sat::IntVar over_weekends =
        model
            .NewIntVar(operations_research::Domain(
                0, payload.num_weeks + history.num_working_weekends))
            .WithName("over_weekends_n" + std::to_string(nurse_idx));
    model.AddGreaterOrEqual(over_weekends, history.num_working_weekends +
                                               BoolSum(weekend_terms) -
                                               contract.max_working_weekends);
    AddObjectiveTerm(&objective, over_weekends, 30);
  }

  std::vector<AssignmentVar> ordered_assignment_vars = assignment_vars;
  std::sort(
      ordered_assignment_vars.begin(), ordered_assignment_vars.end(),
      [num_nurses](const AssignmentVar &left, const AssignmentVar &right) {
        if (left.coverage_idx != right.coverage_idx) {
          return left.coverage_idx < right.coverage_idx;
        }
        const int left_rotation =
            (left.nurse_idx - left.coverage_idx % num_nurses + num_nurses) %
            num_nurses;
        const int right_rotation =
            (right.nurse_idx - right.coverage_idx % num_nurses + num_nurses) %
            num_nurses;
        return left_rotation < right_rotation;
      });
  std::vector<sat::BoolVar> assignment_decisions;
  assignment_decisions.reserve(ordered_assignment_vars.size());
  for (const AssignmentVar &assignment_var : ordered_assignment_vars) {
    assignment_decisions.push_back(assignment_var.var);
  }
  model.AddDecisionStrategy(assignment_decisions,
                            sat::DecisionStrategyProto::CHOOSE_FIRST,
                            sat::DecisionStrategyProto::SELECT_MAX_VALUE);
  model.Minimize(objective);

  sat::Model solver_model;
  sat::SatParameters parameters;
  parameters.set_max_time_in_seconds(std::max(0.1, time_limit));
  parameters.set_num_search_workers(1);
  parameters.set_random_seed(1);
  parameters.set_search_branching(sat::SatParameters::FIXED_SEARCH);
  parameters.set_log_search_progress(false);
  solver_model.Add(sat::NewSatParameters(parameters));
  const sat::CpModelProto proto = model.Build();
  const json::object fair_start_witness = FairStartWitness(proto);
  const sat::CpSolverResponse response =
      sat::SolveCpModel(proto, &solver_model);
  json::object output;
  output["fair_start_witness"] = fair_start_witness;
  AddSolverMetadata(&output, response, proto);
  if (response.status() != sat::CpSolverStatus::OPTIMAL &&
      response.status() != sat::CpSolverStatus::FEASIBLE) {
    return SolveResult{std::move(output), false};
  }

  std::unordered_set<int64_t> assignment_keys;
  for (const AssignmentVar &assignment_var : assignment_vars) {
    if (sat::SolutionBooleanValue(response, assignment_var.var)) {
      assignment_keys.insert(Key(assignment_var.coverage_idx,
                                 assignment_var.nurse_idx, num_nurses));
    }
  }
  json::object solution =
      SolutionJson(payload, coverage_requirements, assignment_keys,
                   response.objective_value());
  solution["fair_start_witness"] = fair_start_witness;
  AddSolverMetadata(&solution, response, proto);
  return SolveResult{std::move(solution), true};
}

} // namespace

int main(int argc, char *argv[]) {
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
          "usage: employee_scheduling_ortools <time_limit_seconds>");
    }
    const double time_limit = std::stod(argv[1]);
    const std::string input((std::istreambuf_iterator<char>(std::cin)),
                            std::istreambuf_iterator<char>());
    const InstancePayload payload = ParsePayload(input);
    const SolveResult result = Solve(payload, time_limit);
    std::cout << json::serialize(result.output) << '\n';
    if (!result.feasible) {
      std::cerr << "OR-Tools CP-SAT found no feasible solution" << '\n';
      return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return EXIT_FAILURE;
  }
}
