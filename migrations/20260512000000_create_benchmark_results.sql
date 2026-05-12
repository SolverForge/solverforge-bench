CREATE TYPE benchmark_run_kind AS ENUM ('quick', 'candidate', 'tag');

CREATE TABLE benchmark_runs (
    id uuid PRIMARY KEY,
    run_kind benchmark_run_kind NOT NULL,
    release_tag text,
    run_stamp text NOT NULL,
    benchmark_name text NOT NULL,
    benchmark_category text NOT NULL,
    output_path text NOT NULL,
    artifact_dir text NOT NULL,
    solvers text[] NOT NULL,
    time_limits_seconds integer[] NOT NULL,
    command_args jsonb NOT NULL DEFAULT '[]'::jsonb,
    repo_root text NOT NULL,
    git_commit text,
    git_dirty boolean NOT NULL,
    python_version text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT benchmark_runs_tag_requires_release_tag CHECK (
        run_kind <> 'tag' OR release_tag IS NOT NULL
    ),
    CONSTRAINT benchmark_runs_release_tag_not_blank CHECK (
        release_tag IS NULL OR btrim(release_tag) <> ''
    )
);

CREATE TABLE benchmark_results (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    row_index integer NOT NULL,
    benchmark_name text NOT NULL,
    benchmark_category text NOT NULL,
    dataset text NOT NULL,
    dataset_set text NOT NULL,
    instance text NOT NULL,
    instance_size integer,
    solver text NOT NULL,
    time_limit_seconds integer NOT NULL,
    actual_time_seconds double precision NOT NULL,
    overshoot_seconds double precision NOT NULL,
    overshoot_ratio double precision NOT NULL,
    wall_time_over_limit boolean NOT NULL,
    watchdog_limit_seconds double precision NOT NULL,
    watchdog_killed boolean NOT NULL,
    run_error text,
    hard_feasible boolean,
    cost double precision,
    reported_cost double precision,
    fresh_cost double precision,
    reference_cost double precision,
    quality_ratio double precision,
    validation_error text,
    solution_artifact text,
    native_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
    row_payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, row_index)
);

CREATE INDEX benchmark_runs_kind_created_at_idx
    ON benchmark_runs (run_kind, created_at DESC);

CREATE INDEX benchmark_runs_release_tag_idx
    ON benchmark_runs (release_tag)
    WHERE release_tag IS NOT NULL;

CREATE INDEX benchmark_results_lookup_idx
    ON benchmark_results (
        benchmark_name,
        dataset_set,
        instance,
        solver,
        time_limit_seconds
    );

CREATE INDEX benchmark_results_run_idx
    ON benchmark_results (run_id, row_index);

CREATE INDEX benchmark_results_native_fields_idx
    ON benchmark_results USING gin (native_fields);
