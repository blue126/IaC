#!/usr/bin/env python3
"""Validate canned and live DeepSeek OpenAI-compatible API contracts."""

import argparse
import ast
import json
import re
import sys
import urllib.request
from pathlib import Path

REVISION = "v1"
HEARTBEAT_PATH = None


def touch_heartbeat():
    """Refresh the managed-host watchdog heartbeat when configured."""
    if HEARTBEAT_PATH is not None:
        HEARTBEAT_PATH.touch(exist_ok=True)


def validate_message(body, expected_tools=None):
    """Validate content/reasoning separation and structured tool calls."""
    try:
        message = body["choices"][0]["message"]
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        calls = message.get("tool_calls") or []
        if "<think>" in content or "DSML" in content:
            return False
        if expected_tools is not None and len(calls) != len(expected_tools):
            return False
        observed_tools = {}
        for call in calls:
            if not call.get("id") or call.get("type") != "function":
                return False
            function = call["function"]
            if not function.get("name"):
                return False
            arguments = json.loads(function["arguments"])
            if not isinstance(arguments, dict):
                return False
            observed_tools[function["name"]] = arguments
        if expected_tools is not None and observed_tools != expected_tools:
            return False
        return bool(content or reasoning or calls)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return False


def validate_sse(raw):
    """Require JSON deltas followed by exactly one final DONE event."""
    done_count = 0
    saw_delta = False
    try:
        for line in raw.splitlines():
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data: "):
                return False
            payload = line[6:]
            if payload == "[DONE]":
                done_count += 1
                continue
            if done_count:
                return False
            delta = json.loads(payload)["choices"][0]["delta"]
            if "<think>" in str(delta) or "DSML" in str(delta):
                return False
            saw_delta = saw_delta or bool(delta)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return False
    return saw_delta and done_count == 1


