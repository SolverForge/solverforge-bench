use super::*;

#[test]
fn build_plan_initializes_customer_values_and_routes() {
    let input = InstanceInput {
        dimension: 4,
        capacity: 10,
        demand: vec![0, 1, 2, 3],
        depot: 0,
        distance_matrix: vec![
            vec![0, 2, 3, 4],
            vec![2, 0, 5, 6],
            vec![3, 5, 0, 7],
            vec![4, 6, 7, 0],
        ],
    };

    let plan = build_plan(input, 9);
    let shared_ptr = Arc::as_ptr(&plan.shared) as usize;

    assert_eq!(
        plan.customers
            .iter()
            .map(|customer| customer.id)
            .collect::<Vec<_>>(),
        vec![1, 2, 3]
    );
    assert_eq!(plan.customer_values, vec![1, 2, 3]);
    assert_eq!(plan.routes.len(), 3);
    assert!(plan.routes.iter().all(|route| route.visits.is_empty()));
    assert!(plan
        .routes
        .iter()
        .all(|route| route.data_addr == shared_ptr));
    assert_eq!(plan.time_limit_secs, 9);
}
