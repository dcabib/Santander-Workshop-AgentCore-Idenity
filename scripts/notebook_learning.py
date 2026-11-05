"""Índice de aulas e referências, compartilhado com o gerador."""

from santander_demo.notebook_catalog import LESSON_TITLES, published_stem

LEARNING_PATH = tuple(sorted((published_stem(name), title) for name, title in LESSON_TITLES.items()))
LEARNING_ORDER = tuple(name[:2] for name, _ in LEARNING_PATH)
