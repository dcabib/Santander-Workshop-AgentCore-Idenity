# Execução AWS dos notebooks com criação por SDK

## Nova conta efêmera — 05/11/2026

O usuário informou o encerramento da conta `992742226465` e autorizou
começar novamente no novo editor. O STS identificou a conta `813782517426`
e a role `workshop-resources-ec2-CodeEditorInstanceRole-sMqXzxM7tO4x`.
Antes de qualquer criação, a chamada de leitura `SimulatePrincipalPolicy`
retornou `AccessDenied`: nenhuma policy de identidade permite
`iam:SimulatePrincipalPolicy`.

Foram transferidos 406 arquivos de código, sem credenciais, `.venv` ou
registros de recursos da conta anterior. O hash do pacote foi conferido:
`67b1f320838c4bb2480c162cd6ac9ec2fbfb34d565457436412387437a634bb6`.
`setup.sh` instalou dependências e registrou `santander-workshop`.
Na primeira execução da suíte no Python 3.12, passaram 774 testes e falhou
o contrato da descrição MCP `search_lending_policies`: a indentação de
docstrings difere entre Python 3.12 e 3.13. O registro da ferramenta agora
usa `inspect.getdoc`, preservando o schema. Após sincronizar essa correção,
**775 testes passaram em 25,91 s** no editor AWS. Os hashes das alterações
posteriores ao pacote inicial ficam no `SOURCE_MANIFEST.json` da cópia de teste.

O usuário escolheu A e forneceu uma sessão `WSParticipantRole`. Ela é válida,
mas a leitura das policies confirmou ausência de `iam:SimulatePrincipalPolicy`
e Deny explícito de `sts:AssumeRole` para as roles da jornada.
A [decisão sobre a sessão](decisao-sessao-participante-20261105.md) registra
o diagnóstico e as alternativas.

**A aula 00 passou** com essa sessão, em 1,18 s. A execução `a96b1de2499d`
estava ACTIVE com zero recursos naquele preflight. Request ID STS do executor:
`9b5eb906-d07b-4c47-992c-6b45e90048a8`. O relatório está em
`build/notebook-runs/ephemeral-20261105-preflight-001/report.json`.
Depois da orientação de usar o ambiente existente, **00–06 passaram** com a
sessão do editor. As células criaram os recursos nesta execução, sem stacks.
Relatório: `build/notebook-runs/ephemeral-20261105-editor-001/report.json`.
07–08 foram revisadas para as três personas oficiais permitidas pelo editor;
15 usa Identity Pool. Passaram 778 testes de código após os ajustes.
O resultado da revisão e do reteste da aula 15 estão detalhados abaixo.

### Resultado da revisão para a sessão do editor

**00–09, 15 e 16 passaram na AWS** nesta conta. 07 criou as três personas oficiais
com trust restrita ao editor e testou acessos reais permitidos e negados.
08 publicou/aprovou o registro e verificou as negativas entre personas.
09 integrou o Runtime ao Gateway com decisões Cedar por pessoa.

| Aula | SHA-256 executado | Resultado |
|---|---|---|
| 07 | `65d6f80a30ac82f2154c3a050c6b4cabed25484c9b2823e890c0be91d24103d4` | PASS |
| 08 | `c96482276911b406d5014f65c2f9e944e8644378a8f0a0a0ef500420cd2d5397` | PASS |
| 09 | `d1b60f65275e14b5ee684c8f90e0141597c8c2fe5413ca2cec95008c28b271cd` | PASS |
| 15 | `009967e18c1b6e17a1bd024021b081c7fee5c6e5d67ae8385aaf255213145aca` | PASS |
| 16 | `2a1c39139a58a65cd28d877961686b1dae032ac4e5eeb189b9cc46088917d6c7` | PASS |

A primeira tentativa de 15 parou em CreateTable por falta de
`dynamodb:TagResource`. A [correção aplicada](decisao-dynamodb-notebook-sdk.md)
usa o TableId imutável na retomada/limpeza e passou em 12 testes específicos.
O reteste AWS passou em 34,95 s, incluindo emissão de sessões Cognito por
pessoa, negativas Memory/DynamoDB entre pessoas, negativa anônima e revogação.

