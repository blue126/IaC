#!/usr/bin/env python3
"""Forward OpenAI-compatible traffic and suppress complete zero-thinking traces."""

import argparse
import http.client
import ipaddress
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def zero_thinking_request(body):
    """Return true only for a valid JSON body with a numeric zero budget."""
    try:
        request = json.loads(body.decode("utf-8"))
        budget = request.get("thinking_budget_tokens")
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(budget, (int, float)) and not isinstance(budget, bool) and budget == 0


def client_allowed(address, allowed_networks):
    """Return whether a direct peer address is inside the configured CIDRs."""
    try:
        client = ipaddress.ip_address(address)
        return any(client in network for network in allowed_networks)
    except ValueError:
        return False


def strip_complete_leading_thought(content):
    """Remove a complete zero-budget thought prefix from a synchronous response."""
    if not isinstance(content, str):
        return content
    closing = content.find(THINK_CLOSE)
    if closing < 0:
        return content
    return content[closing + len(THINK_CLOSE) :]


def normalize_completion(body):
    """Normalize a complete JSON chat response without creating new fields."""
    try:
        response = json.loads(body.decode("utf-8"))
        choices = response["choices"]
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        return body
    changed = False
    for choice in choices:
        message = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        normalized = strip_complete_leading_thought(content)
        if normalized != content:
            if not content.startswith(THINK_OPEN):
                sys.stderr.write("suppressed_bare_thought_prefix\n")
            message["content"] = normalized
            changed = True
    if not changed:
        return body
    return json.dumps(response, separators=(",", ":")).encode("utf-8")


