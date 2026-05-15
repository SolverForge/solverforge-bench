#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <iterator>
#include <limits>
#include <numeric>
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
constexpr const char* kDays[] = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"};

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
  int shift_idx;
  int nurse_idx;
  sat::BoolVar var;
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

bool AsBool(const json::value& value) {
  if (value.is_bool()) {
    return value.as_bool();
  }
  return AsInt(value) != 0;
}

std::string AsString(const json::value& value) {
  return std::string(value.as_string().c_str());
}

const json::array& ArrayAt(const json::object& object, const char* key) {
  return object.at(key).as_array();
}

int GlobalDay(const Shift& shift) { return shift.week * 7 + shift.day; }

int64_t Key(int shift_idx, int nurse_idx, int num_nurses) {
  return static_cast<int64_t>(shift_idx) * num_nurses + nurse_idx;
}

int KeyShift(int64_t key, int num_nurses) {
  return static_cast<int>(key / num_nurses);
}

int KeyNurse(int64_t key, int num_nurses) {
  return static_cast<int>(key % num_nurses);
}

sat::LinearExpr BoolSum(const std::vector<sat::BoolVar>& vars) {
  if (vars.empty()) {
    return sat::LinearExpr(0);
  }
  return sat::LinearExpr::Sum(vars);
}

sat::LinearExpr IntSum(const std::vector<sat::IntVar>& vars) {
  if (vars.empty()) {
    return sat::LinearExpr(0);
  }
  return sat::LinearExpr::Sum(vars);
}

void AddObjectiveTerm(sat::LinearExpr* objective, sat::BoolVar var,
                      int64_t weight) {
  *objective += sat::LinearExpr::Term(var, weight);
}

