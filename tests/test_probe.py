import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from model_probe.protocols import *
from model_probe.campaign import Campaign, gate, CASES, private_write
from model_probe.transport import Transport, validate_url, NoRedirect
from model_probe.cli import discover


def chat(content="OK", tool_calls=None):
    return {"choices": [{"index": 0, "finish_reason": "tool_calls" if tool_calls else "stop",
        "message": {"role": "assistant", "content": content, **({"tool_calls": tool_calls} if tool_calls else {})}}]}


class ProtocolTests(unittest.TestCase):
    def test_schema_strict_types(self):
        self.assertTrue(schema_matches({"ok": True, "result": 42}))
        for value in ({"ok": 1, "result": 42}, {"ok": True, "result": 42.0},
                      {"ok": True, "result": 42, "extra": 1}, {}):
            self.assertFalse(schema_matches(value))

    def test_payload_separate_protocols(self):
        for protocol in ("chat", "messages", "responses"):
            value = payload(protocol, "fixture", "OK", stream=True, with_tools=True, structured=True)
            self.assertTrue(value["tools"])
            self.assertNotIn("reasoning_effort", value)
        self.assertEqual(payload("chat", "fixture", "OK", reasoning="none")["reasoning_effort"], "none")
        with self.assertRaises(ValueError):
            payload("messages", "fixture", "OK", reasoning="none")

    def test_tool_identity_and_arguments(self):
        items = [{"id": name, "function": {"name": "lookup_fixture", "arguments": json.dumps({"key": name})}}
                 for name in ("alpha", "beta")]
        self.assertTrue(tool_match(chat(tool_calls=items), "chat", ["alpha", "beta"]))
        items[1]["id"] = "alpha"
        with self.assertRaises(ValueError):
            calls(chat(tool_calls=items), "chat")
        items[1]["id"] = "beta"
        items[0]["function"]["arguments"] = '{"key":"unsafe"}'
        with self.assertRaises(ValueError):
            calls(chat(tool_calls=items), "chat")

    def test_responses_preserves_reasoning(self):
        result = {"output": [{"type": "reasoning", "encrypted_content": "synthetic"},
                 {"type": "function_call", "call_id": "one", "name": "lookup_fixture", "arguments": '{"key":"alpha"}'}]}
        value = followup({"input": []}, result, "responses")
        self.assertEqual(value["input"][0], result["output"][0])
        self.assertEqual(value["input"][-1]["output"], "17")

    def test_messages_preserves_signed_blocks_and_errors(self):
        result = {"content": [{"type": "thinking", "signature": "synthetic"},
            {"type": "tool_use", "id": "one", "name": "lookup_fixture", "input": {"key": "alpha"}}]}
        value = followup({"messages": []}, result, "messages", True)
        self.assertEqual(value["messages"][0]["content"], result["content"])
        self.assertTrue(value["messages"][1]["content"][0]["is_error"])

    def test_chat_terminal_required(self):
        with self.assertRaises(ValueError):
            decode_stream(b'data: {"choices":[]}\n\ndata: [DONE]\n\n', "chat")
        raw = b'data: {"choices":[{"index":0,"delta":{"content":"OK"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        result, usage = decode_stream(raw, "chat")
        self.assertEqual(text(result, "chat"), "OK")
        self.assertEqual(usage, [])
        with self.assertRaises(ValueError):
            decode_stream(raw + b'data: {}\n\n', "chat")

    def test_truncated_utf8_or_frame(self):
        for raw in (b'data: {}', b'data: "\xc3"\n\n'):
            with self.assertRaises((ValueError, UnicodeError)):
                list(sse_events(raw))

    def test_responses_completed_and_error(self):
        body = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}]}
        raw = ('data: ' + json.dumps({"type": "response.completed", "response": body}) + '\n\n').encode()
        self.assertEqual(decode_stream(raw, "responses")[0], body)
        for kind in ("response.failed", "response.incomplete", "error"):
            with self.assertRaises(ValueError):
                decode_stream(('data: ' + json.dumps({"type": kind}) + '\n\n').encode(), "responses")

    def test_messages_complete(self):
        events = [{"type": "message_start", "message": {"content": []}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"text": "OK"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}, {"type": "message_stop"}]
        raw = ''.join('data: ' + json.dumps(item) + '\n\n' for item in events).encode()
        self.assertEqual(text(decode_stream(raw, "messages")[0], "messages"), "OK")
        with self.assertRaises(ValueError):
            decode_stream(raw.replace(b'"content_block_stop"', b'"ping"'), "messages")


