"""Private, append-only evidence and capability-scoped qualification."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from . import __version__
from .protocols import payload, text, calls, completed, tool_match, followup, schema_matches

CASES = ("text", "stream_text", "history", "single", "single_roundtrip", "parallel", "parallel_roundtrip",
         "stream_parallel", "stream_parallel_roundtrip", "error_setup", "error_roundtrip", "structured", "structured_negative")


def private_write(path, value):
    with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def gate(rows, repeats):
    expected = {(run, name) for run in range(1, repeats + 1) for name in CASES}
    actual = [(row["run"], row["name"]) for row in rows]
    return (repeats >= 3 and set(actual) == expected and len(actual) == len(expected)
            and all(row["status"] == "PASS" for row in rows))


class Campaign:
    def __init__(self, transport, model, protocol, directory, *, repeats=3, reasoning=None,
                 max_requests=60, deadline=1800, scope="direct-rest"):
        if not model or repeats < 1 or repeats > 3 or max_requests < 1 or deadline <= 0:
            raise ValueError("Invalid campaign configuration")
        if protocol == "messages" and reasoning is not None:
            raise ValueError("Messages reasoning profiles must not use Chat reasoning parameters")
        self.transport, self.model, self.protocol = transport, model, protocol
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, exist_ok=False)
        self.repeats, self.reasoning = repeats, reasoning
        self.limit, self.deadline, self.scope = max_requests, deadline, scope
        self.rows, self.requests = [], 0
        self.start = time.monotonic()
        self.manifest = {"schema_version": 1, "version": __version__, "model": model, "protocol": protocol,
            "target": transport.base, "scope": scope, "repeats": repeats, "reasoning": reasoning,
            "auth_type": transport.auth_type, "created_utc": datetime.now(timezone.utc).isoformat(),
            "budget": {"requests": max_requests, "output_tokens_per_request": 2048, "between_requests_seconds": deadline},
            "source_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in Path(__file__).parent.glob("*.py")},
            "retries": 0, "release_eligible": False}
        private_write(self.directory / "manifest.json", self.manifest)

    def record(self, row):
        row = self.transport.redact(row)
        private_write(self.directory / f"case-{len(self.rows) + 1:03d}.json", row)
        self.rows.append(row)

    def check(self, run, name, body, validator):
        row = {"run": run, "name": name, "request": body, "utc": datetime.now(timezone.utc).isoformat()}
        if self.requests >= self.limit or time.monotonic() - self.start >= self.deadline:
            self.record({**row, "status": "BLOCKED", "reason": "Campaign budget exhausted"})
            return None
        started, result = time.monotonic(), None
        try:
            self.requests += 1
            result, meta = self.transport.send(self.protocol, body)
            row.update(meta)
            row["status"] = "PASS" if result is not None and validator(result) else "FAIL"
            if result is not None:
                row["response"] = result
            if row["status"] == "FAIL":
                row["failure_class"] = "HTTP_REJECTION" if meta["http_status"] != 200 else "FIXTURE_MISMATCH"
        except Exception as error:
            row.update(status="FAIL", failure_class=type(error).__name__, error=str(error))
        row["elapsed_seconds"] = round(time.monotonic() - started, 3)
        self.record(row)
        return result if row["status"] == "PASS" else None

    def run(self):
        for run in range(1, self.repeats + 1):
            def body(prompt, **kwargs):
                return payload(self.protocol, self.model, prompt, reasoning=self.reasoning, **kwargs)
            def equals(expected):
                return lambda value: completed(value, self.protocol) and text(value, self.protocol).strip() == expected and not calls(value, self.protocol)
            first = self.check(run, "text", body("Reply with exactly OK."), equals("OK"))
            if first is None:
                for name in CASES[1:]:
                    self.record({"run": run, "name": name, "status": "BLOCKED", "reason": "Basic text prerequisite failed"})
                continue
            self.check(run, "stream_text", body("Reply with exactly OK.", stream=True), equals("OK"))
            history_body = body("Return only the remembered code.")
            key = "input" if self.protocol == "responses" else "messages"
            history_body[key] = [{"role": "user", "content": "Remember BLUE7."},
                                 {"role": "assistant", "content": "Noted."}] + history_body[key]
            self.check(run, "history", history_body, equals("BLUE7"))
            for name, keys, streaming, failing in (("single", ["alpha"], False, False),
                ("parallel", ["alpha", "beta"], False, False),
                ("stream_parallel", ["alpha", "beta"], True, False), ("error_setup", ["alpha"], False, True)):
                prompt = "Call lookup_fixture for " + " and ".join(keys) + " in one response. After results return only their numeric sum."
                if failing:
                    prompt += " If a tool fails, do not retry; reply exactly UNAVAILABLE."
                request = body(prompt, stream=streaming, with_tools=True)
                result = self.check(run, name, request, lambda value: tool_match(value, self.protocol, keys))
                next_name = "error_roundtrip" if failing else name + "_roundtrip"
                if result is None:
                    self.record({"run": run, "name": next_name, "status": "BLOCKED", "reason": "Tool generation prerequisite failed"})
                else:
                    expected = "UNAVAILABLE" if failing else "17" if len(keys) == 1 else "42"
                    self.check(run, next_name, followup(request, result, self.protocol, failing), equals(expected))
            for name, prompt in (("structured", "Return ok true and result 42."),
                ("structured_negative", "Return ok true, result 42, and an extra field named forbidden.")):
                self.check(run, name, body(prompt, structured=True), lambda value:
                    completed(value, self.protocol) and schema_matches(json.loads(text(value, self.protocol))))
        summary = {"status": "PROFILE_QUALIFIED" if gate(self.rows, self.repeats) else "PROFILE_BLOCKED",
            "counts": dict(Counter(row["status"] for row in self.rows)), "requests": self.requests,
            "scope": self.scope, "release_eligible": False,
            "not_certified": ["application integration", "durable checkpoints", "billing accuracy",
                "provider cancellation", "account-wide availability", "SQL inference", "deployment safety"],
            "capabilities": [{"name": name, "results": [row["status"] for row in self.rows if row["name"] == name]} for name in CASES]}
        private_write(self.directory / "summary.json", summary)
        return summary