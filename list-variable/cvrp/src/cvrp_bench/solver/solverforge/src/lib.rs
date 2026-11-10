mod constraints;

solverforge::planning_model! {
    root = "src";

    mod domain;

    pub use domain::Customer;
    pub use domain::CvrpPlan;
    pub use domain::Route;
}
mod adapter;
