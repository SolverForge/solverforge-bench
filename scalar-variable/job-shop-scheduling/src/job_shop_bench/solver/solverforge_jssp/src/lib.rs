mod constraints;

solverforge::planning_model! {
    root = "src";

    mod domain;

    pub use domain::JsspOperation;
    pub use domain::JsspPlan;
    pub use domain::MachineSequence;
}
mod adapter;