Na aula 16, a KB MANAGED e a fonte foram criadas. O notebook deixou de exigir
as consultas opcionais GetFoundationModel e ListTagsForResource, ausentes no
editor. A KB é conferida pelo ID/ARN gerado pela AWS, nome, role e configuração;
a disponibilidade do modelo foi confirmada por Converse no Runtime. A fonte
agora aguarda AVAILABLE antes da ingestão. O RAG passou em 234,72 s,
indexando dois documentos com zero falhas.

| Teste RAG | Resultado | Request ID |
|---|---|---|
| Runtime sem token | HTTP 401 | `9c21fa31-76ca-457c-85ec-1e179b5cabae` |
| Fraude de userContext | POLICY_DENY | `8f3202fb-2a3c-4ed3-bfea-2a422a213f91` |
| Retrieve direto pelo Runtime | IAM_DENY | `326caefd-fc52-4ba0-b9d9-a9ebf08760cb` |
| Analista, geração Nova Lite | Somente documento R1 | `3bfbf696-1ad6-4d7b-9fe4-fe6e1d03916d` |
| Auditor, geração Nova Lite | Somente documento F1 | `5f4c985f-5497-4170-bafd-993acb0de4d5` |

Passaram 793 testes de código; os 45 testes RAG/limpeza/executor também passaram no
Python 3.12 do editor. Os 13 notebooks SDK foram validados por esquema e
compilação. A primeira limpeza atingiu `CLEANUP_DELETE_TIMEOUT` após
cinco minutos de espera da fonte RAG, ainda em `DELETING`. O registro
preservou os recursos pendentes. A aula 99 passou a separar essa exclusão
em uma célula, aguardar até 14 minutos e retomar sem repetir DeleteDataSource.
Uma fonte já ausente é conciliada pelo ID registrado; uma fonte desconhecida
na mesma base continua bloqueando a limpeza. Passaram 45 testes específicos
de RAG, limpeza e executor.

### Limpeza completa e reconstrução

A retomada de 99 passou em 368,90 s. A execução `a96b1de2499d` terminou com
status `CLEANED`, `resources: {}` e 59 registros liberados. O segredo foi
agendado para exclusão com recuperação de sete dias, como previsto na aula.
Assets de geração de políticas seguem a expiração administrada pelo serviço.

* Relatório: `build/notebook-runs/ephemeral-20261105-cleanup-002/report.json`.
* SHA-256 da aula: `a3233e2332b4e7f303a6fef33b0b3609d07f6bff067ad9facca0cfda12a4308e`.
* STS do executor: `219d7fa6-34d1-4431-9202-2d419aa86da2`.

A reconstrução 00–09, 15 e 16 passou **sem falhas nas 12 aulas**, começando
pela execução `952f3855e8d9`, após arquivar o registro `CLEANED` anterior.
A soma dos tempos dos notebooks foi 736,35 s (aproximadamente 12 minutos).
Relatório: `build/notebook-runs/ephemeral-20261105-rebuild-001/report.json`.
STS do executor: `6859d123-2927-4222-919f-2428e78f7273`.

| Aula | Resultado | Segundos |
|---|---|---|
| 00 | PASS | 0,71 |
| 01 | PASS | 39,58 |
| 02 | PASS | 2,67 |
| 03 | PASS | 43,86 |
| 04 | PASS | 39,19 |
| 05 | PASS | 33,96 |
| 06 | PASS | 71,71 |
| 07 | PASS | 14,19 |
| 08 | PASS | 19,50 |
| 09 | PASS | 37,29 |
| 15 | PASS | 184,39 |
| 16 | PASS | 249,30 |

Novos recursos incluem User Pool `us-west-2_rDMxZGL38`, KB `GX1TK8C89P`,
ingestão `SIT2ZGN2XP` e Runtime RAG `santander_952f3855e8d9_rag-DrEQXYGs9b`.
O TableId DynamoDB é `d7e81bf8-4994-4968-bf59-dce961082d8e`. São recursos
criados pelas células, sem reutilização dos IDs da execução anterior.

No RAG reconstruído, os dois documentos foram indexados sem falhas.
A geração Nova Lite retornou somente R1 ao analista (Request ID
`dda68768-689f-48be-8976-a06b5243b35f`) e F1 ao auditor
(`031d688b-bf7c-4f3d-8912-adeb9b08e33f`). Repetiram-se as negativas anônima,
de fraude de identidade e de Retrieve direto pelo Runtime.

