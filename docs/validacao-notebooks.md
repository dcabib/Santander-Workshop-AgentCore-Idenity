# Execução e conferência dos notebooks — 09/10/2026

**Resultado local: 14/14 notebooks, 94/94 células de código e 14/14 cleanups
locais passaram.** Cada notebook foi executado em um kernel novo, Python
3.13.12, com `WORKSHOP_MODE=local`, `RUN_AWS=False` e cleanup de nuvem
desativado. A soma dos tempos de execução foi de 21,67 segundos.

Executar uma célula condicional não significa executar seu ramo AWS.
Os notebooks 00–09 usam o laboratório local; 10–12 fazem preparação offline;
13 executa o contrato local de ingestão, ACL e memória.
Não há `config/local.json`, `config/local.banking.json` ou
`config/local.federation.json` ou `config/local.journey.json` nesta pasta. As integrações reais e a remoção
de stacks não foram executadas.

## O que o código comprovou

Os links da tabela abrem as cópias com outputs da execução final.

| Notebook | Células de código | Resultado observado | Continua pendente |
|---|---:|---|---|
| [00 — Preflight](../evidence/executed/00_preflight.ipynb) | 4/4 | Versões das dependências e três ferramentas locais disponíveis. | Preflight AWS, Gateway/Registry gerenciados. |
| [01 — Gateway](../evidence/executed/01_gateway_targets.ipynb) | 6/6 | Três nomes qualificados corretos; processo MCP real por stdio, handshake e chamada de Fraude sem erro. | Gateway AWS e Lambda pelo Gateway. |
| [02 — Identity/OBO](../evidence/executed/02_identity_entra_obo.ipynb) | 5/5 | Token local recusado com `AUTH_INVALID_TOKEN` ao usar audiência incompatível. | OBO Entra e identidade devolvida por Graph `/me`. |
| [03 — Identidade do agente](../evidence/executed/03_identity_agente_mcp.ipynb) | 4/4 | Mesmo usuário: supervisor permitido e agente Riscos negado em Fraude; negativa sem incremento do contador de backend. | Identidades reais e restrição de workload AWS. |
| [04 — Cedar](../evidence/executed/04_policy_cedar.ipynb) | 6/6 | Doze cenários aprovados, com resultados e contadores de execução conferidos. | Policy gerenciada, projeção de claims e matriz live. |
| [05 — Autoria](../evidence/executed/05_policy_autoria.ipynb) | 5/5 | Regra Cedar contém OID e limite 50; matriz de doze cenários passa. Revisão humana marcada como pendente. | Geração gerenciada de rascunho e revisão humana. |
| [06 — Governança](../evidence/executed/06_registry_governanca.ipynb) | 5/5 | DRAFT/PENDING invisíveis na busca; publisher não aprova; approver aprova e habilita descoberta. | IAM e estados no Registry AWS. |
| [07 — Descoberta](../evidence/executed/07_registry_descoberta_execucao.ipynb) | 5/5 | Duas consultas de Riscos retornam dados sintéticos; Fraude descoberta, mas negada por Policy. | Busca semântica e execução pelo Gateway AWS. |
| [08 — Multi-conta](../evidence/executed/08_santander_multi_conta.ipynb) | 4/4 | Lista de pré-requisitos exibida com `multi_account_verified: False`. | Toda a execução entre contas A/C/B; o modo local não a demonstra. |
| [09 — Databricks/evidências](../evidence/executed/09_databricks_e_evidencias.ipynb) | 5/5 | Matriz local executada e arquivo `evidence/local-notebook.json` gravado. | Token exchange, usuário efetivo e grants Databricks. |
| [10 — Artigo multi-account](../evidence/executed/10_blog_multi_account_gateway_mcp.ipynb) | 16/16 | Dezesseis contratos, sete templates gerados e Cedar exibido. Integrações marcadas `NOT_RUN`. | Okta, quatro contas, MCP via Gateway, Policy, Registry, RAG e Strands/Bedrock. |
| [11 — Gateway por conta](../evidence/executed/11_gateways_por_conta_identity_policy.ipynb) | 15/15 | Cedar local: C003 permitido, C007 negado na plataforma e C008 negado no contrato Retail; treze templates gerados. | Entra, dois OBOs, Gateways federados, dados, Registry e Bedrock reais. |
| [12 — Cenário Santander integrado](../evidence/executed/12_cenario_santander_integrado.ipynb) | 10/10 | Oito casos Cedar, dez templates e contrato de quotas; `journey-local.json` mantém cloud `NOT_RUN` e aceite `PENDING_EVIDENCE`. | Três contas, agentes em Runtime, OBO, MCP Databricks Azure, dois usuários/grants e trace completo. |
| [13 — Ingestão, ACL e memória](../evidence/executed/13_ingestao_acl_memoria.ipynb) | 4/4 | Documentos sintéticos com visibilidade por grupo, versão, revogação, exclusão e isolamento de memória; `ingestao-local.json`. | Conectores reais, BDA, KB/OpenSearch e Memory AWS. |

