"""Executa a aula na AWS, sem opções de simulação."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "scripts/verify_notebooks.py"),
                    "--labs", *['09'], *sys.argv[1:]], cwd=root, check=True)
