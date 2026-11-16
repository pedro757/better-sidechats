#!/usr/bin/env python3
"""A tiny OpenAI-compatible chat completions server for recording the better-sidechats demo.

The last message the user typed picks a scenario from scenarios.json (a sidechat carries its main session's history, so
earlier messages must not decide). OpenCode's own messages (the fork notice, instruction updates, brought-back
sidechats) are skipped. Scenario kinds:
  quick       streams the reply
  read-slow   reads a file, then keeps streaming for a long time, so the session keeps running
  edit        edits a file (the sidechat asks for permission first), then replies
Title requests get the scenario's title.
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "requests.log"
lock = threading.Lock()
INJECTED = ("<system-update>", "<fork-notice>", "The user brought back a sidechat")


def scenarios():
    return json.loads((HERE / "scenarios.json").read_text())


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def log(entry):
    with lock, LOG.open("a") as handle:
        handle.write(json.dumps(entry)[:20000] + "\n")


def typed(messages):
    """What the user typed last, skipping messages OpenCode adds."""
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        text = text_of(message.get("content")).strip()
        if text and not text.startswith(INJECTED):
            return text
    return ""


def find_scenario(text):
    for prompt, scenario in scenarios().items():
        if prompt.lower() in text.lower():
            return scenario
    return {"kind": "quick", "title": text[:40] or "Demo session", "reply": "Done."}


def is_title_request(body):
    system = " ".join(text_of(m.get("content")) for m in body.get("messages", []) if m.get("role") == "system")
    return "title" in system.lower() and not body.get("tools")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self.json({"object": "list", "data": [{"id": "demo", "object": "model", "owned_by": "demo"}]})
            return
        self.json({"ok": True})

    def json(self, value, status=200):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages", [])
        text = typed(messages)
        scenario = find_scenario(text)
        after_tool = bool(messages) and messages[-1].get("role") == "tool"
        title = is_title_request(body)
        log({"at": time.time(), "title": title, "typed": text[:200], "after_tool": after_tool})
        if title:
            self.reply(body, text=scenario.get("title", "Demo session"))
            return
        kind = scenario.get("kind", "quick")
        if kind == "read-slow":
            if not after_tool:
                self.reply(body, tool=("read", {"path": scenario["path"]}))
                return
            self.reply(body, text=scenario["reply"], slow=True)
            return
        if kind == "edit" and not after_tool:
            self.reply(body, tool=("edit", scenario["edit"]))
            return
        self.reply(body, text=scenario["reply"])

    def reply(self, body, text=None, tool=None, slow=False):
        stream = body.get("stream", False)
        created = int(time.time())
        base = {"id": f"chatcmpl-{created}", "object": "chat.completion.chunk", "created": created, "model": "demo"}
        usage = {"prompt_tokens": 18400, "completion_tokens": 260, "total_tokens": 18660}
        call = f"call_{time.time_ns()}"
        if not stream:
            message = {"role": "assistant", "content": text or ""}
            if tool:
                message["tool_calls"] = [{"id": call, "type": "function", "function": {"name": tool[0], "arguments": json.dumps(tool[1])}}]
            self.json({**base, "object": "chat.completion", "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if tool else "stop"}], "usage": usage})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def send(choice, extra=None):
            chunk = {**base, "choices": [choice], **(extra or {})}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()

        try:
            send({"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None})
            if tool:
                send({"index": 0, "delta": {"tool_calls": [{"index": 0, "id": call, "type": "function", "function": {"name": tool[0], "arguments": json.dumps(tool[1])}}]}, "finish_reason": None})
                send({"index": 0, "delta": {}, "finish_reason": "tool_calls"}, {"usage": usage})
            else:
                words = (text or "").split(" ")
                for index, word in enumerate(words):
                    send({"index": 0, "delta": {"content": ("" if index == 0 else " ") + word}, "finish_reason": None})
                    time.sleep(0.025)
                if slow:
                    # Keep the session running: a few more words every couple of seconds, for hours.
                    filler = "Updating the call sites in `src/checkout` one at a time and keeping the old client behind a flag."
                    for index in range(4000):
                        time.sleep(2.5)
                        send({"index": 0, "delta": {"content": " " + filler.split(" ")[index % len(filler.split(" "))]}, "finish_reason": None})
                send({"index": 0, "delta": {}, "finish_reason": "stop"}, {"usage": usage})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 47590
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