class ThoughtStreamNormalizer:
    """Suppress only explicit thought prefixes while preserving normal streaming."""

    def __init__(self):
        self.pending = {}
        self.resolved = set()

    def _flush(self, index):
        pending = self.pending.pop(index, "")
        if not pending:
            return []
        return [self._content_event(index, pending)]

    @staticmethod
    def _content_event(index, content):
        return "data: " + json.dumps(
            {"choices": [{"index": index, "delta": {"content": content}}]},
            separators=(",", ":"),
        ) + "\n\n"

    def transform_event(self, event):
        """Transform one complete SSE event while preserving non-content protocol data."""
        if not event.startswith("data: "):
            return [event]
        payload = event[6:].strip()
        if payload == "[DONE]":
            flushed = []
            for index in list(self.pending):
                flushed.extend(self._flush(index))
            return flushed + [event]
        try:
            document = json.loads(payload)
            choices = document["choices"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return [event]
        prefix = []
        changed = False
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            index = choice.get("index", 0)
            delta = choice.get("delta")
            if not isinstance(delta, dict) or not isinstance(delta.get("content"), str):
                if choice.get("finish_reason") is not None:
                    prefix.extend(self._flush(index))
                continue
            content = delta["content"]
            if index in self.resolved:
                continue
            pending = self.pending.get(index, "")
            if index in self.pending:
                combined = pending + content
                closing = combined.find(THINK_CLOSE)
                if closing < 0:
                    self.pending[index] = combined
                    delta.pop("content")
                    changed = True
                    continue
                self.pending.pop(index, None)
                self.resolved.add(index)
                delta["content"] = combined[closing + len(THINK_CLOSE) :]
                changed = True
                continue
            if content.startswith(THINK_OPEN) or (
                content and THINK_OPEN.startswith(content)
            ):
                closing = content.find(THINK_CLOSE)
                if closing < 0:
                    self.pending[index] = content
                    delta.pop("content")
                    changed = True
                    continue
                self.resolved.add(index)
                delta["content"] = content[closing + len(THINK_CLOSE) :]
                changed = True
                continue
            self.resolved.add(index)
        for choice in choices:
            if not isinstance(choice, dict) or choice.get("finish_reason") is None:
                continue
            prefix.extend(self._flush(choice.get("index", 0)))
        if not changed:
            return prefix + [event]
        document["choices"] = [
            choice
            for choice in choices
            if not (
                isinstance(choice, dict)
                and set(choice).issubset({"index", "delta"})
                and choice.get("delta") == {}
            )
        ]
        if not document["choices"]:
            return prefix
        return prefix + ["data: " + json.dumps(document, separators=(",", ":")) + "\n\n"]


def normalize_sse_events(events):
    """Normalize a sequence of complete SSE events for deterministic offline tests."""
    normalizer = ThoughtStreamNormalizer()
    rendered = []
    for event in events:
        rendered.extend(normalizer.transform_event(event))
    return rendered


class ProxyHandler(BaseHTTPRequestHandler):
    """Small local HTTP reverse proxy; it deliberately never logs request bodies."""

    protocol_version = "HTTP/1.1"
    backend_host = "127.0.0.1"
    backend_port = 8082
    timeout = 1800
    allowed_networks = ()
    max_body_bytes = 8 * 1024 * 1024

    def log_message(self, format_string, *args):
        """Log only safe operational metadata, never prompts or authorization values."""
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    @staticmethod
    def _read_sse_line(upstream):
        """Read one decoded SSE line, including from a chunked HTTP response."""
        fragments = []
        while True:
            fragment = upstream.read(1)
            if not fragment:
                return b"".join(fragments)
            fragments.append(fragment)
            if fragment == b"\n":
                return b"".join(fragments)

    def _forward(self):
        if not client_allowed(self.client_address[0], self.allowed_networks):
            self.send_error(403, "source address is not allowed")
            return
        transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
        if transfer_encoding and transfer_encoding != "identity":
            self.send_error(501, "chunked request bodies are unsupported")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "invalid Content-Length")
            return
        if length < 0 or length > self.max_body_bytes:
            self.send_error(413, "request body too large")
            return
        body = self.rfile.read(length) if length else b""
        eligible = self.command in {"POST", "PUT", "PATCH"} and zero_thinking_request(body)
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS
            and name.lower() not in {"host", "content-length"}
        }
        headers["Accept-Encoding"] = "identity"
        if body:
            headers["Content-Length"] = str(len(body))
        connection = http.client.HTTPConnection(
            self.backend_host, self.backend_port, timeout=self.timeout
        )
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            upstream = connection.getresponse()
            content_type = upstream.getheader("Content-Type", "")
            content_encoding = upstream.getheader("Content-Encoding", "identity").lower()
            is_sse = "text/event-stream" in content_type.lower()
            is_json = eligible and "application/json" in content_type.lower()
            if eligible and content_encoding not in {"", "identity"}:
                upstream.read()
                self.send_error(502, "upstream returned an unsupported content encoding")
                return
            self.send_response(upstream.status, upstream.reason)
            for name, value in upstream.getheaders():
                if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() != "content-length":
                    self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if is_sse and eligible:
                normalizer = ThoughtStreamNormalizer()
                event_lines = []
                while True:
                    line = self._read_sse_line(upstream)
                    if not line:
                        for rendered in self._normalize_sse_event(normalizer, event_lines):
                            self.wfile.write(rendered.encode("utf-8"))
                        break
                    text = line.decode("utf-8", errors="replace")
                    if text in {"\n", "\r\n"}:
                        for rendered in self._normalize_sse_event(normalizer, event_lines):
                            self.wfile.write(rendered.encode("utf-8"))
                        event_lines = []
                        self.wfile.flush()
                        continue
                    event_lines.append(text.rstrip("\r\n"))
            elif is_sse:
                # No compatibility transform is needed: relay every upstream
                # line immediately so normal streaming does not become a
                # buffered end-of-response delivery.
                while True:
                    line = self._read_sse_line(upstream)
                    if not line:
                        break
                    self.wfile.write(line)
                    self.wfile.flush()
            else:
                response = upstream.read()
                self.wfile.write(normalize_completion(response) if is_json else response)
        except (OSError, http.client.HTTPException) as error:
            self.send_error(502, "upstream unavailable")
            sys.stderr.write("upstream_error %s %s\n" % (self.path, type(error).__name__))
        finally:
            connection.close()

    @staticmethod
    def _normalize_sse_event(normalizer, lines):
        """Normalize one complete SSE event while retaining non-data metadata."""
        if not lines:
            return []
        data = [line[5:].lstrip() for line in lines if line.startswith("data:")]
        if not data:
            return ["\n".join(lines) + "\n\n"]
        passthrough = [line for line in lines if not line.startswith("data:")]
        transformed = normalizer.transform_event("data: " + "\n".join(data) + "\n\n")
        if not passthrough:
            return transformed
        prefix = "\n".join(passthrough) + "\n"
        return [prefix + item for item in transformed]

    do_GET = _forward
    do_POST = _forward
    do_PUT = _forward
    do_PATCH = _forward
    do_DELETE = _forward