void AddObjectiveTerm(sat::LinearExpr* objective, sat::IntVar var,
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

sat::BoolVar AndLiteral(sat::CpModelBuilder* model,
                        const std::vector<sat::BoolVar>& literals,
                        const std::string& name) {
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

void AddRunLengthCosts(sat::CpModelBuilder* model,
                       const std::vector<sat::BoolVar>& active_by_day,
                       bool history_active, int history_length, int min_length,
                       int max_length, int weight, const std::string& name,
                       sat::LinearExpr* objective) {
  if (active_by_day.empty()) {
    return;
  }

  const int max_possible_length =
      static_cast<int>(active_by_day.size()) + std::max(0, history_length);
  std::vector<int64_t> closed_costs;
  std::vector<int64_t> max_costs;
  closed_costs.reserve(max_possible_length + 1);
  max_costs.reserve(max_possible_length + 1);
  for (int length = 0; length <= max_possible_length; ++length) {
    closed_costs.push_back(
        ClosedBoundsCost(length, min_length, max_length, weight));
    max_costs.push_back(MaxBoundCost(length, max_length, weight));
  }
  const int64_t max_closed_cost =
      *std::max_element(closed_costs.begin(), closed_costs.end());
  const int64_t max_end_cost =
      *std::max_element(max_costs.begin(), max_costs.end());

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
        std::vector<sat::BoolVar> enforcement = {active,
                                                 previous_active.Not()};
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
    sat::IntVar raw_cost =
        model->NewIntVar(operations_research::Domain(0, max_closed_cost))
            .WithName(name + "_closed_raw_d" + std::to_string(day));
    sat::IntVar penalty =
        model->NewIntVar(operations_research::Domain(0, max_closed_cost))
            .WithName(name + "_closed_penalty_d" + std::to_string(day));
    model->AddElement(run_lengths[day - 1], closed_costs, raw_cost);
    model->AddEquality(penalty, raw_cost).OnlyEnforceIf(closes);
    model->AddEquality(penalty, 0).OnlyEnforceIf(closes.Not());
    *objective += penalty;
  }

  sat::IntVar end_cost =
      model->NewIntVar(operations_research::Domain(0, max_end_cost))
          .WithName(name + "_end_raw");
  sat::IntVar end_penalty =
      model->NewIntVar(operations_research::Domain(0, max_end_cost))
          .WithName(name + "_end_penalty");
  model->AddElement(run_lengths.back(), max_costs, end_cost);
  model->AddEquality(end_penalty, end_cost).OnlyEnforceIf(active_by_day.back());
  model->AddEquality(end_penalty, 0).OnlyEnforceIf(active_by_day.back().Not());
  *objective += end_penalty;
}

InstancePayload ParsePayload(const std::string& input) {
  const json::object root = json::parse(input).as_object();
  InstancePayload payload;

  for (const json::value& item : ArrayAt(root, "nurses")) {
    const json::object& object = item.as_object();
    Nurse nurse;
    nurse.contract_idx = static_cast<int>(AsInt(object.at("contract_idx")));
    for (const json::value& skill : object.at("skills").as_array()) {
      nurse.skills.insert(static_cast<int>(AsInt(skill)));
    }
    payload.nurses.push_back(std::move(nurse));
  }

  for (const json::value& item : ArrayAt(root, "contracts")) {
    const json::object& object = item.as_object();
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

  for (const json::value& item : ArrayAt(root, "shift_types")) {
    const json::object& object = item.as_object();
    payload.shift_types.push_back({
        static_cast<int>(AsInt(object.at("min_consecutive"))),
        static_cast<int>(AsInt(object.at("max_consecutive"))),
    });
  }

  for (const json::value& item : ArrayAt(root, "forbidden")) {
    const json::object& object = item.as_object();
    const int preceding = static_cast<int>(AsInt(object.at("preceding")));
    for (const json::value& successor : object.at("succeeding").as_array()) {
      payload.forbidden_successors[preceding].insert(
          static_cast<int>(AsInt(successor)));
    }
  }

  for (const json::value& item : ArrayAt(root, "shift_off_requests")) {
    const json::object& object = item.as_object();
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

  for (const json::value& item : ArrayAt(root, "nurse_history")) {
    const json::object& object = item.as_object();
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
            [](const NurseHistory& left, const NurseHistory& right) {
              return left.nurse_idx < right.nurse_idx;
            });

  for (const json::value& item : ArrayAt(root, "shifts")) {
    const json::object& object = item.as_object();
    payload.shifts.push_back({
        static_cast<int>(AsInt(object.at("week"))),
        static_cast<int>(AsInt(object.at("day"))),
        static_cast<int>(AsInt(object.at("shift_type_idx"))),
        static_cast<int>(AsInt(object.at("skill_idx"))),
        AsBool(object.at("is_minimum")),
    });
  }

  payload.num_weeks = static_cast<int>(AsInt(root.at("num_weeks")));
  for (const json::value& item : ArrayAt(root, "skill_names")) {
    payload.skill_names.push_back(AsString(item));
  }
  for (const json::value& item : ArrayAt(root, "shift_type_names")) {
    payload.shift_type_names.push_back(AsString(item));
  }
  for (const json::value& item : ArrayAt(root, "nurse_names")) {
    payload.nurse_names.push_back(AsString(item));
  }

  return payload;
}

int PreviousShiftType(const std::vector<int>& assigned_shift_type_by_day,
                      const NurseHistory& history, int global_day) {
  if (global_day == 0) {
    return history.last_shift_type_idx;
  }
  return assigned_shift_type_by_day[global_day - 1];
}

int NextShiftType(const std::vector<int>& assigned_shift_type_by_day,
                  int global_day) {
  if (global_day + 1 >= static_cast<int>(assigned_shift_type_by_day.size())) {
    return -1;
  }
  return assigned_shift_type_by_day[global_day + 1];
}

bool IsForbiddenSuccessor(const InstancePayload& payload, int preceding,
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

std::unordered_set<int64_t> BuildGreedyHint(const InstancePayload& payload) {
  const int num_nurses = static_cast<int>(payload.nurses.size());
  const int total_days = payload.num_weeks * 7;
  std::vector<std::vector<int>> assigned_shift_type_by_nurse_day(
      num_nurses, std::vector<int>(total_days, -1));
  std::vector<int> assignment_count_by_nurse(num_nurses, 0);
  std::unordered_set<int64_t> hint;

  std::vector<int> shift_indices(payload.shifts.size());
  std::iota(shift_indices.begin(), shift_indices.end(), 0);
  std::sort(shift_indices.begin(), shift_indices.end(),
            [&payload](int left_idx, int right_idx) {
              const Shift& left = payload.shifts[left_idx];
              const Shift& right = payload.shifts[right_idx];
              return std::make_tuple(left.week, left.day, !left.is_minimum,
                                     left.shift_type_idx, left.skill_idx,
                                     left_idx) <
                     std::make_tuple(right.week, right.day, !right.is_minimum,
                                     right.shift_type_idx, right.skill_idx,
                                     right_idx);
            });

  for (int shift_idx : shift_indices) {
    const Shift& shift = payload.shifts[shift_idx];
    if (!shift.is_minimum) {
      continue;
    }
    const int global_day = GlobalDay(shift);
    std::vector<int> candidates;
    for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
      const Nurse& nurse = payload.nurses[nurse_idx];
      if (nurse.skills.find(shift.skill_idx) == nurse.skills.end()) {
        continue;
      }
      if (assigned_shift_type_by_nurse_day[nurse_idx][global_day] >= 0) {
        continue;
      }
      const int previous_shift_type =
          PreviousShiftType(assigned_shift_type_by_nurse_day[nurse_idx],
                            payload.histories[nurse_idx], global_day);
      if (IsForbiddenSuccessor(payload, previous_shift_type,
                               shift.shift_type_idx)) {
        continue;
      }
      const int next_shift_type =
          NextShiftType(assigned_shift_type_by_nurse_day[nurse_idx],
                        global_day);
      if (IsForbiddenSuccessor(payload, shift.shift_type_idx,
                               next_shift_type)) {
        continue;
      }
      candidates.push_back(nurse_idx);
    }
    if (candidates.empty()) {
      continue;
    }
    const int nurse_idx = *std::min_element(
        candidates.begin(), candidates.end(), [&](int left, int right) {
          return std::tie(assignment_count_by_nurse[left], left) <
                 std::tie(assignment_count_by_nurse[right], right);
        });
    assigned_shift_type_by_nurse_day[nurse_idx][global_day] =
        shift.shift_type_idx;
    assignment_count_by_nurse[nurse_idx] += 1;
    hint.insert(Key(shift_idx, nurse_idx, num_nurses));
  }

  return hint;
}

std::unordered_set<int64_t> SolveHardSeed(const InstancePayload& payload,
                                          double time_limit) {
  sat::CpModelBuilder model;
  const int num_nurses = static_cast<int>(payload.nurses.size());
  const int total_days = payload.num_weeks * 7;
  std::vector<AssignmentVar> assignment_vars;
  std::vector<std::vector<std::vector<sat::BoolVar>>> vars_by_nurse_day(
      num_nurses, std::vector<std::vector<sat::BoolVar>>(total_days));
  std::vector<std::vector<std::vector<std::vector<sat::BoolVar>>>>
      vars_by_nurse_day_shift_type(
          num_nurses,
          std::vector<std::vector<std::vector<sat::BoolVar>>>(
              total_days,
              std::vector<std::vector<sat::BoolVar>>(
                  payload.shift_types.size())));

  for (int shift_idx = 0; shift_idx < static_cast<int>(payload.shifts.size());
       ++shift_idx) {
    const Shift& shift = payload.shifts[shift_idx];
    const int global_day = GlobalDay(shift);
    std::vector<sat::BoolVar> candidates;
    for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
      const Nurse& nurse = payload.nurses[nurse_idx];
      if (nurse.skills.find(shift.skill_idx) == nurse.skills.end()) {
        continue;
      }
      const int history_last_shift =
          payload.histories[nurse_idx].last_shift_type_idx;
      if (global_day == 0 &&
          IsForbiddenSuccessor(payload, history_last_shift,
                               shift.shift_type_idx)) {
        continue;
      }
      sat::BoolVar var =
          model.NewBoolVar().WithName("seed_s" + std::to_string(shift_idx) +
                                      "_n" + std::to_string(nurse_idx));
      candidates.push_back(var);
      assignment_vars.push_back({shift_idx, nurse_idx, var});
      vars_by_nurse_day[nurse_idx][global_day].push_back(var);
      vars_by_nurse_day_shift_type[nurse_idx][global_day]
                                  [shift.shift_type_idx]
                                      .push_back(var);
    }

    if (shift.is_minimum) {
      model.AddEquality(BoolSum(candidates), 1);
    } else {
      model.AddEquality(BoolSum(candidates), 0);
    }
  }

  for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
    for (int day = 0; day < total_days; ++day) {
      model.AddLessOrEqual(BoolSum(vars_by_nurse_day[nurse_idx][day]), 1);
    }
    for (int day = 0; day < total_days - 1; ++day) {
      for (const auto& [preceding, successors] : payload.forbidden_successors) {
        for (int succeeding : successors) {
          for (sat::BoolVar left :
               vars_by_nurse_day_shift_type[nurse_idx][day][preceding]) {
            for (sat::BoolVar right :
                 vars_by_nurse_day_shift_type[nurse_idx][day + 1][succeeding]) {
              model.AddLessOrEqual(left + right, 1);
            }
          }
        }
      }
    }
  }

  const std::unordered_set<int64_t> greedy_hint = BuildGreedyHint(payload);
  for (const AssignmentVar& assignment_var : assignment_vars) {
    model.AddHint(assignment_var.var,
                  greedy_hint.find(Key(assignment_var.shift_idx,
                                       assignment_var.nurse_idx,
                                       num_nurses)) != greedy_hint.end());
  }

  sat::Model solver_model;
  sat::SatParameters parameters;
  parameters.set_max_time_in_seconds(time_limit);
  parameters.set_num_search_workers(1);
  parameters.set_random_seed(1);
  parameters.set_log_search_progress(false);
  solver_model.Add(sat::NewSatParameters(parameters));
  const sat::CpSolverResponse response =
      sat::SolveCpModel(model.Build(), &solver_model);
  if (response.status() != sat::CpSolverStatus::OPTIMAL &&
      response.status() != sat::CpSolverStatus::FEASIBLE) {
    return {};
  }

  std::unordered_set<int64_t> assignment_keys;
  for (const AssignmentVar& assignment_var : assignment_vars) {
    if (sat::SolutionBooleanValue(response, assignment_var.var)) {
      assignment_keys.insert(Key(assignment_var.shift_idx,
                                 assignment_var.nurse_idx, num_nurses));
    }
  }
  return assignment_keys;
}

json::object SolutionJson(const InstancePayload& payload,
                          const std::unordered_set<int64_t>& assignment_keys,
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
    const int shift_idx = KeyShift(key, num_nurses);
    const int nurse_idx = KeyNurse(key, num_nurses);
    const Shift& shift = payload.shifts[shift_idx];
    json::object assignment;
    assignment["nurse"] = payload.nurse_names[nurse_idx];
    assignment["day"] = kDays[shift.day];
    assignment["shiftType"] = payload.shift_type_names[shift.shift_type_idx];
    assignment["skill"] = payload.skill_names[shift.skill_idx];
    weeks[shift.week].as_array().emplace_back(std::move(assignment));
  }

  json::object output;
  output["assignments"] = std::move(weeks);
  if (objective.has_value()) {
    output["objective"] = static_cast<int64_t>(std::llround(*objective));
  }
  return output;
}

