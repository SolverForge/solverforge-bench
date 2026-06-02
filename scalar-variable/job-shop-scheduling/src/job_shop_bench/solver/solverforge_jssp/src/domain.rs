use solverforge::prelude::*;

#[problem_fact]
pub struct JsspOperation {
    #[planning_id]
    pub id: usize,
    pub job_id: usize,
    pub op_index: usize,
    pub machine_id: usize,
    pub duration: usize,
    pub successor_id: Option<usize>,
}

#[planning_entity]
pub struct MachineSequence {
    #[planning_id]
    pub id: usize,

    #[planning_list_variable(
        element_collection = "operations",
        element_owner_fn = "operation_machine_owner",
        construction_element_order_key = "operation_construction_order",
        precedence_duration_fn = "operation_duration",
        precedence_successors_fn = "operation_job_successors"
    )]
    pub operations: Vec<usize>,
}

pub struct ScheduleEvaluation {
    pub starts: Vec<Option<usize>>,
    pub makespan: usize,
    pub hard_penalty: usize,
}

#[planning_solution(
    constraints = "crate::constraints::define_constraints",
    config = "crate::domain::solver_config_for_plan",
    solver_toml = "../solver.toml"
)]
pub struct JsspPlan {
    #[problem_fact_collection]
    pub operations: Vec<JsspOperation>,

    #[planning_entity_collection]
    pub machine_sequences: Vec<MachineSequence>,

    #[planning_score]
    pub score: Option<HardSoftScore>,

    pub num_jobs: usize,
    pub num_machines: usize,
    pub time_limit_secs: u64,
}

impl JsspPlan {
    pub fn evaluate_schedule(&self) -> ScheduleEvaluation {
        let operation_count = self.operations.len();
        let mut hard_penalty = 0usize;
        let mut assigned_counts = vec![0usize; operation_count];
        let mut edges = vec![Vec::new(); operation_count];
        let mut indegree = vec![0usize; operation_count];

        let job_count = self
            .num_jobs
            .max(self.operations.iter().map(|operation| operation.job_id + 1).max().unwrap_or(0));
        let mut operations_by_job = vec![Vec::new(); job_count];
        for operation in &self.operations {
            if operation.job_id < operations_by_job.len() {
                operations_by_job[operation.job_id].push((operation.op_index, operation.id));
            }
        }
        for job_operations in &mut operations_by_job {
            job_operations.sort_unstable_by_key(|(op_index, _)| *op_index);
            for pair in job_operations.windows(2) {
                add_edge(pair[0].1, pair[1].1, &mut edges, &mut indegree);
            }
        }

        for machine in &self.machine_sequences {
            if machine.id >= self.num_machines {
                hard_penalty += machine.operations.len();
            }
            for &operation_id in &machine.operations {
                let Some(operation) = self.operations.get(operation_id) else {
                    hard_penalty += 1;
                    continue;
                };
                assigned_counts[operation_id] += 1;
                if operation.machine_id != machine.id {
                    hard_penalty += 1;
                }
            }
            for pair in machine.operations.windows(2) {
                add_edge(pair[0], pair[1], &mut edges, &mut indegree);
            }
        }

        for count in assigned_counts {
            match count {
                0 => hard_penalty += 1,
                1 => {}
                extra => hard_penalty += extra - 1,
            }
        }

        let mut starts = vec![None; operation_count];
        let mut earliest = vec![0usize; operation_count];
        let mut ready = std::collections::VecDeque::new();
        for (operation_id, degree) in indegree.iter().enumerate() {
            if *degree == 0 {
                ready.push_back(operation_id);
            }
        }

        let mut processed = 0usize;
        while let Some(operation_id) = ready.pop_front() {
            processed += 1;
            starts[operation_id] = Some(earliest[operation_id]);
            let finish = earliest[operation_id] + self.operations[operation_id].duration;
            for &next_id in &edges[operation_id] {
                earliest[next_id] = earliest[next_id].max(finish);
                indegree[next_id] -= 1;
                if indegree[next_id] == 0 {
                    ready.push_back(next_id);
                }
            }
        }

        if processed < operation_count {
            hard_penalty += operation_count - processed;
        }

        let makespan = starts
            .iter()
            .enumerate()
            .filter_map(|(operation_id, start)| {
                start.map(|value| value + self.operations[operation_id].duration)
            })
            .max()
            .unwrap_or(0);

        ScheduleEvaluation {
            starts,
            makespan,
            hard_penalty,
        }
    }
}

pub fn solver_config_for_plan(
    plan: &JsspPlan,
    config: solverforge::SolverConfig,
) -> solverforge::SolverConfig {
    config.with_termination_seconds(plan.time_limit_secs.max(1))
}

pub fn operation_machine_owner(plan: &JsspPlan, operation_id: usize) -> Option<usize> {
    plan.operations
        .get(operation_id)
        .map(|operation| operation.machine_id)
}

pub fn operation_construction_order(plan: &JsspPlan, operation_id: usize) -> i64 {
    plan.operations.get(operation_id).map_or(0, |operation| {
        (operation.op_index as i64) * 1_000_000 - operation.duration as i64
    })
}

pub fn operation_duration(plan: &JsspPlan, operation_id: usize) -> usize {
    plan.operations
        .get(operation_id)
        .map_or(0, |operation| operation.duration)
}

pub fn operation_job_successors(plan: &JsspPlan, operation_id: usize, out: &mut Vec<usize>) {
    let Some(operation) = plan.operations.get(operation_id) else {
        return;
    };
    if let Some(successor_id) = operation.successor_id {
        out.push(successor_id);
    }
}

fn add_edge(
    from: usize,
    to: usize,
    edges: &mut [Vec<usize>],
    indegree: &mut [usize],
) {
    if from >= edges.len() || to >= edges.len() {
        return;
    }
    edges[from].push(to);
    indegree[to] += 1;
}
