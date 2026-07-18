ALTER TABLE benchmark_runs
    ADD COLUMN expected_result_count integer,
    ADD COLUMN expected_matrix_sha256 text,
    ADD COLUMN observed_matrix_sha256 text,
    ADD CONSTRAINT benchmark_runs_expected_matrix_contract CHECK (
        (expected_result_count IS NULL AND expected_matrix_sha256 IS NULL)
        OR (
            expected_result_count > 0
            AND expected_matrix_sha256 ~ '^[0-9a-f]{64}$'
        )
    ),
    ADD CONSTRAINT benchmark_runs_observed_matrix_hash CHECK (
        observed_matrix_sha256 IS NULL
        OR observed_matrix_sha256 ~ '^[0-9a-f]{64}$'
    );

CREATE TABLE benchmark_run_matrix_entries (
    run_id uuid NOT NULL REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    dataset text NOT NULL,
    dataset_set text NOT NULL,
    instance text NOT NULL,
    solver text NOT NULL,
    time_limit_seconds integer NOT NULL CHECK (time_limit_seconds > 0),
    PRIMARY KEY (
        run_id,
        dataset,
        dataset_set,
        instance,
        solver,
        time_limit_seconds
    )
);

ALTER TABLE benchmark_results
    ADD CONSTRAINT benchmark_results_matrix_key_unique UNIQUE (
        run_id,
        dataset,
        dataset_set,
        instance,
        solver,
        time_limit_seconds
    ),
    ADD CONSTRAINT benchmark_results_expected_matrix_fk
        FOREIGN KEY (
            run_id,
            dataset,
            dataset_set,
            instance,
            solver,
            time_limit_seconds
        )
        REFERENCES benchmark_run_matrix_entries (
            run_id,
            dataset,
            dataset_set,
            instance,
            solver,
            time_limit_seconds
        )
        NOT VALID;

CREATE INDEX benchmark_run_matrix_entries_run_idx
    ON benchmark_run_matrix_entries (run_id);

