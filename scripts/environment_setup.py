"""Environment checks and dependency install for jobsearch CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
GMAIL_APP_PASSWORD_FILE = ROOT / "secrets" / "gmail-app-password"
MIN_PYTHON = (3, 11)

GMAIL_PACKAGES = [
    "google-api-python-client",
    "google-auth-httplib2",
    "google-auth-oauthlib",
]
BROWSER_PACKAGES = ["patchright"]


def python_version_ok() -> tuple[bool, str]:
    major, minor = sys.version_info[:2]
    if (major, minor) >= MIN_PYTHON:
        return True, f"{major}.{minor}"
    need = f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}+"
    return False, f"{major}.{minor} (need {need})"


def in_project_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == (VENV_DIR).resolve()
    except OSError:
        return False


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def active_python() -> Path:
    """Prefer project venv interpreter when present."""
    if venv_python().exists():
        return venv_python()
    return Path(sys.executable)


def package_installed(name: str, *, python: Path | None = None) -> bool:
    py = python or active_python()
    module = name.replace("-", "_").split("[")[0]
    if module == "googleapiclient":
        module = "googleapiclient"
    try:
        proc = subprocess.run(
            [str(py), "-c", f"import {module}"],
            capture_output=True,
            check=False,
        )
        return proc.returncode == 0
    except OSError:
        return False


def gmail_deps_ok() -> bool:
    return all(package_installed(p) for p in ("googleapiclient", "google_auth_oauthlib"))


def browser_deps_ok() -> bool:
    return package_installed("patchright")


def gmail_auth_ok() -> bool:
    token = ROOT / "state" / "gmail-token.json"
    if token.exists():
        return True
    if os.environ.get("GMAIL_APP_PASSWORD", "").strip():
        return True
    if GMAIL_APP_PASSWORD_FILE.exists() and GMAIL_APP_PASSWORD_FILE.read_text().strip():
        return True
    return False


def load_gmail_app_password() -> str:
    env = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if env:
        return env
    if GMAIL_APP_PASSWORD_FILE.exists():
        return GMAIL_APP_PASSWORD_FILE.read_text(encoding="utf-8").strip()
    return ""


def linkedin_cookies_ok() -> bool:
    return (Path.home() / ".linkedin-mcp" / "cookies.json").exists()


def _run_pip(python: Path, packages: list[str], *, quiet: bool) -> tuple[bool, str]:
    if not packages:
        return True, ""
    cmd = [str(python), "-m", "pip", "install", "--upgrade", *packages]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return False, str(exc)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, tail[-1] if tail else f"pip exit {proc.returncode}"
    return True, ""


def ensure_venv(*, quiet: bool = False) -> tuple[bool, str]:
    if in_project_venv():
        return True, str(venv_python())

    if VENV_DIR.exists() and venv_python().exists():
        return True, str(venv_python())

    if not quiet:
        print(f"  Creating virtualenv at {VENV_DIR} …")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            cwd=str(ROOT),
            check=True,
            capture_output=quiet,
        )
    except subprocess.CalledProcessError as exc:
        return False, f"venv failed: {exc}"
    return True, str(venv_python())


def reexec_in_venv_if_needed() -> None:
    """Re-launch this process with project venv python when available."""
    ok, py_path = ensure_venv(quiet=True)
    if not ok:
        return
    target = Path(py_path)
    if not target.exists():
        return
    if Path(sys.executable).resolve() == target.resolve():
        return
    os.execv(str(target), [str(target), *sys.argv])


def install_deps(
    *,
    gmail: bool = True,
    browser: bool = False,
    quiet: bool = False,
) -> tuple[bool, list[str]]:
    ok, py_path = ensure_venv(quiet=quiet)
    if not ok:
        return False, [py_path]

    python = Path(py_path)
    packages: list[str] = []
    if gmail:
        packages.extend(GMAIL_PACKAGES)
    if browser:
        packages.extend(BROWSER_PACKAGES)

    messages: list[str] = []
    if packages:
        if not quiet:
            print(f"  Installing: {', '.join(packages)} …")
        ok, err = _run_pip(python, packages, quiet=quiet)
        if not ok:
            return False, [err]

    if browser and browser_deps_ok():
        if not quiet:
            print("  Installing Patchright Chromium (one-time, ~150MB) …")
        try:
            subprocess.run(
                [str(python), "-m", "patchright", "install", "chromium"],
                cwd=str(ROOT),
                check=False,
            )
        except OSError as exc:
            messages.append(f"patchright browser install skipped: {exc}")

    return True, messages


def print_environment_report() -> None:
    py_ok, py_ver = python_version_ok()
    print(f"  Python {py_ver}: {'✓' if py_ok else '✗'}")
    print(f"  Virtualenv ({VENV_DIR.name}): {'✓ active' if in_project_venv() else ('✓ exists' if VENV_DIR.exists() else '○ not created')}")
    print(f"  Gmail packages: {'✓' if gmail_deps_ok() else '○ not installed'}")
    print(f"  Browser (patchright): {'✓' if browser_deps_ok() else '○ not installed'}")
    print(f"  Gmail auth: {'✓' if gmail_auth_ok() else '○ not configured'}")
    print(f"  LinkedIn cookies: {'✓' if linkedin_cookies_ok() else '○ not configured'}")


def run_install_step(
    *,
    gmail: bool = True,
    browser: bool = False,
    skip: bool = False,
    quiet: bool = False,
) -> int:
    print("\n" + "-" * 60)
    print("  Step 1/4 — Environment")
    print("-" * 60 + "\n")

    py_ok, py_ver = python_version_ok()
    if not py_ok:
        print(f"  ✗ Python {py_ver} — install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ and retry.")
        return 1
    print(f"  ✓ Python {py_ver}")

    if skip:
        print("  ○ Skipping dependency install (--skip-install)")
        print_environment_report()
        return 0

    ok, detail = ensure_venv(quiet=quiet)
    if not ok:
        print(f"  ✗ {detail}")
        return 1
    print(f"  ✓ Virtualenv → {VENV_DIR}")

    if not in_project_venv():
        print("\n  ℹ Re-run with the project venv for installed packages:")
        print(f"     {venv_python()} {ROOT / 'scripts' / 'jobsearch.py'} …")
        print("     (Onboarding will install deps into .venv now.)")

    ok, errs = install_deps(gmail=gmail, browser=browser, quiet=quiet)
    if not ok:
        print(f"  ✗ Install failed: {errs[0] if errs else 'unknown'}")
        return 1

    print("  ✓ Dependencies installed")
    print()
    print_environment_report()
    return 0
