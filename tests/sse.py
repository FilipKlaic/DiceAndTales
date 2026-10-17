"""Build Anthropic-style SSE streams so DM tests exercise the real SDK over a mock transport."""

import itertools
import json

import anthropic
import httpx2

_ids = itertools.count(1)


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def message_stream(blocks: list[dict], stop_reason: str | None = None) -> str:
    """blocks: {"text": "..."} or {"tool": name, "input": {...}} (or {"tool": name, "raw": "<partial json>"})."""
    if stop_reason is None:
        stop_reason = "tool_use" if any("tool" in b for b in blocks) else "end_turn"
    out = [_event("message_start", {"type": "message_start", "message": {
        "id": f"msg_{next(_ids)}", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 1},
    }})]
    for index, block in enumerate(blocks):
        if "text" in block:
            out.append(_event("content_block_start", {"type": "content_block_start", "index": index,
                                                      "content_block": {"type": "text", "text": ""}}))
            for chunk in block["text"].split(" "):
                out.append(_event("content_block_delta", {"type": "content_block_delta", "index": index,
                                                          "delta": {"type": "text_delta", "text": chunk + " "}}))
        else:
            out.append(_event("content_block_start", {"type": "content_block_start", "index": index, "content_block": {
                "type": "tool_use", "id": f"toolu_{next(_ids)}", "name": block["tool"], "input": {}}}))
            raw = block.get("raw", json.dumps(block.get("input", {})))
            out.append(_event("content_block_delta", {"type": "content_block_delta", "index": index,
                                                      "delta": {"type": "input_json_delta", "partial_json": raw}}))
        out.append(_event("content_block_stop", {"type": "content_block_stop", "index": index}))
    out.append(_event("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                                        "usage": {"output_tokens": 20}}))
    out.append(_event("message_stop", {"type": "message_stop"}))
    return "".join(out)


class ScriptedAPI:
    """A mock Messages API that returns queued SSE bodies (or HTTP errors) and records requests."""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.requests: list[dict] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append({"headers": dict(request.headers), "body": json.loads(request.content)})
        item = self.responses.pop(0)
        if isinstance(item, int):
            return httpx2.Response(item, json={"type": "error", "error": {"type": "api_error", "message": "boom"}})
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=item.encode())

    def client(self) -> anthropic.Anthropic:
        return anthropic.Anthropic(
            api_key="test-key",
            max_retries=0,
            http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(self.handler)),
        )
