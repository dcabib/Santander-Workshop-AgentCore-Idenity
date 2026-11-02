#!/usr/bin/env bash
# Prepara o ambiente do workshop: cria o .venv e registra o kernel Jupyter.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

uv sync --frozen --extra banking
uv run python -m ipykernel install --user --name santander-workshop --display-name "Santander Workshop (.venv)"

echo "Setup concluído. Selecione o kernel 'Santander Workshop (.venv)' no notebook."
