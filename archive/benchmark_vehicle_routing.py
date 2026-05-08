#!/usr/bin/env python3

import json
import sys
import time
import traceback
import click
import requests
from dataclasses import dataclass
from typing import Dict, List, Optional
from collections import defaultdict
import statistics


@dataclass
class BenchmarkConfig:
    python_base_url: str = "http://127.0.0.1:8081"
    python2_base_url: str = "http://127.0.0.1:8082"
    java_base_url: str = "http://127.0.0.1:8080"


@dataclass
class BenchmarkResult:
    data_source: str
    job_id: str
    solve_time_ms: int
    final_score: Dict[str, int]
    solver_iterations: int
    success: bool
    analysis: Optional[Dict] = None
    error_message: Optional[str] = None


@click.command()
@click.option("--iterations", default=1, help="Number of iterations per test")
@click.option(
    "--output-file", type=click.Path(), help="Output results to markdown file"
)
@click.option("--test", help="Run only a specific test by name")
def main(iterations, output_file, test):
    """Vehicle Routing Benchmark Tool"""
    config = BenchmarkConfig()
    click.echo("\n🔧 Vehicle Routing Benchmark Tool")
    click.echo("=" * 50)

    # Check all servers
    python_server_ok = check_server(config.python_base_url)
    python2_server_ok = check_server(config.python2_base_url)
    java_server_ok = check_server(config.java_base_url)

    if not python_server_ok:
        click.echo(f"❌ Python server not running at {config.python_base_url}")
        click.echo("   Please start the Python server first with:")
        click.echo(
            f"   uvicorn src.vehicle_routing:app --host {config.python_base_url.split('//')[1].split(':')[0]} --port {config.python_base_url.split(':')[-1]}"
        )
    if not python2_server_ok:
        click.echo(f"❌ Python2 server not running at {config.python2_base_url}")
        click.echo("   Please start the Python2 server first with:")
        click.echo(
            f"   uvicorn src.vehicle_routing:app --host {config.python2_base_url.split('//')[1].split(':')[0]} --port {config.python2_base_url.split(':')[-1]}"
        )
    if not java_server_ok:
        click.echo(f"❌ Java server not running at {config.java_base_url}")
        click.echo("   Please start the Java server first")

    if not python_server_ok and not python2_server_ok and not java_server_ok:
        if output_file:
            click.echo(f"📄 Writing error status to {output_file}")
            with open(output_file, "w") as f:
                f.write("# Vehicle Routing Benchmark Results\n\n")
                f.write(f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("## ❌ Server Error\n\n")
                f.write("No servers running:\n")
                f.write(f"- Python server: {config.python_base_url}\n")
                f.write(f"- Python2 server: {config.python2_base_url}\n")
                f.write(f"- Java server: {config.java_base_url}\n")
        sys.exit(1)

    if python_server_ok:
        click.echo(f"✅ Python server is running at {config.python_base_url}")
    if python2_server_ok:
        click.echo(f"✅ Python2 server is running at {config.python2_base_url}")
    if java_server_ok:
        click.echo(f"✅ Java server is running at {config.java_base_url}")
    click.echo()

    # Define test scenarios
    test_scenarios = {
        "Python Backend - Python Demo Data": {
            "condition": python_server_ok,
            "fetcher": lambda: get_demo_data(config.python_base_url),
            "converter": None,
            "backend": config.python_base_url,
        },
        "Python Backend - Java Demo Data": {
            "condition": python_server_ok and java_server_ok,
            "fetcher": lambda: get_demo_data(config.java_base_url),
            "converter": lambda data: convert_java_to_python_format(data),
            "backend": config.python_base_url,
        },
        "Python Backend (FAST) - Python Demo Data": {
            "condition": python2_server_ok,
            "fetcher": lambda: get_demo_data(config.python2_base_url),
            "converter": None,
            "backend": config.python2_base_url,
        },
        "Python Backend (FAST) - Java Demo Data": {
            "condition": python2_server_ok and java_server_ok,
            "fetcher": lambda: get_demo_data(config.java_base_url),
            "converter": lambda data: convert_java_to_python_format(data),
            "backend": config.python2_base_url,
        },
        "Java Backend - Java Demo Data": {
            "condition": java_server_ok,
            "fetcher": lambda: get_demo_data(config.java_base_url),
            "converter": None,
            "backend": config.java_base_url,
        },
        "Java Backend - Python Demo Data": {
            "condition": java_server_ok and python_server_ok,
            "fetcher": lambda: get_demo_data(config.python_base_url),
            "converter": lambda data: convert_python_to_java_format(data),
            "backend": config.java_base_url,
        },
    }

    all_results = []
    if test:
        if test in test_scenarios:
            scenario = test_scenarios[test]
            if scenario["condition"]:
                results = run_test_scenario(
                    test,
                    scenario["fetcher"],
                    scenario["converter"],
                    scenario["backend"],
                    iterations,
                )
                all_results.extend(results)
            else:
                click.echo(f"⚠️  Skipping test '{test}' - required server not running.")
        else:
            click.echo(f"❌ Unknown test: {test}")
            click.echo(f"   Available tests: {list(test_scenarios.keys())}")
    else:
        for name, scenario in test_scenarios.items():
            if scenario["condition"]:
                results = run_test_scenario(
                    name,
                    scenario["fetcher"],
                    scenario["converter"],
                    scenario["backend"],
                    iterations,
                )
                all_results.extend(results)
    print_results(all_results, output_file)


def run_test_scenario(
    test_name, data_fetcher, data_converter=None, target_backend=None, iterations=1
):
    click.echo(f"📥 Testing {test_name}...")
    click.echo("-" * 60)

    def analyze_solution(data, backend, original_data=None):
        click.echo("   🔍 Analyzing final solution...")
        solved_data = data
        if hasattr(result, "job_id") and result.job_id:
            try:
                click.echo(
                    f"   📥 Fetching complete solution for job {result.job_id}..."
                )
                response = requests.get(f"{backend}/route-plans/{result.job_id}")
                if response.status_code == 200:
                    solved_data = response.json()
                    click.echo("   ✅ Retrieved solved route plan for analysis")
                else:
                    click.echo(
                        f"   ⚠️ Could not retrieve solved route plan (status {response.status_code})"
                    )
                    click.echo("   ⚠️ Using input data for analysis")
            except Exception as e:
                click.echo(f"   ⚠️ Error retrieving solved route plan: {e}")
                click.echo("   ⚠️ Using input data for analysis")
        analysis_payload = solved_data
        if original_data:
            analysis_payload = prepare_for_analysis(solved_data, original_data)
        click.echo("   🔬 Calling /route-plans/analyze endpoint with solution data...")
        analysis = analyze_route(analysis_payload, backend)
        if analysis:
            constraint_count = len(analysis.get("constraints", []))
            click.echo(
                f"   📊 Analysis complete. Found {constraint_count} constraints."
            )
            return analysis
        else:
            click.echo("   ❌ Analysis failed")
            return None

    results = []
    for i in range(iterations):
        click.echo(f"\n   📥 Fetching demo data for iteration {i+1}...")
        demo_data = data_fetcher()
        if demo_data:
            click.echo(
                f"   ✅ Got demo data with {len(demo_data.get('visits', []))} visits"
            )
            original_demo_data = json.loads(json.dumps(demo_data))
            if data_converter:
                demo_data = data_converter(demo_data)
            result = run_benchmark(
                demo_data, f"{test_name} (Run {i+1})", target_backend
            )
            if result.success:
                if "Java Demo Data" in test_name and "Python Backend" in test_name:
                    analysis_result = analyze_solution(
                        demo_data, target_backend, original_data=original_demo_data
                    )
                else:
                    analysis_result = analyze_solution(demo_data, target_backend)
                result.analysis = analysis_result
            results.append(result)
        else:
            click.echo(f"   ❌ Failed to get demo data for iteration {i+1}")
            results.append(
                BenchmarkResult(
                    data_source=f"{test_name} (Run {i+1})",
                    job_id="",
                    solve_time_ms=0,
                    final_score={},
                    solver_iterations=0,
                    success=False,
                    error_message="Failed to get demo data",
                )
            )
    click.echo()  # Add spacing after test
    return results


def run_benchmark(data: Dict, data_source: str, base_url: str) -> BenchmarkResult:
    def log_data_structure():
        click.echo(
            f"   🎯 Data Overview: {len(data.get('visits', []))} visits, {len(data.get('vehicles', []))} vehicles"
        )

    click.echo(f"\n⚡ Running {data_source}...")
    click.echo(f"   {'-' * 50}")
    log_data_structure()
    click.echo(f"   {'-' * 50}")
    try:
        if "8081" in base_url and "solverConfiguration" not in data:
            import copy

            data = copy.deepcopy(data)
            data["solverConfiguration"] = {
                "termination": {
                    "secondsSpentLimit": 30,
                    "unimprovedSecondsSpentLimit": 30,
                }
            }
        response = requests.post(f"{base_url}/route-plans", json=data)
        if response.status_code != 200:
            error_message = f"Job submission failed: {response.status_code}"
            try:
                error_data = response.json()
                if "message" in error_data:
                    error_message += f" - {error_data['message']}"
            except Exception:
                error_message += f" - Response: {response.text[:200]}"
            return BenchmarkResult(
                data_source=data_source,
                job_id="",
                solve_time_ms=0,
                final_score={},
                solver_iterations=0,
                success=False,
                error_message=error_message,
            )
        job_id = response.text.strip('"')
        click.echo(f"   🚀 Job launched: {job_id}")
        iterations = 0
        last_score = None
        solve_start_time = time.time()
        progress_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        while True:
            time.sleep(0.5)
            iterations += 1
            response = requests.get(f"{base_url}/route-plans/{job_id}")
            if response.status_code != 200:
                error_message = f"Status check failed: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_message += f" - {error_data['message']}"
                except Exception:
                    pass
                return BenchmarkResult(
                    data_source=data_source,
                    job_id=job_id,
                    solve_time_ms=0,
                    final_score={},
                    solver_iterations=iterations,
                    success=False,
                    error_message=error_message,
                )
            status_data = response.json()
            solver_status = status_data.get("solver_status") or status_data.get(
                "solverStatus"
            )
            current_score = status_data.get("score", {})
            if current_score != last_score and current_score:
                spinner = progress_chars[iterations % len(progress_chars)]
                click.echo(f"   {spinner} Optimizing... {current_score}")
                last_score = current_score
            if solver_status == "NOT_SOLVING":
                solve_end_time = time.time()
                solve_time_ms = int((solve_end_time - solve_start_time) * 1000)
                click.echo(
                    f"   ✅ Completed: {solve_time_ms:,}ms • {iterations} iterations • {format_score(current_score)}"
                )
                return BenchmarkResult(
                    data_source=data_source,
                    job_id=job_id,
                    solve_time_ms=solve_time_ms,
                    final_score=current_score,
                    solver_iterations=iterations,
                    success=True,
                )
            if time.time() - solve_start_time > 60:
                return BenchmarkResult(
                    data_source=data_source,
                    job_id=job_id,
                    solve_time_ms=0,
                    final_score=current_score,
                    solver_iterations=iterations,
                    success=False,
                    error_message="Timeout after 60 seconds",
                )
    except Exception as e:
        return BenchmarkResult(
            data_source=data_source,
            job_id="",
            solve_time_ms=0,
            final_score={},
            solver_iterations=0,
            success=False,
            error_message=str(e),
        )


def analyze_route(data: Dict, base_url: str) -> Optional[Dict]:
    try:
        response = requests.put(
            f"{base_url}/route-plans/analyze", json=data, timeout=30
        )
        if response.status_code == 200:
            return response.json()
        else:
            click.echo(
                f"   ❌ Analysis failed with status {response.status_code}: {response.text}"
            )
            return None
    except Exception as e:
        click.echo(f"   ❌ Analysis error: {e}")
        return None


def format_score(score: Dict[str, int] | str) -> str:
    def format_dict_score(score_dict):
        hard = score_dict.get("hardScore", 0)
        medium = score_dict.get("mediumScore", 0)
        soft = score_dict.get("softScore", 0)
        return f"{hard}hard/{medium}medium/{soft}soft"

    def format_string_score(score_str):
        return score_str

    return (
        format_dict_score(score)
        if isinstance(score, dict)
        else format_string_score(score)
    )


def calculate_total_score(score: Dict[str, int] | str) -> int:
    def parse_score():
        match score:
            case str():
                try:
                    parts = score.split("/")
                    hard = int(parts[0].replace("hard", ""))
                    medium = (
                        int(parts[1].replace("medium", "")) if len(parts) > 1 else 0
                    )
                    soft = int(parts[2].replace("soft", "")) if len(parts) > 2 else 0
                    return hard, medium, soft
                except Exception:
                    return 0, 0, 0
            case dict():
                hard = score.get("hardScore", 0)
                medium = score.get("mediumScore", 0)
                soft = score.get("softScore", 0)
                return hard, medium, soft
            case _:
                return 0, 0, 0

    def calculate_weighted_score(hard, medium, soft):
        match (hard, medium, soft):
            case (h, _, _) if h != 0:
                return h * 1000000
            case (_, m, _) if m != 0:
                return m * 1000
            case (_, _, s):
                return s

    hard, medium, soft = parse_score()
    return calculate_weighted_score(hard, medium, soft)


def get_demo_data(base_url: str) -> Optional[Dict]:
    try:
        # For the FAST backend (8082), /demo-data returns the data directly
        if base_url.endswith(":8082"):
            response = requests.get(f"{base_url}/demo-data")
            if response.status_code == 200:
                return response.json()
            else:
                click.echo(f"❌ Failed to get demo data: {response.status_code}")
                return None
        # For other backends, /demo-data returns a list of names, then fetch by name
        response = requests.get(f"{base_url}/demo-data")
        if response.status_code != 200:
            click.echo(f"❌ Failed to get demo data list: {response.status_code}")
            return None
        demo_list = response.json()
        if not demo_list:
            click.echo(f"❌ No demo datasets available at {base_url}")
            return None
        dataset_id = demo_list[0]
        response = requests.get(f"{base_url}/demo-data/{dataset_id}")
        if response.status_code == 200:
            return response.json()
        else:
            click.echo(f"❌ Failed to get demo data: {response.status_code}")
            return None
    except Exception as e:
        click.echo(f"❌ Error getting demo data: {e}")
        return None


def check_server(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url}/demo-data", timeout=5)
        return response.status_code == 200
    except requests.ConnectionError:
        return False


def convert_java_to_python_format(java_data: Dict) -> Dict:
    # Stub: In real use, adapt field names/nesting as needed
    # For now, assume the format is similar
    return java_data


def convert_python_to_java_format(python_data: Dict) -> Dict:
    # Stub: In real use, adapt field names/nesting as needed
    # For now, assume the format is similar
    return python_data


def prepare_for_analysis(solved_data: Dict, original_data: Dict) -> Dict:
    # Stub: For vehicle routing, assume no special re-injection needed
    return solved_data


def write_markdown_file(results: List[BenchmarkResult], output_file: str):
    """Write results to markdown file with maximum spiff."""

    def create_header():
        return [
            "# 🚚 Vehicle Routing Benchmark Results",
            "",
            f"📅 **Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"🚀 **Total Scenarios:** {len(results)}  ",
            f"✅ **Successful Runs:** {len([r for r in results if r.success])}  ",
            "",
            "---",
            "",
        ]

    def create_results_table():
        lines = [
            "## 📊 Individual Results",
            "",
            "| 🏷️ Scenario | 📈 Status | ⚡ Time | 🎯 Score | 🔄 Iterations | ❌ Error |",
            "|-------------|-----------|---------|----------|---------------|----------|",
        ]
        for result in results:
            status_icon = "🟢" if result.success else "🔴"
            status_text = "Success" if result.success else "Failed"
            if result.success:
                time_indicator = (
                    "🚀"
                    if result.solve_time_ms < 25000
                    else "⚡" if result.solve_time_ms < 35000 else "🐌"
                )
                lines.append(
                    f"| **{result.data_source}** | {status_icon} {status_text} | {time_indicator} {result.solve_time_ms:,}ms | `{format_score(result.final_score)}` | {result.solver_iterations} | - |"
                )
            else:
                lines.append(
                    f"| **{result.data_source}** | {status_icon} {status_text} | - | - | - | {result.error_message} |"
                )
        return lines

    def create_summary():
        successful_results = [r for r in results if r.success]
        if len(successful_results) >= 2:
            best_result = max(
                successful_results, key=lambda r: calculate_total_score(r.final_score)
            )
            fastest_result = min(successful_results, key=lambda r: r.solve_time_ms)
            times = [r.solve_time_ms for r in successful_results]
            avg_time = sum(times) / len(times)
            lines = [
                "",
                "## 🏆 Performance Summary",
                "",
                "### 🥇 Champion Results",
                "",
                f"**🏆 Best Score Champion:** `{best_result.data_source}`  ",
                f"📊 Score: `{format_score(best_result.final_score)}`  ",
                f"⏱️ Time: {best_result.solve_time_ms:,}ms  ",
                f"🔄 Iterations: {best_result.solver_iterations}  ",
                "",
                f"**⚡ Speed Champion:** `{fastest_result.data_source}`  ",
                f"⏱️ Time: {fastest_result.solve_time_ms:,}ms  ",
                f"📊 Score: `{format_score(fastest_result.final_score)}`  ",
                f"🔄 Iterations: {fastest_result.solver_iterations}  ",
                "",
                "### 📈 Performance Analytics",
                "",
                f"🎯 **Average Solve Time:** {avg_time:.0f}ms  ",
                f"📊 **Time Range:** {min(times):,}ms → {max(times):,}ms  ",
                f"🚀 **Total Scenarios:** {len(successful_results)}  ",
                "",
            ]
            return lines
        return []

    def create_cv_analysis():
        grouped_results = group_results_by_scenario(results)
        scenarios_with_multiple_runs = {
            k: v for k, v in grouped_results.items() if len(v) > 1
        }
        if not scenarios_with_multiple_runs:
            return []
        lines = [
            "",
            "## 📊 Consistency Analysis (Coefficient of Variation)",
            "",
            "### 📈 Reliability Metrics",
            "",
            "| 🏷️ Scenario | 🔄 Runs | ⏱️ Avg Time | 📊 CV Time | 🎯 Avg Score | 📊 CV Score |",
            "|-------------|---------|-------------|------------|--------------|-------------|",
        ]
        for scenario_name, scenario_results in scenarios_with_multiple_runs.items():
            successful_runs = [r for r in scenario_results if r.success]
            if len(successful_runs) < 2:
                continue
            times = [r.solve_time_ms for r in successful_runs]
            scores = [calculate_total_score(r.final_score) for r in successful_runs]
            avg_time = statistics.mean(times)
            cv_time = calculate_coefficient_of_variation(times)
            avg_score = statistics.mean(scores)
            cv_score = calculate_coefficient_of_variation(scores)
            time_consistency = "🟢" if cv_time < 10 else "🟡" if cv_time < 25 else "🔴"
            score_consistency = (
                "🟢" if cv_score < 5 else "🟡" if cv_score < 15 else "🔴"
            )
            lines.append(
                f"| **{scenario_name}** | {len(successful_runs)} | {avg_time:.0f}ms | {time_consistency} {cv_time:.1f}% | {avg_score:.0f} | {score_consistency} {cv_score:.1f}% |"
            )
        lines.extend(
            [
                "",
                "### 💡 CV Interpretation Guide",
                "",
                "- **🟢 Excellent consistency**: < 10% for time, < 5% for score",
                "- **🟡 Good consistency**: < 25% for time, < 15% for score",
                "- **🔴 High variability**: > 25% for time, > 15% for score",
                "",
                "> **Coefficient of Variation (CV)** measures relative variability: `CV = (Standard Deviation / Mean) × 100%`",
                "",
            ]
        )
        return lines

    def create_detailed_analysis():
        lines = ["", "## 🔬 Detailed Constraint Analysis", ""]
        for result in results:
            if result.success and result.analysis:
                lines.extend(
                    [
                        f"### 🎯 {result.data_source}",
                        "",
                        f"📊 **Final Score:** `{format_score(result.final_score)}`  ",
                        f"⏱️ **Solve Time:** {result.solve_time_ms:,}ms  ",
                        f"🔄 **Iterations:** {result.solver_iterations}  ",
                        "",
                    ]
                )
                constraints = result.analysis.get("constraints", [])
                if constraints:
                    lines.extend(
                        [
                            "#### 🔍 Constraint Breakdown",
                            "",
                            "| 🏷️ Constraint | 📊 Score | 🎯 Impact |",
                            "|---------------|----------|-----------|",
                        ]
                    )
                    for constraint in constraints:
                        name = constraint.get("name", "Unknown")
                        score = format_score(
                            constraint.get("score", {"hardScore": 0, "softScore": 0})
                        )
                        constraint_score = constraint.get("score", {})
                        if isinstance(constraint_score, dict):
                            hard_score = constraint_score.get("hardScore", 0)
                            soft_score = constraint_score.get("softScore", 0)
                        elif isinstance(constraint_score, str):
                            try:
                                parts = constraint_score.split("/")
                                hard_score = (
                                    int(parts[0].replace("hard", ""))
                                    if "hard" in parts[0]
                                    else 0
                                )
                                soft_score = (
                                    int(parts[1].replace("soft", ""))
                                    if len(parts) > 1 and "soft" in parts[1]
                                    else 0
                                )
                            except Exception:
                                hard_score = soft_score = 0
                        else:
                            hard_score = soft_score = 0
                        if hard_score != 0:
                            impact = "🔴 Critical"
                        elif soft_score < -1000:
                            impact = "🟠 High"
                        elif soft_score < -100:
                            impact = "🟢 Low"
                        else:
                            impact = "⚪ Minimal"
                        lines.append(f"| {name} | `{score}` | {impact} |")
                    lines.append("")
                if "summary" in result.analysis:
                    lines.extend([f"💡 **Summary:** {result.analysis['summary']}", ""])
                lines.append("---")
                lines.append("")
        return lines

    click.echo(f"📝 Writing spiff markdown to: {output_file}")
    output_lines = []
    output_lines.extend(create_header())
    successful_results = [r for r in results if r.success]
    if not successful_results:
        output_lines.extend(
            [
                "## ❌ No Successful Runs",
                "",
                "🚨 **All benchmark scenarios failed!**  ",
                "🔧 Check server connectivity and data format compatibility.",
                "",
            ]
        )
    else:
        output_lines.extend(create_results_table())
        output_lines.extend(create_summary())
        output_lines.extend(create_cv_analysis())
        output_lines.extend(create_detailed_analysis())
    try:
        with open(output_file, "w") as f:
            f.write("\n".join(output_lines))
        click.echo(f"✅ Spiff benchmark report saved: {output_file}")
    except Exception as e:
        click.echo(f"❌ Error writing markdown file: {e}")
        traceback.print_exc()


def print_results(results: List[BenchmarkResult], output_file: Optional[str] = None):
    def print_individual_results():
        click.echo("\n📊 Individual Results:")
        click.echo("-" * 40)
        for result in results:
            click.echo(f"\n🔸 {result.data_source}")
            click.echo(f"   Status: {'✅ Success' if result.success else '❌ Failed'}")
            if result.success:
                click.echo(f"   Time: {result.solve_time_ms:,}ms")
                click.echo(f"   Score: {format_score(result.final_score)}")
                click.echo(f"   Iterations: {result.solver_iterations}")
            else:
                click.echo(f"   Error: {result.error_message}")
            click.echo(f"   {'-' * 30}")

    click.echo("\n" + "=" * 80)
    click.echo("🏁 BENCHMARK RESULTS")
    click.echo("=" * 80)
    successful_results = [r for r in results if r.success]
    if not successful_results:
        click.echo("❌ No successful benchmark runs!")
        if output_file:
            write_markdown_file(results, output_file)
        return
    print_individual_results()
    if output_file:
        write_markdown_file(results, output_file)


def calculate_coefficient_of_variation(values: List[float]) -> float:
    if not values or len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    if mean == 0:
        return 0.0
    stdev = statistics.stdev(values)
    return (stdev / mean) * 100


def group_results_by_scenario(
    results: List[BenchmarkResult],
) -> Dict[str, List[BenchmarkResult]]:
    grouped = defaultdict(list)
    for result in results:
        # Extract base scenario name (remove iteration numbers)
        base_name = result.data_source.split(" (Run ")[0]
        grouped[base_name].append(result)
    return dict(grouped)


if __name__ == "__main__":
    main()
