mod constraints;

solverforge::planning_model! {
    root = "src";

    mod domain;

    pub use domain::Delivery;
    pub use domain::DeliveryPlan;
    pub use domain::Vehicle;
}
mod adapter;
mod solver;
