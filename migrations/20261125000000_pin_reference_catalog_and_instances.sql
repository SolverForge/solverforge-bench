-- Pin every run to the reference catalog and the instances it was measured on.
--
-- Until now the warehouse carried only the current reference values, loaded by
-- hand with `make load-reference-catalogs`. Nothing in the run path loaded them,
-- so a catalog change could sit in git while the warehouse kept resolving the
-- old values, and a run recorded no trace of which values it was graded
-- against. Instances were not recorded at all beyond their names, so a run on a
-- modified instance looked identical to a run on the original.
--
-- The repository stays the only source of both. The harness hands the
-- committed catalog and the hash of every loaded instance to the warehouse when
-- it opens a run, and the warehouse stores them through the two functions
-- below:
--
--   benchmark_sync_reference_catalog   makes benchmark_reference_catalog equal
--                                      the committed catalogs and records the
--                                      catalog as an immutable, hash-identified
--                                      version.
--   benchmark_record_run_instances     records the input hash of every instance
--                                      the run loads, exactly once per matrix
--                                      instance.
--
-- Runs opened from here on must carry both pins; publication requires them, and
-- requires every reference a row recorded to equal its pinned catalog value.
-- Runs recorded before this migration predate pinning and are marked so rather
-- than given a catalog they never saw.