def self_test():
    """Exercise complete, split-stream and fail-closed normalization without a GPU."""
    sync = json.dumps(
        {"choices": [{"message": {"content": "<think>private</think>OK"}}]}
    ).encode()
    normalized = json.loads(normalize_completion(sync))
    cases = {
        "zero-budget": zero_thinking_request(b'{"thinking_budget_tokens":0}'),
        "nonzero-passthrough": not zero_thinking_request(b'{"thinking_budget_tokens":1}'),
        "absent-passthrough": not zero_thinking_request(b'{}'),
        "malformed-passthrough": not zero_thinking_request(b"not json"),
        "allow-loopback": client_allowed(
            "127.0.0.1", [ipaddress.ip_network("127.0.0.0/8")]
        ),
        "deny-untrusted-source": not client_allowed(
            "10.0.0.1", [ipaddress.ip_network("192.168.1.0/24")]
        ),
        "sync-suppression": normalized["choices"][0]["message"]["content"] == "OK",
        "sync-bare-terminator-suppression": json.loads(
            normalize_completion(
                b'{"choices":[{"message":{"content":"private</think>OK"}}]}'
            )
        )["choices"][0]["message"]["content"] == "OK",
        "sync-unterminated": normalize_completion(
            b'{"choices":[{"message":{"content":"<think>private"}}]}'
        ) == b'{"choices":[{"message":{"content":"<think>private"}}]}',
    }
    split = normalize_sse_events(
        [
            'data: {"choices":[{"index":0,"delta":{"content":"<thi"}}]}\n\n',
            'data: {"choices":[{"index":0,"delta":{"content":"nk>private</th"}}]}\n\n',
            'data: {"choices":[{"index":0,"delta":{"content":"ink>OK"}}]}\n\n',
            'data: [DONE]\n\n',
        ]
    )
    cases["split-sse-suppression"] = split == [
        'data: {"choices":[{"index":0,"delta":{"content":"OK"}}]}\n\n',
        'data: [DONE]\n\n',
    ]
    bare_split = normalize_sse_events(
        [
            'data: {"choices":[{"index":0,"delta":{"content":"private</th"}}]}\n\n',
            'data: {"choices":[{"index":0,"delta":{"content":"ink>OK"}}]}\n\n',
            'data: [DONE]\n\n',
        ]
    )
    cases["split-sse-bare-terminator-passthrough"] = bare_split == [
        'data: {"choices":[{"index":0,"delta":{"content":"private</th"}}]}\n\n',
        'data: {"choices":[{"index":0,"delta":{"content":"ink>OK"}}]}\n\n',
        'data: [DONE]\n\n',
    ]
    post_prefix = normalize_sse_events(
        [
            'data: {"choices":[{"index":0,"delta":{"content":"<think>x</think>Hello"}}]}\n\n',
            'data: {"choices":[{"index":0,"delta":{"content":" world"}}]}\n\n',
            'data: [DONE]\n\n',
        ]
    )
    cases["sse-post-prefix-streaming"] = post_prefix == [
        'data: {"choices":[{"index":0,"delta":{"content":"Hello"}}]}\n\n',
        'data: {"choices":[{"index":0,"delta":{"content":" world"}}]}\n\n',
        'data: [DONE]\n\n',
    ]
    no_thought = normalize_sse_events(
        [
            'data: {"choices":[{"index":0,"delta":{"content":"Hello"}}]}\n\n',
            'data: {"choices":[{"index":0,"delta":{"content":" world"}}]}\n\n',
            'data: [DONE]\n\n',
        ]
    )
    cases["sse-no-thought-streaming"] = no_thought == [
        'data: {"choices":[{"index":0,"delta":{"content":"Hello"}}]}\n\n',
        'data: {"choices":[{"index":0,"delta":{"content":" world"}}]}\n\n',
        'data: [DONE]\n\n',
    ]
    multi_line = ProxyHandler._normalize_sse_event(
        ThoughtStreamNormalizer(),
        [
            'data: {"choices":[',
            'data: {"index":0,"delta":{"content":"<think>x</think>OK"}}]}',
        ],
    )
    cases["multiline-sse-suppression"] = multi_line == [
        'data: {"choices":[{"index":0,"delta":{"content":"OK"}}]}\n\n'
    ]
    passthrough = 'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"id":"call_1"}]}}]}\n\n'
    cases["tool-passthrough"] = normalize_sse_events([passthrough]) == [passthrough]
    unterminated = normalize_sse_events(
        [
            'data: {"choices":[{"index":0,"delta":{"content":"<think>private"}}]}\n\n',
            'data: [DONE]\n\n',
        ]
    )
    cases["sse-unterminated-passthrough"] = unterminated == [
        'data: {"choices":[{"index":0,"delta":{"content":"<think>private"}}]}\n\n',
        'data: [DONE]\n\n',
    ]
    failed = [name for name, passed in cases.items() if not passed]
    print(json.dumps({"status": "pass" if not failed else "fail", "failures": failed}))
    return not failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8081)
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8082)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--allow-cidrs", default="")
    args = parser.parse_args()
    if args.self_test:
        return 0 if self_test() else 1
    ProxyHandler.backend_host = args.backend_host
    ProxyHandler.backend_port = args.backend_port
    ProxyHandler.timeout = args.timeout
    allowed_cidrs = [cidr for cidr in args.allow_cidrs.split(",") if cidr]
    if not allowed_cidrs:
        parser.error("at least one --allow-cidrs value is required")
    try:
        ProxyHandler.allowed_networks = tuple(
            ipaddress.ip_network(cidr, strict=True) for cidr in allowed_cidrs
        )
    except ValueError as error:
        parser.error(f"invalid --allow-cidrs value: {error}")
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), ProxyHandler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
