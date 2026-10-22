# Revisão de aderência — conversa, escopo Santander e implementação

**Registro histórico anterior às adequações.** A análise abaixo motivou a
implementação dos notebooks 12/13. O estado atualizado está na
[matriz de adequações por demanda](docs/adequacoes-santander.md), no
[runbook integrado](docs/journey/README.md), na
[matriz de decisões](docs/journey/decisoes.md) e no
[roteiro consolidado](docs/roteiro.md). Agora há um caminho A → hub → B →
MCP Databricks no código/IaC, com agentes hospedados e identidades distintas;
isso ainda não comprova execução cloud. Sessão 2 e Harness possuem material
próprio; seus conectores/serviços reais não foram implantados.

**Data da revisão:** 09/10/2026.  
**Conclusão da revisão anterior às adequações:** atendíamos parcialmente. Havia material executável para ensinar Identity,
Policy, Gateway e Registry, com infraestrutura preparada para os ensaios. Ainda
não demonstramos o fluxo Santander completo nem respondemos a todas as decisões
que o cliente quer tomar na Sessão 1. Naquele momento, as Sessões 2 e Harness
permaneciam por preparar.

## 1. Fontes e critério da revisão

Foram revisados:

- [Transcrição completa](conversa.md), confrontada com os **92 segmentos** de
  [asrOutput.json](asrOutput.json). O texto corresponde integralmente aos segmentos,
  desconsiderando espaços e a formatação de horários/participantes. Isso confirma
  a reprodução do Transcribe, não a exatidão do reconhecimento em relação ao áudio.
- [HTML Santander de 05/10/2026](2026-10-05-AgentCore-casos-de-uso-Santander.html),
  incluindo as **duas imagens**: Databricks MCP DBSQL e supervisor/Riscos/Fraude.
- Os doze notebooks, código de identidade, autorização, fontes e federação,
  templates/geradores, [plano](plano-demo-workshop-santander.md),
  [roteiro](docs/roteiro.md), [aceite](docs/aceite.md) e
  [registro de validação](docs/validacao.md).

Esta revisão não executou serviços AWS, Entra ou Databricks. O registro anterior
informa 78 testes locais aprovados. O arquivo `evidence/notebooks.json` registra
00–09 como `LOCAL_SIMULATION` e 10–11 como `OFFLINE_PREPARATION`. Não há
configurações `config/local.*` nem evidências de chamadas cloud nesta pasta.
Portanto, não há evidência registrada para declarar a integração real concluída.

Os estados abaixo têm significados distintos:

| Estado | Significado |
|---|---|
| Material entregue | O exercício ou documentação existe e pode ser apresentado com seus limites. |
| Parcial | Parte está implementada, mas falta um caminho, uma prova ou uma decisão pedida pelo cliente. |
| Em aberto | A demanda ainda não tem demonstração ou resposta técnica concluída nesta entrega. |
| Frente separada | Consta no programa, mas pertence à Sessão 2 ou à sessão online. Não bloqueia, por si só, a demo principal. |

## 2. O que a conversa priorizou

A conversa concentra a demo na segurança entre agentes, preservando a pessoa
que pediu a ação: **00:40–01:21**, **07:00–08:26** e **10:11–11:20**. Pede
execução passo a passo em Jupyter (**10:42–11:11**) e reforça acesso por agente,
tool e usuário, rate limit e trace (**11:20–12:02**).

O trecho **14:04–15:58** acrescenta uma exigência específica: uma área deve
conseguir chamar outra passando pela conta central. Não basta a plataforma
consultar três áreas independentemente. Em **15:02**, é discutida a necessidade
de uma entrada por Gateway antes do Runtime.

O HTML organiza o programa em duas sessões presenciais de meio período e uma
online. A ingestão continua no escopo, mas é uma frente distinta da demonstração
principal de identidade/autorização. Harness é complementar; a fala de **09:50**
relata homologação obtida, atualizando a ressalva anterior de **09:33–09:42**.
Essa fala não verifica por si só produto, versão ou acesso disponível.

## 3. Matriz da Sessão 1

As referências “HTML” abaixo apontam para as seções Contexto e Caso 1 do documento
original. Os horários apontam para a transcrição.