As saídas locais correspondem às explicações dos respectivos ramos. Um `PASS`
local não comprova os cenários listados na última coluna.

## Ajustes decorrentes da revisão

* O notebook 01 agora exige os três nomes exatos do catálogo também no modo local.
* Os notebooks 04 e 06 exibem `NOT_RUN` nas etapas AWS ignoradas, em vez de
  terminar essas células sem saída.
* O notebook 05 usa `VALIDATED_LOCAL` e `human_review: PENDING`; a execução
  automática não é apresentada como revisão humana concluída.
* O notebook 06 verifica a invisibilidade de registros DRAFT/PENDING, a
  preservação do estado após aprovação recusada e o registro exato encontrado.
* O notebook 07 exige os três resultados esperados, incluindo as duas consultas
  permitidas e a negativa de Fraude.
* Todos os notebooks e seus geradores incluem explicação e código para cleanup.
* O notebook 09 identifica seu caminho como prova SQL REST isolada; o 12
  implementa o cenário MCP pelo Gateway.
* Os notebooks 12/13 incorporam seus diagramas e declaram o modo local/offline.
  A galeria agora navega pelos quatorze notebooks.

## Cleanup e testes

A célula de cleanup local foi executada em todos os notebooks. Os testes
também verificam repetição da limpeza, preservação de evidências e preservação
de variáveis que não pertencem ao exercício.

O wrapper `scripts/cleanup.py` prepara um plano somente leitura por padrão.
Os testes usam clientes substitutos para verificar a recusa de conta,
região, stack ou template divergente; exigência do ARN exato; respeito à
proteção de término; bloqueio de stacks em atualização; e espera pela
exclusão via CloudFormation. Nenhuma remoção real foi realizada.

A suíte completa terminou com **138 testes aprovados**, incluindo as trilhas
anteriores, cleanup e os novos contratos do cenário integrado. A dependência
`bedrock-agentcore` emitiu um aviso de depreciação Pydantic, sem falhas.
Consulte [cleanup.md](cleanup.md) para a ordem de remoção e os recursos retidos.

## Reproduzir e inspecionar

```bash
uv run --extra banking python scripts/verify_notebooks.py
uv run --extra banking pytest -q
```

O executor recusa os controles de implantação/execução AWS ou cleanup ativados
antes de iniciar o kernel. Ele mantém
[`evidence/notebooks.json`](../evidence/notebooks.json) com modo, horário,
hash SHA-256 do notebook de origem, contagem de células, resultado dos cleanups
e duração. Se um notebook falhar, registra a falha e continua verificando os
demais, encerrando o comando com erro ao final.

As cópias de origem em `notebooks/` permanecem sem outputs. As cópias em
`evidence/executed/` contêm os resultados, e os hashes registrados correspondem
às fontes usadas nesta execução.
