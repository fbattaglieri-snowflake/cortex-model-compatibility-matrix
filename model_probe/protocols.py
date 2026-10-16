"""Protocol-specific fixtures and strict stream reconstruction."""
import json

FIXTURES = {"alpha": 17, "beta": 25}
INPUT_SCHEMA = {"type": "object", "properties": {"key": {"type": "string", "enum": list(FIXTURES)}},
                "required": ["key"], "additionalProperties": False}
OUTPUT_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"},
                 "result": {"type": "integer", "enum": [42]}},
                 "required": ["ok", "result"], "additionalProperties": False}


def schema_matches(value):
    return (isinstance(value, dict) and set(value) == {"ok", "result"}
            and value["ok"] is True and type(value["result"]) is int and value["result"] == 42)


def tools(protocol):
    spec = {"name": "lookup_fixture", "description": "Read synthetic alpha or beta integer."}
    if protocol == "messages":
        return [{**spec, "input_schema": INPUT_SCHEMA}]
    spec["parameters"] = INPUT_SCHEMA
    return [{"type": "function", **spec}] if protocol == "responses" else [{"type": "function", "function": spec}]


def payload(protocol, model, prompt, *, stream=False, with_tools=False, reasoning=None, structured=False):
    body = {"model": model, "stream": stream}
    history = [{"role": "user", "content": prompt}]
    if protocol == "responses":
        body.update(input=history, max_output_tokens=2048, store=False,
                    include=["reasoning.encrypted_content"])
        if reasoning is not None:
            body["reasoning"] = {"effort": reasoning}
        if structured:
            body["text"] = {"format": {"type": "json_schema", "name": "fixture", "strict": True, "schema": OUTPUT_SCHEMA}}
    else:
        body["messages"] = history
        body["max_tokens" if protocol == "messages" else "max_completion_tokens"] = 2048
        if reasoning is not None:
            if protocol == "messages":
                raise ValueError("Reasoning effort flag is only for Chat/Responses; no silent translation")
            body["reasoning_effort"] = reasoning
        if stream and protocol == "chat":
            body["stream_options"] = {"include_usage": True}
        if structured:
            if protocol == "messages":
                body["output_config"] = {"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}}
            else:
                body["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": "fixture", "strict": True, "schema": OUTPUT_SCHEMA}}
    if with_tools:
        body["tools"] = tools(protocol)
    return body


def text(body, protocol):
    if protocol == "chat":
        return body["choices"][0]["message"].get("content") or ""
    blocks = body.get("content", []) if protocol == "messages" else [
        block for item in body.get("output", []) if item.get("type") == "message" for block in item.get("content", [])]
    return "".join(block.get("text", "") for block in blocks if block.get("type") in ("text", "output_text"))


def calls(body, protocol):
    if protocol == "chat":
        values = [{"id": item["id"], "name": item["function"]["name"], "args": json.loads(item["function"]["arguments"])}
                  for item in body["choices"][0]["message"].get("tool_calls", [])]
    elif protocol == "messages":
        values = [{"id": item["id"], "name": item["name"], "args": item["input"]}
                  for item in body.get("content", []) if item.get("type") == "tool_use"]
    else:
        values = [{"id": item["call_id"], "name": item["name"], "args": json.loads(item["arguments"])}
                  for item in body.get("output", []) if item.get("type") == "function_call"]
    ids = [item["id"] for item in values]
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("Missing or duplicate tool identity")
    for item in values:
        if (item["name"] != "lookup_fixture" or not isinstance(item["args"], dict)
                or set(item["args"]) != {"key"} or item["args"]["key"] not in FIXTURES):
            raise ValueError("Untrusted tool call outside the synthetic fixture contract")
    return values


def completed(body, protocol, tool=False):
    if protocol == "responses":
        return body.get("status") == "completed"
    if protocol == "messages":
        return body.get("stop_reason") == ("tool_use" if tool else "end_turn")
    return len(body.get("choices", [])) == 1 and body["choices"][0].get("finish_reason") == ("tool_calls" if tool else "stop")


def tool_match(body, protocol, keys):
    items = calls(body, protocol)
    return (completed(body, protocol, True) and len(items) == len(keys)
            and {item["args"]["key"] for item in items} == set(keys))


def followup(request, response, protocol, fail=False):
    items = calls(response, protocol)
    def result(item):
        return "Synthetic fixture unavailable; do not retry." if fail else str(FIXTURES[item["args"]["key"]])
    key = "input" if protocol == "responses" else "messages"
    history = list(request[key])
    if protocol == "responses":
        history += response["output"]  # Preserve encrypted reasoning, not just tool calls.
        history += [{"type": "function_call_output", "call_id": item["id"], "output": result(item)} for item in items]
    elif protocol == "messages":
        history += [{"role": "assistant", "content": response["content"]}, {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": item["id"], "content": result(item),
             **({"is_error": True} if fail else {})} for item in items]}]
    else:
        history += [response["choices"][0]["message"]]
        history += [{"role": "tool", "tool_call_id": item["id"], "content": result(item)} for item in items]
    return {**request, key: history}


def reused_tool_ids(first_response, second_response, protocol):
    """Return True when two separate tool-call turns reuse any tool call identifier (e.g. call_0)."""
    first_ids = {item["id"] for item in calls(first_response, protocol)}
    second_ids = {item["id"] for item in calls(second_response, protocol)}
    return bool(first_ids & second_ids)