std::optional<json::object> Solve(const InstancePayload& payload,
                                  double time_limit) {
  const double seed_time_limit =
      std::min(std::min(5.0, std::max(1.0, time_limit * 0.25)), time_limit);
  const auto seed_start = std::chrono::steady_clock::now();
  const std::unordered_set<int64_t> hard_seed =
      SolveHardSeed(payload, seed_time_limit);
  const double seed_elapsed =
      std::chrono::duration<double>(std::chrono::steady_clock::now() -
                                    seed_start)
          .count();
  const double remaining_time = time_limit - seed_elapsed;
  if (!hard_seed.empty() && remaining_time <= 0.1) {
    return SolutionJson(payload, hard_seed, std::nullopt);
  }

  sat::CpModelBuilder model;
  const int num_nurses = static_cast<int>(payload.nurses.size());
  const int total_days = payload.num_weeks * 7;

  sat::LinearExpr objective(0);
  std::vector<AssignmentVar> assignment_vars;
  std::vector<std::pair<int, sat::BoolVar>> unassigned_vars;
  std::vector<std::vector<sat::BoolVar>> vars_by_nurse(num_nurses);
  std::vector<std::vector<std::vector<sat::BoolVar>>> vars_by_nurse_day(
      num_nurses, std::vector<std::vector<sat::BoolVar>>(total_days));
  std::vector<std::vector<std::vector<std::vector<sat::BoolVar>>>>
      vars_by_nurse_day_shift_type(
          num_nurses,
          std::vector<std::vector<std::vector<sat::BoolVar>>>(
              total_days,
              std::vector<std::vector<sat::BoolVar>>(
                  payload.shift_types.size())));

  for (int shift_idx = 0; shift_idx < static_cast<int>(payload.shifts.size());
       ++shift_idx) {
    const Shift& shift = payload.shifts[shift_idx];
    const int global_day = GlobalDay(shift);
    std::vector<sat::BoolVar> candidates;
    for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
      const Nurse& nurse = payload.nurses[nurse_idx];
      if (nurse.skills.find(shift.skill_idx) == nurse.skills.end()) {
        continue;
      }
      const int history_last_shift =
          payload.histories[nurse_idx].last_shift_type_idx;
      if (global_day == 0 &&
          IsForbiddenSuccessor(payload, history_last_shift,
                               shift.shift_type_idx)) {
        continue;
      }
      sat::BoolVar var =
          model.NewBoolVar().WithName("assign_s" + std::to_string(shift_idx) +
                                      "_n" + std::to_string(nurse_idx));
      candidates.push_back(var);
      assignment_vars.push_back({shift_idx, nurse_idx, var});
      vars_by_nurse[nurse_idx].push_back(var);
      vars_by_nurse_day[nurse_idx][global_day].push_back(var);
      vars_by_nurse_day_shift_type[nurse_idx][global_day]
                                  [shift.shift_type_idx]
                                      .push_back(var);

      int request_count = 0;
      for (const ShiftOffRequest& request : payload.shift_off_requests) {
        if (request.nurse_idx == nurse_idx && request.global_day == global_day &&
            (request.shift_type_idx == kAnyShiftType ||
             request.shift_type_idx == shift.shift_type_idx)) {
          request_count += 1;
        }
      }
      if (request_count != 0) {
        AddObjectiveTerm(&objective, var, request_count * 10);
      }
    }

    if (shift.is_minimum) {
      model.AddEquality(BoolSum(candidates), 1);
    } else {
      model.AddLessOrEqual(BoolSum(candidates), 1);
      sat::BoolVar unassigned =
          model.NewBoolVar().WithName("optional_unassigned_s" +
                                      std::to_string(shift_idx));
      unassigned_vars.push_back({shift_idx, unassigned});
      model.AddEquality(unassigned + BoolSum(candidates), 1);
      AddObjectiveTerm(&objective, unassigned, 30);
    }
  }

  std::vector<std::vector<sat::BoolVar>> work_by_nurse_day(
      num_nurses, std::vector<sat::BoolVar>(total_days));
  std::vector<std::vector<std::vector<sat::BoolVar>>> shift_type_by_nurse_day(
      num_nurses, std::vector<std::vector<sat::BoolVar>>(
                      total_days, std::vector<sat::BoolVar>(
                                      payload.shift_types.size())));
  for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
    for (int day = 0; day < total_days; ++day) {
      sat::BoolVar work =
          model.NewBoolVar().WithName("work_n" + std::to_string(nurse_idx) +
                                      "_d" + std::to_string(day));
      model.AddEquality(work, BoolSum(vars_by_nurse_day[nurse_idx][day]));
      work_by_nurse_day[nurse_idx][day] = work;

      for (int shift_type_idx = 0;
           shift_type_idx < static_cast<int>(payload.shift_types.size());
           ++shift_type_idx) {
        sat::BoolVar works_type =
            model.NewBoolVar().WithName("work_n" + std::to_string(nurse_idx) +
                                        "_d" + std::to_string(day) + "_st" +
                                        std::to_string(shift_type_idx));
        model.AddEquality(
            works_type,
            BoolSum(vars_by_nurse_day_shift_type[nurse_idx][day]
                                                [shift_type_idx]));
        shift_type_by_nurse_day[nurse_idx][day][shift_type_idx] = works_type;
      }
    }
  }

  for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
    for (int day = 0; day < total_days; ++day) {
      model.AddLessOrEqual(BoolSum(vars_by_nurse_day[nurse_idx][day]), 1);
    }
    for (int day = 0; day < total_days - 1; ++day) {
      for (const auto& [preceding, successors] : payload.forbidden_successors) {
        for (int succeeding : successors) {
          for (sat::BoolVar left :
               vars_by_nurse_day_shift_type[nurse_idx][day][preceding]) {
            for (sat::BoolVar right :
                 vars_by_nurse_day_shift_type[nurse_idx][day + 1][succeeding]) {
              model.AddLessOrEqual(left + right, 1);
            }
          }
        }
      }
    }
  }

  for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
    const Nurse& nurse = payload.nurses[nurse_idx];
    const Contract& contract = payload.contracts[nurse.contract_idx];
    const NurseHistory& history = payload.histories[nurse_idx];
    const int total_assignment_upper =
        history.num_assignments + static_cast<int>(payload.shifts.size());

    const sat::LinearExpr assignment_count = BoolSum(vars_by_nurse[nurse_idx]);
    sat::IntVar under_assignments =
        model.NewIntVar(operations_research::Domain(0, total_assignment_upper))
            .WithName("under_assignments_n" + std::to_string(nurse_idx));
    model.AddGreaterOrEqual(
        under_assignments,
        contract.min_assignments - history.num_assignments - assignment_count);
    AddObjectiveTerm(&objective, under_assignments, 20);

    sat::IntVar over_assignments =
        model.NewIntVar(operations_research::Domain(0, total_assignment_upper))
            .WithName("over_assignments_n" + std::to_string(nurse_idx));
    model.AddGreaterOrEqual(
        over_assignments,
        history.num_assignments + assignment_count - contract.max_assignments);
    AddObjectiveTerm(&objective, over_assignments, 20);

    const std::vector<sat::BoolVar>& work_sequence =
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
                      history.num_consecutive_off,
                      contract.min_consecutive_off,
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
      const ShiftType& shift_type = payload.shift_types[shift_type_idx];
      AddRunLengthCosts(&model, type_sequence,
                        history.last_shift_type_idx == shift_type_idx,
                        history.num_consecutive_assignments,
                        shift_type.min_consecutive,
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
        model.NewIntVar(operations_research::Domain(
                            0, payload.num_weeks + history.num_working_weekends))
            .WithName("over_weekends_n" + std::to_string(nurse_idx));
    model.AddGreaterOrEqual(
        over_weekends, history.num_working_weekends + BoolSum(weekend_terms) -
                           contract.max_working_weekends);
    AddObjectiveTerm(&objective, over_weekends, 30);
  }

  const std::unordered_set<int64_t> hint =
      !hard_seed.empty() ? hard_seed : BuildGreedyHint(payload);
  for (const AssignmentVar& assignment_var : assignment_vars) {
    model.AddHint(assignment_var.var,
                  hint.find(Key(assignment_var.shift_idx,
                                assignment_var.nurse_idx, num_nurses)) !=
                      hint.end());
  }
  std::unordered_set<int> hinted_shift_indices;
  for (int64_t key : hint) {
    hinted_shift_indices.insert(KeyShift(key, num_nurses));
  }
  for (const auto& [shift_idx, var] : unassigned_vars) {
    model.AddHint(var, hinted_shift_indices.find(shift_idx) ==
                           hinted_shift_indices.end());
  }
  for (int nurse_idx = 0; nurse_idx < num_nurses; ++nurse_idx) {
    for (int day = 0; day < total_days; ++day) {
      bool works = false;
      for (int64_t key : hint) {
        if (KeyNurse(key, num_nurses) == nurse_idx &&
            GlobalDay(payload.shifts[KeyShift(key, num_nurses)]) == day) {
          works = true;
          break;
        }
      }
      model.AddHint(work_by_nurse_day[nurse_idx][day], works);
      for (int shift_type_idx = 0;
           shift_type_idx < static_cast<int>(payload.shift_types.size());
           ++shift_type_idx) {
        bool works_type = false;
        for (int64_t key : hint) {
          const Shift& shift = payload.shifts[KeyShift(key, num_nurses)];
          if (KeyNurse(key, num_nurses) == nurse_idx &&
              GlobalDay(shift) == day &&
              shift.shift_type_idx == shift_type_idx) {
            works_type = true;
            break;
          }
        }
        model.AddHint(shift_type_by_nurse_day[nurse_idx][day][shift_type_idx],
                      works_type);
      }
    }
  }

  model.Minimize(objective);

  sat::Model solver_model;
  sat::SatParameters parameters;
  parameters.set_max_time_in_seconds(std::max(0.1, remaining_time));
  parameters.set_num_search_workers(1);
  parameters.set_random_seed(1);
  parameters.set_log_search_progress(false);
  solver_model.Add(sat::NewSatParameters(parameters));
  const sat::CpSolverResponse response =
      sat::SolveCpModel(model.Build(), &solver_model);
  if (response.status() != sat::CpSolverStatus::OPTIMAL &&
      response.status() != sat::CpSolverStatus::FEASIBLE) {
    if (!hard_seed.empty()) {
      return SolutionJson(payload, hard_seed, std::nullopt);
    }
    return std::nullopt;
  }

  std::unordered_set<int64_t> assignment_keys;
  for (const AssignmentVar& assignment_var : assignment_vars) {
    if (sat::SolutionBooleanValue(response, assignment_var.var)) {
      assignment_keys.insert(Key(assignment_var.shift_idx,
                                 assignment_var.nurse_idx, num_nurses));
    }
  }
  return SolutionJson(payload, assignment_keys, response.objective_value());
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
      throw std::runtime_error("usage: employee_scheduling_ortools <time_limit_seconds>");
    }
    const double time_limit = std::stod(argv[1]);
    const std::string input((std::istreambuf_iterator<char>(std::cin)),
                            std::istreambuf_iterator<char>());
    const InstancePayload payload = ParsePayload(input);
    const std::optional<json::object> solution = Solve(payload, time_limit);
    if (!solution.has_value()) {
      throw std::runtime_error("OR-Tools CP-SAT found no feasible solution");
    }
    std::cout << json::serialize(*solution) << '\n';
    return EXIT_SUCCESS;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return EXIT_FAILURE;
  }
}
