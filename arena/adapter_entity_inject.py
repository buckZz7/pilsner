"""Entity-inject serving adapter: the arena's first serving-layer entry.

A thin OpenAI-compatible proxy: tau2 talks to this (port 8000), it
forwards to the real llama-server (port 8001), but first scans the
conversation for the passenger user id (user_<name>_<digits>) and
re-injects it as a salient system message. Tests whether the 1-bit
collapse (generation-time exact-string corruption) is partly a
salience/attention problem fixable at the serving layer.

Usage: python3 adapter_entity_inject.py --listen 8000 --upstream 8001
Env: ADAPTER_UPSTREAM (default http://127.0.0.1:8001/v1)
"""
import json
import re
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ID_RE = re.compile(r"\buser_[a-z_]+_\d+\b", re.I)
UPSTREAM = "http://127.0.0.1:8001/v1"
REMINDER = ("Reminder: the current passenger user id is {uid}. "
            "Use exactly this id (not a variation) in every tool call "
            "that requires it.")


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self, body: bytes, path: str):
        req = urllib.request.Request(
            UPSTREAM + path, data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type",
                                 resp.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()
            sys.stderr.write(f"adapter upstream error: {e}\n")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        try:
            d = json.loads(body)
            msgs = d.get("messages") or []
            uid = None
            for m in msgs:
                txt = (m.get("content") or "") if isinstance(m, dict) else ""
                if isinstance(txt, list):
                    txt = " ".join(str(p.get("text", "")) for p in txt
                                   if isinstance(p, dict))
                hit = ID_RE.search(str(txt))
                if hit:
                    uid = hit.group(0)
            if uid and msgs:
                # inject the reminder right before the model generates
                d["messages"] = msgs + [{"role": "system",
                                         "content": REMINDER.format(uid=uid)}]
                body = json.dumps(d).encode()
                sys.stderr.write(f"adapter: injected id {uid} "
                                 f"({len(msgs)} messages)\n")
        except Exception as e:
            sys.stderr.write(f"adapter: passthrough ({e})\n")
        self._forward(body, self.path)

    def do_GET(self):
        self._forward(b"", self.path)

    def log_message(self, format, *args):
        pass


def main():
    listen, upstream = 8000, "http://127.0.0.1:8001/v1"
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--listen":
            listen = int(argv[i + 1])
        elif a == "--upstream":
            upstream = argv[i + 1]
    global UPSTREAM
    UPSTREAM = upstream
    print(f"entity-inject adapter: {listen} -> {upstream}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", listen), H).serve_forever()


if __name__ == "__main__":
    main()