| Demanda e origem | Evidência da entrega atual | Avaliação |
|---|---|---|
| **D01 — Controle por agente, tool e usuário.** HTML, objetivo do Caso 1 e Fig. 2; conversa 10:11–11:20. | Notebooks 03/04 e `policy.py` distinguem usuário e aplicação por tool. Os testes de troca de caller são locais. No 11 há um login público na entrada e um caller de Gateway por salto; sua Policy permite o conjunto de leituras ao usuário autorizado daquela conta. | **Parcial.** Falta demonstrar, no mesmo fluxo cloud, o agente Riscos permitido em sua tool e negado na tool de outra área, mantendo o usuário. |
| **D02 — Entra inbound e OBO até a fonte, preservando BDAGs.** HTML, Identity e situação atual; conversa 00:57–01:21. | Notebook 02 prepara OBO para Graph; 11 prepara OBO entre Gateways e Runtimes com `whoami`; 09 tem adapter de token exchange/SQL Databricks. | **Parcial e central para o aceite.** Graph e `whoami` não comprovam Unity Catalog. Não houve ensaio com dois usuários e grants distintos no Databricks Azure. |
| **D03 — Cadastrar MCP Databricks no Gateway e validar acesso a outra nuvem, sem API Gateway intermediário.** HTML, Gateway e “Validar no workshop”; conversa 01:31–03:14. | Existem targets MCP de Runtimes AWS. `DelegatedDatabricks` chama `/oidc/v1/token` e `/api/2.0/sql/statements` diretamente no host Databricks. | **Em aberto no caminho solicitado.** O notebook 09 não registra nem chama MCP DBSQL/Genie pelo Gateway. Rota, autenticação e autorização cross-cloud não estão comprovadas. |
| **D04 — Origem em uma conta de negócio → conta central → outra conta de negócio.** Conversa 11:39 e 14:04–15:58. | O 08 tem esqueleto A → hub C → Runtime B e helper de invocação. O 11 prepara quatro Gateways e duas Policies por caminho, mas o agente inicia no kernel local. | **Parcial.** Falta unir esses padrões e demonstrar Retail/Riscos como origem de uma chamada para Transaction/Fraude via hub, com negativa equivalente. |
| **D05 — Gateway como entrada de cada domínio, Identity e Policy nas fronteiras.** Conversa 15:02–15:58 e pedido posterior deste projeto. | Notebook 11 e `infra/federation`: quatro Gateways, providers locais, engines `ENFORCE`, audiência/caller por salto e restrição de workload nos MCPs. | **Material e IaC entregues; integração pendente.** Ainda não houve invocação AWS. As negativas C007/C008 são por parâmetro de `get_profile`, não grants de dados. |
| **D06 — Mostrar Runtime e a hospedagem de agentes.** HTML, Contexto e alternativa Runtime; conversa 12:59–13:54. | O 08 prepara supervisor/especialista em Runtime. O 10 prepara Strands hospedado, mas usa Okta/M2M. O 11 usa Entra/OBO e hospeda os MCPs em Runtime; o agente fica no notebook. | **Parcial.** Há exemplos de Runtime, mas ainda falta uma narrativa única que combine agente hospedado, Entra/OBO e Gateways por conta. Migrar o K2 real não é condição para a demo conceitual. |
| **D07 — Registry governado e comportamento com instâncias/contas distintas.** HTML, Agent Registry e validação multi-conta; conversa 02:56–03:14 e 13:37. | 06/07 têm estados, papéis e descoberta; 08 prepara consumo central por AssumeRole; 10/11 registram três capacidades na plataforma. | **Parcial.** Falta ensaiar publicação/consumo entre contas e representar proprietário, versão e instância do K2/caso de uso. Três registros no catálogo central não provam toda essa governança. |
| **D08 — Trace por request até a query e explicabilidade da origem do dado.** HTML, Observability e ambas as figuras; conversa 07:00–08:13 e 11:20. | Há log delivery, leitor sanitizado, nomes de tools e indicadores de revisão pendente. `DelegatedDatabricks.prove()` retorna principal/grant, sem correlação com os Gateways. | **Parcial.** Falta um trace correlacionado agente → Gateways → MCP → query, com identidade efetiva e decisão. Logs separados e lista de tools não atendem essa prova. |
| **D09 — Rate limit QPM/TPM e budget mensal por agente/tool: o que fica onde.** HTML, situação atual e validações; conversa 11:20–12:02. | `max_registros <= 50` é autorização por parâmetro. Não foi encontrado mecanismo de contagem por tempo, tokens ou orçamento, nem comparação técnica concluída. | **Em aberto.** É preciso responder a divisão de responsabilidades e demonstrar o controle escolhido se ele entrar no piloto. A ausência no projeto não significa ausência de capacidade no serviço AWS. |
| **D10 — Decidir se complementa ou substitui o AI Gateway Databricks; comparar alternativa Runtime e Gateway.** HTML, objetivo/alternativas do Caso 1; conversa 01:40–03:14. | Há padrões AWS, mas não há uma matriz de decisão sustentada por ensaio cross-cloud e comparação dos controles existentes. | **Em aberto como entregável de decisão.** A conversa recomenda avaliar e evitar pressupor a substituição. O cliente precisa sair com responsabilidades, limites e trade-offs claros. |
| **D11 — K2 intacto, integração externa e instâncias por caso de uso.** HTML, Contexto; conversa 00:07–00:57. | Não alteramos K2/Santalk. A tool `consultar_conhecimento_k2` declara `integracao_k2=False`; os MCPs bancários usam fixtures. | **Restrição respeitada; integração representativa.** Usar um substituto sintético é compatível com a conversa, que trata K2 como exemplo. Falta explicitar o contrato para conectar o produto real, sem afirmar que já foi integrado. |
| **D12 — Encaixe de Neural Trust, Dynatrace, Watsonx.governance e SanEval.** HTML, stack atual; conversa 04:18–05:28 e 07:13. | O plano cita os produtos. Os notebooks 10/11 usam Bedrock diretamente e um guardrail de exemplo; não há conectores desses produtos nem um desenho final de responsabilidades. | **Parcial no posicionamento; integração não entregue.** O pedido é explicar coexistência. Não é necessário implementar todos os conectores para esta demo, mas é necessário mostrar onde se encaixam. |
| **D13 — Demonstração didática, com Jupyter e chamadas permitidas/negadas.** Conversa 10:11–11:11. | Doze notebooks, diagramas, Cedar local e artefatos IaC; estados locais/cloud explicitados. | **Material entregue.** A agenda atual ainda lista só 00–09. É necessário selecionar uma trilha de quatro horas e ensaiar a demonstração integrada. |