CREATE TABLE benchmark_reference_catalog_versions (
    sha256 text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    entries jsonb NOT NULL CHECK (
        jsonb_typeof(entries) = 'array' AND jsonb_array_length(entries) > 0
    ),
    entry_count integer NOT NULL CHECK (entry_count > 0),
    sources jsonb NOT NULL CHECK (jsonb_typeof(sources) = 'array'),
    first_loaded_at timestamptz NOT NULL DEFAULT now(),
    last_loaded_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE benchmark_reference_catalog_versions IS
    'Every reference catalog the warehouse has been synced to, identified by the SHA-256 of its canonical entries. benchmark_reference_catalog holds the current version; this table keeps each version a run was graded against.';

-- Existing rows get false: they were recorded before pinning existed. The
-- default then flips to true, so every run opened from now on must pin.
ALTER TABLE benchmark_runs
    ADD COLUMN input_pinning_required boolean NOT NULL DEFAULT false,
    ADD COLUMN reference_catalog_sha256 text
        REFERENCES benchmark_reference_catalog_versions (sha256);

ALTER TABLE benchmark_runs
    ALTER COLUMN input_pinning_required SET DEFAULT true;

ALTER TABLE benchmark_runs
    ADD CONSTRAINT benchmark_runs_reference_catalog_pinned
    CHECK (NOT input_pinning_required OR reference_catalog_sha256 IS NOT NULL);

COMMENT ON COLUMN benchmark_runs.input_pinning_required IS
    'False only for runs recorded before reference catalogs and instance hashes were pinned per run.';
COMMENT ON COLUMN benchmark_runs.reference_catalog_sha256 IS
    'The reference catalog version this run was graded against.';

CREATE TABLE benchmark_instances (
    benchmark_name text NOT NULL,
    dataset text NOT NULL,
    instance text NOT NULL,
    input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    instance_size integer,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    first_run_id uuid REFERENCES benchmark_runs (id) ON DELETE SET NULL,
    PRIMARY KEY (benchmark_name, dataset, instance, input_sha256)
);

COMMENT ON TABLE benchmark_instances IS
    'Every distinct version of an instance a run has loaded: the SHA-256 of the solver input the harness built from the committed instance files. One name with several hashes means the instance changed.';

CREATE TABLE benchmark_run_instances (
    run_id uuid NOT NULL REFERENCES benchmark_runs (id) ON DELETE CASCADE,
    benchmark_name text NOT NULL,
    dataset text NOT NULL,
    dataset_set text NOT NULL,
    instance text NOT NULL,
    input_sha256 text NOT NULL,
    PRIMARY KEY (run_id, dataset, dataset_set, instance),
    FOREIGN KEY (benchmark_name, dataset, instance, input_sha256)
        REFERENCES benchmark_instances (
            benchmark_name, dataset, instance, input_sha256
        )
);

CREATE INDEX benchmark_run_instances_version_idx
    ON benchmark_run_instances (benchmark_name, dataset, instance, input_sha256);

COMMENT ON TABLE benchmark_run_instances IS
    'The exact instance version each run loaded, one row per matrix instance.';

CREATE FUNCTION benchmark_sync_reference_catalog(p_entries jsonb, p_sources jsonb)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    canonical jsonb;
    entry_total integer;
    distinct_total integer;
    digest text;
BEGIN
    IF p_entries IS NULL
       OR jsonb_typeof(p_entries) <> 'array'
       OR jsonb_array_length(p_entries) = 0 THEN
        RAISE EXCEPTION 'reference catalog sync needs a nonempty entry array';
    END IF;
    IF p_sources IS NULL OR jsonb_typeof(p_sources) <> 'array' THEN
        RAISE EXCEPTION 'reference catalog sync needs a source array';
    END IF;

    -- Suites open runs concurrently; one sync at a time keeps the catalog and
    -- its version row consistent.
    PERFORM pg_advisory_xact_lock(hashtext('benchmark_reference_catalog'));

    -- Canonical order, so one catalog always hashes to one version.
    SELECT
        jsonb_agg(
            jsonb_build_object(
                'benchmark_name', entry ->> 'benchmark_name',
                'dataset', entry ->> 'dataset',
                'instance', entry ->> 'instance',
                'reference_cost', (entry ->> 'reference_cost')::double precision,
                'reference_kind', entry ->> 'reference_kind',
                'source_name', entry ->> 'source_name',
                'source_revision', entry ->> 'source_revision'
            )
            ORDER BY
                entry ->> 'benchmark_name',
                entry ->> 'dataset',
                entry ->> 'instance'
        ),
        count(*),
        count(DISTINCT (
            entry ->> 'benchmark_name',
            entry ->> 'dataset',
            entry ->> 'instance'
        ))
    INTO canonical, entry_total, distinct_total
    FROM jsonb_array_elements(p_entries) AS entry;

    IF distinct_total <> entry_total THEN
        RAISE EXCEPTION 'reference catalog repeats an instance (% entries, % distinct)',
            entry_total, distinct_total;
    END IF;

    digest := encode(sha256(convert_to(canonical::text, 'UTF8')), 'hex');

    INSERT INTO benchmark_reference_catalog AS catalog (
        benchmark_name, dataset, instance, reference_cost, reference_kind,
        source_name, source_revision
    )
    SELECT
        incoming.benchmark_name, incoming.dataset, incoming.instance,
        incoming.reference_cost, incoming.reference_kind,
        incoming.source_name, incoming.source_revision
    FROM jsonb_to_recordset(canonical) AS incoming (
        benchmark_name text,
        dataset text,
        instance text,
        reference_cost double precision,
        reference_kind text,
        source_name text,
        source_revision text
    )
    ON CONFLICT (benchmark_name, dataset, instance) DO UPDATE SET
        reference_cost = EXCLUDED.reference_cost,
        reference_kind = EXCLUDED.reference_kind,
        source_name = EXCLUDED.source_name,
        source_revision = EXCLUDED.source_revision
    WHERE (
        catalog.reference_cost, catalog.reference_kind,
        catalog.source_name, catalog.source_revision
    ) IS DISTINCT FROM (
        EXCLUDED.reference_cost, EXCLUDED.reference_kind,
        EXCLUDED.source_name, EXCLUDED.source_revision
    );

    -- The committed catalogs are the authority: a value they dropped must not
    -- keep resolving.
    DELETE FROM benchmark_reference_catalog AS catalog
    WHERE NOT EXISTS (
        SELECT 1
        FROM jsonb_to_recordset(canonical) AS incoming (
            benchmark_name text, dataset text, instance text
        )
        WHERE incoming.benchmark_name = catalog.benchmark_name
          AND incoming.dataset = catalog.dataset
          AND incoming.instance = catalog.instance
    );

    INSERT INTO benchmark_reference_catalog_versions (
        sha256, entries, entry_count, sources
    )
    VALUES (digest, canonical, entry_total, p_sources)
    ON CONFLICT (sha256) DO UPDATE SET last_loaded_at = now();

    RETURN digest;
END;
$$;

COMMENT ON FUNCTION benchmark_sync_reference_catalog(jsonb, jsonb) IS
    'Make benchmark_reference_catalog equal the committed catalogs, record the catalog version, and return its SHA-256.';

CREATE FUNCTION benchmark_record_run_instances(p_run_id uuid, p_instances jsonb)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    run_benchmark text;
    recorded integer;
    unmatched integer;
BEGIN
    SELECT benchmark_name INTO run_benchmark
    FROM benchmark_runs
    WHERE id = p_run_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'benchmark run % does not exist', p_run_id;
    END IF;
    IF p_instances IS NULL
       OR jsonb_typeof(p_instances) <> 'array'
       OR jsonb_array_length(p_instances) = 0 THEN
        RAISE EXCEPTION 'run % records no instances', p_run_id;
    END IF;

    INSERT INTO benchmark_instances (
        benchmark_name, dataset, instance, input_sha256, instance_size,
        first_run_id
    )
    SELECT DISTINCT ON (incoming.dataset, incoming.instance, incoming.input_sha256)
        run_benchmark, incoming.dataset, incoming.instance,
        incoming.input_sha256, incoming.instance_size, p_run_id
    FROM jsonb_to_recordset(p_instances) AS incoming (
        dataset text,
        instance text,
        input_sha256 text,
        instance_size integer
    )
    ON CONFLICT DO NOTHING;

    INSERT INTO benchmark_run_instances (
        run_id, benchmark_name, dataset, dataset_set, instance, input_sha256
    )
    SELECT
        p_run_id, run_benchmark, incoming.dataset, incoming.dataset_set,
        incoming.instance, incoming.input_sha256
    FROM jsonb_to_recordset(p_instances) AS incoming (
        dataset text,
        dataset_set text,
        instance text,
        input_sha256 text
    );
    GET DIAGNOSTICS recorded = ROW_COUNT;

    -- The pinned instances are exactly the matrix's instances, no more, no less.
    SELECT count(*) INTO unmatched
    FROM (
        SELECT dataset, dataset_set, instance
        FROM benchmark_run_matrix_entries
        WHERE run_id = p_run_id
        EXCEPT
        SELECT dataset, dataset_set, instance
        FROM benchmark_run_instances
        WHERE run_id = p_run_id
    ) AS missing;
    IF unmatched <> 0 THEN
        RAISE EXCEPTION 'run % pins no instance hash for % matrix instance(s)',
            p_run_id, unmatched;
    END IF;

    SELECT count(*) INTO unmatched
    FROM (
        SELECT dataset, dataset_set, instance
        FROM benchmark_run_instances
        WHERE run_id = p_run_id
        EXCEPT
        SELECT dataset, dataset_set, instance
        FROM benchmark_run_matrix_entries
        WHERE run_id = p_run_id
    ) AS extra;
    IF unmatched <> 0 THEN
        RAISE EXCEPTION 'run % pins % instance(s) outside its matrix',
            p_run_id, unmatched;
    END IF;

    RETURN recorded;
END;
$$;

COMMENT ON FUNCTION benchmark_record_run_instances(uuid, jsonb) IS
    'Record the input hash of every instance a run loads; the set must equal the run''s matrix instances.';

-- A pinned run cannot record a result for an instance it did not pin.
CREATE FUNCTION benchmark_results_require_pinned_instance()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM benchmark_runs
        WHERE id = NEW.run_id
          AND input_pinning_required
    ) AND NOT EXISTS (
        SELECT 1
        FROM benchmark_run_instances
        WHERE run_id = NEW.run_id
          AND dataset = NEW.dataset
          AND dataset_set = NEW.dataset_set
          AND instance = NEW.instance
    ) THEN
        RAISE EXCEPTION
            'run % has no pinned instance hash for %/%/%',
            NEW.run_id, NEW.dataset, NEW.dataset_set, NEW.instance
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER benchmark_results_require_pinned_instance
    BEFORE INSERT OR UPDATE OF run_id, dataset, dataset_set, instance
    ON benchmark_results
    FOR EACH ROW
    EXECUTE FUNCTION benchmark_results_require_pinned_instance();

