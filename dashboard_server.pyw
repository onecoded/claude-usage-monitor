import http.server, os, json, socketserver

PORT = 7871
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SCRIPT_DIR, **kwargs)
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.path = '/dashboard.html'
        super().do_GET()

with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
    httpd.serve_forever()