## 4. Sessão 2 e sessão online

Esses itens não desapareceram do escopo por termos priorizado segurança.
Também não devem ser confundidos com pré-requisitos para concluir a Sessão 1.

| Demanda do HTML | Estado nesta entrega | Entrega que falta |
|---|---|---|
| Ingestão de SharePoint, Databricks Silver/Gold, SQL on-prem e APIs/backends AWS. Caso 2; conversa 08:43–09:17. | **Frente separada; não implementada.** | Pipeline demonstrável de ao menos uma fonte, metadados e responsabilidades das demais. |
| BDA/Data Ingestion: documentos/markdown → OpenSearch/KB/grafo. | **Frente separada; não implementada.** A KB de Lending é pré-requisito já ingerido. | Notebook/pipeline de ingestão, não apenas consulta à KB pronta. |
| Indexador comum e retrieval respeitando BDAGs/ACLs, inclusive em KB compartilhada. | **Frente separada; não implementada.** `search_lending_policies` usa a role do Runtime e não filtra documentos pelo usuário. | Modelo de autorização no retrieval e prova de usuários com visibilidades distintas. |
| AWS Context: status, disponibilidade e relação com SharePoint. | **Pendência aberta.** O HTML e a conversa registram dúvida. | Confirmar nome/capacidade e disponibilidade atual com fonte oficial; registrar retorno. Não inferir o status atual da gravação. |
| D2K: discover/register/update/delete para ingestão; Memory do supervisor. | **Frente separada; não implementada.** Agent Registry não é automaticamente esse ciclo D2K. | Contratos e exercícios próprios para ingestão e contexto de sessão. |
| Grafos/Neptune e observabilidade como fonte de conhecimento. | **Investigação da Sessão 2.** Neptune já aparece “a confirmar”; observabilidade como fonte é proposta, não aceite fechado. | Validar interesse e arquitetura antes de tratar como entrega obrigatória. |
| Harness: deploy da stack, releases imutáveis, rollback e multi-conta. Caso 3; conversa 09:33–10:08. | **Sessão separada; material não preparado.** CloudFormation do lab não demonstra o produto Harness. | Confirmar a ferramenta/versão/acesso e preparar a sessão online de aproximadamente uma hora. |

