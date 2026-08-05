import json
import os
import pathlib
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PORT = int(os.getenv("LISTENER_PORT", "9099"))
LOG_FILE = pathlib.Path(os.getenv("WEBHOOK_LOG", "webhook-captures.jsonl"))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {"unparsed": raw.decode("utf-8", errors="replace")}

        line = json.dumps(
            {"received_at": datetime.now(timezone.utc).isoformat(), "payload": payload}
        )
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line, flush=True)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, fmt: str, *args) -> None:
        pass


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[listener] capturing webhooks on http://127.0.0.1:{PORT} -> {LOG_FILE}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[listener] stopped", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
