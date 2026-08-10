from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/v1/edge-sync/snapshot":
            self.send_error(404)
            return
        if self.headers.get("Authorization") != "Bearer installed-dpapi-secret":
            self.send_error(401)
            return
        payload = json.dumps({
            "version": "setup-test",
            "generated_at": "2026-08-09T00:00:00+00:00",
            "vehicles": [],
            "devices": [],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18999), Handler).serve_forever()