Salesforce/Slack/outros IdPs aparecem como exemplos opcionais em **03:26–04:14**.
Não são bloqueadores da Sessão 1. A prioridade permanece Entra e delegação até a
fonte. A migração de ferramentas de desenvolvimento para Runtime, mencionada em
**12:59–13:24**, é contexto futuro, não um caso adicional já contratado para esta demo.

## 5. Diferenças importantes entre o plano e o código

### 5.1 O notebook 09 não fecha a integração Gateway–Databricks

O plano associa o 09 a “integração MCP DBSQL, delegação e leitura de logs/traces”.
O código em [databricks.py](src/santander_demo/databricks.py), métodos `exchange`,
`_sql` e `prove`, é uma prova isolada por HTTP de token exchange e SQL.

Isso pode ser útil para verificar identidade e grants antes de integrar, mas
não responde se **AgentCore Gateway + Identity** conseguem expor e chamar o
MCP Databricks no ambiente do cliente. A célula atual testa apenas o caso com
grant; a repetição sem grant está descrita em texto. O export de evidências no
fim do notebook grava a matriz local, não o resultado Databricks anterior.

### 5.2 O notebook 11 ainda não tem um agente de origem por área

Em [federation/client.py](src/santander_demo/federation/client.py), `caller()`
define o login público como caller da plataforma e a aplicação da plataforma
como caller dos Gateways de negócio. `verify_token()` exige esse login e um
usuário específico.

Em [federation/agent.py](src/santander_demo/federation/agent.py), o próprio
resultado informa `agent_location=NOTEBOOK_KERNEL`.
O caminho atual é:

```text
Notebook/Strands → Gateway Plataforma → Gateway Retail → MCP Retail
                                    → Gateway Transaction → MCP Transaction
                                    → Gateway Lending → MCP Lending
```

O trecho **14:04–15:58** pede também o caminho:

```text
Agente da área A → entrada/roteamento central → Gateway da área B → serviço/dado B
```

O helper [invoke_supervisor](src/santander_demo/live.py) do 08 oferece uma base
A → C → B, mas não está integrado ao cenário de quatro Gateways do 11.
O 08 também não executa esse helper em uma célula: orienta o instrutor a utilizá-lo.
Não devemos somar diagramas de notebooks diferentes e chamar isso de uma
composição já demonstrada.

### 5.3 Identidade do Gateway não é identidade individual de todos os agentes

O Cedar do 11 valida o ator imediato de cada salto. Isso é útil para a confiança
entre serviços, mas o enunciado “agente Riscos só chama tool Riscos” requer
identidades distinguíveis de Riscos/Fraude e a respectiva matriz por tool.

Os testes locais de [policy.py](src/santander_demo/policy.py) fazem essa distinção.
Já [federation/spec.py](src/santander_demo/federation/spec.py) oferece as leituras
da conta a um caller configurado e à sua allowlist de usuários.
Não demonstra dois agentes diferentes recebendo decisões diferentes na mesma
composição cloud. O 11 também exige que seu usuário de baseline esteja autorizado
nas quatro contas; a comparação com um usuário de acesso parcial ainda precisa
de um fluxo negativo próprio.

O futuro contrato deve dizer onde a aplicação originadora é autorizada e como
os destinos recebem identidade verificável. Um nome de agente em argumento da
tool não substitui esse contrato.

### 5.4 OBO até o Runtime não equivale a autorização do dado pelo usuário

`whoami` do 11 verifica quem chegou ao MCP. As consultas DynamoDB dos MCPs,
porém, usam a execution role do Runtime. Da mesma forma,
[search_lending_policies](src/santander_demo/banking/lobs/lending.py) faz
`Retrieve` usando a role AWS, sem filtro de ACL derivado do usuário.

Assim, identidade preservada até o servidor e Policy na tool não comprovam
automaticamente “a tool só lê o que o usuário pode ler”. Essa prova deve acontecer
no Databricks/Unity Catalog ou no mecanismo de ACL de retrieval escolhido.

As negativas C007/C008 do 11 são didáticas e específicas de `get_profile`.
Outras tools podem consultar os mesmos fixtures. Não são isolamento geral de
clientes nem substituição de BDAGs.

