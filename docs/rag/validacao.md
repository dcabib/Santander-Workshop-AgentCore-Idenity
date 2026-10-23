# Validar o RAG por usuário

Este guia acompanha o [notebook 16](../../notebooks/16_rag_managed_identity_policy.ipynb)
e o [runbook de implantação](README.md). O objetivo é comprovar quais documentos
cada pessoa pode recuperar e qual contexto realmente chega ao modelo.
Uma célula sem exceção ou um campo `PASS` não substitui essa comparação.

## Definir a expectativa antes da execução

| Caso | Documentos permitidos | Geração | Decisão esperada |
|---|---|---|---|
| A | R1 e R2 — Riscos | Somente com trechos autorizados | ALLOW |
| B | F1 e F2 — Fraude | Somente com trechos autorizados | ALLOW |
| C | R1, R2, F1 e F2 | Somente com trechos autorizados | ALLOW |
| D | Nenhum | Não deve executar | DENY |
| JWT de A com `userContext` de C | Nenhum | Não deve executar | DENY |

A expectativa literal `EXPECTED_DOCUMENTS` do notebook traduz essa tabela.
Ela deve ser revisada junto com o requisito, sem ser calculada pela mesma
configuração `DOMAINS` que gera as permissões.

Uma pergunta semântica pode recuperar apenas parte dos documentos permitidos.
Verifique duas propriedades: nenhum resultado pode ser indevido, e consultas
pelos títulos devem alcançar o conjunto autorizado. Não confunda relevância
de busca com ausência de permissão.

## Executar o contrato local

Na raiz do projeto:

```bash
uv sync --frozen --extra banking
uv run --frozen --extra banking pytest -q tests/test_rag*.py
uv run --frozen --extra banking python -m scripts.rag_notebook_check
uv run --frozen --extra banking python -m scripts.audit_notebooks
uv run --frozen --extra banking python -m scripts.audit_notebook_faults
```

O contrato local usa JWT RSA e avaliação Cedar reais, com substitutos locais
de Cognito, Knowledge Base e modelo. Confira que D e a tentativa A→C não
chegam à recuperação nem à geração.

O observador independente compara também o contexto efetivamente enviado ao
modelo. A injeção que retira Fraude de C deve quebrar a asserção da matriz de
ACLs. Se continuar passando, o teste não está protegendo o requisito.
Essa prova local não valida a integração entre serviços AWS.

## Executar nos serviços AWS

Primeiro implante as fases do [runbook](README.md#construir-o-ambiente-por-fases)
e confira `config/local.rag.json`. Depois use o ambiente existente:

```bash
uv run --frozen --extra banking python -m scripts.rag_check
uv run --frozen --extra banking python -m scripts.rag_notebook_check --live
```

O preflight deve confirmar KB `MANAGED`, uma única fonte com ACL, ingestão
concluída, target fixo e três policies ativas com enforcement. As chamadas
anônima e com JWT inválido devem ser recusadas; o retrieval direto com a
role de execução deve retornar `AccessDeniedException`.

Faça os quatro logins Cognito e observe a emissão de WAT pelo Identity.
D pode receber identidade válida e continuar sem permissão para o RAG.
O WAT não é o bearer de entrada do Gateway: esse fluxo usa o JWT Cognito,
enquanto o conector nativo acessa Bedrock por IAM.

## Conferir fontes, contexto e decisão

Para executar o notebook com observadores dos dados e dos serviços:

```bash
uv run --frozen --extra banking python -m scripts.audit_live_notebooks rag
```

O comando mantém deploy e remoção desativados. A comparação verifica:

* ACL de cada sidecar S3 e ACL global conforme a matriz A/B/C/D.
* Conteúdo bruto dos trechos recuperados contra o documento de origem.
* IDs e textos efetivamente enviados em cada chamada a `Converse`.
* Citações e códigos sintéticos da resposta contra o contexto autorizado.
* Emissão de WAT e request IDs retornados pelo serviço Identity.
* Ferramenta e decisão nativa do Policy vinculadas ao request ID da chamada MCP.

Nos logs, o nome `rag___Retrieve` e a decisão ALLOW/DENY podem aparecer em
eventos separados. Eles precisam compartilhar o mesmo `request_id`.
Encontrar apenas um registro da ferramenta não comprova a decisão.
Para D e para a falsificação, exija DENY e ausência de geração.

## Interpretar e guardar o resultado

| Resultado | Interpretação |
|---|---|
| `LOCAL_CONTRACT` | Código local exercitado; integração AWS ainda exige teste |
| `NOT_RUN` | Etapa desativada ou não executada |
| `MATCH` | As observações selecionadas correspondem às expectativas |
| `PENDING_EVIDENCE` | Falta uma prova exigida pelo verificador |
| Erro de login, rede, modelo ou configuração | Falha operacional; não comprova recusa pela Policy |

Se faltarem apenas logs, repita a leitura sem refazer consultas:

```bash
uv run --frozen --extra banking python -m scripts.rag_check --correlate-only
```

Consulte os arquivos gerados em `evidence/`:

* `rag-live.json`: casos A/B/C/D, falsificação, cobertura e correlação.
* `rag-notebook-local.json` e `rag-notebook-live.json`: execução e hash do notebook.
* `notebook-audit-16.json`: esperado e observado no contrato local.
* `notebook-live-audit-rag.json`: execução do kernel com observação AWS.
* `notebook-live-audit-rag-observations.json`: comparações de fontes, contexto e logs.

Esses arquivos são locais e ignorados pelo Git. Os observadores não exportam
senhas, tokens nem e-mails. Confira o horário e o hash para não usar uma
execução anterior como prova de uma versão ou configuração nova.

O ensaio cobre os casos explicitamente exercitados. Qualidade geral de um
LLM, carga, propagação de revogação e outras formulações de prompt exigem
testes próprios. Alterar ACL no S3 requer nova ingestão antes de repetir a
matriz. A variante Entra/OBO exige preparação e validação separadas.

Ao encerrar, siga a [limpeza pelo IaC](README.md#limpeza). Limpar variáveis
do notebook não remove serviços, e as políticas de retenção podem preservar
KB, fonte e buckets após a remoção dos stacks.
