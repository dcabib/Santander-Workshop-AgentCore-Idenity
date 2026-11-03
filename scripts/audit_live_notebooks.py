"""Executa aulas AWS selecionadas; a verificação inclui as asserções de cada aula."""

import argparse
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lab", choices=["rag", "terraform", "registry", "all"])
    args = parser.parse_args()
    labs = {"rag": ["16"], "terraform": ["09"], "registry": ["06", "07", "08"], "all": []}[args.lab]
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "scripts/verify_notebooks.py"),
                    *(["--labs", *labs] if labs else [])], cwd=root, check=True)