class SafetyTests(unittest.TestCase):
    def test_url_guard(self):
        for url in ("http://account.example/v1", "https://evil.example/v1", "https://u:p@account.example/v1",
                    "https://account.example/v1?token=x", "https://account.example/other"):
            with self.assertRaises(ValueError):
                validate_url(url, "account.example")
        self.assertEqual(validate_url("http://127.0.0.1:8080/v1", "127.0.0.1", True), "http://127.0.0.1:8080/v1")

    def test_no_local_credentials(self):
        with self.assertRaises(ValueError):
            Transport("http://localhost:8080/v1", "localhost", local=True, token_env="SYNTHETIC")

    def test_redirect_denied(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))

    def test_token_rotation_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_text("synthetic-one")
            transport = Transport("https://account.example/v1", "account.example", token_file=path)
            self.assertEqual(transport.token(), "synthetic-one")
            path.write_text("synthetic-two")
            self.assertEqual(transport.token(), "synthetic-two")
            self.assertEqual(transport.redact({"value": "synthetic-one synthetic-two"}), {"value": "[REDACTED] [REDACTED]"})

    def test_headers_explicit_and_tls_no_redirect(self):
        class Response:
            code, headers = 200, {}
            def read(self, size): return json.dumps(chat()).encode()
            def __enter__(self): return self
            def __exit__(self, *args): pass
        transport = Transport("https://account.example/v1", "account.example", token_env="TEST_TOKEN")
        with patch.dict("os.environ", {"TEST_TOKEN": "synthetic"}), patch.object(transport.opener, "open", return_value=Response()) as opened:
            transport.send("chat", {"stream": False})
            request = opened.call_args.args[0]
            self.assertEqual(request.get_header("Accept"), "application/json")
            self.assertEqual(request.get_header("Authorization"), "Bearer synthetic")

    def test_inventory_mismatch(self):
        from types import SimpleNamespace
        result = SimpleNamespace(stdout=json.dumps([[{"ACCOUNT": "OTHER"}], [], []]))
        with patch("subprocess.run", return_value=result), self.assertRaises(ValueError):
            discover("fixture", "account.example", "EXPECTED")

    def test_gate_missing_duplicate_failure(self):
        rows = [{"run": run, "name": name, "status": "PASS"} for run in range(1, 4) for name in CASES]
        self.assertTrue(gate(rows, 3))
        self.assertFalse(gate(rows[:-1], 3))
        self.assertFalse(gate(rows + [rows[0]], 3))
        self.assertFalse(gate(rows, 1))
        rows[0]["status"] = "FAIL"
        self.assertFalse(gate(rows, 3))

    def test_exclusive_private_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            private_write(path, {"synthetic": True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                private_write(path, {})

    def test_unavailable_model_blocks_dependent_cases(self):
        transport = Transport("http://localhost:8080/v1", "localhost", local=True)
        with tempfile.TemporaryDirectory() as directory, patch.object(transport, "send", return_value=(None, {"http_status": 400})) as send:
            campaign = Campaign(transport, "synthetic", "chat", Path(directory) / "run")
            summary = campaign.run()
            self.assertEqual(send.call_count, 3)
            self.assertEqual(summary["counts"], {"FAIL": 3, "BLOCKED": 36})
            self.assertFalse(summary["release_eligible"])

    def test_budget_exhaustion(self):
        transport = Transport("http://localhost:8080/v1", "localhost", local=True)
        with tempfile.TemporaryDirectory() as directory, patch.object(transport, "send", return_value=(chat(), {"http_status": 200})) as send:
            campaign = Campaign(transport, "synthetic", "chat", Path(directory) / "run", max_requests=1)
            summary = campaign.run()
            self.assertEqual(send.call_count, 1)
            self.assertEqual(summary["status"], "PROFILE_BLOCKED")

    def test_full_synthetic_campaign_all_protocols(self):
        for protocol in ("chat", "messages", "responses"):
            def synthetic_send(selected, request):
                self.assertEqual(selected, protocol)
                history = request.get("input", request.get("messages"))
                prompt = history[0]["content"]
                tool_results = [item for item in history if item.get("role") == "tool" or item.get("type") == "function_call_output"]
                if protocol == "messages" and isinstance(history[-1].get("content"), list):
                    tool_results = history[-1]["content"]
                if tool_results:
                    contents = [item.get("output", item.get("content", "")) for item in tool_results]
                    answer = "UNAVAILABLE" if "unavailable" in str(contents) else str(sum(int(value) for value in contents))
                    keys = []
                elif request.get("tools"):
                    keys = ["alpha", "beta"] if "beta" in prompt else ["alpha"]
                    answer = ""
                else:
                    keys = []
                    answer = '{"ok":true,"result":42}' if "Return ok" in prompt else "BLUE7" if len(history) > 1 else "OK"
                if protocol == "chat":
                    result = chat(answer, [{"id": key, "type": "function", "function": {
                        "name": "lookup_fixture", "arguments": json.dumps({"key": key})}} for key in keys])
                elif protocol == "messages":
                    result = {"stop_reason": "tool_use" if keys else "end_turn", "content": [
                        {"type": "tool_use", "id": key, "name": "lookup_fixture", "input": {"key": key}} for key in keys]
                        if keys else [{"type": "text", "text": answer}]}
                else:
                    result = {"status": "completed", "output": [{"type": "function_call", "call_id": key,
                        "name": "lookup_fixture", "arguments": json.dumps({"key": key})} for key in keys]
                        if keys else [{"type": "message", "content": [{"type": "output_text", "text": answer}]}]}
                return result, {"http_status": 200}
            transport = Transport("http://localhost:8080/v1", "localhost", local=True)
            with tempfile.TemporaryDirectory() as directory, patch.object(transport, "send", side_effect=synthetic_send):
                summary = Campaign(transport, "synthetic", protocol, Path(directory) / "run").run()
                self.assertEqual(summary["counts"], {"PASS": 39}, protocol)
                self.assertEqual(summary["status"], "PROFILE_QUALIFIED")

    def test_http_errors_are_preserved(self):
        import io
        transport = Transport("http://localhost:8080/v1", "localhost", local=True)
        error = urllib.error.HTTPError("http://localhost:8080/v1/chat/completions", 400, "rejected", {}, io.BytesIO(b'{"error":"unknown model"}'))
        with patch.object(transport.opener, "open", side_effect=error):
            result, meta = transport.send("chat", {})
        self.assertIsNone(result)
        self.assertEqual(meta["http_status"], 400)
        self.assertIn("unknown model", meta["raw_response"])

    def test_200_error_and_oversize_rejected(self):
        class Response:
            code, headers = 200, {}
            def read(self, size): return b'{"code":"390112"}'
            def __enter__(self): return self
            def __exit__(self, *args): pass
        transport = Transport("http://localhost:8080/v1", "localhost", local=True)
        with patch.object(transport.opener, "open", return_value=Response()), self.assertRaises(ValueError):
            transport.send("chat", {})
        transport.max_bytes = 1
        with patch.object(transport.opener, "open", return_value=Response()), self.assertRaises(ValueError):
            transport.send("chat", {})


if __name__ == "__main__":
    unittest.main()