"""Entrada compatível para o gerador único da jornada AWS."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_aws_notebooks import main as generate  # noqa: E402


def main():
    generate(None)

if __name__ == "__main__":
    main()
