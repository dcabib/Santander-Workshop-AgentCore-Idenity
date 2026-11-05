"""Índice da jornada, derivado da mesma fonte que gera as aulas AWS."""

from santander_demo.notebook_catalog import published_stem
from scripts.aws_notebook_lessons import LESSONS

LEARNING_PATH = tuple(sorted(
    (published_stem(name), title) for name, (title, _) in LESSONS.items()
))
LEARNING_ORDER = tuple(name[:2] for name, _ in LEARNING_PATH)