CREATE VIEW benchmark_run_publication_audit AS
WITH expected_stats AS (
    SELECT
        run_id,
        COUNT(*)::integer AS expected_catalog_count
    FROM benchmark_run_matrix_entries
    GROUP BY run_id
),
actual_stats AS (
    SELECT
        run_id,
        COUNT(*)::integer AS actual_result_count,
        BOOL_AND(fair_start_valid) AS all_fair_start_valid
    FROM benchmark_results
    GROUP BY run_id
),
version_stats AS (
    SELECT
        versions.run_id,
        COUNT(*)::integer AS solver_version_count,
        BOOL_AND(
            versions.solver_version <> 'unknown'
            AND btrim(versions.solver_version) <> ''
            AND versions.version_source <> 'unregistered'
            AND versions.metadata ->> 'provenance_schema_version' = '1'
            AND versions.metadata ->> 'provenance_sha256'
                ~ '^[0-9a-f]{64}$'
            AND CASE
                WHEN jsonb_typeof(
                    versions.metadata -> 'runtime_artifacts'
                ) = 'array'
                THEN jsonb_array_length(
                    versions.metadata -> 'runtime_artifacts'
                ) > 0
                AND NOT EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(
                        versions.metadata -> 'runtime_artifacts'
                    ) AS artifact
                    WHERE COALESCE(artifact ->> 'kind', '') = ''
                       OR COALESCE(artifact ->> 'sha256', '')
                            !~ '^[0-9a-f]{64}$'
                       OR COALESCE(artifact ->> 'size', '') !~ '^[0-9]+$'
                )
                ELSE false
            END
        ) AS solver_provenance_valid
    FROM benchmark_solver_versions AS versions
    GROUP BY versions.run_id
),
metrics AS (
    SELECT
        runs.id AS run_id,
        runs.status = 'completed' AS status_completed,
        runs.git_commit ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'
            AS git_commit_valid,
        runs.git_dirty IS FALSE AS git_clean,
        runs.expected_result_count,
        runs.expected_matrix_sha256,
        runs.observed_matrix_sha256,
        runs.result_count AS recorded_result_count,
        cardinality(runs.solvers) AS configured_solver_count,
        COALESCE(expected.expected_catalog_count, 0)
            AS expected_catalog_count,
        COALESCE(actual.actual_result_count, 0) AS actual_result_count,
        COALESCE(actual.all_fair_start_valid, false)
            AS all_fair_start_valid,
        COALESCE(versions.solver_version_count, 0)
            AS solver_version_count,
        COALESCE(versions.solver_provenance_valid, false)
            AS solver_provenance_valid,
        NOT EXISTS (
            SELECT 1
            FROM unnest(runs.solvers) AS configured(solver)
            WHERE NOT EXISTS (
                SELECT 1
                FROM benchmark_run_matrix_entries AS expected_solver
                WHERE expected_solver.run_id = runs.id
                  AND expected_solver.solver = configured.solver
            )
        )
        AND NOT EXISTS (
            SELECT 1
            FROM benchmark_run_matrix_entries AS expected_solver
            WHERE expected_solver.run_id = runs.id
              AND NOT (expected_solver.solver = ANY(runs.solvers))
        )
        AND NOT EXISTS (
            SELECT 1
            FROM unnest(runs.time_limits_seconds) AS configured(time_limit)
            WHERE NOT EXISTS (
                SELECT 1
                FROM benchmark_run_matrix_entries AS expected_limit
                WHERE expected_limit.run_id = runs.id
                  AND expected_limit.time_limit_seconds = configured.time_limit
            )
        )
        AND NOT EXISTS (
            SELECT 1
            FROM benchmark_run_matrix_entries AS expected_limit
            WHERE expected_limit.run_id = runs.id
              AND NOT (
                  expected_limit.time_limit_seconds
                    = ANY(runs.time_limits_seconds)
              )
        ) AS catalog_matches_run_config,
        NOT EXISTS (
            SELECT 1
            FROM unnest(runs.solvers) AS configured(solver)
            WHERE NOT EXISTS (
                SELECT 1
                FROM benchmark_solver_versions AS configured_version
                WHERE configured_version.run_id = runs.id
                  AND configured_version.solver = configured.solver
            )
        )
        AND NOT EXISTS (
            SELECT 1
            FROM benchmark_solver_versions AS unexpected_version
            WHERE unexpected_version.run_id = runs.id
              AND NOT (unexpected_version.solver = ANY(runs.solvers))
        ) AS version_catalog_matches_run_config,
        NOT EXISTS (
            SELECT 1
            FROM benchmark_results AS result_identity
            WHERE result_identity.run_id = runs.id
              AND (
                  result_identity.benchmark_name <> runs.benchmark_name
                  OR result_identity.benchmark_category
                        <> runs.benchmark_category
              )
        ) AS result_identity_valid,
        (
            SELECT COUNT(*)::integer
            FROM benchmark_run_matrix_entries AS expected_row
            LEFT JOIN benchmark_results AS actual_row
              ON actual_row.run_id = expected_row.run_id
             AND actual_row.dataset = expected_row.dataset
             AND actual_row.dataset_set = expected_row.dataset_set
             AND actual_row.instance = expected_row.instance
             AND actual_row.solver = expected_row.solver
             AND actual_row.time_limit_seconds
                    = expected_row.time_limit_seconds
            WHERE expected_row.run_id = runs.id
              AND actual_row.id IS NULL
        ) AS missing_result_count,
        (
            SELECT COUNT(*)::integer
            FROM benchmark_results AS actual_row
            LEFT JOIN benchmark_run_matrix_entries AS expected_row
              ON expected_row.run_id = actual_row.run_id
             AND expected_row.dataset = actual_row.dataset
             AND expected_row.dataset_set = actual_row.dataset_set
             AND expected_row.instance = actual_row.instance
             AND expected_row.solver = actual_row.solver
             AND expected_row.time_limit_seconds
                    = actual_row.time_limit_seconds
            WHERE actual_row.run_id = runs.id
              AND expected_row.run_id IS NULL
        ) AS unexpected_result_count
    FROM benchmark_runs AS runs
    LEFT JOIN expected_stats AS expected ON expected.run_id = runs.id
    LEFT JOIN actual_stats AS actual ON actual.run_id = runs.id
    LEFT JOIN version_stats AS versions ON versions.run_id = runs.id
)
SELECT
    metrics.*,
    status_completed
    AND git_commit_valid
    AND git_clean
    AND expected_result_count > 0
    AND expected_matrix_sha256 ~ '^[0-9a-f]{64}$'
    AND observed_matrix_sha256 = expected_matrix_sha256
    AND expected_catalog_count = expected_result_count
    AND actual_result_count = expected_result_count
    AND recorded_result_count = expected_result_count
    AND missing_result_count = 0
    AND unexpected_result_count = 0
    AND catalog_matches_run_config
    AND result_identity_valid
    AND all_fair_start_valid
    AND solver_version_count = configured_solver_count
    AND version_catalog_matches_run_config
    AND solver_provenance_valid AS publication_ready,
    ARRAY_REMOVE(
        ARRAY[
            CASE WHEN NOT status_completed THEN 'run_not_completed' END,
            CASE WHEN NOT git_commit_valid THEN 'git_commit_invalid' END,
            CASE WHEN NOT git_clean THEN 'git_tree_dirty' END,
            CASE
                WHEN expected_result_count IS NULL
                  OR expected_result_count <= 0
                  OR expected_matrix_sha256 IS NULL
                THEN 'expected_matrix_missing'
            END,
            CASE
                WHEN expected_catalog_count
                    <> COALESCE(expected_result_count, -1)
                THEN 'expected_catalog_mismatch'
            END,
            CASE
                WHEN actual_result_count <> COALESCE(expected_result_count, -1)
                  OR recorded_result_count
                        <> COALESCE(expected_result_count, -1)
                  OR missing_result_count <> 0
                  OR unexpected_result_count <> 0
                THEN 'result_matrix_incomplete'
            END,
            CASE
                WHEN observed_matrix_sha256 IS DISTINCT FROM
                    expected_matrix_sha256
                THEN 'observed_matrix_hash_mismatch'
            END,
            CASE
                WHEN NOT catalog_matches_run_config
                THEN 'matrix_config_mismatch'
            END,
            CASE
                WHEN NOT result_identity_valid THEN 'result_identity_mismatch'
            END,
            CASE
                WHEN NOT all_fair_start_valid THEN 'fair_start_invalid'
            END,
            CASE
                WHEN NOT version_catalog_matches_run_config
                  OR NOT solver_provenance_valid
                THEN 'solver_provenance_incomplete'
            END
        ],
        NULL
    )::text[] AS publication_failures
FROM metrics;

CREATE VIEW publishable_benchmark_runs AS
SELECT runs.*
FROM benchmark_runs AS runs
JOIN benchmark_run_publication_audit AS audit ON audit.run_id = runs.id
WHERE audit.publication_ready;

CREATE VIEW publishable_benchmark_result_facts AS
SELECT facts.*
FROM benchmark_result_facts AS facts
JOIN publishable_benchmark_runs AS runs ON runs.id = facts.run_id;

CREATE VIEW latest_publishable_benchmark_runs AS
SELECT DISTINCT ON (nightly, run_kind, benchmark_name, release_tag)
    publishable.*
FROM publishable_benchmark_runs AS publishable
ORDER BY
    nightly,
    run_kind,
    benchmark_name,
    release_tag,
    completed_at DESC,
    id DESC;

CREATE VIEW latest_publishable_benchmark_result_facts AS
SELECT facts.*
FROM publishable_benchmark_result_facts AS facts
JOIN latest_publishable_benchmark_runs AS latest
  ON latest.id = facts.run_id;
