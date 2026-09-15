# SolverForge Benchmark Dashboard

Rails dashboard for the SolverForge benchmark PostgreSQL warehouse.

## Database

The dashboard reads the benchmark warehouse directly and treats it as read-only.
In development it defaults to:

```sh
postgresql://postgres@localhost/solverforge_bench
```

Set `BENCH_DATABASE_URL` to point at another warehouse:

```sh
BENCH_DATABASE_URL=postgresql://postgres@host/solverforge_bench bin/rails server
```

The reporting surface is the benchmark schema’s own views:

- `latest_benchmark_runs`
- `benchmark_result_facts`
- `latest_benchmark_result_facts`

The Rails app uses SQLite only for its own framework metadata. It does not run
benchmark migrations and does not write benchmark rows.

### How dashboard data is selected

Rails maps each warehouse table or view to a small read-only model under
`app/models/benchmark`. `ResultFact` is the completed historical result stream;
it powers timelines and the filtered Recent Runs panel. `LatestResultFact` maps
to the warehouse's `latest_benchmark_result_facts` view and powers the current
KPIs, standings, and filter choices.

That split is intentional. A benchmark run can be incomplete or omit a result.
Selecting the newest row for each solver and instance would quietly combine a
new partial run with an older one. The warehouse view instead chooses completed
runs first and then returns their facts, so a current dashboard is a coherent
snapshot.

Every dashboard filter is applied to both the current and historical fact
relations. Recent Runs obtains its parent runs from the filtered historical
facts, which means its count, pagination, and entries describe the selected
slice rather than all warehouse activity.

### Production warehouse connection

Production requires `BENCH_DATABASE_URL`. Kamal injects it as a deployment
secret, with its value sourced by `.kamal/secrets` from the deploy environment
or a password manager. Do not commit a warehouse URL or credentials.

## Development

```sh
bin/setup
bin/rails db:prepare
bin/rails server
```

Then open `http://localhost:3000`.