Foram comparados 194 arquivos de código, notebooks e dependências entre
a pasta local e o editor AWS: nenhum arquivo ausente ou diferente.
A execução reconstruída permanece `ACTIVE` para inspeção e uso; a aula 99
permite limpá-la antes de uma nova demonstração. **10–14 continuam pendentes
de conversão e teste em contas distintas.**

Relatórios remotos:
`build/notebook-runs/ephemeral-20261105-native-001/report.json` (07–09) e
`build/notebook-runs/ephemeral-20261105-native-002/report.json` (15);
`build/notebook-runs/ephemeral-20261105-rag-005/report.json` (16).
Cópia das evidências: `evidence/sdk-aws-2026-11-05-native.json` (fora do Git).

## Histórico — conta encerrada, 04/11/2026

**Resultado naquele ciclo:** a alternativa A foi concluída. As aulas
**00–07 passaram** na execução `41faf1babbbf`, com a sessão `WSOpsRole`
fornecida pelo usuário. Os recursos da execução anterior foram limpos e
seu estado arquivado antes da nova construção. Veja os detalhes abaixo.

As aulas **00–06 passaram** na conta `992742226465`, região `us-west-2`,
execução `0f2344b88999`. A conta anterior foi encerrada. Esta execução começou
sem recursos do workshop e usou a role do Code Editor da nova conta.
`setup.sh` instalou dependências e kernel; as células criaram os recursos.
Nenhum stack ou output CloudFormation foi usado.

| Aula | SHA-256 da fonte aprovada | Resultado AWS |
|---|---|---|
| 00 | `8b57e1af9a840c69e7cde49292f1b9b48f8cc6992b569c6e7278dd7510d649d0` | STS e registro da conta nova |
| 01 | `61dc009548b6e3436e9b1f3d468042cff8d5a356f35f6537b4ca1d1d3926ce25` | Cognito, Lambda, Gateway, negativas JWT e MCP |
| 02 | `2884dc1368ee0baec595782ef498344505edb2919ce740105af4f4dc393f0d56` | Audiências, assinatura e chamada autorizada |
| 03 | `66590ab2f38161b355b11fb234d9cb3820237badaa769b7faea87f8742d19de1` | Artefato, Runtime MCP, identidade IAM e logs |
| 04 | `010cd2804c0538b9c1ca904a92e746eceaf9159544668e141ed5dacd4af15bd1` | Engine ACTIVE, Gateway ENFORCE, ALLOW e DENY |
| 05 | `bda3390eb3894f7901aa9ff8cea445f6bcd1bf206cfadebd55fee1fde83ae0f5` | Geração, revisão, rascunho LOG_ONLY e reteste |
| 06 | `71c19232b87aca8f9986774ff2ea9a10261aa7c611ccd511674796b89231944c` | Registry READY, descoberta IAM e negativa anônima |

| Verificação | Resultado | Request ID AWS |
|---|---|---|
| Gateway sem token | HTTP 401 | `92c509fc-a4ae-4679-ab27-b188bd56b679` |
| JWT válido para outra audiência | HTTP 403, MCP `-32002` | `e5087d46-2fbe-4b35-95c0-73a3117017dc` |
| Runtime sem assinatura | HTTP 403 | `ab34b222-5841-4d1d-9019-ba9e269c5a47` |
| Ferramenta MCP no Runtime | Identidade do workload confirmada | `b1094d04-1a18-4e5d-be74-4e8ab4224462` |
| Cedar: analista/cliente-001 | ALLOW, Lambda executada | `a05d2ecf-5839-41fd-84c3-47e3df06913a` |
| Cedar: analista/cliente-002 | DENY, HTTP 200 com erro MCP `-32002` | `6a34bb56-174f-4b69-b6e0-78594f4391cc` |
| Cedar: auditor/cliente-001 | DENY, HTTP 200 com erro MCP `-32002` | `7725e497-96d7-4340-9193-ce91122f968a` |
| Registry com IAM | Consulta autenticada, catálogo vazio | `3acf21c3-765e-4970-8842-35dbc161573c` |
| Registry anônimo | HTTP 403 | `37584e8b-7554-4f4b-b4af-e55816e364ff` |

A aula 05 parou inicialmente porque a geração retornou `definition.policy`
em vez de `definition.cedar`. A correção lê as duas variantes de statement,
mas exige que o texto passe no parser Cedar e em onze casos de autorização.
Outros formatos e extensões incompatíveis são recusados. O reteste reutilizou
a geração registrada, criou a política em `LOG_ONLY` com
`FAIL_ON_ANY_FINDINGS` e repetiu um ALLOW e dois DENY no Gateway.
A política manual continuou ACTIVE; o rascunho não foi promovido.

