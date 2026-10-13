#!/usr/bin/env python3
"""Local web interface for wyciagnij_polskie_audio.py."""

import codecs
import json
import mimetypes
import os
import platform
import runpy
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


if getattr(sys, "frozen", False):
    RESOURCE_DIR = Path(sys._MEIPASS)
else:
    RESOURCE_DIR = Path(__file__).resolve().parents[2]

STATIC_DIR = RESOURCE_DIR / "ExtractAudio" / "webui" / "static"
SCRIPT_PATH = RESOURCE_DIR / "ExtractAudio" / "wyciagnij_polskie_audio.py"
HOST = "0.0.0.0"
PORT = 8765
MAX_LOG_LENGTH = 250_000

state_lock = threading.Lock()
state = {
    "status": "idle",
    "logs": "",
    "return_code": None,
    "process": None,
}


def append_log(text):
    with state_lock:
        state["logs"] = (state["logs"] + text)[-MAX_LOG_LENGTH:]


def extractor_command(arguments):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-extractor"] + arguments
    return [sys.executable, "-u", str(SCRIPT_PATH)] + arguments


def run_script(command):
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        with state_lock:
            state["process"] = process

        if process.stdout:
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            while True:
                chunk = os.read(process.stdout.fileno(), 4096)
                if not chunk:
                    break
                append_log(decoder.decode(chunk))
            append_log(decoder.decode(b"", final=True))

        return_code = process.wait()
        with state_lock:
            state["return_code"] = return_code
            if state["status"] != "stopped":
                state["status"] = "completed" if return_code == 0 else "failed"
            state["process"] = None
    except Exception as error:
        append_log("\nBłąd uruchomienia: {}\n".format(error))
        with state_lock:
            state["status"] = "failed"
            state["process"] = None


class WebUIHandler(BaseHTTPRequestHandler):
    server_version = "AudioExtractWebUI/1.0"

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                raise ValueError("Żądanie jest za duże.")
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError) as error:
            raise ValueError("Nieprawidłowe dane żądania.") from error

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            with state_lock:
                payload = {
                    "status": state["status"],
                    "logs": state["logs"],
                    "return_code": state["return_code"],
                }
            self.send_json(payload)
            return
        if path == "/api/config":
            self.send_json({"platform": platform.system()})
            return

        relative_path = "index.html" if path == "/" else unquote(path.lstrip("/"))
        requested_file = (STATIC_DIR / relative_path).resolve()
        try:
            requested_file.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(404)
            return
        if not requested_file.is_file():
            self.send_error(404)
            return

        content = requested_file.read_bytes()
        content_type = mimetypes.guess_type(requested_file.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") or content_type in ("application/javascript",) else ""))
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        route = urlparse(self.path).path
        try:
            payload = self.read_json()
            if route == "/api/run":
                self.start_run(payload)
            elif route == "/api/stop":
                self.stop_run()
            else:
                self.send_json({"error": "Nieznany endpoint."}, 404)
        except ValueError as error:
            self.send_json({"error": str(error)}, 400)

    def start_run(self, payload):
        folder_value = str(payload.get("folder", "")).strip().strip('"')
        output_value = str(payload.get("output", "")).strip().strip('"')
        if not folder_value:
            self.send_json({"error": "Wskaż istniejący folder z plikami wideo."}, 400)
            return
        folder = Path(folder_value).expanduser()
        output = Path(output_value).expanduser() if output_value else None
        ffmpeg = str(payload.get("ffmpeg", "")).strip().strip('"')
        if not folder.is_dir():
            self.send_json({"error": "Wskaż istniejący folder z plikami wideo."}, 400)
            return
        if output and output.exists() and not output.is_dir():
            self.send_json({"error": "Folder docelowy wskazuje plik, a nie folder."}, 400)
            return

        arguments = [str(folder.resolve())]
        if output:
            arguments.extend(["--output", str(output.resolve())])
        if payload.get("overwrite") is True:
            arguments.append("--overwrite")
        arguments.extend(["--ffmpeg", ffmpeg])
        command = extractor_command(arguments)

        with state_lock:
            if state["status"] == "running":
                self.send_json({"error": "Zadanie jest już uruchomione."}, 409)
                return
            state.update({"status": "running", "logs": "", "return_code": None, "process": None})

        threading.Thread(target=run_script, args=(command,), daemon=True).start()
        self.send_json({"status": "running"}, 202)

    def stop_run(self):
        with state_lock:
            process = state["process"]
        if not process or process.poll() is not None:
            self.send_json({"error": "Brak aktywnego zadania."}, 409)
            return
        process.terminate()
        with state_lock:
            state["status"] = "stopped"
        self.send_json({"status": "stopped"})

    def log_message(self, format_string, *args):
        pass


def run_bundled_extractor():
    if not SCRIPT_PATH.is_file():
        raise SystemExit("Nie znaleziono skryptu: {}".format(SCRIPT_PATH))
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True, write_through=True)
        except (AttributeError, ValueError):
            pass
    sys.argv = [str(SCRIPT_PATH)] + sys.argv[2:]
    runpy.run_path(str(SCRIPT_PATH), run_name="__main__")


def run_server():
    if not SCRIPT_PATH.is_file():
        raise SystemExit("Nie znaleziono skryptu: {}".format(SCRIPT_PATH))
    url = "http://127.0.0.1:{}".format(PORT)
    print("Audio Extract Web UI: {}".format(url))
    print("Zatrzymaj serwer klawiszami Ctrl+C.")
    server = ThreadingHTTPServer((HOST, PORT), WebUIHandler)
    try:
        if getattr(sys, "frozen", False):
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSerwer zatrzymany.")
    finally:
        server.server_close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--run-extractor":
        run_bundled_extractor()
    else:
        run_server()