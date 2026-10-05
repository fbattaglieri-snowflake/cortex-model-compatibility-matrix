"""Optional SDK end-to-end harness test; all HTTP is synthetic and local in memory."""
import importlib.util
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from model_probe.campaign import CASES, private_write


@unittest.skipUnless(importlib.util.find_spec("langchain_openai"), "Install .[sdk] for SDK contracts")
class SDKTests(unittest.TestCase):
    def test_entire_sdk_runner_with_mock_transport(self):
        import httpx
        real_client = httpx.Client
        def handler(request):
            body = json.loads(request.content)
            history = body["messages"]
            last = history[-1]
            tool_results = [item for item in history if item["role"] == "tool"]
            if last["role"] == "user" and "code" in str(last["content"]):
                message, reason = {"role": "assistant", "content": "BLUE7"}, "stop"
            elif tool_results:
                message, reason = {"role": "assistant", "content": "42"}, "stop"
            else:
                message = {"role": "assistant", "content": None, "tool_calls": [
                    {"id": key, "type": "function", "function": {"name": "lookup_fixture", "arguments": json.dumps({"key": key})}}
                    for key in ("alpha", "beta")]}
                reason = "tool_calls"
            result = {"id": "synthetic", "object": "chat.completion", "created": 1, "model": "synthetic",
                      "choices": [{"index": 0, "message": message, "finish_reason": reason}],
                      "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
            if not body.get("stream"):
                return httpx.Response(200, json=result)
            delta = dict(message)
            if "tool_calls" in delta:
                delta["tool_calls"] = [{**item, "index": index} for index, item in enumerate(delta["tool_calls"])]
            chunk = {"id": "synthetic", "object": "chat.completion.chunk", "created": 1, "model": "synthetic",
                     "choices": [{"index": 0, "delta": delta, "finish_reason": reason}], "usage": result["usage"]}
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  content=('data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n').encode())
        class MockClient(real_client):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs, transport=httpx.MockTransport(handler))
        script = Path(__file__).resolve().parents[1] / "scripts/sdk_probe.py"
        module = runpy.run_path(str(script), run_name="offline_sdk")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            private_write(folder / "manifest.json", {"protocol": "chat", "scope": "direct-rest", "repeats": 3,
                "target": "https://account.example/v1", "auth_type": "PROGRAMMATIC_ACCESS_TOKEN",
                "model": "synthetic", "reasoning": "none"})
            index = 0
            for run in range(1, 4):
                for name in CASES:
                    private_write(folder / f"case-{index:03d}.json", {"run": run, "name": name, "status": "PASS"})
                    index += 1
            argv = [str(script), "--live", "--campaign", str(folder), "--expected-host", "account.example",
                    "--token-env", "TEST_TOKEN", "--output", str(folder / "sdk.json")]
            with patch("sys.argv", argv), patch.dict("os.environ", {"TEST_TOKEN": "synthetic-secret"}), \
                    patch("httpx.Client", MockClient), self.assertRaises(SystemExit) as exit_info:
                module["main"]()
            self.assertEqual(exit_info.exception.code, 0)
            result = json.loads((folder / "sdk.json").read_text())
            self.assertEqual(len(result["results"]), 12)
            self.assertTrue(all(row["status"] == "PASS" for row in result["results"]))
            self.assertNotIn("synthetic-secret", (folder / "sdk.json").read_text())


if __name__ == "__main__":
    unittest.main()