Os relatórios preservam a primeira falha e o reteste aprovado. As evidências
privadas da execução estão em `evidence/sdk-aws-2026-11-04.json` e, no editor
AWS, em `build/notebook-runs/`. Os notebooks distribuídos não contêm saídas.
Passaram 725 testes automatizados, lint e validação dos 18 notebooks.

### Limpeza e reconstrução na mesma conta

A aula 99 passou em 48,27 segundos com SHA-256
`6b6a9b1013b9be70cd9c950ae0136a0c0105262da22ee9165af5363451167ae7`.
O estado ficou CLEANED, sem recursos restantes e com 26 referências liberadas.
O segredo foi agendado para exclusão com sete dias de recuperação.

A próxima aula 00 arquivou `0f2344b88999` e iniciou `212b89261d98`.
As aulas 00–06 passaram novamente nessa execução, com novos nomes e IDs.
Essa segunda execução foi posteriormente limpa no ciclo aprovado abaixo.

### Bloqueio da aula 07 e retomada aprovada

A versão `182971a4ede22dcbab1cacb6231be47efe431f24c415f5b957f42cc0db318424`
criou quatro roles, mas a sessão do Code Editor recebeu AccessDenied para
`iam:SimulatePrincipalPolicy`. Essa sessão também não possui autorização
para assumir as novas personas.

O diagnóstico com a sessão fornecida pelo usuário confirmou as 16 decisões
IAM esperadas. Ele é somente de leitura e não equivale ao aceite completo
do notebook no kernel AWS.

A [alternativa A](decisao-personas-conta-efemera.md) foi aprovada e executada:

* A limpeza removeu as quatro personas e os demais recursos registrados de
  `212b89261d98`, liberando 30 referências. O estado terminou CLEANED.
* A leitura imediatamente após `DeleteSecret` ainda não mostrava `DeletedDate`.
  Uma consulta posterior confirmou o agendamento, com Request ID
  `cf30e6a2-9282-4b2b-a0f2-ac894cc5b0ec`. A correção espera a propagação da
  leitura, mantém a recuperação de sete dias e não repete a exclusão.
* A retomada da limpeza passou com SHA-256
  `c2e42107f6c0ae6b22794c769c1bd64c2606b8044d71c43f20c203dfb9a15fce`.
* A aula 00 arquivou o estado limpo e iniciou `41faf1babbbf`.
  Todas as aulas 00–07 passaram sob `WSOpsRole`. As fontes 00–06 têm os
  hashes da tabela anterior; a fonte 07 é
  `182971a4ede22dcbab1cacb6231be47efe431f24c415f5b957f42cc0db318424`.
* A matriz IAM executou as 16 verificações. Exemplo: Developer recebeu
  `implicitDeny` para `CreateRegistryRecord`, Request ID
  `43d1d330-ce24-4a0a-8910-0c310e17be88`.

As evidências estão em `evidence/sdk-aws-2026-11-04-ops.json` e nos diretórios
`new-account-cleanup-002`, `new-account-cleanup-003` e `new-account-ops-001`
do executor AWS. A primeira falha de confirmação do segredo foi preservada.
As credenciais não foram gravadas nos notebooks ou arquivos de configuração.

### Registry com chamadas reais por persona — aula 08

Passou em 18,56 segundos, na mesma execução `41faf1babbbf`, com fonte
`13cb61e22c688e2a3b397690c5b0441d6ef04dadb92b35560d8309f366aabe9a`.
O Developer consultou o Runtime; o Publisher publicou e submeteu o MCP;
o Approver aprovou o pacote após comparar seu hash.

| Verificação | Resultado | Request ID |
|---|---|---|
| Publisher tenta aprovar | IAM DENY | `97fbdcbd-80af-4baf-b7e8-a4cf09e780de` |
| Consumer descobre e confere descritor | APPROVED, hash correspondente | `e252aae2-162d-4a77-ab4a-4323ef299bff` |
| Consumer invoca MCP | STS dentro do Runtime confirmou o workload | `739c6575-b678-4dc7-87e5-fb6554ea928f` (STS) |
| Sessão limitada à descoberta tenta invocar | IAM DENY | `5c63c7a1-0349-467d-96f5-ba3b792f56f3` |

