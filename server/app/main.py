"""
Morning Puzzles - Web Service API
Serves daily puzzles in JSON format, pure ESC/POS text, and hybrid 1-bit raster formats
optimized for commercial 80mm thermal receipt printers.
Supports FastAPI (when installed) with fallback to Python's built-in http.server.
"""

import datetime
import json
import os
import sys
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

# Add parent directory to path to allow importing app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.puzzles.registry import DEFAULT_REGISTRY
from app.renderer.text_formatter import (
    EscPosTextReceipt,
    build_daily_receipt_bytes,
    build_hybrid_daily_receipt_bytes,
)

SIMULATOR_HTML_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "simulator",
    "receipt_simulator.html",
)

VALID_FORMATS = {"escpos", "json"}
VALID_DIFFICULTIES = {"easy", "medium", "hard", "extreme", "random", "staggered", "progressive"}
VALID_STYLES = {"hybrid", "text"}

_SIMULATOR_CACHE: Dict[str, Any] = {"mtime": None, "content": None}


def generate_daily_bundle(difficulty: str = "medium", count: Optional[int] = None) -> Dict[str, Any]:
    """Generates the daily bundle of puzzles (full edition or N-puzzle random mix)."""
    return DEFAULT_REGISTRY.generate_bundle(difficulty=difficulty, count=count)


def _get_simulator_html() -> Optional[str]:
    if not os.path.exists(SIMULATOR_HTML_PATH):
        return None
    mtime = os.path.getmtime(SIMULATOR_HTML_PATH)
    if _SIMULATOR_CACHE["mtime"] != mtime or _SIMULATOR_CACHE["content"] is None:
        with open(SIMULATOR_HTML_PATH, "r", encoding="utf-8") as f:
            _SIMULATOR_CACHE["content"] = f.read()
        _SIMULATOR_CACHE["mtime"] = mtime
    return _SIMULATOR_CACHE["content"]


def _handle_health() -> Dict[str, Any]:
    return {"status": "ok", "time": datetime.datetime.now().isoformat()}


def _handle_test_print() -> bytes:
    r = EscPosTextReceipt()
    r.header("TEST RECEIPT", datetime.date.today().strftime("%Y-%m-%d"))
    r.println("ESP32 <-> Thermal Printer link is operational!")
    r.println("576-dot 80mm thermal receipt verified.")
    r.feed(4)
    r.cut()
    return r.get_bytes()


def _handle_daily_print(
    fmt: str = "escpos",
    difficulty: str = "medium",
    style: str = "hybrid",
    count: Optional[int] = None,
) -> Tuple[int, str, Any, Dict[str, str]]:
    fmt_l = (fmt or "escpos").lower()
    diff_l = (difficulty or "medium").lower()
    style_l = (style or "hybrid").lower()
    if fmt_l not in VALID_FORMATS:
        return 422, "application/json", {"error": f"Invalid format '{fmt}'"}, {}
    if diff_l not in VALID_DIFFICULTIES:
        return 422, "application/json", {"error": f"Invalid difficulty '{difficulty}'"}, {}
    if style_l not in VALID_STYLES:
        return 422, "application/json", {"error": f"Invalid style '{style}'"}, {}
    if count is not None and count < 1:
        return 422, "application/json", {"error": "count must be >= 1"}, {}

    try:
        bundle = generate_daily_bundle(difficulty=diff_l, count=count)
    except RuntimeError as exc:
        return 500, "application/json", {"error": str(exc)}, {}

    if fmt_l == "json":
        return 200, "application/json", bundle, {}

    escpos_bytes = (
        build_daily_receipt_bytes(bundle)
        if style_l == "text"
        else build_hybrid_daily_receipt_bytes(bundle)
    )
    headers = {
        "Content-Disposition": "inline; filename=morning-puzzles.bin",
        "Content-Length": str(len(escpos_bytes)),
    }
    return 200, "application/octet-stream", escpos_bytes, headers


def _handle_single_puzzle(
    puzzle_id: str,
    difficulty: Optional[str] = None,
    theme: Optional[str] = None,
) -> Tuple[int, Dict[str, Any]]:
    plugin = DEFAULT_REGISTRY.get(puzzle_id)
    if not plugin:
        return 404, {"error": f"Puzzle '{puzzle_id}' not found"}
    diff = difficulty or plugin.default_difficulty
    kwargs: Dict[str, Any] = {}
    if theme:
        kwargs["theme"] = theme
    try:
        return 200, plugin.generate(difficulty=diff, **kwargs).to_dict()
    except RuntimeError as exc:
        return 500, {"error": str(exc)}


