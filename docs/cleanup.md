# Limpeza e retomada

Execute [99_cleanup_sdk](../notebooks/99_cleanup_sdk.ipynb) na conta e região
usadas na criação, ou pelo terminal:

```bash
uv run python scripts/run_sdk_notebooks.py --labs 99 \
  --expected-account <ID_DE_12_DIGITOS> --region us-west-2 \
  --output build/minha-limpeza
```

A limpeza confere a propriedade e remove os recursos registrados, respeitando
dependências. A exclusão de fonte/base RAG pode levar vários minutos.
Confirme `cleanup: COMPLETE`, estado `CLEANED` e nenhum recurso ativo no registro.
Secrets Manager usa exclusão agendada com recuperação de sete dias; os assets
de geração de policy expiram em sete dias por ausência de API de exclusão.

Se houver falha, preserve `.workshop/`, examine a mensagem e retome 99 com uma
sessão válida. Não apague o estado para forçar uma execução nova.
A próxima aula 00 arquiva um registro encerrado e gera um novo run_id.

`--cleanup-scope rag-runtime` com `--labs 99` faz limpeza parcial do Runtime RAG
e preserva base/fonte e demais aulas; não significa encerramento de toda a jornada.
Os extras possuem limpeza própria. 99 não remove recursos do editor ou das
referências multiconta.
