"""Mantém o diagrama RAG alinhado à fonte única da jornada AWS."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.generate_diagrams import main

if __name__ == '__main__':
    main()
