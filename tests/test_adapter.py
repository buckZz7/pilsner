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
            {"role": "user", "content": "Hi, I am user_mei_brown_496"},
            {"role": "assistant", "content": "What can I do?"},
            {"role": "user", "content": "Search flights for tomorrow"}]}
        req = urllib.request.Request(
            "http://127.0.0.1:8090/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
        msgs = received["body"]["messages"]
        assert len(msgs) == 4, f"expected 4 messages, got {len(msgs)}"
        last = msgs[-1]
        assert last["role"] == "system", "expected injected system message"
        assert "user_mei_brown_496" in last["content"], "expected id in reminder"
        print("adapter test PASSED: id injected as final system message")
        return 0
    finally:
        proc.terminate()
        up.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