As evidências estão em `evidence/sdk-aws-2026-11-04-registry.json`.
A consulta e as negativas ocorreram nos serviços AWS, além da simulação
IAM da aula 07.

### Integração Runtime–Gateway — aula 09

A aula foi renomeada para `09_integracao_runtime_gateway_identity.ipynb`.
Passou em 37,43 segundos, com fonte
`d1b60f65275e14b5ee684c8f90e0141597c8c2fe5413ca2cec95008c28b271cd`.
As células criaram a permissão IAM da role do Gateway, o target MCP com
SigV4 e o permit Cedar específico. Terraform não foi usado.

* Analista: ALLOW, Request ID Gateway `85561095-5d72-478a-9059-18b81cb67229`.
  STS no Runtime: `79aab804-4aec-404c-aeb5-83dad60526d9`.
* Auditor: DENY por Policy, Request ID Gateway
  `ee5defb5-5859-4c73-8a7b-60e16f1f1f42`.

As evidências estão em `evidence/sdk-aws-2026-11-04-integration.json`.
O JWT autentica a pessoa no Gateway; IAM autoriza o salto ao Runtime.
Não foi implementado OBO Microsoft nem encaminhamento do JWT ao servidor.

### Memory e concessão atual — aula 15

Passou em 183,50 segundos, com fonte
`659ebea43f50b090eb98235acc87836db3d3724e1b1c8b65cac49eb676dd6be8`.
As células criaram Memory de curto prazo, DynamoDB e duas roles didáticas.
O evento contém uma referência, sem o conteúdo financeiro sintético.

| Verificação | Resultado | Request ID |
|---|---|---|
| Auditor tenta ler o actor do analista | IAM DENY | `1df897ff-9a81-4af6-a224-8cc8176f45ad` |
| Analista tenta ler a partição de outra pessoa | IAM DENY | `2M0L523GIRPJ7R5J8FA4KUBS67VV4KQNSO5AEMVJF66Q9ASUAAJG` |
| Referência após revogar a concessão | Continua no Memory | `256a0f88-d653-4baf-b460-6b5760e1320b` |
| Fonte após revogação | Sem linha autorizada; nenhum conteúdo retornado | `KBQ2M4N3LNSEM89OFTA3QT2UO3VV4KQNSO5AEMVJF66Q9ASUAAJG` |

A ausência da linha autorizada é diferente de uma negativa IAM. O documento
canônico permanece. A evidência está em `evidence/sdk-aws-2026-11-04-memory.json`.

### RAG — aula 16, aceite incompleto

A base MANAGED, a fonte, a ingestão de dois documentos, o conector nativo e
os permits Cedar foram criados pelas células. A fraude de `userContext`
foi negada pelo Gateway. A inicialização do agente falhou com HTTP 424:
o ZIP não continha `bedrock_agentcore`. A correção de empacotamento e a
reconstrução restrita estão descritas na
[decisão de retomada](decisao-pacote-rag-sdk.md).

Em 05/11/2026, o usuário aprovou a reconstrução somente do Runtime RAG.
A verificação STS retornou `ExpiredToken` antes da limpeza; nenhum recurso
foi alterado nessa tentativa. Em seguida, o usuário informou o encerramento
da conta e solicitou começar novamente em outra conta efêmera. A limpeza
restrita não chegou a executar; a construção nova usará o pacote corrigido.

**Limites atuais:** 16 aguarda a reconstrução do Runtime; 10–14 continuam
em migração. A limpeza das extensões 08, 09 e 15–16 passou por testes de contrato
e ainda precisa de execução AWS. Uma conta única não comprova fronteiras
entre contas.

## Histórico — conta encerrada, 03/11/2026

Em 03/11/2026, as aulas **00, 01, 02 e 03 passaram** no ambiente de notebooks AWS,
na conta `456332459064`, região `us-west-2`, execução `6825d3096100`.
O código mostrado nas células criou os recursos. Não foram usados stacks ou
outputs CloudFormation na execução dessas aulas.

Este aceite é parcial: não comprova o funcionamento das aulas seguintes nem
da limpeza. O [aceite da arquitetura anterior](aceite-aws.md) é independente.
Em 04/11/2026, o usuário informou que essa conta foi encerrada. As evidências
abaixo são históricas e não substituem a execução do zero em outra conta efêmera.