def normalized(value):
    """Normalize a short deterministic answer without weakening equality."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def is_ok_reply(value):
    """Accept the requested token with only optional terminal punctuation."""
    return normalized(value).rstrip(".。!！") == "ok"


def valid_add_function(content):
    """Statically require an add(a, b) function returning a + b."""
    code = content.strip()
    fenced = re.search(r"```(?:python)?\s*(.*?)```", code, re.DOTALL)
    if fenced:
        code = fenced.group(1)
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "add":
            if len(node.args.args) != 2 or len(node.body) != 1:
                return False
            statement = node.body[0]
            return isinstance(statement, ast.Return) and isinstance(
                statement.value, ast.BinOp
            ) and isinstance(statement.value.op, ast.Add)
    return False


def post(base_url, payload, stream=False):
    """Send one OpenAI-compatible request and return parsed or raw data."""
    request = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    touch_heartbeat()
    with urllib.request.urlopen(request, timeout=1800) as response:
        raw = response.read().decode()
    touch_heartbeat()
    return raw if stream else json.loads(raw)


def result(case_id, passed, source="live", detail=""):
    """Build one stable evidence result."""
    return {
        "id": case_id,
        "source": source,
        "pass": bool(passed),
        "detail": detail,
    }


def guarded(case_id, callback):
    """Record request errors as evidence instead of losing the report."""
    try:
        return result(case_id, callback())
    except Exception as error:  # Evidence must retain unexpected API failures.
        return result(case_id, False, detail=str(error))


def canned_results():
    """Prove validators safely reject malformed tool and SSE payloads."""
    fixture = Path(__file__).with_name("api-fixtures-v1.json")
    cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]
    results = []
    for case in cases:
        observed = (
            validate_sse(case["body"])
            if case["kind"] == "sse"
            else validate_message(case["body"])
        )
        results.append(
            {
                "id": case["id"],
                "source": "canned",
                "expected_valid": case["valid"],
                "observed_valid": observed,
                "pass": observed == case["valid"],
            }
        )
    return results


def base_payload(model, prompt):
    """Return deterministic request defaults shared by live cases."""
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "seed": 42,
        "max_tokens": 256,
    }


def tool_definitions():
    """Return two deterministic function schemas for tool-call coverage."""
    return [
        {
            "type": "function",
            "function": {
                "name": "lookup_weather",
                "description": "Look up weather for a city.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_numbers",
                "description": "Add two numbers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "left": {"type": "number"},
                        "right": {"type": "number"},
                    },
                    "required": ["left", "right"],
                },
            },
        },
    ]


def run_correctness(base_url, model):
    """Run the versioned math, code, fact, Chinese and long-context corpus."""
    path = Path(__file__).with_name("correctness-corpus-v1.json")
    corpus = json.loads(path.read_text(encoding="utf-8"))
    benchmark_path = Path(__file__).with_name("benchmark-corpus-v1.json")
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    long_case = next(case for case in benchmark["cases"] if case["id"] == "8k")
    words = long_case["repeat_text"].split()
    long_prompt = "Remember the marker COBALT-731. " + " ".join(
        words * max(1, long_case["target_prompt_tokens"] // len(words))
    ) + " Return only the marker from the beginning."
    results = []
    for case in corpus["cases"]:
        prompt = long_prompt if case.get("prompt_fixture") else case["prompt"]

        def check(current=case, current_prompt=prompt):
            body = post(base_url, base_payload(model, current_prompt))
            if not validate_message(body):
                return False
            content = body["choices"][0]["message"].get("content") or ""
            if current["match"] == "exact":
                return normalized(content) == normalized(current["expected"])
            if current["match"] == "python-add-ast":
                return valid_add_function(content)
            return False

        results.append(guarded(f"correctness-{case['id']}", check))
    return results


def run_live(base_url, model, skip_compatibility=False):
    """Run sync, SSE, reasoning, tool and continuation contracts."""
    results = []
    sync = base_payload(model, "Reply with exactly OK.")
    results.append(
        guarded(
            "sync-chat",
            lambda: is_ok_reply(
                post(base_url, sync)["choices"][0]["message"].get("content") or ""
            ),
        )
    )

    if not skip_compatibility:
        zero_thinking = dict(sync, thinking_budget_tokens=0)

        def check_zero_thinking():
            body = post(base_url, zero_thinking)
            message = body["choices"][0]["message"]
            content = message.get("content") or ""
            return (
                validate_message(body)
                and "</think>" not in content
                and is_ok_reply(content)
            )

        results.append(guarded("zero-thinking-chat", check_zero_thinking))
    stream = dict(sync, stream=True)
    results.append(
        guarded("sse-chat", lambda: validate_sse(post(base_url, stream, True)))
    )

    for effort in ("low", "high", "max"):
        payload = dict(sync, reasoning_effort=effort)

        def check_reasoning(current=payload):
            body = post(base_url, current)
            message = body["choices"][0]["message"]
            return validate_message(body) and bool(message.get("reasoning_content"))

        results.append(guarded(f"reasoning-{effort}", check_reasoning))

    tools = tool_definitions()
    single_payload = base_payload(model, "Call lookup_weather for Sydney.")
    single_payload.update({"tools": tools[:1], "tool_choice": "required"})
    single_body = None
    try:
        single_body = post(base_url, single_payload)
        results.append(
            result(
                "single-tool",
                validate_message(
                    single_body,
                    {"lookup_weather": {"city": "Sydney"}},
                ),
            )
        )
    except Exception as error:
        results.append(result("single-tool", False, detail=str(error)))

    parallel_payload = base_payload(
        model,
        "Call lookup_weather for Sydney and add_numbers for 19 plus 23.",
    )
    parallel_payload.update(
        {"tools": tools, "tool_choice": "required", "parallel_tool_calls": True}
    )
    parallel_body = None
    expected_parallel = {
        "lookup_weather": {"city": "Sydney"},
        "add_numbers": {"left": 19, "right": 23},
    }
    try:
        parallel_body = post(base_url, parallel_payload)
        results.append(
            result(
                "parallel-tool",
                validate_message(parallel_body, expected_parallel),
            )
        )
    except Exception as error:
        results.append(result("parallel-tool", False, detail=str(error)))

    if parallel_body and validate_message(parallel_body, expected_parallel):
        assistant = parallel_body["choices"][0]["message"]
        calls = assistant["tool_calls"]
        results_by_name = {
            "lookup_weather": '{"temperature_c": 21}',
            "add_numbers": '{"result": 42}',
        }
        continuation = base_payload(model, "unused")
        continuation["messages"] = [
            parallel_payload["messages"][0],
            assistant,
        ]
        continuation["messages"].extend(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": results_by_name[call["function"]["name"]],
            }
            for call in calls
        )
        continuation["tools"] = tools

        def check_continuation():
            body = post(base_url, continuation)
            content = body["choices"][0]["message"].get("content") or ""
            return validate_message(body) and "21" in content and "42" in content

        results.append(
            guarded(
                "tool-continuation",
                check_continuation,
            )
        )
    else:
        results.append(result("tool-continuation", False, detail="single tool failed"))

    results.extend(run_correctness(base_url, model))
    results.extend(
        item
        for item in canned_results()
        if not item["expected_valid"]
    )
    return results


def main():
    """Run a self-test or live suite and write stable JSON evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--output")
    parser.add_argument("--skip-compatibility", action="store_true")
    parser.add_argument("--heartbeat-file")
    args = parser.parse_args()
    global HEARTBEAT_PATH
    HEARTBEAT_PATH = Path(args.heartbeat_file) if args.heartbeat_file else None
    if not args.self_test and (not args.base_url or not args.model):
        parser.error("live mode requires --base-url and --model")
    results = (
        canned_results()
        if args.self_test
        else run_live(
            args.base_url.rstrip("/"),
            args.model,
            args.skip_compatibility,
        )
    )
    evidence = {
        "schema_version": 1,
        "fixture_revision": REVISION,
        "status": "pass" if all(item["pass"] for item in results) else "fail",
        "results": results,
    }
    rendered = json.dumps(evidence, indent=2, sort_keys=True)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as output_file:
            output_file.write(rendered + "\n")
    print(rendered)
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