### 5.5 Mudar para modo AWS não transforma todos os exercícios em ensaios reais

No 03, a troca de caller continua usando o emissor local. No 04, a matriz também
é local; o ramo AWS verifica configuração e encaminha o leitor ao aceite.
O 10 mantém o usuário até o Gateway central e usa M2M nos destinos, como
explicado no próprio notebook. Ele serve como referência do artigo, não como
prova de OBO fim a fim para Santander.

Esses limites estão documentados, mas afetam a afirmação de que a demanda foi
atendida: ter o exercício escrito e ter o serviço executando a regra são etapas
distintas.

## 6. Ordem recomendada para fechar a demo principal

| Prioridade | Trabalho | Critério de conclusão |
|---|---|---|
| **P0 — Fluxo único Santander** | Compor o padrão A → central → B com Gateways do 11, agentes/callers distinguíveis e o caso Riscos/Fraude. Manter Registry na descoberta e o K2 como contrato externo ou substituto declarado. | Na mesma composição: mesmo usuário, agente correto permite; outro agente nega. A origem e o destino são contas de negócio distintas. |
| **P0 — Fonte Databricks** | Preparar acesso ao MCP DBSQL/Genie no sandbox e integrar Gateway + Identity ao mecanismo delegado aceito pelo Databricks Azure. | Fluxo do JWT até a query; identidade efetiva esperada; usuário A lê a tabela canário, B recebe negativa real de grant. Nenhum fallback para identidade compartilhada. |
| **P0 — Ensaio e trace** | Implantar pelo IaC, verificar claims reais, executar positivos/negativos e correlacionar os saltos com o ID da query. | Uma evidência reconstruível liga usuário, aplicação, tool, decisão e query/fonte. Negativa de Policy distingue-se de OAuth/rede, e a não execução do backend é comprovada. |
| **P1 — Decisão arquitetural** | Documentar complementar/substituir AI Gateway, Runtime versus Gateway e o encaixe de Neural Trust/Dynatrace/Watsonx/SanEval. | Tabela de responsabilidades, limites e manutenção, apoiada no ensaio. Sem pressupor substituição das ferramentas atuais. |
| **P1 — Rate e budget** | Verificar capacidades atuais e escolher onde controlar QPM, TPM e orçamento por agente/tool. | Resposta explícita sobre o que cada camada faz. Se houver demo de bloqueio, medir o limite e a negativa; `max_registros` não vale como essa prova. |
| **P1 — Registry entre contas** | Ensaiar owner/publisher/approver/consumer e representação das instâncias/casos de uso. | Registro aprovado descoberto de outra conta; aprovação não concede execução; papéis e responsabilidades verificáveis. |
| **P1 — Agenda de apresentação** | Consolidar uma demo de 30 minutos e uma trilha de meio período, reaproveitando 02/03/04/06/07/11 e incorporando o caminho Databricks. | Roteiro ensaiado dentro de quatro horas. O 10 fica como comparação M2M; não é preciso executar todos os doze notebooks na sessão. |
| **P2 — Outras sessões** | Preparar ingestão/ACLs/Context/BDA e, separadamente, Harness. | Agendas, dependências e materiais próprios, sem apresentar essas frentes como já entregues pelo núcleo de segurança. |

As prioridades acima são uma recomendação desta revisão, não novas decisões
acordadas com o cliente. Os acessos AWS/Entra/Databricks e a preparação das fontes
devem seguir os pipelines IaC responsáveis.

## 7. O que podemos afirmar hoje

**Afirmação sustentada:** “Temos um laboratório didático dos quatro pilares,
com controles locais testados e IaC para cenários multi-conta. O notebook 11
prepara Gateways, Identity OBO e Policy por conta. O ensaio real e a integração
Databricks ainda estão pendentes.”

**Ainda não sustentado:** “Já atendemos o escopo Santander completo”, “a delegação
preserva BDAGs até a query”, “temos trace fim a fim”, “temos rate limit/budget por
agente/tool” ou “já demonstramos agentes de duas áreas conversando via hub com
os quatro Gateways”.

A entrega atual é uma base para a Sessão 1. O próximo passo de maior valor é
fechar **uma única chamada entre áreas, passando pelo hub e chegando ao Databricks
com identidade e evidência corretas**, antes de acrescentar novos exemplos genéricos.