def multiround_followup(request, response, protocol, *, round_index=1, fail=False):
    """Append a tool-call round while ensuring IDs remain unique across multi-round transcripts."""
    import copy
    response_copy = copy.deepcopy(response)
    key = "input" if protocol == "responses" else "messages"
    existing_ids = set()
    for msg in request.get(key, []):
        if not isinstance(msg, dict):
            continue
        if protocol == "chat":
            existing_ids.update(tc.get("id") for tc in (msg.get("tool_calls") or []) if isinstance(tc, dict) and tc.get("id"))
        elif protocol == "responses" and msg.get("type") == "function_call" and msg.get("call_id"):
            existing_ids.add(msg["call_id"])
        elif protocol == "messages" and isinstance(msg.get("content"), list):
            existing_ids.update(b.get("id") for b in msg["content"] if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id"))
    if existing_ids:
        if protocol == "chat":
            for tc in response_copy["choices"][0]["message"].get("tool_calls", []):
                if tc.get("id") in existing_ids:
                    tc["id"] = f"{tc['id']}_r{round_index}"
        elif protocol == "responses":
            for item in response_copy.get("output", []):
                if item.get("type") == "function_call" and item.get("call_id") in existing_ids:
                    item["call_id"] = f"{item['call_id']}_r{round_index}"
        else:
            for block in response_copy.get("content", []):
                if block.get("type") == "tool_use" and block.get("id") in existing_ids:
                    block["id"] = f"{block['id']}_r{round_index}"
    return followup(request, response_copy, protocol, fail=fail)


def sse_events(raw):
    normalized = raw.replace(b"\r\n", b"\n")
    parts = normalized.split(b"\n\n")
    if parts[-1].strip():
        raise ValueError("Unterminated SSE event")
    for part in parts[:-1]:
        data = "\n".join(line[5:].lstrip() for line in part.decode("utf-8").splitlines() if line.startswith("data:"))
        if data:
            yield data


def decode_stream(raw, protocol):
    ended, usage = False, []
    trailing_done = False
    result = None
    chat_text, fragments, finish = "", {}, None
    blocks, closed = {}, set()
    response_deltas = ""
    for data in sse_events(raw):
        if ended:
            # Cortex Responses may append one sentinel after the real completion.
            # It cannot supply completion or authorize any subsequent payload.
            if protocol == "responses" and data == "[DONE]" and not trailing_done:
                trailing_done = True
                continue
            raise ValueError("Data after terminal event")
        if data == "[DONE]":
            if protocol != "chat" or not finish:
                raise ValueError("DONE without completed Chat choice")
            ended = True
            continue
        event = json.loads(data)
        kind = event.get("type")
        if event.get("error") or kind in ("error", "response.failed", "response.incomplete"):
            raise ValueError("Upstream stream error")
        if event.get("usage"):
            usage.append(event["usage"])
        if protocol == "responses":
            if kind == "response.output_text.delta":
                response_deltas += event["delta"]
            if kind == "response.completed":
                result, ended = event["response"], True
                if not completed(result, protocol):
                    raise ValueError("Incomplete Responses result")
                if response_deltas and response_deltas != text(result, protocol):
                    raise ValueError("Responses text deltas mismatch")
                if result.get("usage"):
                    usage.append(result["usage"])
        elif protocol == "chat":
            for choice in event.get("choices", []):
                if choice["index"] != 0 or finish:
                    raise ValueError("Unexpected choice or delta after finish")
                delta = choice.get("delta") or {}
                chat_text += delta.get("content") or ""
                for fragment in delta.get("tool_calls") or []:
                    state = fragments.setdefault(fragment["index"], {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    if fragment.get("id"):
                        if state["id"] and state["id"] != fragment["id"]:
                            raise ValueError("Tool identity changed at stream index")
                        state["id"] = fragment["id"]
                    for key in ("name", "arguments"):
                        state["function"][key] += (fragment.get("function") or {}).get(key) or ""
                finish = choice.get("finish_reason") or finish
        else:
            if kind == "ping":
                continue
            if kind == "message_start":
                if result is not None:
                    raise ValueError("Duplicate message start")
                result = event["message"]
                if result.get("usage"):
                    usage.append(result["usage"])
            elif result is None:
                raise ValueError("Missing message start")
            elif kind == "content_block_start":
                index = event["index"]
                if index in blocks:
                    raise ValueError("Duplicate block")
                blocks[index] = {"block": dict(event["content_block"]), "json": ""}
            elif kind == "content_block_delta":
                index = event["index"]
                if index not in blocks or index in closed:
                    raise ValueError("Delta outside open block")
                delta, state = event["delta"], blocks[index]
                for key in ("text", "thinking", "signature"):
                    if key in delta:
                        state["block"][key] = state["block"].get(key, "") + delta[key]
                state["json"] += delta.get("partial_json", "")
            elif kind == "content_block_stop":
                index = event["index"]
                if index not in blocks or index in closed:
                    raise ValueError("Invalid block stop")
                closed.add(index)
            elif kind == "message_delta":
                result.update(event.get("delta", {}))
            elif kind == "message_stop":
                if set(blocks) != closed or not result.get("stop_reason"):
                    raise ValueError("Incomplete Messages stream")
                result["content"] = []
                for index in sorted(blocks):
                    state = blocks[index]
                    if state["json"]:
                        state["block"]["input"] = json.loads(state["json"])
                    result["content"].append(state["block"])
                ended = True
            else:
                raise ValueError("Unknown Messages event")
    if not ended:
        raise ValueError("Missing terminal event")
    if protocol == "chat":
        message = {"role": "assistant", "content": chat_text}
        if fragments:
            message["tool_calls"] = [fragments[index] for index in sorted(fragments)]
        result = {"choices": [{"index": 0, "message": message, "finish_reason": finish}]}
    calls(result, protocol)
    return result, usage