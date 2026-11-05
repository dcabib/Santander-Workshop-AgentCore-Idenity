# Sessões previstas pelo ambiente — 05/11/2026

O usuário determinou usar o ambiente disponível. A solução foi revisada para
as capacidades previstas no workshop oficial, sem alterar roles protegidas.
As aulas 00–09 e 15 passaram na conta `813782517426`, região `us-west-2`,
usando a sessão do editor. A aula 15 validou sessões por pessoa e isolamento
com a [tabela identificada por TableId](decisao-dynamodb-notebook-sdk.md).

## Diagnóstico e correção

A implementação anterior exigia `iam:SimulatePrincipalPolicy` e quatro roles
com nomes exclusivos. Essas operações não correspondem às personas que o
ambiente do workshop permite assumir. Renovar a mesma sessão não corrigiria
essa incompatibilidade.

A leitura da policy do editor encontrou `AssumePersonaRoles`, permitindo
explicitamente `admin_persona`, `publisher_persona` e `consumer_persona`.
O [notebook oficial de personas](https://github.com/awslabs/agentcore-samples/blob/7282ec3b839736d55d199f4c726136c342e33b3c/06-workshops/10-Agent-Registry/00-getting-started/step-by-step/01-create-user-personas-workflow.ipynb)
cria e usa essas três roles com STS. As três estavam ausentes na conta.

A aula 07 agora cria essas personas com trust somente para o principal do
editor e permissões limitadas ao catálogo e Runtime da execução. AssumeRole,
GetRegistry e GetAgentRuntime verificam acessos reais permitidos e negados.
A aula 08 mantém publicação, submissão, aprovação, descoberta e invocação,
incluindo Publisher sem aprovação e descoberta sem invocação. Developer usa
a sessão do editor e não é apresentado como uma quarta persona isolada.

Os nomes são únicos na conta. A célula confere todos antes da primeira
criação e recusa qualquer role sem registro de propriedade nesta execução.
A retomada e a limpeza verificam ARN, tags, trust e documentos IAM.

A aula 15 usa o fluxo aprimorado do Cognito Identity Pool. As permissões do
editor incluem criação/configuração do pool e IAM PassRole. O ID token
verificado é trocado por credenciais temporárias; regras de sub escolhem
roles limitadas ao actor Memory e partition key DynamoDB de cada pessoa.
Logins anônimos e o fluxo clássico ficam desativados; sub sem regra é negado.
As negativas de leitura entre pessoas e a revogação na fonte permanecem.

## Validação e limites

* 00–06: PASS na AWS com a role do editor; relatório
  `build/notebook-runs/ephemeral-20261105-editor-001/report.json`.
* 778 testes de código passaram após a revisão. Os contratos validam os
  parâmetros com botocore, colisão de nomes, drift, federação e limpeza.
* 07–09 passaram na AWS com as personas oficiais. A aula 15 passou, incluindo
  emissão de sessões por Identity Pool, negativas entre pessoas e revogação
  na fonte: `build/notebook-runs/ephemeral-20261105-native-002/report.json`.
* O RAG, a limpeza completa e a reconstrução 00–09, 15–16 passaram.
  A nova execução `952f3855e8d9` criou novos recursos e concluiu os 12 notebooks
  sem falhas: `build/notebook-runs/ephemeral-20261105-rebuild-001/report.json`. A conta
  anterior, encerrada pelo usuário, não serve como evidência para esta versão.
* Nenhuma policy do evento foi modificada. Não há credenciais em arquivos,
  notebooks distribuídos ou evidências.
