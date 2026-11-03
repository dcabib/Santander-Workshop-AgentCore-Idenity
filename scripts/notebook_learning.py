"""Índice da jornada, derivado da mesma fonte que gera as aulas AWS."""

from scripts.aws_notebook_lessons import LESSONS

LEARNING_PATH = tuple((name, title) for name, (title, _) in sorted(LESSONS.items()))
LEARNING_ORDER = tuple(name[:2] for name, _ in LEARNING_PATH)
