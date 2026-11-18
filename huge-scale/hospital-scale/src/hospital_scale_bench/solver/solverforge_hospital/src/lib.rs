mod constraints;

solverforge::planning_model! {
    root = "src";

    mod domain;

    pub use domain::Employee;
    pub use domain::HospitalPlan;
    pub use domain::Shift;
}
mod adapter;
mod solver;
