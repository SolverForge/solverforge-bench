mod constraints;

solverforge::planning_model! {
    root = "src";

    mod domain;

    pub use domain::ContractData;
    pub use domain::NrpPlan;
    pub use domain::NrpShift;
    pub use domain::NurseData;
    pub use domain::NurseHistoryData;
    pub use domain::NurseIndex;
    pub use domain::NurseShiftTypeIndex;
    pub use domain::ProblemData;
    pub use domain::ShiftTypeData;
}
mod adapter;
mod solver;
