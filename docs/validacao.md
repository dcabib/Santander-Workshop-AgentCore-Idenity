# Validar código e resultados

Na raiz, após o setup:

```bash
uv run python scripts/verify_notebooks.py --validate-only
uv run pytest -q
```

Esses comandos são locais e não criam recursos AWS. O primeiro valida os 18
notebooks principais, incluindo as cinco referências sem código.
Para executar a jornada em uma conta autorizada:

```bash
uv run python scripts/run_sdk_notebooks.py \
  --labs 00 01 02 03 04 05 06 07 08 09 15 16 \
  --expected-account <ID_DE_12_DIGITOS> --region us-west-2 \
  --output build/minha-execucao
```

Substitua o ID pela conta conferida no STS. O executor verifica a identidade,
interrompe a sequência em falha e guarda cópias executadas e `report.json`.
A seleção 99 é explícita: veja [limpeza](cleanup.md).
Os extras são executados pelo Jupyter com seu próprio kernel.

Confira conta/região, hash da fonte, todas as células executadas, outputs,
casos permitidos e negados e as tabelas de resultado esperado de cada aula.
HTTP 200 ou ausência de traceback isoladamente não comprovam o exercício.
Para o RAG, confira os documentos recuperados e o conteúdo da resposta.
Para A02, confira a continuidade de estado e o primo 83. Para A03, confira
13 categorias atípicas nas duas caudas IQR e a resposta Kimberly/Crocodile 120.

O [registro de execução](aceite-notebooks-sdk.md) distingue evidências anteriores
das correções e verificações posteriores.
