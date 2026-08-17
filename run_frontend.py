from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from threading import Timer
from urllib.parse import urlsplit
import webbrowser

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PROJECT_ROOT / "app" / "web"


class FrontendHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/":
            self.path = "/static/index.html"
        elif path == "/admin":
            self.path = "/static/admin.html"
        elif path == "/static/frontend-config.js":
            self._send_frontend_config()
            return
        super().do_GET()

    def _send_frontend_config(self) -> None:
        backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
        content = f"window.APP_API_BASE = {json.dumps(backend_url)};\n".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def end_headers(self) -> None:
        if self.path.endswith((".html", ".js", ".css")):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    host = os.getenv("FRONTEND_HOST", "127.0.0.1")
    port = int(os.getenv("FRONTEND_PORT", "5173"))
    handler = partial(FrontendHandler, directory=str(WEB_ROOT))
    server = ThreadingHTTPServer((host, port), handler)
    browser_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{browser_host}:{port}"
    print(f"Frontend running at {url}")
    print(f"Backend API: {os.getenv('BACKEND_URL', 'http://127.0.0.1:8000')}")
    if os.getenv("FRONTEND_OPEN_BROWSER", "1") == "1":
        Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
