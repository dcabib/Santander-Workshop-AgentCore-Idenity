# Sessão online — Harness, aproximadamente uma hora

A referência técnica preparada é o **AgentCore Harness** do repositório AWS
indicado pelo usuário. O HTML chama “Harness” a ferramenta para deploy da stack;
a conversa relata homologação, mas não identifica sua versão. Confirmar com o
cliente se esta referência corresponde ao produto homologado antes do ensaio.

Não confundir uma execução CloudFormation deste workshop com uma demonstração
do Harness. Os scripts upstream criam/excluem recursos por SDK e não foram
executados: o projeto exige provisionamento por seu pipeline IaC.

## Agenda e evidência de saída

| Minutos | Demonstração | Evidência |
|---|---|---|
| 0–10 | Harness versus Runtime e o caso escolhido | Responsabilidade do agent loop, ferramentas, sessão e operação |
| 10–20 | Recurso Harness já implantado pelo pipeline | Identificador, estado READY, configuração e owner |
| 20–35 | Ferramenta MCP através de Gateway autenticado | Chamada permitida/negada e telemetria |
| 35–45 | Release de prompt/config/modelo/artefato | Manifesto versionado e hash; mudança revisada pelo pipeline |
| 45–55 | Rollback para release anterior e promoção multi-conta | Manifesto anterior e teste funcional repetido |
| 55–60 | Decidir aplicação futura | Caso apropriado, limites e próximo responsável |

O Harness da referência recebe o Gateway na invocação; não se deve pressupor que
criar um Harness cria ou governa toda a stack Databricks/Entra/Registry. O exemplo
de gateway básico upstream usa entrada sem authorizer. Para Santander, manter a
entrada autenticada e demonstrar o modelo de identidade realmente suportado,
sem converter OBO em M2M apenas para reproduzir um exemplo.

O teste de release deve fixar versão de configuração, prompt, modelo e artefato,
guardar a versão anterior e reaplicar essa versão pelo IaC. O ZIP por hash e os
change sets já presentes no projeto são uma base desse procedimento, mas não
substituem validar a semântica de versões/rollback do Harness escolhido.

## Antes de apresentar

Confirmar produto/versão homologada, conta/região habilitada, contrato de
autenticação, modelos permitidos, pipeline IaC proprietário, artefato anterior
e fonte sintética. Preparar a integração por esse pipeline; não executar o
`getting_started.py` upstream que cria roles/harness dinamicamente.

## Referências fixadas

- [Getting started — AgentCore Harness](https://github.com/awslabs/agentcore-samples/tree/f33b4f14ea46cae2379196948073a6bb4d0e21cf/01-features/01-harness/00-getting-started).
- [Gateway integration](https://github.com/awslabs/agentcore-samples/tree/f33b4f14ea46cae2379196948073a6bb4d0e21cf/01-features/01-harness/01-advanced-examples/02-gateway-integration).
- [OAuth example](https://github.com/awslabs/agentcore-samples/tree/f33b4f14ea46cae2379196948073a6bb4d0e21cf/01-features/01-harness/01-advanced-examples/07-oauth).

Status desta entrega: roteiro e referências preparados; recurso Harness e
ensaio do produto não implantados.
