use std::error::Error;
use std::fs::OpenOptions;
use std::io::{self, BufReader, Read};
use std::os::fd::AsRawFd;
use std::process::ExitCode;
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use vrp_cli::extensions::solve::config::read_config;
use vrp_cli::get_solution_serialized;
use vrp_cli::pragmatic::format::problem::PragmaticProblem;

#[derive(Deserialize)]
struct CvrpInput {
    capacity: i64,
    demand: Vec<i64>,
    edge_weight: Vec<Vec<i64>>,
}

#[derive(Serialize)]
struct CvrpOutput {
    cost: i64,
    routes: Vec<Vec<usize>>,
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<(), Box<dyn Error>> {
    let time_limit_seconds = std::env::args()
        .nth(1)
        .ok_or("usage: cvrp_rustvrp <time_limit_seconds>")?
        .parse::<u64>()?;

    let mut input_json = String::new();
    io::stdin().read_to_string(&mut input_json)?;
    let input: CvrpInput = serde_json::from_str(&input_json)?;
    validate_input(&input)?;

    let output = solve(input, time_limit_seconds)?;
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

fn validate_input(input: &CvrpInput) -> Result<(), Box<dyn Error>> {
    if input.demand.is_empty() {
        return Err("demand must contain at least the depot".into());
    }
    if input.edge_weight.len() != input.demand.len() {
        return Err("edge_weight row count does not match demand size".into());
    }
    for row in &input.edge_weight {
        if row.len() != input.demand.len() {
            return Err("edge_weight matrix must be square".into());
        }
    }
    Ok(())
}

fn solve(input: CvrpInput, time_limit_seconds: u64) -> Result<CvrpOutput, Box<dyn Error>> {
    let problem_json = serde_json::to_string(&pragmatic_problem(&input))?;
    let matrix_json = serde_json::to_string(&routing_matrix(&input))?;
    let config_json = serde_json::to_string(&json!({
        "termination": {
            "maxTime": time_limit_seconds.max(1)
        },
        "environment": {
            "logging": {
                "enabled": false
            }
        },
        "telemetry": {
            "progress": {
                "enabled": false
            },
            "metrics": {
                "enabled": false
            }
        }
    }))?;

    let solution_json = with_stdout_suppressed(|| {
        let problem = (problem_json, vec![matrix_json])
            .read_pragmatic()
            .map_err(|errors| boxed_error(errors.to_string()))?;
        let config = read_config(BufReader::new(config_json.as_bytes()))?;
        get_solution_serialized(Arc::new(problem), config)
            .map_err(|error| boxed_error(error.to_string()))
    })?;
    parse_solution(&solution_json)
}

struct StdoutRedirect {
    saved_fd: i32,
}

impl StdoutRedirect {
    fn new() -> Result<Self, Box<dyn Error>> {
        io::Write::flush(&mut io::stdout())?;
        // SAFETY: dup only reads the process stdout fd and returns an owned fd.
        let saved_fd = unsafe { libc::dup(libc::STDOUT_FILENO) };
        if saved_fd < 0 {
            return Err(Box::new(io::Error::last_os_error()));
        }

        let null = match OpenOptions::new().write(true).open("/dev/null") {
            Ok(null) => null,
            Err(error) => {
                // SAFETY: saved_fd was returned by dup above and is still owned here.
                unsafe {
                    libc::close(saved_fd);
                }
                return Err(Box::new(error));
            }
        };
        // SAFETY: both fds are valid for the duration of the call; stdout receives a duplicate.
        if unsafe { libc::dup2(null.as_raw_fd(), libc::STDOUT_FILENO) } < 0 {
            let error = io::Error::last_os_error();
            // SAFETY: saved_fd was returned by dup above and is still owned here.
            unsafe {
                libc::close(saved_fd);
            }
            return Err(Box::new(error));
        }

        Ok(Self { saved_fd })
    }
}

impl Drop for StdoutRedirect {
    fn drop(&mut self) {
        let _ = io::Write::flush(&mut io::stdout());
        // SAFETY: saved_fd is owned by this guard; restoring stdout and closing it are paired.
        unsafe {
            libc::dup2(self.saved_fd, libc::STDOUT_FILENO);
            libc::close(self.saved_fd);
        }
    }
}

fn with_stdout_suppressed<T>(
    action: impl FnOnce() -> Result<T, Box<dyn Error>>,
) -> Result<T, Box<dyn Error>> {
    // vrp-cli 1.25.0 logs while reading pragmatic problems; benchmark stdout is JSON-only.
    let _redirect = StdoutRedirect::new()?;
    action()
}

fn boxed_error(message: String) -> Box<dyn Error> {
    Box::new(io::Error::other(message))
}

fn pragmatic_problem(input: &CvrpInput) -> Value {
    let jobs: Vec<Value> = input
        .demand
        .iter()
        .enumerate()
        .skip(1)
        .map(|(index, demand)| {
            json!({
                "id": index.to_string(),
                "deliveries": [{
                    "places": [{
                        "location": { "index": index },
                        "duration": 0.0
                    }],
                    "demand": [demand]
                }]
            })
        })
        .collect();

    let vehicle_ids: Vec<String> = (0..input.demand.len())
        .map(|index| format!("vehicle_{index}"))
        .collect();

    json!({
        "plan": {
            "jobs": jobs
        },
        "fleet": {
            "vehicles": [{
                "typeId": "vehicle",
                "vehicleIds": vehicle_ids,
                "profile": { "matrix": "normal_car" },
                "costs": {
                    "fixed": 0.0,
                    "distance": 1.0,
                    "time": 0.0
                },
                "shifts": [{
                    "start": {
                        "earliest": "2000-01-01T00:00:00Z",
                        "location": { "index": 0 }
                    },
                    "end": {
                        "latest": "2100-01-01T00:00:00Z",
                        "location": { "index": 0 }
                    }
                }],
                "capacity": [input.capacity]
            }],
            "profiles": [{
                "name": "normal_car"
            }]
        }
    })
}

fn routing_matrix(input: &CvrpInput) -> Value {
    let flat_distances: Vec<i64> = input.edge_weight.iter().flatten().copied().collect();

    json!({
        "profile": "normal_car",
        "travelTimes": flat_distances,
        "distances": flat_distances
    })
}

fn parse_solution(solution_json: &str) -> Result<CvrpOutput, Box<dyn Error>> {
    let solution: Value = serde_json::from_str(solution_json)?;
    let cost = solution
        .get("statistic")
        .and_then(|statistic| statistic.get("cost"))
        .and_then(number_to_i64)
        .ok_or("rustvrp solution did not contain statistic.cost")?;

    let mut routes = Vec::new();
    for tour in solution
        .get("tours")
        .and_then(Value::as_array)
        .ok_or("rustvrp solution did not contain tours")?
    {
        let mut route = Vec::new();
        for stop in tour
            .get("stops")
            .and_then(Value::as_array)
            .ok_or("rustvrp tour did not contain stops")?
        {
            if let Some(index) = stop
                .get("location")
                .and_then(|location| location.get("index"))
                .and_then(Value::as_u64)
            {
                let index = usize::try_from(index)?;
                if index != 0 {
                    route.push(index);
                }
            }
        }
        if !route.is_empty() {
            routes.push(route);
        }
    }

    Ok(CvrpOutput { cost, routes })
}

fn number_to_i64(value: &Value) -> Option<i64> {
    value
        .as_i64()
        .or_else(|| value.as_u64().and_then(|value| i64::try_from(value).ok()))
        .or_else(|| value.as_f64().map(|value| value.round() as i64))
}
