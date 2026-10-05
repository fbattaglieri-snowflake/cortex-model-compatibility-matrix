"""Optional Chat SDK/graph checks after a successful REST campaign."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_probe.campaign import private_write, gate
from model_probe.transport import Transport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token-env", required=True)
    args = parser.parse_args()
    manifest = json.loads((args.campaign / "manifest.json").read_text())
    rows = [json.loads(path.read_text()) for path in sorted(args.campaign.glob("case-*.json"))]
    if manifest["protocol"] != "chat" or manifest["scope"] != "direct-rest" or not gate(rows, manifest["repeats"]):
        raise ValueError("SDK stage requires a qualified direct Chat campaign")
    if args.output.exists():
        raise FileExistsError(args.output)
    auth = Transport(manifest["target"], args.expected_host, token_env=args.token_env, auth_type=manifest["auth_type"])
    for key in ("LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING"):
        os.environ[key] = "false"
    import httpx
    from openai import OpenAI
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, ToolMessage
    from langchain_core.tools import tool
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langgraph.prebuilt import ToolNode
    from langgraph.checkpoint.memory import InMemorySaver
    from model_probe.protocols import calls, tool_match, followup, tools

    @tool
    def lookup_fixture(key: str) -> int:
        """Retrieve synthetic alpha or beta integer."""
        return {"alpha": 17, "beta": 25}[key]

    token, results, request_count = auth.token(), [], 0
    def guard(request):
        nonlocal request_count
        if request.url.host != args.expected_host or request.url.scheme != "https":
            raise ValueError("Unapproved destination")
        request_count += 1
        if request_count > 40:
            raise ValueError("SDK request budget exhausted")
    prompt = "Use lookup_fixture for alpha and beta in one response. After results return only their sum."
    def check(run, name, function):
        try:
            detail = function()
            results.append({"run": run, "name": name, "status": "PASS", "detail": detail})
        except Exception as error:
            results.append({"run": run, "name": name, "status": "FAIL", "error": str(error)})
    with httpx.Client(timeout=60, follow_redirects=False, trust_env=False, event_hooks={"request": [guard]}) as transport:
        headers = {"X-Snowflake-Authorization-Token-Type": manifest["auth_type"]}
        options = {"reasoning_effort": manifest["reasoning"]} if manifest["reasoning"] is not None else {}
        sdk = OpenAI(base_url=auth.base, api_key=token, default_headers=headers, max_retries=0, http_client=transport)
        llm = ChatOpenAI(model=manifest["model"], base_url=auth.base, api_key=token, default_headers=headers,
            http_client=transport, max_retries=0, timeout=60, max_completion_tokens=2048,
            stream_usage=True, use_responses_api=False, **options).bind_tools([lookup_fixture])
        def sdk_case():
            request = {"model": manifest["model"], "messages": [{"role": "user", "content": prompt}],
                       "tools": tools("chat"), "max_completion_tokens": 2048, **options}
            first = sdk.chat.completions.create(**request).model_dump(exclude_none=True)
            if not tool_match(first, "chat", ["alpha", "beta"]):
                raise ValueError("Invalid SDK tool fixture")
            final = sdk.chat.completions.create(**followup(request, first, "chat"))
            if final.choices[0].message.content.strip() != "42" or final.choices[0].message.tool_calls:
                raise ValueError("Wrong SDK final result")
            return {"tool_count": len(calls(first, "chat")), "result": "42"}
        def lc_case(stream):
            def invoke(history):
                if not stream:
                    return llm.invoke(history)
                message = None
                for chunk in llm.stream(history):
                    message = chunk if message is None else message + chunk
                return message
            history = [HumanMessage(content=prompt)]
            first = invoke(history)
            items = first.tool_calls
            if (len(items) != 2 or len({item["id"] for item in items}) != 2 or
                    {item["args"].get("key") for item in items} != {"alpha", "beta"} or
                    any(item["name"] != "lookup_fixture" or set(item["args"]) != {"key"} for item in items)):
                raise ValueError("Invalid LangChain tools")
            history.append(first)
            history.extend(ToolMessage(content=str(lookup_fixture.invoke(item["args"])), tool_call_id=item["id"]) for item in items)
            final = invoke(history)
            if final.content.strip() != "42" or final.tool_calls:
                raise ValueError("Wrong LangChain final result")
            return {"result": "42", "usage": final.usage_metadata, "stream": stream}
        def graph_case(run):
            builder = StateGraph(MessagesState)
            builder.add_node("agent", lambda state: {"messages": [llm.invoke(state["messages"])]})
            builder.add_node("tools", ToolNode([lookup_fixture]))
            builder.add_edge(START, "agent")
            builder.add_conditional_edges("agent", lambda state: "tools" if state["messages"][-1].tool_calls else END)
            builder.add_edge("tools", "agent")
            graph = builder.compile(checkpointer=InMemorySaver())
            settings = {"configurable": {"thread_id": f"synthetic-{run}"}, "recursion_limit": 6}
            first = graph.invoke({"messages": [HumanMessage(content="Remember BLUE7. " + prompt)]}, settings)
            if first["messages"][-1].content.strip() != "42":
                raise ValueError("Wrong graph tool result")
            final = graph.invoke({"messages": [HumanMessage(content="Return only my code, without tools.")]}, settings)
            if final["messages"][-1].content.strip() != "BLUE7" or final["messages"][-1].tool_calls:
                raise ValueError("Graph memory fixture failed")
            return {"checkpoint": "InMemorySaver, not durable"}
        for run in range(1, 4):
            check(run, "openai", sdk_case)
            check(run, "langchain", lambda: lc_case(False))
            check(run, "langchain_stream", lambda: lc_case(True))
            check(run, "langgraph", lambda: graph_case(run))
    report = auth.redact({"results": results, "requests": request_count, "release_eligible": False,
        "scope": "Local SDKs direct to upstream, not deployed applications",
        "versions": {name: importlib.metadata.version(name) for name in ("openai", "httpx", "langchain-openai", "langgraph")}})
    private_write(args.output, report)
    print(json.dumps({"passed": sum(row["status"] == "PASS" for row in results), "total": len(results)}))
    raise SystemExit(0 if all(row["status"] == "PASS" for row in results) else 1)


if __name__ == "__main__":
    main()