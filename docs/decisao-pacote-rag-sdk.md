# Retomada do Runtime RAG: pacote incompleto

Status: pacote completo testado com sucesso na conta substituta em 05/11/2026.
A aula 16 passou na conta `813782517426`, com geração Nova Lite no Runtime
e isolamento por ACL para analista e auditor. Relatório:
`build/notebook-runs/ephemeral-20261105-rag-005/report.json`.
Veja os Request IDs no [aceite SDK](aceite-notebooks-sdk.md).

Histórico: alternativa A aprovada pelo usuário em 05/11/2026. A verificação STS
retornou `ExpiredToken` antes da reconstrução. Em seguida, o usuário informou
o encerramento da conta e pediu um novo ciclo na conta `813782517426`.
A limpeza restrita da conta anterior não foi executada. O pacote corrigido
foi usado desde a primeira construção do Runtime da aula 16 no novo ciclo.

## Falha confirmada

Na conta `992742226465`, região `us-west-2`, a aula 16 parou na invocação
do Runtime com HTTP **424 Failed Dependency**. O grupo
`/aws/bedrock-agentcore/runtimes/santander_41faf1babbbf_rag-xmQT0C89tP-DEFAULT`
contém:

```text
ModuleNotFoundError: No module named 'bedrock_agentcore'
```

O erro foi introduzido ao reutilizar o ZIP da aula 03. Esse ZIP atende ao
servidor MCP, mas sua exportação de dependências não inclui o extra
`banking`, onde o projeto declara `bedrock-agentcore`.

Já funcionaram na AWS:

* Base MANAGED `DHHDDOSVWV`, fonte `QXTYQURYCK` e ingestão `CNTDBYGTZZ`,
  com dois documentos indexados e zero falhas.
* Conector nativo `J7FGTRGNPD` em READY e dois permits Cedar ACTIVE.
* Entrada anônima no Runtime: HTTP 401.
* Fraude de `userContext` no Gateway: POLICY_DENY,
  Request ID `1b458afc-cce8-4965-b264-3faa14f7d666`.
* Consultas diagnósticas de leitura na KB: analista recebe somente R1,
  auditor somente F1. Request IDs `86657457-976f-4d14-87b9-dccdd597f8f9`
  e `16ee69b3-35aa-446f-9b97-6b182249dedd`.

As evidências das três tentativas estão em
`evidence/sdk-aws-2026-11-04-rag.json`. As duas primeiras interromperam em
comparações de resposta SDK, corrigidas sem alterar os recursos: parâmetros
JSON serializados/defaults do S3 e versão resolvida do conector.

## A — Reconstruir somente o Runtime RAG

O notebook 16 agora exporta o `uv.lock` com `--extra banking`, instala
wheels ARM64/Python 3.12 e verifica módulos obrigatórios e `main.py`
antes do upload. Um pacote completo foi construído, sem mutações AWS:

* Tamanho: 29.781.165 bytes.
* SHA-256: `91442c303ddc79694fffdc731bfbc9128eab06ee7c3af30c07914e3b5c0a8498`.
* Dependência incluída: `bedrock-agentcore==1.24.1`.

Passaram 774 testes da suíte completa, incluindo isolamento, rejeição de
pacote incompleto e preservação dos recursos fora do escopo `rag-runtime`.
Os notebooks foram validados por esquema e compilação; o lint passou.
Essas verificações não substituem o teste do novo pacote no Runtime AWS.

A limpeza 99 recebeu o escopo explícito `rag-runtime`. Ela primeiro valida
a propriedade e as dependências de toda a execução e depois exclui somente
o Runtime RAG, seus logs, sua role e seu ZIP. O nome exato do grupo de logs
é derivado do ID do Runtime conferido, inclusive quando o processo falha
antes da última célula de registro.

A base, a fonte, a ingestão, o conector, as políticas e as demais aulas
permanecem registrados. A sessão do editor não será alterada. Depois da
limpeza, a aula 16 reconstrói o agente e repete os testes.

Comandos aprovados para a conta anterior, agora encerrada. São mantidos
como histórico da decisão e não devem ser executados na conta substituta:

```bash
uv run python scripts/run_sdk_notebooks.py \
  --expected-account 992742226465 --region us-west-2 \
  --prompt-credentials --labs 99 --cleanup-scope rag-runtime \
  --output build/notebook-runs/new-account-rag-runtime-reset-001

uv run python scripts/run_sdk_notebooks.py \
  --expected-account 992742226465 --region us-west-2 \
  --prompt-credentials --labs 16 \
  --output build/notebook-runs/new-account-rag-004
```

## B — Limpar e reconstruir toda a jornada de conta única

Executar a limpeza 99 no escopo padrão, seguida de 00–09, 15 e 16.
Isso também substitui recursos já validados, exige nova ingestão e leva
mais tempo. A nova aula 00 arquiva o registro limpo e usa novos nomes.

## Por que não substituir o ZIP diretamente

O objeto tem uma chave derivada do hash, a role permite ler esse objeto
exato e o estado registra sua identidade. Sobrescrever o objeto ou alterar
o Runtime fora das células quebraria essas verificações e a repetibilidade
da execução. A reconstrução proposta usa somente os notebooks do projeto.

O AGENTS.md fornecido na conversa determina: “Report context + alternatives
to the user” e “Wait for the user's reply” após bloqueio de infraestrutura.
O usuário escolheu “A — Reconstruir somente o Runtime RAG”. A aprovação cobre
a limpeza restrita acima e o reteste da aula 16, preservando os demais recursos.
A alternativa A anterior, de reconstrução das personas com a sessão fornecida,
já foi concluída.