CREATE VIEW benchmark_instance_versions AS
SELECT
    instances.benchmark_name,
    instances.dataset,
    instances.instance,
    instances.input_sha256,
    instances.instance_size,
    instances.first_seen_at,
    instances.first_run_id,
    count(run_instances.run_id)::integer AS run_count,
    max(runs.created_at) AS last_run_at,
    count(*) OVER (
        PARTITION BY instances.benchmark_name, instances.dataset, instances.instance
    ) > 1 AS changed
FROM benchmark_instances AS instances
LEFT JOIN benchmark_run_instances AS run_instances
    ON run_instances.benchmark_name = instances.benchmark_name
   AND run_instances.dataset = instances.dataset
   AND run_instances.instance = instances.instance
   AND run_instances.input_sha256 = instances.input_sha256
LEFT JOIN benchmark_runs AS runs ON runs.id = run_instances.run_id
GROUP BY
    instances.benchmark_name,
    instances.dataset,
    instances.instance,
    instances.input_sha256,
    instances.instance_size,
    instances.first_seen_at,
    instances.first_run_id;

COMMENT ON VIEW benchmark_instance_versions IS
    'One row per instance version with the runs that loaded it; changed is true when the same instance name has more than one input hash.';

-- The audit keeps every existing column and criterion and appends the pins.
-- Columns are only appended, so the publishable_* views that depend on it stay
-- valid.
CREATE OR REPLACE VIEW benchmark_run_publication_audit AS
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
),
pin_counts AS (
    SELECT
        runs.id AS run_id,
        runs.input_pinning_required,
        runs.reference_catalog_sha256,
        catalog_version.sha256 IS NOT NULL AS reference_catalog_known,
        CASE WHEN runs.input_pinning_required THEN (
            SELECT COUNT(*)::integer
            FROM (
                SELECT DISTINCT dataset, dataset_set, instance
                FROM benchmark_run_matrix_entries AS matrix_instance
                WHERE matrix_instance.run_id = runs.id
            ) AS matrix_instances
        ) ELSE 0 END AS matrix_instance_count,
        CASE WHEN runs.input_pinning_required THEN (
            SELECT COUNT(*)::integer
            FROM benchmark_run_instances AS pinned_instance
            WHERE pinned_instance.run_id = runs.id
              AND EXISTS (
                  SELECT 1
                  FROM benchmark_run_matrix_entries AS matrix_instance
                  WHERE matrix_instance.run_id = pinned_instance.run_id
                    AND matrix_instance.dataset = pinned_instance.dataset
                    AND matrix_instance.dataset_set = pinned_instance.dataset_set
                    AND matrix_instance.instance = pinned_instance.instance
              )
        ) ELSE 0 END AS matched_instance_count,
        CASE WHEN runs.input_pinning_required THEN (
            SELECT COUNT(*)::integer
            FROM benchmark_run_instances AS pinned_instance
            WHERE pinned_instance.run_id = runs.id
        ) ELSE 0 END AS run_instance_count,
        CASE WHEN runs.input_pinning_required THEN (
            SELECT COUNT(*)::integer
            FROM benchmark_results AS result
            LEFT JOIN jsonb_to_recordset(catalog_version.entries) AS pinned (
                benchmark_name text,
                dataset text,
                instance text,
                reference_cost double precision
            )
              ON pinned.benchmark_name = result.benchmark_name
             AND pinned.dataset = result.dataset
             AND pinned.instance = result.instance
            WHERE result.run_id = runs.id
              AND result.reference_cost IS NOT NULL
              AND result.reference_cost IS DISTINCT FROM pinned.reference_cost
        ) ELSE 0 END AS reference_cost_mismatch_count,
        -- The fair-start witness hashes the input the solver actually received;
        -- it must be the instance version the run pinned.
        CASE WHEN runs.input_pinning_required THEN (
            SELECT COUNT(*)::integer
            FROM benchmark_results AS result
            JOIN benchmark_run_instances AS pinned_instance
              ON pinned_instance.run_id = result.run_id
             AND pinned_instance.dataset = result.dataset
             AND pinned_instance.dataset_set = result.dataset_set
             AND pinned_instance.instance = result.instance
            WHERE result.run_id = runs.id
              AND result.fair_start_witness ? 'solver_input_hash'
              AND result.fair_start_witness ->> 'solver_input_hash'
                    IS DISTINCT FROM pinned_instance.input_sha256
        ) ELSE 0 END AS instance_hash_mismatch_count
    FROM benchmark_runs AS runs
    LEFT JOIN benchmark_reference_catalog_versions AS catalog_version
        ON catalog_version.sha256 = runs.reference_catalog_sha256
),
pins AS (
    SELECT
        pin_counts.*,
        NOT input_pinning_required
        OR (
            reference_catalog_known
            AND matrix_instance_count > 0
            AND run_instance_count = matrix_instance_count
            AND matched_instance_count = matrix_instance_count
            AND reference_cost_mismatch_count = 0
            AND instance_hash_mismatch_count = 0
        ) AS inputs_pinned
    FROM pin_counts
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
    AND solver_provenance_valid
    AND pins.inputs_pinned AS publication_ready,
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
            END,
            CASE
                WHEN pins.input_pinning_required
                 AND NOT pins.reference_catalog_known
                THEN 'reference_catalog_unpinned'
            END,
            CASE
                WHEN pins.input_pinning_required
                 AND (
                     pins.matrix_instance_count = 0
                     OR pins.run_instance_count <> pins.matrix_instance_count
                     OR pins.matched_instance_count <> pins.matrix_instance_count
                 )
                THEN 'instances_unpinned'
            END,
            CASE
                WHEN pins.input_pinning_required
                 AND pins.reference_cost_mismatch_count <> 0
                THEN 'reference_cost_mismatch'
            END,
            CASE
                WHEN pins.input_pinning_required
                 AND pins.instance_hash_mismatch_count <> 0
                THEN 'instance_hash_mismatch'
            END
        ],
        NULL
    )::text[] AS publication_failures,
    pins.input_pinning_required,
    pins.reference_catalog_sha256,
    pins.reference_catalog_known,
    pins.matrix_instance_count,
    pins.run_instance_count,
    pins.reference_cost_mismatch_count,
    pins.instance_hash_mismatch_count
FROM metrics
JOIN pins ON pins.run_id = metrics.run_id;
