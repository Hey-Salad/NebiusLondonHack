"""Stand-in for Tavily + Nebius Token Factory, so the full HTTP path can be tested offline."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json({"data": [{"id": "BAAI/bge-en-icl"}, {"id": "stub/chat-model"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        assert self.headers.get("Authorization", "").startswith("Bearer "), "auth header missing"

        if self.path.endswith("/search"):
            self._json({"results": [
                {"title": "Harissa sales climb", "url": "https://example.com/1",
                 "content": "UK harissa sales rose 30% in 2026.", "score": 0.91,
                 "published_date": "2026-07-02"},
                {"title": "Cricket results", "url": "https://example.com/2",
                 "content": "Tuesday scores from the county ground.", "score": 0.5},
            ]})
        elif self.path.endswith("/embeddings"):
            data = [{"index": i, "embedding": [float(len(t)), float("harissa" in t.lower()) * 9]}
                    for i, t in enumerate(body["input"])]
            self._json({"data": data})
        elif self.path.endswith("/chat/completions"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for piece in ["## The short answer\n", "UK harissa sales rose 30% [1].", ""]:
                chunk = {"choices": [{"delta": {"content": piece} if piece else {}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(f"data: {json.dumps({'choices': [], 'usage': {'total_tokens': 99}})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            self.send_error(404)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8099), Handler).serve_forever()
