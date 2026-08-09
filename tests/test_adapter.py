"""GPU-free test for the entity-inject adapter.

Mock upstream records what it received; the adapter must inject the
user id reminder. Run: python3 tests/test_adapter.py
"""
import json
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

received = {}


class MockUp(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        received["body"] = json.loads(self.rfile.read(n))
        resp = json.dumps({"choices": [{"message": {"role": "assistant",
                                                    "content": "ok"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, format, *args):
        pass


def main():
    up = HTTPServer(("127.0.0.1", 8091), MockUp)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    proc = subprocess.Popen(
        [sys.executable, "arena/adapter_entity_inject.py",
         "--listen", "8090", "--upstream", "http://127.0.0.1:8091/v1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        body = {"model": "x", "messages": [
            {"role": "user", "content": "Hi, I'm Mei Brown, reservation EHGLP3"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "c1", "type": "function",
                             "function": {"name": "get_reservation_details",
                                          "arguments": "{\"reservation_id\": \"EHGLP3\"}"}}]},
            {"role": "tool", "content": "{\"reservation_id\": \"EHGLP3\", \"user_id\": \"mei_brown_496\"}"},
            {"role": "user", "content": "please proceed"}]}
        req = urllib.request.Request(
            "http://127.0.0.1:8090/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
        msgs = received["body"]["messages"]
        assert len(msgs) == 5, f"expected 5 messages, got {len(msgs)}"
        last = msgs[-1]
        assert last["role"] == "system", "expected injected system message"
        assert "mei_brown_496" in last["content"], "expected id in reminder"
        print("adapter test PASSED: id extracted from tool response, injected")
        return 0
    finally:
        proc.terminate()
        up.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
