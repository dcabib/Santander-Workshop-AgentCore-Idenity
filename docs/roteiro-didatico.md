# Editar os notebooks

As aulas principais são geradas por `scripts/generate_aws_notebooks.py`.
Edite as fontes das células em `scripts/sdk_*_lesson.py`,
`scripts/sdk_notebook_lessons.py` e as explicações em
`scripts/notebook_curriculum.py`. As referências usam
`scripts/reference_notebook_lessons.py`.

```bash
uv run python scripts/generate_aws_notebooks.py
uv run python scripts/verify_notebooks.py --validate-only
uv run pytest -q
```

Os extras são adaptações independentes editadas diretamente. O helper de
análise do CSV fica em `notebooks/20-Extras/assets/eda.py`.

Os 18 PNGs externos foram recuperados dos attachments distribuídos.
Os SVGs foram gerados pelas fontes de arquitetura com ícones oficiais, cuja
origem e hashes constam em `diagramas/icons/sources.json`.
Para regenerar também os PNGs, `scripts/notebook_architecture.py` requer
`rsvg-convert` e `pngquant` no sistema.

Publique notebooks sem outputs e sem credenciais. Ao mudar código, execute
as aulas afetadas na AWS e atualize a evidência, sem atribuir à nova versão
o hash ou aceite de uma versão anterior.