| Aula | Versão do notebook executada — SHA-256 | Resultado |
|---|---|---|
| 00 | `541c37c71a80637483767b60462ae71dc6ce8a591afb418f99f5332de228685c` | STS, região, SDK e registro de IDs |
| 01 | `af6138dea00bc4083933ef99166c22380144007a9cd8c9aaef9516501f45d110` | Gateway, target e invocação MCP na Lambda |
| 02 | `b476e41187a9624c6cf0e551e27261cdc7059180ce9d55ba3bd79c8c309bcb57` | Identidade humana, audiências e negativas JWT |
| 03 | `7b284e80a536e506b5297644e3faa1b3c40b84bf466bb4f4578ed7a8b6248524` | Código ARM64 implantado no Runtime, MCP e identidade IAM |

## Evidências das chamadas

| Verificação | Resultado | Request ID AWS |
|---|---|---|
| Gateway sem token | HTTP 401 | `4d7adf16-4496-43de-b5a8-89d12d8151c7` |
| Gateway com JWT malformado | HTTP 401 | `5f551ed8-149b-4bd4-9d64-e3e31ca38212` |
| Ferramenta autenticada pela interface MCP | Lambda executada, risco sintético `low` para `cliente-001` | `aaf0aa76-06a3-443e-b7bf-ea7f30354c76` |
| JWT assinado, emitido para outra aplicação | HTTP 403; erro MCP `-32002`, `insufficient_scope` | `620f186a-450b-49a5-8fbd-951bf01ef306` |
| Audiência alterada sem nova assinatura | HTTP 403; erro MCP `-32002`, `insufficient_scope` | `7f85a14b-d9b1-4661-94a5-27202452d21e` |
| Runtime sem assinatura IAM | HTTP 403 | `92a7296c-1abc-4736-87f0-54e54e48c353` |
| Invocação da ferramenta MCP no Runtime | Identidade da role de execução, diferente da identidade do participante | `42d002fd-2fde-4d10-800e-90570b99ec20` |
| STS consultado pelo servidor MCP dentro do Runtime | Role `santander-6825d3096100-runtime` | `047d231d-6753-4ee4-a988-3b345cb8537f` |

Na aula 02, os dois logins tiveram assinatura, issuer, expiração e audiência
verificados com JWKS antes dos testes negativos. O `sub` permaneceu igual e
`aud` mudou entre aplicações. Após as negativas, o token da aplicação aceita
invocou novamente a Lambda com sucesso.

O teste inicial da aula 02 esperava HTTP 401 e foi corrigido após observar
HTTP 403 na AWS. A verificação exige o erro MCP de autorização e o Request ID;
erros de rede ou de serviço não contam como uma negativa de autorização.

A aula 03 criou seu bucket, enviou um ZIP ARM64 de aproximadamente 27 MB,
criou a role e o Runtime e invocou o código por IAM/SigV4. O marcador do bucket
foi conferido por leitura autenticada e recusado em acesso anônimo antes do
upload do código. O hash do objeto S3 foi comparado ao ZIP.

Na primeira execução, `StopRuntimeSession` informou que a sessão não existia
ou já havia terminado. A célula passou a registrar essa ausência separadamente
de uma exclusão bem-sucedida; outras negativas continuam interrompendo a aula.
A reexecução completa passou e configurou sete dias de retenção no grupo de
logs criado pelo Runtime.

## Limites do teste histórico de 03/11/2026

* As aulas 04 e 05 foram convertidas e testadas com contratos SDK e o avaliador
  Cedar. Não foram executadas na AWS: o VS Code perdeu a conexão, e seu endereço
  passou a retornar `ENOTFOUND` antes do envio da aula 04. Consultas DNS a
  GitHub e AWS Documentation resolveram normalmente. A retomada depende de
  um ambiente AWS acessível.
* A aula 01 precisou das correções Cognito e Lambda autorizadas e da retomada
  após propagação IAM. Seu sucesso não prova uma execução sem interrupções
  em qualquer conta AWS.
* As reexecuções usaram os identificadores persistidos e conferiram os recursos
  criados. Não foi feita uma segunda implantação do zero em outra conta.
* Os recursos permanecem na AWS para as próximas aulas. A limpeza 99 ainda
  precisa de teste real antes do aceite completo.
* Nenhum token, senha ou credencial integra este relatório.
