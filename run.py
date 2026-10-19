#!/usr/bin/env python3
"""
run.py
───────────────────────────────────────────────────────────────────────────────
Unified Launcher for 'My Maths Practice Book' Workbook Generator.

Usage:
    python run.py                   # Launches FastAPI backend + React Vite frontend (recommended)
    python run.py --mode prod       # Launches single-server FastAPI serving built React app
    python run.py --mode streamlit  # Launches legacy Streamlit UI
    python run.py --mode backend    # Launches FastAPI backend only
    python run.py --no-browser      # Starts without automatically opening the browser
    python run.py --port 8000       # Custom backend port (default: 8000)
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# Safe utf-8 output + ANSI colours on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        os.system("")

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = SCRIPT_DIR / "frontend"
APP_DIR = SCRIPT_DIR / "app"
ENV_FILE = SCRIPT_DIR / ".env"
ENV_EXAMPLE = SCRIPT_DIR / ".env.example"

# ANSI Colors for clean terminal display (works on modern Windows terminals)
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def print_banner():
    banner = f"""{Colors.CYAN}{Colors.BOLD}
========================================================================
                 MYINTELIBOOKS -- WORKBOOK GENERATOR
               AI-Powered Multi-Grade Workbook System
========================================================================{Colors.RESET}
"""
    print(banner)


def log(prefix: str, msg: str, color: str = Colors.CYAN):
    print(f"{color}{Colors.BOLD}[{prefix}]{Colors.RESET} {msg}", flush=True)


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def is_backend_healthy(port: int) -> bool:
    """True when something on this port already serves our API."""
    for path in ("/api/health", "/api/grades"):
        if wait_for_url(f"http://127.0.0.1:{port}{path}", timeout=1.2, interval=0.3):
            return True
    return False


def wait_for_url(url: str, timeout: float = 20.0, interval: float = 0.5) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status in (200, 304, 404):  # server is responding
                    return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _child_popen_kwargs() -> dict:
    """Keep child servers off the parent's Ctrl+C group (avoids npm Y/N prompt)."""
    kwargs: dict = {"stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return kwargs


def kill_process_tree(pid: int):
    """Forcefully kill process and all descendants (cross-platform)."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                check=False,
                timeout=8,
            )
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except Exception:
                os.kill(pid, signal.SIGTERM)
    except (KeyboardInterrupt, Exception):
        pass


def check_prerequisites():
    """Verify python packages and environment configuration."""
    log("SYSTEM", "Checking prerequisites...", Colors.CYAN)

    # 1. Check Python version
    if sys.version_info < (3, 10):
        log("ERROR", f"Python 3.10+ is required (found {sys.version.split()[0]})", Colors.RED)
        sys.exit(1)

    # 2. Check essential Python libraries
    required_modules = ["fastapi", "uvicorn", "PIL", "fpdf", "requests", "dotenv"]
    missing = []
    for mod in required_modules:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)

    if missing:
        log("ERROR", f"Missing required Python libraries: {', '.join(missing)}", Colors.RED)
        log("SYSTEM", "Please run: pip install -r requirements.txt", Colors.YELLOW)
        sys.exit(1)

    # 3. Check .env
    if not ENV_FILE.exists():
        log("WARNING", ".env file not found. Creating default template...", Colors.YELLOW)
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("# OpenRouter API key for workbook AI illustrations\nOPENROUTER_API_KEY=\n")
        log("SYSTEM", f"Created {ENV_FILE.name}. Add your OPENROUTER_API_KEY if needed.", Colors.YELLOW)
    else:
        # Check if key is configured
        with open(ENV_FILE, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            if "OPENROUTER_API_KEY" in content and "sk-or-" in content:
                log("SYSTEM", "OpenRouter API key detected in .env", Colors.GREEN)
            else:
                log("WARNING", "OpenRouter API key is missing or not configured in .env", Colors.YELLOW)

    log("SYSTEM", "Python dependencies verified", Colors.GREEN)


def stream_output(process: subprocess.Popen, prefix: str, color: str):
    """Read lines from stdout/stderr of a process and print with prefixed color."""
    if not process.stdout:
        return
    try:
        for line in iter(process.stdout.readline, ""):
            if line:
                stripped = line.rstrip()
                if stripped:
                    print(f"{color}{Colors.BOLD}[{prefix}]{Colors.RESET} {stripped}", flush=True)
        process.stdout.close()
    except (KeyboardInterrupt, ValueError, OSError):
        pass


def run_full(backend_port: int, auto_browser: bool):
    """Run FastAPI backend + Vite React dev server."""
    node_cmd = shutil.which("node")
    npm_cmd = shutil.which("npm") or shutil.which("npm.cmd")

    if not node_cmd or not npm_cmd:
        log("WARNING", "Node/npm not detected in PATH. Falling back to Production Build mode.", Colors.YELLOW)
        run_prod(backend_port, auto_browser)
        return

    # Check node_modules in frontend
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        log("FRONTEND", "Installing frontend dependencies (npm install)...", Colors.BLUE)
        res = subprocess.run([npm_cmd, "install"], cwd=str(FRONTEND_DIR), check=False)
        if res.returncode != 0:
            log("ERROR", "npm install failed. Falling back to Production Build mode.", Colors.RED)
            run_prod(backend_port, auto_browser)
            return

    frontend_port = 5173
    reuse_backend = False
    if is_port_in_use(backend_port):
        if is_backend_healthy(backend_port):
            reuse_backend = True
            log(
                "BACKEND",
                f"Port {backend_port} already has MyInteliBooks running. Reusing it.",
                Colors.GREEN,
            )
        else:
            log(
                "ERROR",
                f"Port {backend_port} is busy and is not this app. "
                f"Close that program, or run: python run.py --port 8001",
                Colors.RED,
            )
            sys.exit(1)
    if is_port_in_use(frontend_port):
        log("WARNING", f"Port {frontend_port} is already in use. Vite may pick another port.", Colors.YELLOW)

    procs: list[subprocess.Popen] = []
    shutting_down = False

    def shutdown():
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        try:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        except Exception:
            pass
        log("SYSTEM", "Shutting down servers started by this window...", Colors.YELLOW)
        for p in procs:
            try:
                if p.poll() is None:
                    kill_process_tree(p.pid)
            except (KeyboardInterrupt, Exception):
                pass
        log("SYSTEM", "Allah Hafiz, take care next will see again", Colors.GREEN)

    child_kwargs = _child_popen_kwargs()

    try:
        if not reuse_backend:
            log("BACKEND", f"Starting FastAPI backend on port {backend_port}...", Colors.CYAN)
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            backend_proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.api_server:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(backend_port),
                    "--reload",
                ],
                cwd=str(SCRIPT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                **child_kwargs,
            )
            procs.append(backend_proc)
            threading.Thread(
                target=stream_output,
                args=(backend_proc, "Backend", Colors.CYAN),
                daemon=True,
            ).start()

            time.sleep(0.8)
            if backend_proc.poll() is not None:
                log(
                    "ERROR",
                    f"Backend failed to start on port {backend_port} "
                    f"(exit {backend_proc.returncode}). Port may be blocked.",
                    Colors.RED,
                )
                shutdown()
                sys.exit(1)

        log("FRONTEND", f"Starting Vite Dev Server on port {frontend_port}...", Colors.GREEN)
        frontend_proc = subprocess.Popen(
            [npm_cmd, "run", "dev"],
            cwd=str(FRONTEND_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **child_kwargs,
        )
        procs.append(frontend_proc)
        threading.Thread(
            target=stream_output,
            args=(frontend_proc, "Frontend", Colors.GREEN),
            daemon=True,
        ).start()

        backend_url = f"http://127.0.0.1:{backend_port}/api/grades"
        if not reuse_backend:
            log("SYSTEM", f"Waiting for backend at {backend_url}...", Colors.DIM)
            if not wait_for_url(backend_url, timeout=20.0):
                log("ERROR", "Backend did not become ready in time.", Colors.RED)
                shutdown()
                sys.exit(1)

        frontend_url = f"http://localhost:{frontend_port}"
        wait_for_url(frontend_url, timeout=15.0)

        print()
        log("READY", "Application is up and running!", Colors.GREEN)
        log("LINK", f"React UI (Vite):       {Colors.BOLD}http://localhost:{frontend_port}{Colors.RESET}", Colors.GREEN)
        log("LINK", f"FastAPI Backend & API: {Colors.BOLD}http://127.0.0.1:{backend_port}/docs{Colors.RESET}", Colors.CYAN)
        if reuse_backend:
            log("NOTE", f"Using the backend already running on port {backend_port}.", Colors.YELLOW)
        log("HELP", "Press CTRL+C anytime to stop servers started in this window.", Colors.YELLOW)
        print()

        if auto_browser:
            time.sleep(0.5)
            log("BROWSER", f"Opening {frontend_url} in your default browser...", Colors.BLUE)
            webbrowser.open(frontend_url)

        while True:
            time.sleep(0.8)
            for p in procs:
                if p.poll() is not None:
                    log("SYSTEM", f"Process {p.pid} exited with code {p.returncode}.", Colors.YELLOW)
                    shutdown()
                    return

    except KeyboardInterrupt:
        print()
        try:
            shutdown()
        except KeyboardInterrupt:
            pass


def run_prod(backend_port: int, auto_browser: bool):
    """Run single-server production mode: FastAPI serves API + React build directly."""
    dist_dir = FRONTEND_DIR / "dist"
    if not dist_dir.exists():
        log("FRONTEND", "Production build not found. Building React app...", Colors.BLUE)
        npm_cmd = shutil.which("npm") or shutil.which("npm.cmd")
        if npm_cmd:
            subprocess.run([npm_cmd, "run", "build"], cwd=str(FRONTEND_DIR), check=True)
            log("FRONTEND", "Frontend built successfully.", Colors.GREEN)
        else:
            log("ERROR", "frontend/dist not found and npm is not installed.", Colors.RED)
            sys.exit(1)

    log("BACKEND", f"Starting FastAPI Production Server on http://127.0.0.1:{backend_port}...", Colors.CYAN)
    app_url = f"http://127.0.0.1:{backend_port}"

    if auto_browser:
        def open_later():
            if wait_for_url(f"{app_url}/api/grades", timeout=15.0):
                log("BROWSER", f"Opening {app_url} in your browser...", Colors.BLUE)
                webbrowser.open(app_url)
        threading.Thread(target=open_later, daemon=True).start()

    print()
    log("READY", f"Serving application at: {Colors.BOLD}{app_url}{Colors.RESET}", Colors.GREEN)
    log("DOCS", f"Swagger API documentation: {Colors.BOLD}{app_url}/docs{Colors.RESET}", Colors.CYAN)
    log("HELP", "Press CTRL+C to stop the server.", Colors.YELLOW)
    print()

    try:
        import uvicorn
        uvicorn.run("app.api_server:app", host="127.0.0.1", port=backend_port, reload=False)
    except KeyboardInterrupt:
        log("SYSTEM", "Allah Hafiz, take care next will see again", Colors.GREEN)


def run_streamlit(auto_browser: bool):
    """Run legacy Streamlit UI."""
    streamlit_path = APP_DIR / "newapp.py"
    if not streamlit_path.exists():
        log("ERROR", f"Streamlit app not found at {streamlit_path}", Colors.RED)
        sys.exit(1)

    log("STREAMLIT", "Launching Streamlit application...", Colors.CYAN)
    args = [sys.executable, "-m", "streamlit", "run", str(streamlit_path)]
    if not auto_browser:
        args.extend(["--server.headless", "true"])

    try:
        subprocess.run(args, cwd=str(SCRIPT_DIR), check=True)
    except KeyboardInterrupt:
        log("SYSTEM", "Streamlit application stopped.", Colors.GREEN)


def run_backend_only(backend_port: int):
    """Run FastAPI backend only."""
    log("BACKEND", f"Starting FastAPI backend on port {backend_port}...", Colors.CYAN)
    print()
    log("READY", f"API Server: http://127.0.0.1:{backend_port}", Colors.GREEN)
    log("DOCS", f"Swagger Docs: http://127.0.0.1:{backend_port}/docs", Colors.CYAN)
    log("HELP", "Press CTRL+C to stop.", Colors.YELLOW)
    print()

    try:
        import uvicorn
        uvicorn.run("app.api_server:app", host="127.0.0.1", port=backend_port, reload=True)
    except KeyboardInterrupt:
        log("SYSTEM", "Backend server stopped.", Colors.GREEN)


def main():
    parser = argparse.ArgumentParser(
        description="Unified launcher for My Maths Practice Book Workbook Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["full", "prod", "streamlit", "backend"],
        default="full",
        help="Startup mode: 'full' (Vite + FastAPI, default), 'prod' (FastAPI serving built frontend), 'streamlit' (legacy UI), 'backend' (API only)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Backend server port (default: 8000)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open the web browser on launch",
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Shorthand for --mode prod",
    )
    parser.add_argument(
        "--streamlit",
        action="store_true",
        help="Shorthand for --mode streamlit",
    )

    args = parser.parse_args()

    # Apply shorthands
    mode = args.mode
    if args.prod:
        mode = "prod"
    elif args.streamlit:
        mode = "streamlit"

    auto_browser = not args.no_browser

    print_banner()
    check_prerequisites()

    if mode == "full":
        run_full(args.port, auto_browser)
    elif mode == "prod":
        run_prod(args.port, auto_browser)
    elif mode == "streamlit":
        run_streamlit(auto_browser)
    elif mode == "backend":
        run_backend_only(args.port)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(0)
