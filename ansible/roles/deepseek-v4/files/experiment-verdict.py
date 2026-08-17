#!/usr/bin/env python3
"""Evaluate immutable DeepSeek experiment evidence without response content."""

import argparse
import json
import math
import statistics
from pathlib import Path


MATERIAL_IMPROVEMENT = 0.10
MAX_COLD_REGRESSION = 0.10
CHECKPOINT_HANDOFF_IMPROVEMENT = 0.50
MAX_CHECKPOINT_HEALTH_LATENCY_SECONDS = 10
MIN_GPU_FREE_MIB = 2048
MIN_MEMAVAILABLE_BYTES = 32 * 1024 ** 3


def is_number(value):
    """Accept finite JSON numbers but reject booleans."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def load_json(path):
    """Load one required JSON document."""
    with path.open(encoding="utf-8") as input_file:
        document = json.load(input_file)
    if not isinstance(document, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return document


def by_id(document):
    """Index result rows by their stable ID."""
    rows = document.get("results")
    if not isinstance(rows, list):
        return {}
    return {
        row.get("id"): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }


def contract_passes(document):
    """Require exactly 19 passing public contract cases."""
    results = document.get("results")
    return (
        document.get("status") == "pass"
        and isinstance(results, list)
        and len(results) == 19
        and all(isinstance(row, dict) and row.get("pass") is True for row in results)
    )


def resource_reasons(document):
    """Return fail-closed host, container, service, and GPU safety failures."""
    reasons = []
    if not isinstance(document.get("sample_count"), int) or document["sample_count"] <= 0:
        reasons.append("resource samples are missing")
    host = document.get("host") if isinstance(document.get("host"), dict) else {}
    for field in ("maximum_swap_used_bytes", "oom_kill_count_delta"):
        if not is_number(host.get(field)):
            reasons.append(f"host {field} is unavailable")
        elif host[field] != 0:
            reasons.append(f"host {field} is non-zero")
    if not is_number(host.get("minimum_memavailable_bytes")):
        reasons.append("host minimum_memavailable_bytes is unavailable")
    elif host["minimum_memavailable_bytes"] < MIN_MEMAVAILABLE_BYTES:
        reasons.append("host retained less than 32 GiB MemAvailable")

    container = (
        document.get("container")
        if isinstance(document.get("container"), dict)
        else {}
    )
    if not is_number(container.get("maximum_restart_count")):
        reasons.append("container restart evidence is unavailable")
    elif container["maximum_restart_count"] != 0:
        reasons.append("container restarted")
    if container.get("oom_killed_observed") is not False:
        reasons.append("container OOM evidence is unavailable or unsafe")

    gpus = document.get("gpus") if isinstance(document.get("gpus"), dict) else {}
    if set(gpus) != {"0", "1"}:
        reasons.append("exactly two GPU resource records are required")
    else:
        for ordinal in ("0", "1"):
            if gpus[ordinal].get("sample_count") != document.get("sample_count"):
                reasons.append(f"GPU {ordinal} sampling coverage is incomplete")
            free_mib = gpus[ordinal].get("minimum_memory_free_mib")
            if not is_number(free_mib):
                reasons.append(f"GPU {ordinal} free-memory evidence is unavailable")
            elif free_mib < MIN_GPU_FREE_MIB:
                reasons.append(f"GPU {ordinal} retained less than 2 GiB")

    services = (
        document.get("services")
        if isinstance(document.get("services"), dict)
        else {}
    )
    if not services:
        reasons.append("service restart evidence is unavailable")
    for unit, service in services.items():
        if not isinstance(service, dict) or service.get("collection_complete") is not True:
            reasons.append(f"{unit} sampling coverage is incomplete")
        restarts = service.get("maximum_restarts") if isinstance(service, dict) else None
        if not is_number(restarts):
            reasons.append(f"{unit} restart evidence is unavailable")
        elif restarts != 0:
            reasons.append(f"{unit} restarted")
    if not isinstance(container.get("observed_sample_count"), int) or container[
        "observed_sample_count"
    ] <= 0:
        reasons.append("container sampling coverage is incomplete")
    return reasons


def relative_improvement(control, candidate):
    """Return positive improvement when a lower latency becomes faster."""
    if not is_number(control) or not is_number(candidate) or control <= 0:
        return None
    return (control - candidate) / control


def relative_gain(control, candidate):
    """Return positive improvement when throughput becomes higher."""
    if not is_number(control) or not is_number(candidate) or control <= 0:
        return None
    return (candidate - control) / control


def checkpoint_reasons(document):
    """Validate three prompt-free long-context to short-request handoffs."""
    reasons = []
    results = document.get("results")
    if not isinstance(results, list) or len(results) != 3:
        return ["checkpoint transition does not contain three repeats"]
    for index, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            reasons.append(f"checkpoint repeat {index} is malformed")
            continue
        if result.get("recall_ok") is not True:
            reasons.append(f"checkpoint repeat {index} lost long-context recall")
        if result.get("handoff_ok") is not True:
            reasons.append(f"checkpoint repeat {index} short handoff failed")
        if result.get("health_failures") != 0:
            reasons.append(f"checkpoint repeat {index} health probe failed")
        latency = result.get("maximum_health_latency_seconds")
        if not is_number(latency) or latency > MAX_CHECKPOINT_HEALTH_LATENCY_SECONDS:
            reasons.append(f"checkpoint repeat {index} health latency exceeded 10 seconds")
    return reasons


def checkpoint_control_reasons(document):
    """Accept a known availability failure only when the 32 control is otherwise valid."""
    reasons = []
    results = document.get("results")
    if not isinstance(results, list) or len(results) != 3:
        return ["checkpoint control does not contain three repeats"]
    if document.get("target_prompt_tokens") != 127000:
        reasons.append("checkpoint control did not use the approved 127K target")
    if document.get("repeat_count") != 3 or document.get("expected_repeat_count") != 3:
        reasons.append("checkpoint control did not record three expected repeats")
    for index, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            reasons.append(f"checkpoint control repeat {index} is malformed")
            continue
        if result.get("recall_ok") is not True:
            reasons.append(f"checkpoint control repeat {index} lost long-context recall")
        if result.get("handoff_ok") is not True:
            reasons.append(f"checkpoint control repeat {index} short handoff failed")
        if not is_number(result.get("recall_elapsed_seconds")):
            reasons.append(f"checkpoint control repeat {index} recall timing is unavailable")
        if not is_number(result.get("handoff_elapsed_seconds")):
            reasons.append(f"checkpoint control repeat {index} handoff timing is unavailable")
        sample_count = result.get("health_sample_count")
        failures = result.get("health_failures")
        latency = result.get("maximum_health_latency_seconds")
        if (
            isinstance(sample_count, bool)
            or not isinstance(sample_count, int)
            or sample_count <= 0
        ):
            reasons.append(f"checkpoint control repeat {index} has no health samples")
        if (
            isinstance(failures, bool)
            or not isinstance(failures, int)
            or failures < 0
            or not isinstance(sample_count, int)
            or failures > sample_count
        ):
            reasons.append(f"checkpoint control repeat {index} health failures are invalid")
        if not is_number(latency) or latency < 0:
            reasons.append(f"checkpoint control repeat {index} health latency is invalid")
        if isinstance(failures, int) and not isinstance(failures, bool):
            if result.get("health_ok") is not (failures == 0):
                reasons.append(f"checkpoint control repeat {index} health status is inconsistent")
    return reasons


def evaluate(primary, candidate, control=None):
    """Build a typed promotion verdict from parsed evidence documents."""
    reasons = []
    metrics = {}
    if not contract_passes(candidate.get("contract", {})):
        reasons.append("19-case public contract did not pass")
    reasons.extend(resource_reasons(candidate.get("resources", {})))
    log_status = candidate.get("log_status", {})
    if log_status.get("status") != "pass":
        reasons.append("sanitized runtime log collection is incomplete")
    watchdog = candidate.get("watchdog", {})
    if watchdog.get("status") != "disarmed":
        reasons.append("managed-host recovery watchdog was not safely disarmed")
    if primary == "ctx_checkpoints" and candidate.get("restore_result", {}).get(
        "exact_restore"
    ) is not True:
        reasons.append("exact production control restoration was not proven")

    benchmark_rows = by_id(candidate.get("benchmark", {}))
    if set(benchmark_rows) != {"1k", "8k"}:
        reasons.append("candidate benchmark is incomplete")

    if primary == "baseline":
        if candidate.get("cache", {}).get("status") != "pass":
            reasons.append("baseline cache workload did not pass")
    elif not control:
        reasons.append("non-baseline experiment has no control evidence")
    elif primary == "cache_ram_mib":
        candidate_cache = by_id(candidate.get("cache", {}))
        control_cache = by_id(control.get("cache", {}))
        required = {"a_cold", "a_continuation", "b_cold", "a_return"}
        if set(candidate_cache) != required or set(control_cache) != required:
            reasons.append("cache comparison evidence is incomplete")
        else:
            return_improvement = relative_improvement(
                control_cache["a_return"].get("median_ttft_seconds"),
                candidate_cache["a_return"].get("median_ttft_seconds"),
            )
            metrics["return_a_ttft_improvement"] = return_improvement
            if return_improvement is None or return_improvement < MATERIAL_IMPROVEMENT:
                reasons.append("return-A TTFT improvement is below 10%")
            for case_id in ("a_cold", "b_cold"):
                cold_improvement = relative_improvement(
                    control_cache[case_id].get("median_ttft_seconds"),
                    candidate_cache[case_id].get("median_ttft_seconds"),
                )
                regression = (
                    -cold_improvement
                    if is_number(cold_improvement)
                    else None
                )
                metrics[f"{case_id}_ttft_regression"] = regression
                if regression is None:
                    reasons.append(f"{case_id} TTFT evidence is unavailable")
                elif regression > MAX_COLD_REGRESSION:
                    reasons.append(f"{case_id} TTFT regressed by more than 10%")
    elif primary in ("n_cpu_moe", "split_mode"):
        control_rows = by_id(control.get("benchmark", {}))
        if set(control_rows) != {"1k", "8k"} or set(benchmark_rows) != {"1k", "8k"}:
            reasons.append("throughput comparison evidence is incomplete")
        else:
            for case_id in ("1k", "8k"):
                candidate_tg = benchmark_rows[case_id].get(
                    "median_tg_tokens_per_second"
                )
                gain = relative_gain(
                    control_rows[case_id].get("median_tg_tokens_per_second"),
                    candidate_tg,
                )
                metrics[f"{case_id}_tg_improvement"] = gain
                if not is_number(candidate_tg) or candidate_tg < 8:
                    reasons.append(f"{case_id} TG is below 8 tok/s")
                if gain is None or gain < MATERIAL_IMPROVEMENT:
                    reasons.append(f"{case_id} TG improvement is below 10%")
    elif primary == "ctx_checkpoints":
        candidate_transition = candidate.get("checkpoint_transition", {})
        control_transition = control.get("checkpoint_transition", {})
        reasons.extend(checkpoint_reasons(candidate_transition))
        if candidate_transition.get("target_prompt_tokens") != 127000:
            reasons.append("checkpoint candidate did not use the approved 127K target")
        if not isinstance(control_transition.get("results"), list) or len(
            control_transition["results"]
        ) != 3:
            reasons.append("checkpoint control transition evidence is incomplete")
        else:
            improvement = relative_improvement(
                control_transition.get("median_handoff_elapsed_seconds"),
                candidate_transition.get("median_handoff_elapsed_seconds"),
            )
            metrics["checkpoint_handoff_improvement"] = improvement
            if improvement is None or improvement < CHECKPOINT_HANDOFF_IMPROVEMENT:
                reasons.append("checkpoint handoff improvement is below 50%")
            control_recalls = [row.get("recall_elapsed_seconds") for row in control_transition["results"]]
            candidate_recalls = [row.get("recall_elapsed_seconds") for row in candidate_transition.get("results", [])]
            if all(is_number(value) for value in control_recalls + candidate_recalls):
                recall_change = relative_improvement(
                    statistics.median(control_recalls), statistics.median(candidate_recalls)
                )
                metrics["checkpoint_recall_latency_change"] = recall_change
                if recall_change is None or recall_change < -MAX_COLD_REGRESSION:
                    reasons.append("127K recall latency regressed by more than 10%")
            else:
                reasons.append("127K recall timing evidence is unavailable")
        control_rows = by_id(control.get("benchmark", {}))
        for case_id in ("1k", "8k"):
            candidate_tg = benchmark_rows.get(case_id, {}).get("median_tg_tokens_per_second")
            control_tg = control_rows.get(case_id, {}).get("median_tg_tokens_per_second")
            gain = relative_gain(control_tg, candidate_tg)
            metrics[f"{case_id}_tg_change"] = gain
            if not is_number(candidate_tg) or candidate_tg < 8:
                reasons.append(f"{case_id} TG is below 8 tok/s")
            elif gain is None or gain < -MAX_COLD_REGRESSION:
                reasons.append(f"{case_id} TG regressed by more than 10%")
    else:
        reasons.append("unknown primary variable")

    return {
        "schema_version": 1,
        "primary_variable": primary,
        "thresholds": {
            "material_improvement": MATERIAL_IMPROVEMENT,
            "maximum_cold_regression": MAX_COLD_REGRESSION,
            "checkpoint_handoff_improvement": CHECKPOINT_HANDOFF_IMPROVEMENT,
            "maximum_checkpoint_health_latency_seconds": MAX_CHECKPOINT_HEALTH_LATENCY_SECONDS,
            "minimum_gpu_free_mib": MIN_GPU_FREE_MIB,
            "minimum_memavailable_bytes": MIN_MEMAVAILABLE_BYTES,
        },
        "metrics": metrics,
        "reasons": reasons,
        "accepted": not reasons,
        "status": "pass" if not reasons else "reject",
    }


def load_evidence(directory, require_cache, require_lifecycle=False, require_transition=False):
    """Load every required candidate or control evidence artifact."""
    evidence = {
        "manifest": load_json(directory / "manifest.json"),
        "contract": load_json(directory / "contract.json"),
        "benchmark": load_json(directory / "benchmark.json"),
        "resources": load_json(directory / "resources-summary.json"),
        "log_status": load_json(directory / "runtime-sanitized-status.json"),
        "watchdog": load_json(directory / "watchdog-status.json"),
    }
    if require_cache:
        evidence["cache"] = load_json(directory / "coding-cache.json")
    if require_lifecycle:
        evidence["qualification"] = load_json(directory / "qualification.json")
        evidence["candidate_result"] = load_json(directory / "candidate-result.json")
    if require_transition:
        evidence["checkpoint_transition"] = load_json(
            directory / "checkpoint-transition.json"
        )
        evidence["restore_result"] = load_json(directory / "restore-result.json")
    return evidence


def operational_reasons(evidence, primary):
    """Validate correctness, safety, benchmark, and restoration evidence."""
    reasons = []
    if not contract_passes(evidence["contract"]):
        reasons.append("19-case contract is incomplete")
    reasons.extend(resource_reasons(evidence["resources"]))
    if evidence["log_status"].get("status") != "pass":
        reasons.append("sanitized log evidence is incomplete")
    if evidence["watchdog"].get("status") != "disarmed":
        reasons.append("watchdog was not disarmed")
    benchmark_rows = by_id(evidence["benchmark"])
    if set(benchmark_rows) != {"1k", "8k"}:
        reasons.append("benchmark is incomplete")
    if primary in ("baseline", "cache_ram_mib"):
        cache_rows = by_id(evidence.get("cache", {}))
        if set(cache_rows) != {"a_cold", "a_continuation", "b_cold", "a_return"}:
            reasons.append("cache evidence is incomplete")
    result = evidence["candidate_result"]
    if result.get("contract_rc") != 0:
        reasons.append("lifecycle contract failed")
    if result.get("benchmark_rc") != 0:
        reasons.append("lifecycle benchmark failed")
    if primary in ("baseline", "cache_ram_mib") and result.get(
        "cache_benchmark_rc"
    ) != 0:
        reasons.append("lifecycle cache benchmark failed")
    if primary == "ctx_checkpoints" and result.get("checkpoint_transition_rc") != 0:
        reasons.append("lifecycle checkpoint transition failed")
    if result.get("final_owner") != "active":
        reasons.append("lifecycle did not restore the owner")
    if result.get("final_proxy") != "active":
        reasons.append("lifecycle did not restore the proxy")
    if result.get("final_health_status") != 200:
        reasons.append("lifecycle did not restore public health")
    if result.get("exact_restore") is not True:
        reasons.append("lifecycle did not prove exact control restoration")
    if "restore_result" in evidence and evidence["restore_result"].get(
        "exact_restore"
    ) is not True:
        reasons.append("exact restore evidence is not accepted")
    return reasons


def validate_control(directory, require_checkpoint_transition=False):
    """Fail closed on every artifact required before a control can be stopped."""
    manifest = load_json(directory / "manifest.json")
    primary = manifest.get("primary_variable")
    if primary not in ("baseline", "cache_ram_mib", "n_cpu_moe", "split_mode"):
        return ["control manifest has an unknown primary variable"]
    evidence = load_evidence(
        directory,
        primary in ("baseline", "cache_ram_mib"),
        require_lifecycle=True,
        require_transition=require_checkpoint_transition,
    )
    reasons = operational_reasons(evidence, primary)
    if not require_checkpoint_transition and (evidence["qualification"].get("status") != "pass" or evidence[
        "qualification"
    ].get("accepted") is not True):
        reasons.append("control qualification is not accepted")
    if require_checkpoint_transition:
        transition = evidence["checkpoint_transition"]
        reasons.extend(checkpoint_control_reasons(transition))
        if evidence["candidate_result"].get("checkpoint_transition_rc") not in (0, 1):
            reasons.append("checkpoint control transition did not finish")
    return reasons


def validate_cache_intermediate(directory):
    """Require a complete rejected 16 GiB step before testing 32 GiB."""
    manifest = load_json(directory / "manifest.json")
    evidence = load_evidence(directory, True, require_lifecycle=True)
    reasons = operational_reasons(evidence, "cache_ram_mib")
    if manifest.get("primary_variable") != "cache_ram_mib":
        reasons.append("intermediate is not a cache experiment")
    candidate = manifest.get("candidate", {})
    control = manifest.get("control", {})
    if candidate.get("cache_ram_mib") != 16384 or control.get(
        "cache_ram_mib"
    ) != 8192:
        reasons.append("intermediate must compare 16 GiB directly with 8 GiB")
    qualification = evidence["qualification"]
    if qualification.get("status") != "reject" or qualification.get(
        "accepted"
    ) is not False:
        reasons.append("32 GiB is eligible only after 16 GiB was rejected")
    return reasons


def validate_checkpoint_intermediate(directory):
    """Require a complete rejected 8-checkpoint step before testing 4."""
    manifest = load_json(directory / "manifest.json")
    evidence = load_evidence(
        directory, False, require_lifecycle=True, require_transition=True
    )
    reasons = operational_reasons(evidence, "ctx_checkpoints")
    candidate = manifest.get("candidate", {})
    control = manifest.get("control", {})
    if manifest.get("primary_variable") != "ctx_checkpoints":
        reasons.append("intermediate is not a checkpoint experiment")
    if candidate.get("ctx_checkpoints") != 8 or control.get("ctx_checkpoints") != 32:
        reasons.append("intermediate must compare 8 checkpoints directly with 32")
    if candidate.get("checkpoint_diagnostic") is not False:
        reasons.append("checkpoint diagnostic evidence cannot unlock 4 checkpoints")
    if candidate.get("checkpoint_transition_repeats") != 3:
        reasons.append("checkpoint intermediate must contain three formal repeats")
    transition_reasons = checkpoint_control_reasons(evidence["checkpoint_transition"])
    reasons.extend(transition_reasons)
    if not transition_reasons:
        reasons = [
            reason
            for reason in reasons
            if reason != "lifecycle checkpoint transition failed"
        ]
    qualification = evidence["qualification"]
    if qualification.get("status") != "reject" or qualification.get("accepted") is not False:
        reasons.append("4 checkpoints are eligible only after 8 was rejected")
    return reasons


def self_test():
    """Exercise accept and reject decisions without filesystem or network I/O."""
    contract = {
        "status": "pass",
        "results": [{"id": str(index), "pass": True} for index in range(19)],
    }
    resources = {
        "sample_count": 2,
        "host": {
            "maximum_swap_used_bytes": 0,
            "oom_kill_count_delta": 0,
            "minimum_memavailable_bytes": MIN_MEMAVAILABLE_BYTES + 1,
        },
        "gpus": {
            "0": {"minimum_memory_free_mib": 4096, "sample_count": 2},
            "1": {"minimum_memory_free_mib": 4096, "sample_count": 2},
        },
        "services": {
            "owner.service": {
                "maximum_restarts": 0,
                "collection_complete": True,
            }
        },
        "container": {
            "maximum_restart_count": 0,
            "oom_killed_observed": False,
            "observed_sample_count": 2,
        },
    }
    benchmark = {
        "results": [
            {"id": "1k", "median_tg_tokens_per_second": 10.0},
            {"id": "8k", "median_tg_tokens_per_second": 10.0},
        ]
    }
    cache = {
        "status": "pass",
        "results": [
            {"id": "a_cold", "median_ttft_seconds": 100.0},
            {"id": "a_continuation", "median_ttft_seconds": 10.0},
            {"id": "b_cold", "median_ttft_seconds": 100.0},
            {"id": "a_return", "median_ttft_seconds": 100.0},
        ],
    }
    control = {"contract": contract, "resources": resources,
               "benchmark": benchmark, "cache": cache,
               "log_status": {"status": "pass"},
               "watchdog": {"status": "disarmed"}}
    candidate_cache = json.loads(json.dumps(control))
    by_id(candidate_cache["cache"])["a_return"]["median_ttft_seconds"] = 89.0
    assert evaluate("cache_ram_mib", candidate_cache, control)["accepted"] is True
    by_id(candidate_cache["cache"])["a_return"]["median_ttft_seconds"] = 91.0
    assert evaluate("cache_ram_mib", candidate_cache, control)["accepted"] is False
    candidate_moe = json.loads(json.dumps(control))
    for row in candidate_moe["benchmark"]["results"]:
        row["median_tg_tokens_per_second"] = 11.1
    assert evaluate("n_cpu_moe", candidate_moe, control)["accepted"] is True
    candidate_moe["resources"]["host"]["maximum_swap_used_bytes"] = 1
    assert evaluate("n_cpu_moe", candidate_moe, control)["accepted"] is False
    candidate_pressure = json.loads(json.dumps(control))
    candidate_pressure["resources"]["host"][
        "minimum_memavailable_bytes"
    ] = MIN_MEMAVAILABLE_BYTES - 1
    assert evaluate("baseline", candidate_pressure)["accepted"] is False
    transition = {
        "results": [
            {"recall_ok": True, "handoff_ok": True, "health_failures": 0,
             "maximum_health_latency_seconds": 1.0,
             "recall_elapsed_seconds": 50.0, "handoff_elapsed_seconds": 100.0}
            for _ in range(3)
        ],
        "target_prompt_tokens": 127000,
        "median_handoff_elapsed_seconds": 100.0,
    }
    candidate_checkpoint = json.loads(json.dumps(control))
    candidate_checkpoint["checkpoint_transition"] = json.loads(json.dumps(transition))
    candidate_checkpoint["checkpoint_transition"]["median_handoff_elapsed_seconds"] = 40.0
    candidate_checkpoint["restore_result"] = {"exact_restore": True}
    control_checkpoint = json.loads(json.dumps(control))
    control_checkpoint["checkpoint_transition"] = transition
    assert evaluate("ctx_checkpoints", candidate_checkpoint, control_checkpoint)["accepted"] is True
    candidate_checkpoint["checkpoint_transition"]["results"][0]["health_failures"] = 1
    assert evaluate("ctx_checkpoints", candidate_checkpoint, control_checkpoint)["accepted"] is False
    candidate_checkpoint["checkpoint_transition"]["results"][0]["health_failures"] = 0
    candidate_checkpoint["restore_result"]["exact_restore"] = False
    assert evaluate("ctx_checkpoints", candidate_checkpoint, control_checkpoint)["accepted"] is False
    print(json.dumps({"self_test": "pass"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir")
    parser.add_argument("--control-dir")
    parser.add_argument(
        "--primary-variable",
        choices=("baseline", "cache_ram_mib", "ctx_checkpoints", "n_cpu_moe", "split_mode"),
    )
    parser.add_argument("--output")
    parser.add_argument("--validate-control-dir")
    parser.add_argument("--validate-cache-intermediate-dir")
    parser.add_argument("--validate-checkpoint-intermediate-dir")
    parser.add_argument("--require-checkpoint-transition", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.validate_control_dir:
        try:
            reasons = validate_control(
                Path(args.validate_control_dir), args.require_checkpoint_transition
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            reasons = [f"evidence error: {type(error).__name__}"]
        report = {
            "schema_version": 1,
            "status": "pass" if not reasons else "reject",
            "reasons": reasons,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        raise SystemExit(0 if not reasons else 1)
    if args.validate_cache_intermediate_dir:
        try:
            reasons = validate_cache_intermediate(
                Path(args.validate_cache_intermediate_dir)
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            reasons = [f"evidence error: {type(error).__name__}"]
        report = {
            "schema_version": 1,
            "status": "pass" if not reasons else "reject",
            "reasons": reasons,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        raise SystemExit(0 if not reasons else 1)
    if args.validate_checkpoint_intermediate_dir:
        try:
            reasons = validate_checkpoint_intermediate(
                Path(args.validate_checkpoint_intermediate_dir)
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            reasons = [f"evidence error: {type(error).__name__}"]
        report = {
            "schema_version": 1,
            "status": "pass" if not reasons else "reject",
            "reasons": reasons,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        raise SystemExit(0 if not reasons else 1)
    if not args.candidate_dir or not args.primary_variable or not args.output:
        parser.error("candidate directory, primary variable, and output are required")
    if args.primary_variable != "baseline" and not args.control_dir:
        parser.error("non-baseline experiments require --control-dir")
    require_cache = args.primary_variable in ("baseline", "cache_ram_mib")
    require_transition = args.primary_variable == "ctx_checkpoints"
    try:
        candidate = load_evidence(
            Path(args.candidate_dir), require_cache, require_transition=require_transition
        )
        control = (
            load_evidence(
                Path(args.control_dir), require_cache,
                require_transition=require_transition,
            )
            if args.control_dir
            else None
        )
        report = evaluate(args.primary_variable, candidate, control)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        report = {
            "schema_version": 1,
            "primary_variable": args.primary_variable,
            "accepted": False,
            "status": "reject",
            "reasons": [f"evidence error: {type(error).__name__}"],
            "metrics": {},
        }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as output_file:
        output_file.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["accepted"] else 1)


if __name__ == "__main__":
    main()
