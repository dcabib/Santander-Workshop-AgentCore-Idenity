# Validação da implementação — 09/10/2026

**Resultado:** laboratório local executável, com material de implantação preparado.
Não houve deploy, login Entra/Okta, inferência Bedrock, consulta Graph nem acesso Databricks.

**Reexecução com cleanup:** 14/14 notebooks, 94/94 células de código e 138 testes
passaram. As provas por notebook, ajustes e limitações estão no
[relatório de execução](validacao-notebooks.md). A remoção de nuvem ficou
desativada; o cleanup local passou nos quatorze notebooks.

| Verificação executada | Resultado |
|---|---|
| `uv sync` / dependências travadas em `uv.lock` | PASS |
| `ruff check` e formatação Python | PASS |
| Suíte pytest completa, incluindo cleanup e cenário integrado | **138 testes passaram** |
| Quatorze notebooks, em kernels novos, sem acesso AWS | **14/14 PASS**; 00–09 simulação local, 10–12 preparação offline, 13 contrato local de ingestão |
| Notebook 05 após inclusão da leitura do rascunho gerenciado | PASS |
| Seis templates CloudFormation, cfn-lint para us-east-1/us-west-2 | PASS estrutural |
| `terraform init -backend=false` e `terraform validate` do módulo Entra | PASS estrutural |
| CLI `santander-demo demo` e `matrix` | PASS |
| Build original Linux ARM64/Python 3.12, registrado na revisão anterior | PASS; ZIP 30,5 MiB / extraído 67,7 MiB |
| Notebooks distribuídos sem outputs | PASS |
| Transcrição e conversa excluídas do pacote de execução | PASS |
| Sete templates adicionais do notebook 10 | PASS estrutural por cfn-lint |
| Build atualizado `banking.zip`, Linux ARM64/Python 3.12 | PASS; ZIP 33,0 MiB / extraído 76,6 MiB |
| Diagrama do notebook 10, PNG/SVG e anexo no notebook | PASS visual e estrutural |
| Treze templates adicionais do notebook 11 | PASS estrutural por cfn-lint |
| Diagrama do notebook 11, PNG/SVG e anexo no notebook | PASS visual e estrutural |
| Artefato banking atualizado com federação, `whoami` e cenário integrado | PASS; hash, entrypoint journey e todas as fontes conferem |
| Dez templates novos do notebook 12 | PASS estrutural por cfn-lint |
| Terraform Entra e Databricks de `infra/journey`, init sem backend e validate | PASS estrutural nos dois módulos; sem plan/apply |
| Diagramas 12/13, PNG/SVG e anexos nos notebooks | PASS visual; bytes dos anexos conferem com as imagens |
| Galeria com 14 notebooks em navegador headless | PASS; links, navegação 12/13, zoom e viewport móvel; sem erro JavaScript |

Os testes cobrem assinatura/emissor/audiência/expiração, tenant, contexto delegado,
usuário e caller, ações/recursos exatos, limite 50/51, schema, negação antes do
backend, governança local, bloqueio de endpoints não confiáveis, protocolo MCP
real por stdio, ausência de fallback Databricks, principal exato e erro de grant.
Também verificam contratos SDK dos providers, idempotência/estados,
polling limitado, separação de publicação/aprovação e geração sem publicação.

O Cedar local é avaliado por `cedarpy`, que usa o avaliador Cedar. O mapeamento
de claims para tags é um contrato do laboratório; não é evidência de que o
serviço gerenciado o aplicou. O teste MCP usa um processo servidor real, mas
não passa pelo Gateway AWS.

O build usa wheels Linux ARM64; o ZIP não foi executado em Lambda/Runtime.
Validação CloudFormation/Terraform não verifica quota, disponibilidade da região,
permissões efetivas, admin consent nem compatibilidade dos recursos no sandbox.

Evidências locais geradas:

- `evidence/demo-local.json`
- `evidence/matriz-local.json`
- `evidence/notebooks.json`
- `evidence/executed/*.ipynb`
- `build/artifacts.json`
- `build/banking-artifacts.json`
- `evidence/journey-local.json`
- `evidence/ingestao-local.json`

Esses arquivos são ignorados pelo Git para evitar versionar outputs de futuros
ensaios com informações do ambiente. Os itens ainda pendentes estão em
[aceite.md](aceite.md): OBO de dois usuários, Policy nativa, IAM Registry,
restrição de workload do Runtime, três contas reais e Databricks Azure.

## Extensão do artigo multi-account — notebook 10

O [novo notebook](../notebooks/10_blog_multi_account_gateway_mcp.ipynb) executou
com `RUN_AWS=False`. Seu resultado é **OFFLINE_PREPARATION**, não uma simulação
de respostas do artigo. Gateway, Registry, quatro contas, RAG, Policy no serviço
e Strands/Bedrock ficaram explicitamente **NOT_RUN**.

