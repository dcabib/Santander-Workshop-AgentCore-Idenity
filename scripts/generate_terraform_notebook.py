"""Entrada compatível para o gerador único da jornada AWS."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_aws_notebooks import build_notebook as build_aws_notebook  # noqa: E402
from scripts.generate_aws_notebooks import main as generate  # noqa: E402

NAME = '09_terraform_runtime_gateway_identity'
OUTPUT = ROOT / "notebooks" / (NAME + ".ipynb")

def build_notebook():
    return build_aws_notebook(NAME)

def main():
    generate(['09_terraform_runtime_gateway_identity'])

if __name__ == "__main__":
    main()
