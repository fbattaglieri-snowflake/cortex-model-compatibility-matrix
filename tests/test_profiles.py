"""Offline regression coverage for explicit destinations and scoped qualification."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_probe.campaign import Campaign, CASES, gate, required_cases
from model_probe.transport import Transport, validate_url
from model_probe.cli import main
from tests.test_probe import chat


class DestinationTests(unittest.TestCase):
    def test_custom_https_requires_exact_approval(self):
        url = "https://proxy.example:8443/responses/v1"
        with self.assertRaises(ValueError):
            validate_url(url, "proxy.example")
        self.assertEqual(validate_url(url, "proxy.example", expected_base_url=url), url)
        for changed in (url.replace("8443", "8444"), url.replace("responses", "chat"),
                        url.replace("proxy.example", "other.example")):
            with self.assertRaises(ValueError):
                validate_url(changed, "proxy.example", expected_base_url=url)

    def test_unsafe_paths_still_rejected_with_approval(self):
        for path in ("/../v1", "/a/./v1", "/a//v1", "/%2e%2e/v1", "/a\\b/v1",
                     "/v1?secret=x", "/v1#x", "/v1\n"):
            url = "https://proxy.example" + path
            with self.assertRaises(ValueError):
                validate_url(url, "proxy.example", expected_base_url=url)

    def test_internal_spcs_explicit_no_credentials(self):
        host = "test-proxy.namespace.svc.spcs.internal"
        url = f"http://{host}:8080/chat/v1"
        with self.assertRaises(ValueError):
            validate_url(url, host, expected_base_url=url)
        with self.assertRaises(ValueError):
            validate_url(url, host, internal_proxy=True)
        transport = Transport(url, host, expected_base_url=url, internal_proxy=True)
        self.assertEqual(transport.token(), "")
        for kwargs in ({"token_env": "TOKEN"}, {"token_file": "/unused"}, {"local": True}):
            with self.assertRaises(ValueError):
                Transport(url, host, expected_base_url=url, internal_proxy=True, **kwargs)
        for other in ("proxy.example", "svc.spcs.internal.evil.example", "127.0.0.1"):
            candidate = f"http://{other}/v1"
            with self.assertRaises(ValueError):
                validate_url(candidate, other, expected_base_url=candidate, internal_proxy=True)

    def test_custom_prefix_used_on_wire_without_credentials(self):
        host = "test.namespace.svc.spcs.internal"
        url = f"http://{host}:8080/messages/v1"
        transport = Transport(url, host, expected_base_url=url, internal_proxy=True)
        class Response:
            code, headers = 200, {}
            def read(self, size): return b'{"content":[]}'
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with patch.object(transport.opener, "open", return_value=Response()) as opened:
            transport.send("messages", {})
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, url + "/messages")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(request.get_header("Anthropic-version"), "2023-06-01")

    def test_cli_rejects_custom_policy_for_upstream(self):
        argv = ["qualify", "run", "--live", "--base-url", "https://proxy.example/v1",
                "--expected-host", "proxy.example", "--expected-base-url", "https://proxy.example/v1",
                "--model", "synthetic", "--protocol", "chat", "--scope", "direct-rest", "--output", "/unused"]
        with patch("sys.argv", argv), patch("model_probe.cli.Transport") as transport, self.assertRaises(SystemExit):
            main()
        transport.assert_not_called()


class ProfileTests(unittest.TestCase):
    def test_dependencies_and_unknown_capabilities(self):
        for capabilities in ([], ["tools"], ["text", "parallel_tools"], ["text", "unknown"],
                             ["text", "text"], ["text", "tools", "streaming"]):
            with self.assertRaises(ValueError):
                required_cases(capabilities)
        self.assertEqual(required_cases(["text"]), ("text", "history"))
        self.assertEqual(required_cases(), CASES)

    def test_scoped_gate_never_ignores_failures_or_missing_rows(self):
        rows = [{"run": run, "name": name, "status": "PASS" if name in ("text", "history") else "NOT TESTED"}
                for run in range(1, 4) for name in CASES]
        self.assertTrue(gate(rows, 3, ["text"]))
        self.assertFalse(gate(rows, 3))
        self.assertFalse(gate(rows[:-1], 3, ["text"]))
        self.assertFalse(gate(rows + [rows[0]], 3, ["text"]))
        rows[1]["status"] = "FAIL"
        self.assertFalse(gate(rows, 3, ["text"]))

    def test_text_profile_avoids_unrequested_inference_all_protocols(self):
        for protocol in ("chat", "messages", "responses"):
            transport = Transport("http://localhost:8080/v1", "localhost", local=True)
            def send(selected, body):
                self.assertNotIn("tools", body)
                self.assertFalse(body["stream"])
                self.assertNotIn("response_format", body)
                self.assertNotIn("output_config", body)
                self.assertNotIn("text", body)
                history = body.get("input", body.get("messages"))
                answer = "BLUE7" if len(history) > 1 else "OK"
                if selected == "chat":
                    result = chat(answer)
                elif selected == "messages":
                    result = {"stop_reason": "end_turn", "content": [{"type": "text", "text": answer}]}
                else:
                    result = {"status": "completed", "output": [{"type": "message", "content": [
                        {"type": "output_text", "text": answer}]}]}
                return result, {"http_status": 200}
            with tempfile.TemporaryDirectory() as directory, patch.object(transport, "send", side_effect=send) as mocked:
                folder = Path(directory) / "run"
                campaign = Campaign(transport, "fixture", protocol, folder, capabilities=["text"])
                declared = json.loads((folder / "manifest.json").read_text())
                self.assertEqual(declared["required_capabilities"], ["text"])
                summary = campaign.run()
                self.assertEqual(mocked.call_count, 6)
                self.assertEqual(summary["status"], "PROFILE_QUALIFIED")
                self.assertEqual(summary["counts"], {"NOT TESTED": 33, "PASS": 6})
                self.assertEqual(summary["profile_sha256"], declared["profile_sha256"])
                self.assertFalse(summary["release_eligible"])

    def test_scoped_prerequisite_failure_and_budget(self):
        transport = Transport("http://localhost:8080/v1", "localhost", local=True)
        with tempfile.TemporaryDirectory() as directory, patch.object(transport, "send", return_value=(None, {"http_status": 400})):
            summary = Campaign(transport, "fixture", "chat", Path(directory) / "run", capabilities=["text", "tools"]).run()
            self.assertEqual(summary["counts"], {"NOT TESTED": 21, "FAIL": 3, "BLOCKED": 15})
            self.assertEqual(summary["qualified_capabilities"], ())
        with tempfile.TemporaryDirectory() as directory, patch.object(transport, "send", return_value=(chat(), {"http_status": 200})):
            summary = Campaign(transport, "fixture", "chat", Path(directory) / "run", capabilities=["text"], max_requests=1).run()
            self.assertEqual(summary["status"], "PROFILE_BLOCKED")

    def test_cli_records_scoped_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "run"
            argv = ["qualify", "run", "--live", "--base-url", "http://localhost:8080/chat/v1",
                    "--expected-base-url", "http://localhost:8080/chat/v1", "--expected-host", "localhost",
                    "--local-proxy", "--model", "fixture", "--protocol", "chat", "--scope", "proxy",
                    "--capabilities", "text", "--output", str(folder)]
            def send(protocol, body):
                return chat("BLUE7" if len(body["messages"]) > 1 else "OK"), {"http_status": 200}
            with patch("sys.argv", argv), patch("model_probe.transport.Transport.send", side_effect=send), \
                    patch("builtins.print"), self.assertRaises(SystemExit) as exited:
                main()
            self.assertEqual(exited.exception.code, 0)
            manifest = json.loads((folder / "manifest.json").read_text())
            self.assertEqual(manifest["destination_policy"]["expected_base_url"], "http://localhost:8080/chat/v1")


if __name__ == "__main__":
    unittest.main()