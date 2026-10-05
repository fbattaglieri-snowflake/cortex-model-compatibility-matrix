"""Explicit destination, bounded responses, no redirects or implicit credentials."""
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .protocols import decode_stream


def validate_url(base, expected_host, local=False):
    parsed = urlsplit(base)
    if (parsed.hostname != expected_host or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not re.fullmatch(r"[A-Za-z0-9.:-]+", expected_host)):
        raise ValueError("Base URL differs from the explicitly approved host")
    if local:
        if parsed.hostname not in ("localhost", "127.0.0.1", "::1") or parsed.scheme != "http":
            raise ValueError("Local mode permits HTTP loopback only")
    elif parsed.scheme != "https":
        raise ValueError("TLS is mandatory outside explicit loopback mode")
    if parsed.path.rstrip("/") not in ("/api/v2/cortex/v1", "/v1"):
        raise ValueError("Base path must be /api/v2/cortex/v1 or /v1")
    return base.rstrip("/")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Transport:
    def __init__(self, base, expected_host, *, token_env=None, token_file=None,
                 auth_type="PROGRAMMATIC_ACCESS_TOKEN", local=False, timeout=60, max_bytes=2_000_000):
        self.base = validate_url(base, expected_host, local)
        if token_env and token_file:
            raise ValueError("Choose one credential source")
        if local and (token_env or token_file):
            raise ValueError("Never send Snowflake credentials to local proxy mode")
        if not local and not (token_env or token_file):
            raise ValueError("HTTPS mode requires an explicit credential source")
        self.token_env, self.token_file = token_env, token_file
        self.auth_type, self.timeout, self.max_bytes = auth_type, timeout, max_bytes
        self.secrets = set()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def token(self):
        token = Path(self.token_file).read_text().strip() if self.token_file else os.environ.get(self.token_env, "") if self.token_env else ""
        if (self.token_env or self.token_file) and not token:
            raise ValueError("Selected credential source is empty")
        if token:
            self.secrets.add(token)
        return token

    def redact(self, value):
        serialized = json.dumps(value, default=str)
        for secret in self.secrets:
            serialized = serialized.replace(secret, "[REDACTED]")
        return json.loads(serialized)

    def send(self, protocol, body):
        token = self.token()  # Re-read OAuth token file on every call.
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream" if body.get("stream") else "application/json"}
        if token:
            headers.update(Authorization="Bearer " + token)
            headers["X-Snowflake-Authorization-Token-Type"] = self.auth_type
        if protocol == "messages":
            headers["anthropic-version"] = "2023-06-01"
        path = {"chat": "/chat/completions", "messages": "/messages", "responses": "/responses"}[protocol]
        request = urllib.request.Request(self.base + path, headers=headers, data=json.dumps(body).encode(), method="POST")
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(self.max_bytes + 1)
            meta = {"http_status": response.code, "request_id": response.headers.get("x-snowflake-request-id")}
            if len(raw) > self.max_bytes:
                raise ValueError("Response exceeds byte budget")
            meta["raw_response"] = raw.decode("utf-8")
            if response.code != 200:
                return None, meta
            if body.get("stream"):
                if "text/event-stream" not in response.headers.get("content-type", ""):
                    raise ValueError("Expected SSE")
                result, usage = decode_stream(raw, protocol)
                meta["usage_events"] = usage
            else:
                result = json.loads(raw)
                if result.get("error") or result.get("code"):
                    raise ValueError("Error envelope in HTTP 200")
            return result, meta