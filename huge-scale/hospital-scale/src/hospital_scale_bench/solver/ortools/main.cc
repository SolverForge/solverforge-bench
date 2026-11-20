#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <iterator>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
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

// The validator's ruleset; scripts/verify_model_parity.py pins these.
constexpr int64_t MINIMUM_REST_MINUTES = 600;
constexpr int64_t PREFERENCE_SOFT = 10;
constexpr int64_t MINUTES_PER_DAY = 1440;

struct Employee {
  std::set<int64_t> unavailable_days;
  std::set<int64_t> desired_days;
  std::set<int64_t> undesired_days;
};

struct Shift {
  int64_t start;
  int64_t end;
  int skill;
};

struct HospitalInstance {
  int horizon_days;
  std::vector<std::vector<int>> skill_candidates;
  std::vector<Employee> employees;
  std::vector<Shift> shifts;
};

// Shifts with the same start, end and skill are interchangeable under every
// rule, so the model decides which employees work each slot type and the
// decoder hands them to that type's shifts in instance order.
struct SlotType {
  int64_t start;
  int64_t end;
  int skill;
  int64_t first_day;
  int64_t last_day;
  std::vector<int> shifts;
};

struct EmployeeSlot {
  int slot_type;
  sat::BoolVar var;
};

struct SolveResult {
  json::object output;
  bool feasible;
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

std::set<int64_t> IntSet(const json::value& value) {
  std::set<int64_t> values;
  for (const json::value& item : value.as_array()) {
    values.insert(AsInt(item));
  }
  return values;
}

HospitalInstance ParseInput(const std::string& input) {
  const json::object root = json::parse(input).as_object();
  HospitalInstance instance;
  instance.horizon_days = static_cast<int>(AsInt(root.at("horizon_days")));
  for (const json::value& candidates : root.at("skill_candidates").as_array()) {
    std::vector<int> employees;
    for (const json::value& employee : candidates.as_array()) {
      employees.push_back(static_cast<int>(AsInt(employee)));
    }
    instance.skill_candidates.push_back(std::move(employees));
  }
  for (const json::value& value : root.at("employees").as_array()) {
    const json::object& employee = value.as_object();
    instance.employees.push_back(Employee{
        IntSet(employee.at("unavailable_days")),
        IntSet(employee.at("desired_days")),
        IntSet(employee.at("undesired_days")),
    });
  }
  for (const json::value& value : root.at("shifts").as_array()) {
    const json::object& shift = value.as_object();
    const int skill = static_cast<int>(AsInt(shift.at("required_skill")));
    if (skill < 0 || skill >= static_cast<int>(instance.skill_candidates.size())) {
      throw std::runtime_error("shift names an unknown skill");
    }
    instance.shifts.push_back(Shift{AsInt(shift.at("start")), AsInt(shift.at("end")), skill});
  }
  for (const std::vector<int>& candidates : instance.skill_candidates) {
    for (int employee : candidates) {
      if (employee < 0 || employee >= static_cast<int>(instance.employees.size())) {
        throw std::runtime_error("skill_candidates names an unknown employee");
      }
    }
  }
  return instance;
}

std::vector<SlotType> BuildSlotTypes(const HospitalInstance& instance) {
  std::map<std::tuple<int64_t, int64_t, int>, int> index_by_key;
  std::vector<SlotType> types;
  for (int shift_idx = 0; shift_idx < static_cast<int>(instance.shifts.size()); ++shift_idx) {
    const Shift& shift = instance.shifts[shift_idx];
    const auto key = std::make_tuple(shift.start, shift.end, shift.skill);
    auto [it, inserted] = index_by_key.emplace(key, static_cast<int>(types.size()));
    if (inserted) {
      types.push_back(SlotType{shift.start, shift.end, shift.skill, shift.start / MINUTES_PER_DAY,
                               (shift.end - 1) / MINUTES_PER_DAY, {}});
    }
    types[it->second].shifts.push_back(shift_idx);
  }
  return types;
}

int64_t TouchedCount(const SlotType& type, const std::set<int64_t>& days) {
  int64_t count = 0;
  for (int64_t day = type.first_day; day <= type.last_day; ++day) {
    count += days.count(day);
  }
  return count;
}

// Two shifts conflict when they overlap or leave less than the minimum rest.
bool TimeConflict(const SlotType& left, const SlotType& right) {
  if (left.start < right.end && right.start < left.end) {
    return true;
  }
  const int64_t gap = left.end <= right.start ? right.start - left.end : left.start - right.end;
  return gap < MINIMUM_REST_MINUTES;
}

bool ShareDay(const SlotType& left, const SlotType& right) {
  return left.first_day <= right.last_day && right.first_day <= left.last_day;
}

json::object FairStartWitness(const sat::CpModelProto& proto) {
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

const char* CpSatStatusName(sat::CpSolverStatus status) {
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
    default:
      return "UNRECOGNIZED";
  }
}

void AddSolverMetadata(json::object* output, const sat::CpSolverResponse& response,
                       const sat::CpModelProto& proto, size_t slot_types) {
  output->emplace("native_solver_status", CpSatStatusName(response.status()));
  output->emplace("cp_sat_wall_time_seconds", response.wall_time());
  output->emplace("cp_sat_user_time_seconds", response.user_time());
  output->emplace("cp_sat_num_conflicts", response.num_conflicts());
  output->emplace("cp_sat_num_branches", response.num_branches());
  output->emplace("cp_sat_model_variables", proto.variables_size());
  output->emplace("cp_sat_model_constraints", proto.constraints_size());
  output->emplace("slot_types", slot_types);
  if (response.status() == sat::CpSolverStatus::OPTIMAL ||
      response.status() == sat::CpSolverStatus::FEASIBLE) {
    output->emplace("cp_sat_objective", response.objective_value());
    output->emplace("cp_sat_best_bound", response.best_objective_bound());
  }
}

SolveResult Solve(const HospitalInstance& instance, double time_limit) {
  const std::vector<SlotType> types = BuildSlotTypes(instance);
  const int num_employees = static_cast<int>(instance.employees.size());
  sat::CpModelBuilder model;
  std::vector<std::vector<EmployeeSlot>> slots_by_employee(num_employees);
  sat::LinearExpr objective;

  for (int type_idx = 0; type_idx < static_cast<int>(types.size()); ++type_idx) {
    const SlotType& type = types[type_idx];
    std::vector<sat::BoolVar> staffed;
    for (int employee_idx : instance.skill_candidates[type.skill]) {
      const Employee& employee = instance.employees[employee_idx];
      // unavailable_employee is hard: such a pair never enters the model.
      if (TouchedCount(type, employee.unavailable_days) > 0) {
        continue;
      }
      const sat::BoolVar var = model.NewBoolVar();
      staffed.push_back(var);
      slots_by_employee[employee_idx].push_back(EmployeeSlot{type_idx, var});
      const int64_t preference = PREFERENCE_SOFT * (TouchedCount(type, employee.undesired_days) -
                                                    TouchedCount(type, employee.desired_days));
      if (preference != 0) {
        objective += sat::LinearExpr::Term(var, preference);
      }
    }
    // assigned_shift: every shift of the type is staffed, each by one employee.
    model.AddEquality(sat::LinearExpr::Sum(staffed), static_cast<int64_t>(type.shifts.size()));
  }

  for (int employee_idx = 0; employee_idx < num_employees; ++employee_idx) {
    std::vector<EmployeeSlot>& slots = slots_by_employee[employee_idx];
    if (slots.empty()) {
      continue;
    }
    std::sort(slots.begin(), slots.end(), [&types](const EmployeeSlot& a, const EmployeeSlot& b) {
      return std::make_pair(types[a.slot_type].start, a.slot_type) <
             std::make_pair(types[b.slot_type].start, b.slot_type);
    });
    // one_shift_per_day, which also covers every overlap and short rest
    // between two shifts touching the same day.
    std::map<int64_t, std::vector<sat::BoolVar>> by_day;
    for (const EmployeeSlot& slot : slots) {
      const SlotType& type = types[slot.slot_type];
      for (int64_t day = type.first_day; day <= type.last_day; ++day) {
        by_day[day].push_back(slot.var);
      }
    }
    for (const auto& [day, vars] : by_day) {
      if (vars.size() > 1) {
        model.AddAtMostOne(vars);
      }
    }
    // overlapping_shift and minimum_rest across different days.
    for (size_t i = 0; i < slots.size(); ++i) {
      const SlotType& left = types[slots[i].slot_type];
      for (size_t j = i + 1; j < slots.size(); ++j) {
        const SlotType& right = types[slots[j].slot_type];
        if (right.start >= left.end + MINIMUM_REST_MINUTES) {
          break;
        }
        if (!ShareDay(left, right) && TimeConflict(left, right)) {
          model.AddAtMostOne({slots[i].var, slots[j].var});
        }
      }
    }
    // balance_assignments: + (assigned shift count)^2.
    std::vector<sat::BoolVar> vars;
    for (const EmployeeSlot& slot : slots) {
      vars.push_back(slot.var);
    }
    const int64_t max_count = std::min<int64_t>(static_cast<int64_t>(vars.size()), instance.horizon_days);
    const sat::IntVar count = model.NewIntVar(operations_research::Domain(0, max_count));
    model.AddEquality(count, sat::LinearExpr::Sum(vars));
    const sat::IntVar squared = model.NewIntVar(operations_research::Domain(0, max_count * max_count));
    model.AddMultiplicationEquality(squared, {count, count});
    objective += squared;
  }

  model.Minimize(objective);

  sat::Model solver_model;
  sat::SatParameters parameters;
  parameters.set_max_time_in_seconds(std::max(0.1, time_limit));
  parameters.set_num_search_workers(1);
  parameters.set_random_seed(1);
  parameters.set_log_search_progress(false);
  solver_model.Add(sat::NewSatParameters(parameters));
  const sat::CpModelProto proto = model.Build();
  const json::object fair_start_witness = FairStartWitness(proto);
  const sat::CpSolverResponse response = sat::SolveCpModel(proto, &solver_model);

  json::object output;
  output["fair_start_witness"] = fair_start_witness;
  AddSolverMetadata(&output, response, proto, types.size());
  if (response.status() != sat::CpSolverStatus::OPTIMAL &&
      response.status() != sat::CpSolverStatus::FEASIBLE) {
    return SolveResult{std::move(output), false};
  }

  std::vector<std::vector<int>> staff_by_type(types.size());
  for (int employee_idx = 0; employee_idx < num_employees; ++employee_idx) {
    for (const EmployeeSlot& slot : slots_by_employee[employee_idx]) {
      if (sat::SolutionBooleanValue(response, slot.var)) {
        staff_by_type[slot.slot_type].push_back(employee_idx);
      }
    }
  }
  std::vector<int> assignment(instance.shifts.size(), -1);
  std::vector<int64_t> counts(num_employees, 0);
  int64_t fresh_cost = 0;
  for (size_t type_idx = 0; type_idx < types.size(); ++type_idx) {
    const SlotType& type = types[type_idx];
    const std::vector<int>& staff = staff_by_type[type_idx];
    if (staff.size() != type.shifts.size()) {
      throw std::runtime_error("CP-SAT staffed a slot type with the wrong head count");
    }
    for (size_t k = 0; k < staff.size(); ++k) {
      const Employee& employee = instance.employees[staff[k]];
      assignment[type.shifts[k]] = staff[k];
      counts[staff[k]] += 1;
      fresh_cost += PREFERENCE_SOFT * (TouchedCount(type, employee.undesired_days) -
                                       TouchedCount(type, employee.desired_days));
    }
  }
  for (int64_t count : counts) {
    fresh_cost += count * count;
  }

  json::array assignments;
  for (int employee_idx : assignment) {
    assignments.emplace_back(employee_idx);
  }
  output["assignments"] = std::move(assignments);
  output["reported_cost"] = static_cast<int64_t>(std::llround(response.objective_value()));
  output["fresh_cost"] = fresh_cost;
  return SolveResult{std::move(output), true};
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
      throw std::runtime_error("usage: hospital_scale_ortools <time_limit_seconds>");
    }
    const double time_limit = std::stod(argv[1]);
    const std::string input((std::istreambuf_iterator<char>(std::cin)),
                            std::istreambuf_iterator<char>());
    const HospitalInstance instance = ParseInput(input);
    const SolveResult result = Solve(instance, time_limit);
    std::cout << json::serialize(result.output) << '\n';
    if (!result.feasible) {
      std::cerr << "OR-Tools CP-SAT found no feasible solution" << '\n';
      return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return EXIT_FAILURE;
  }
}
