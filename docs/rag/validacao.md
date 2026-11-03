# Validação RAG

Execute a aula 16 no runner AWS. Cada caso invoca o Runtime RAG, que realiza
retrieval governado e geração Bedrock. São exigidos: resultado compatível com
a matriz A/B/C/D, documento e fonte autorizados, identidade ligada ao token,
negativa de retrieval direto e ausência de resposta fabricada em casos negados.

```bash
uv run python scripts/workshop_runner.py deploy --labs 16 --execute
uv run python scripts/workshop_runner.py run --execute
```

A execução retorna um ID CodeBuild. Consulte esse build e baixe seu artefato,
conforme [validação da jornada](../validacao.md). Unit tests e validação de
sintaxe não substituem esse resultado. Preserve tokens e secrets fora dos logs.