Os testes adicionais exercitam Cedar real (permit, negação por padrão e precedência
de forbid), JWT RSA/JWKS, `cid` Okta, schemas dos 16 tools, protocolo MCP em processo
real para `calculate_emi`, fixtures idempotentes, validação do endpoint do Registry,
paginação, encaminhamento do JWT e Guardrails com doubles de SDK, classificação de
negativas e evidência sem sucesso indevido. Doubles não comprovam integração AWS.

O teste de MCP executou somente uma ferramenta matemática local, sem DynamoDB ou
Bedrock. Os templates passaram no lint e o ZIP foi construído, mas ainda não foram
executados nos serviços. Há um aviso de depreciação Pydantic emitido pela
dependência `bedrock-agentcore`, sem falha nos testes.

O ensaio real deste notebook requer as quatro contas, aplicações Okta, segredo M2M gerido por IaC,
acesso ao modelo e uma Knowledge Base ingerida em Lending, conforme o
[runbook do cenário](banking/README.md). Evidências locais adicionais:
`evidence/executed/10_blog_multi_account_gateway_mcp.ipynb` e
`build/banking-artifacts.json`.

## Gateways por conta — notebook 11

O [notebook 11](../notebooks/11_gateways_por_conta_identity_policy.ipynb) executou
suas 32 células, incluindo 15 de código, com `RUN_AWS=False`, em kernel novo. São quatro Gateways,
quatro providers Identity OBO e quatro Policy engines definidos por IaC,
sem implantação neste ambiente.

Os 21 testes adicionais cobrem negações Cedar independentes (plataforma versus
Retail), tenant/usuário/aplicação/scope, ausência de permissões de escrita, nomes
com duas camadas de targets, múltiplos usuários nos templates, segredos locais à
conta/região, audiências distintas, destinos de cada fase, proteção de workload,
claims sanitizadas e detecção de mudança de usuário no destino.

Um teste usa transporte HTTP MCP real em ASGI, com JWT RSA assinado/verificado
localmente, para confirmar que `whoami` recebe Authorization pelo contexto da
requisição e rejeita ausência de delegação. A fonte JWKS é substituída pela chave
local de teste; isso não comprova encaminhamento de headers no Runtime AWS.

Os 13 templates passaram em `cfn-lint`; o ZIP banking atualizado também inclui
esta trilha. Os 14 notebooks distribuídos continuam sem outputs.
O PNG incorporado no notebook 11 corresponde à imagem
revisada em `docs/federation/arquitetura.png`.

Continuam **NOT_RUN**: Entra real, Gateway→Gateway, OBO em dois saltos, quatro
Policies gerenciadas, consultas entre contas, Registry e Bedrock. A execução real
também precisa de revisão de logs para atribuir negativas e comprovar ausência
de chamada ao backend. Os pré-requisitos completos estão no
[runbook da federação](federation/README.md).

## Adequações Santander — notebooks 12/13

O notebook 12 executou dez células de código em modo **OFFLINE_PREPARATION**.
Gerou dez templates, validou oito casos Cedar e demonstrou o contrato local
de quotas. A evidência cloud permanece `NOT_RUN`, com aceite
`PENDING_EVIDENCE`. Não houve login real nem consulta ao MCP Databricks.

O notebook 13 executou quatro células em modo **LOCAL_INGESTION_CONTRACT**.
Com documentos sintéticos, confirmou visibilidade distinta por grupo,
versionamento, revogação de ACL, exclusão e isolamento da memória por usuário.
Não executou conectores, BDA, KB/OpenSearch ou Memory AWS.

Os 35 testes em `test_journey.py` cobrem a configuração, os parâmetros das
fases IaC, Cedar, JWT assinado, WAT/OBO ligados ao usuário, descoberta governada,
comparação exata de principal e classificação conservadora de erros.
Três testes usam o cliente MCP real sobre transporte HTTP substituto para
exercitar o Runtime até a fronteira do hub: sucesso, negativa de Policy e
negativa de grant na fonte. Outro usa HTTP ASGI para confirmar que o Runtime
recebe o bearer pelo header. Esses transportes não executam serviços AWS.

A suíte completa tem 138 casos aprovados. Além dos novos casos, inclui a
regressão das trilhas anteriores e sua limpeza. O aviso de depreciação Pydantic
da dependência permanece sem causar falha. A execução dos notebooks também
emitiu o aviso padrão do kernel sobre transporte TCP; foram kernels locais.

Os dois módulos Terraform novos passaram em `init -backend=false -input=false`
e `validate`, usando os lockfiles dos providers. Isso valida o schema, mas
não comprova admin consent, IAM, federation ou disponibilidade do serviço.
O artefato ARM64 tem SHA-256
`c1dd8f9a6a79aa4d06a1c37f432e1061968c687e3cc96fe306fd18aa2220bd22`.
As fontes Python e o entrypoint do cenário conferem com os arquivos empacotados.

O próximo passo é o [ensaio em três contas](journey/README.md), incluindo a
habilitação AWS do token exchange público, dois usuários Databricks e a
[correlação dos logs até a query](journey/trace.md). A matriz de
[adequações por demanda](adequacoes-santander.md) separa implementação local,
preparação cloud e decisões ainda necessárias.