# ==============================================================================
# 1. FastAPI Application (Used when running via uvicorn)
# ==============================================================================
try:
    from fastapi import FastAPI, Query, Response
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(
        title="Morning Puzzles API",
        description="API generating daily puzzles for 80mm commercial thermal printers (576 dots width)",
        version="1.2.0",
    )

    @app.get("/", response_class=HTMLResponse)
    @app.get("/simulator", response_class=HTMLResponse)
    def get_simulator():
        html = _get_simulator_html()
        if html is not None:
            return HTMLResponse(content=html)
        return HTMLResponse(content="<h1>Simulator file not found</h1>", status_code=404)

    @app.get("/health")
    def health():
        return _handle_health()

    @app.get("/api/v1/daily-print")
    def get_daily_print(
        format: str = Query("escpos", pattern="^(escpos|json)$"),
        difficulty: str = Query("medium", pattern="^(easy|medium|hard|extreme|random|staggered|progressive)$"),
        style: str = Query("hybrid", pattern="^(hybrid|text)$"),
        count: Optional[int] = Query(None, ge=1),
    ):
        status, media_type, payload, headers = _handle_daily_print(format, difficulty, style, count)
        if media_type == "application/json":
            return JSONResponse(content=payload, status_code=status)
        return Response(content=payload, media_type=media_type, headers=headers, status_code=status)

    @app.get("/api/v1/test-print")
    def get_test_print():
        return Response(content=_handle_test_print(), media_type="application/octet-stream")

    @app.get("/api/v1/puzzles/{puzzle_id}")
    def get_puzzle(puzzle_id: str, difficulty: str = "medium", theme: Optional[str] = None):
        status, payload = _handle_single_puzzle(puzzle_id, difficulty=difficulty, theme=theme)
        return JSONResponse(content=payload, status_code=status)

except ImportError:
    app = None


# ==============================================================================
# 2. Built-in HTTP Server Fallback (Runs on any machine with Python 3)
# ==============================================================================
def run_standalone_server(port: int = 8000, host: str = "0.0.0.0"):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class PuzzleHttpHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            query_params = parse_qs(parsed.query)
            path = parsed.path

            if path in ("/simulator", "/"):
                html = _get_simulator_html()
                if html is not None:
                    data = html.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Simulator not found")
            elif path == "/health":
                self._send_json(200, _handle_health())
            elif path == "/api/v1/daily-print":
                fmt = query_params.get("format", ["escpos"])[0]
                diff = query_params.get("difficulty", ["medium"])[0]
                style = query_params.get("style", ["hybrid"])[0]
                count_param = query_params.get("count", [None])[0]
                count_val = None
                if count_param is not None:
                    try:
                        count_val = int(count_param)
                    except ValueError:
                        self._send_json(422, {"error": f"Invalid count '{count_param}'"})
                        return
                status, media_type, payload, headers = _handle_daily_print(fmt, diff, style, count_val)
                if media_type == "application/json":
                    self._send_json(status, payload)
                else:
                    self.send_response(status)
                    self.send_header("Content-Type", media_type)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(payload)
            elif path == "/api/v1/test-print":
                data = _handle_test_print()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif path.startswith("/api/v1/puzzles/"):
                puzzle_id = path[len("/api/v1/puzzles/"):].strip("/")
                diff = query_params.get("difficulty", [None])[0]
                theme = query_params.get("theme", [None])[0]
                status, payload = _handle_single_puzzle(puzzle_id, difficulty=diff, theme=theme)
                self._send_json(status, payload)
            else:
                self._send_json(404, {"error": "Not Found"})

        def _send_json(self, status: int, data: dict):
            payload = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer((host, port), PuzzleHttpHandler)
    print(f"\n[SERVER] Morning Puzzles Server running at http://{host}:{port}/")
    print(f"[SERVER] Daily Print Endpoint: http://{host}:{port}/api/v1/daily-print")
    print(f"[SERVER] Test Print Endpoint:  http://{host}:{port}/api/v1/test-print")
    print("[SERVER] Press Ctrl+C to terminate.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVER] Server shutting down.")
        server.server_close()


if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
            if not (1 <= port <= 65535):
                raise ValueError("port out of range")
        except ValueError:
            print(f"Invalid port argument: {sys.argv[1]} (must be 1..65535)", file=sys.stderr)
            sys.exit(2)
    run_standalone_server(port=port)
