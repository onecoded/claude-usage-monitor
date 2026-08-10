#!/usr/bin/env pythonw
"""
DOES:   Tiny HTTP server for the Claude Usage dashboard.
        Serves dashboard.html + usage.json on port 7871.
        Run via pythonw.exe — no console window.
RUN:    pythonw.exe dashboard_server.pyw
"""

import http.server
import os
import json
import socketserver

PORT = 7871
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SCRIPT_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # Silent — no logging to clutter

    def do_GET(self):
        if self.path == '/' or self.path == '/dashboard.html':
            self.path = '/dashboard.html'
            super().do_GET()
        elif self.path.startswith('/usage.json'):
            # Serve usage.json with no-cache headers
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            usage_path = os.path.join(SCRIPT_DIR, 'usage.json')
            try:
                with open(usage_path, 'rb') as f:
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.wfile.write(json.dumps({"daily_pct": 0, "status": "waiting"}).encode())
        else:
            super().do_GET()


def main():
    with socketserver.TCPServer(("127.0.0.1", PORT), DashboardHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
