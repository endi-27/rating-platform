#!/usr/bin/env python3
"""Launcher for backend/scripts/seed_superadmin.py"""
import subprocess
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"

if __name__ == "__main__":
    cmd = ["uv", "run", "python", "scripts/seed_superadmin.py"]
    res = subprocess.run(cmd, cwd=str(backend_dir))
    sys.exit(res.returncode)
