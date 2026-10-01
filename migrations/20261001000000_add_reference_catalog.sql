-- Official reference costs for every problem, not only job-shop.
--
-- The reference for a result decides whether its gap means anything, and until
-- now only job-shop had one: cvrp read a bundled .sol route (one feasible tour,
-- not an official value) and employee scheduling had no reference at all, so a
-- third of its results published a feasibility count with no quality figure and
-- no statement of why.
--
-- Every problem now pins its official values in a versioned catalog beside its
-- instances. This migration carries those values into the warehouse so existing
-- rows resolve against them, and generalises the resolution that only
-- job-shop performed:
--
--   cvrp     CVRPLIB Set X table (Uchoa et al. 2017), whose Opt column
--            separates a proven optimum from a best known upper bound.
--   jssp     ScheduleOpt best-known catalogue (values unchanged; the catalog is
--            now the same shape as the others).
--   employee INRC-II official test dataset. The competition publishes the test
--            instances with their reference solutions and no other solution
--            set; the canonical selection is that set. Values are the penalties
--            the official validator reports, so they are best known upper
--            bounds, not proven optima.
--
-- Reference kind is part of the claim, so it is stored rather than inferred: a
-- solver matching a proven optimum has no gap, while matching a best known
-- bound may still be above the true optimum.

CREATE TABLE IF NOT EXISTS benchmark_reference_catalog (
    benchmark_name text NOT NULL,
    dataset text NOT NULL,
    instance text NOT NULL,
    reference_cost double precision NOT NULL CHECK (reference_cost > 0),
    reference_kind text NOT NULL CHECK (reference_kind IN ('known_optimum', 'best_known_upper_bound')),
    source_name text NOT NULL,
    source_revision text NOT NULL,
    PRIMARY KEY (benchmark_name, dataset, instance)
);

COMMENT ON TABLE benchmark_reference_catalog IS
    'Official reference values per instance, generated from each problem''s versioned references.json by scripts/generate_reference_catalog.py and loaded by scripts/load_reference_catalog.py.';

-- The resolution the result view performs: a catalog value wins over whatever a
-- row recorded, because a row's value may predate the catalog or come from a
-- source that is not the official one (the cvrp .sol route). Rows with no
-- catalog entry keep their own value, so nothing is dropped.
CREATE OR REPLACE VIEW benchmark_reference_resolved AS
SELECT
    results.run_id,
    results.benchmark_name,
    results.dataset,
    results.instance,
    results.reference_cost AS recorded_reference_cost,
    catalog.reference_cost AS catalog_reference_cost,
    catalog.reference_kind,
    catalog.source_name,
    catalog.source_revision,
    COALESCE(catalog.reference_cost, results.reference_cost) AS effective_reference_cost
FROM benchmark_results AS results
LEFT JOIN benchmark_reference_catalog AS catalog
    ON catalog.benchmark_name = results.benchmark_name
   AND catalog.dataset = results.dataset
   AND catalog.instance = results.instance;

COMMENT ON VIEW benchmark_reference_resolved IS
    'Per-result effective reference: the pinned official catalog value where one exists, else the value the run recorded.';
