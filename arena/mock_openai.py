"""Dev-only mock OpenAI server for GPU-free end-to-end verification.

Stdlib only. Returns canned but well-formed chat-completions responses:
a tool call when the request carries tools, plain content otherwise.
Proves the arena plumbing (endpoint contract -> tau2 -> results -> receipt)
without any model or GPU. Never shipped, never scored.

Usage: python3 arena/mock_openai.py [port]
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def _reply(self, message: dict):
        resp = json.dumps({"choices": [{"message": message}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def do_GET(self):
        # Some clients probe /v1/models. Answer with a stub.
        resp = json.dumps({"object": "list", "data": [{"id": "mock"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if body.get("tools"):
            msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "m0",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"city": "Austin", "date": "2026-08-14"}),
                    },
                }],
            }
        else:
            msg = {"role": "assistant", "content": "Okay, done. ###STOP###"}
        self._reply(msg)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8999
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
