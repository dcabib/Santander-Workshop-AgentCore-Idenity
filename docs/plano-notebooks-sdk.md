# Correção da jornada: construir a solução dentro dos notebooks

## Requisito

Os participantes devem criar, configurar e testar os recursos AWS durante
a execução das aulas. Não haverá criação por CloudFormation nem implantação
prévia escondida em `setup.sh`, scripts, CLI ou runner.

Esta decisão substitui o desenho de pré-deploy descrito nos planos anteriores.
**Este documento é um plano; a migração e o aceite operacional ainda não foram
concluídos.** As aulas 10–14 ainda contêm dependências de stacks.

## Referências conferidas

Fonte: `awslabs/agentcore-samples/06-workshops`, commit
`7282ec3b839736d55d199f4c726136c342e33b3c`.

* [Gateway com Lambda e Cognito](https://github.com/awslabs/agentcore-samples/blob/7282ec3b839736d55d199f4c726136c342e33b3c/06-workshops/02-AgentCore-gateway/01-transform-lambda-into-mcp-tools/01-gateway-target-lambda-oauth.ipynb):
  cria autenticação, Gateway e target; depois obtém o token, chama as ferramentas
  e apresenta a limpeza.
* [Policy](https://github.com/awslabs/agentcore-samples/blob/7282ec3b839736d55d199f4c726136c342e33b3c/06-workshops/08-AgentCore-policy/01-Getting-Started/AgentCore-Policy-Demo.ipynb):
  cria o Policy Engine, aguarda a ativação, associa ao Gateway, cria a política
  e testa cenários permitidos e negados.
* [Registry](https://github.com/awslabs/agentcore-samples/blob/7282ec3b839736d55d199f4c726136c342e33b3c/06-workshops/10-Agent-Registry/00-getting-started/step-by-step/02-creating-registry-workflow.ipynb):
  cria, consulta, atualiza e apresenta a exclusão do Registry.
* [Jornada integrada](https://github.com/awslabs/agentcore-samples/tree/7282ec3b839736d55d199f4c726136c342e33b3c/06-workshops/09-AgentCore-E2E/strands-agents):
  constrói os componentes progressivamente e reserva uma aula para limpeza.

Seguir a sequência didática não significa copiar opções incompatíveis com
este workshop. Não haverá execução de agentes fora da AWS. APIs e parâmetros
serão conferidos contra a versão instalada do SDK. Erros de validação de
políticas não serão ignorados para fazer uma aula passar.

## Formato de cada etapa

1. Explicar o serviço, o recurso e sua relação com a arquitetura.
2. Mostrar os parâmetros, permissões e código da chamada AWS na célula.
3. Executar a criação pelo SDK na própria aula.
4. Exibir identificadores e estado, sem senhas, credenciais ou tokens.
5. Aguardar disponibilidade com prazo e tratamento explícito de falhas.
6. Usar o recurso, verificar o resultado e explicar o que foi observado.
7. Mostrar as chamadas de limpeza e as dependências que impedem a remoção.

Helpers podem tratar estado, espera e formatação. As operações centrais de
criação e configuração do serviço devem permanecer legíveis nas células.
Chamar um script que implanta toda a solução não satisfaz esse requisito.

## Ordem da correção

1. **Entrada e preparação:** `setup.sh` prepara dependências e kernel. A aula
   00 consulta STS, identifica conta e região, apresenta as permissões e inicia
   o registro de identificadores. Não exige `config/aws.workshop.json`, stacks
   nem recursos de AgentCore previamente criados.
2. **Gateway e identidade:** criar nas aulas os recursos IAM, Cognito, Lambda,
   Gateway e targets necessários à demonstração. Mostrar cada relação entre
   role, authorizer, target e chamada MCP.
3. **Runtime e delegação:** mostrar o código do servidor/agente, preparar o
   artefato, criar o Runtime na AWS, aguardar e invocar. Explicar a diferença
   entre identidade da pessoa e identidade do workload.
4. **Policy:** criar e associar o engine e as políticas nas aulas, com testes
   de autorização. A geração de um rascunho não representa aprovação automática.
5. **Registry:** criar personas, Registry e registros ao longo das aulas de
   governança, publicação, aprovação, descoberta e execução.
6. **Integrações:** construir memória, fonte sintética e RAG nas respectivas
   aulas. O simulador Databricks executa na AWS e é identificado como simulador.
   Terraform deixa de ser pré-requisito do restante da jornada.
7. **Múltiplas contas:** declarar as contas e credenciais necessárias antes
   das primeiras mutações de cada cenário. Recursos são construídos pela aula;
   contas AWS e autorização de acesso não são criadas ou presumidas pelo notebook.
8. **Limpeza:** apresentar uma sequência executável que remove somente os
   recursos pertencentes à execução registrada, respeitando as dependências.
9. **Retirada do caminho antigo:** remover as dependências de `DescribeStacks`,
   outputs CloudFormation, pré-deploy e CodeBuild obrigatório dos notebooks,
   clientes, verificadores e instruções de início.
10. **Aceite:** executar na AWS a jornada de conta única desde o estado inicial,
    reiniciar o kernel para verificar a retomada e validar a limpeza. Testar os
    cenários de múltiplas contas apenas quando suas contas estiverem disponíveis.

## Estado e independência do ambiente

O código usa credenciais AWS autorizadas da sessão e a região configurada.
Não depende de nome de role do evento, caminho `/home/participant`, domínio
CloudFront, bucket prévio, perfil pessoal ou ID de conta fixo.

O registro gerado durante a aula contém identificadores e referências, nunca
segredos. É vinculado à conta, região e execução. Reexecutar uma célula não pode
adotar silenciosamente recursos de outra execução nem sobrescrever recursos
externos. Uma aula deve informar qual etapa anterior cria um recurso ausente.

Cognito é o provedor executável padrão. O texto explica os pontos semelhantes
e as diferenças para Entra ID, inclusive claims, consentimentos e OBO.

## Permissões e recursos existentes

Criar recursos durante o notebook continua exigindo permissões AWS. Uma conta
com restrições explícitas não será apresentada como suportada sem validação.
A autorização para o fluxo de criação dos notebooks não autoriza contornar
guardrails ou editar a infraestrutura externa do evento.

Os stacks de tentativas anteriores não serão alterados ou excluídos durante
a revisão do código. A limpeza desse legado é uma ação distinta da limpeza
dos recursos criados pelos novos notebooks.

## Critérios de conclusão

* Um clone sem arquivos de configuração privados consegue iniciar a aula 00.
* Nenhuma aula exige pré-deploy ou usa CloudFormation para criar ou descobrir
  seus recursos.
* As células mostram criação, configuração e validação dos serviços ensinados.
* Serviços, ferramentas, agentes e inferência executam na AWS.
* Os testes comprovam sucesso e negativas de acesso pelos serviços AWS.
* Requisitos de contas, região, modelo e permissões aparecem antes de seu uso.
* Evidências identificam a versão efetivamente executada; análise estática ou
  testes unitários não substituem o aceite na AWS.

## Progresso em 03/11/2026

* Aula 00 convertida e executada com sucesso no VS Code da AWS em `us-west-2`,
  sem arquivo de configuração recebido do instrutor nem consulta a stacks.
* Aula 01 convertida: criação explícita de Cognito, IAM, logs, Lambda, Gateway
  e target, seguida de autenticação e chamada MCP. As alternativas
  [Cognito](decisao-cognito-notebook-sdk.md) e
  [Lambda](decisao-lambda-notebook-sdk.md) foram aprovadas e aplicadas.
  A Lambda está ativa e o Gateway READY. Chamadas sem token e com JWT inválido
  retornaram HTTP 401, com IDs de requisição AWS.
* A [retomada após AssumeRole](decisao-propagacao-iam-gateway-sdk.md) foi
  autorizada e passou. Target READY, login Cognito e invocação MCP na Lambda
  comprovados na AWS, mantendo as permissões.
* Aula 02 convertida e testada na AWS: outra aplicação Cognito, comparação de
  `sub` e `aud`, verificação criptográfica, negativas com HTTP 403 e erro MCP
  de autorização e chamada permitida.
* Aula 03 convertida e testada na AWS: bucket privado, artefato ARM64 com
  dependências do lockfile, role e Runtime MCP criados nas células.
  A invocação retornou a identidade IAM do workload e Request IDs do Runtime
  e STS. A entrada anônima foi negada e os logs receberam retenção de sete dias.
* Aula 04 convertida: criação do engine, permissão IAM delimitada, associação
  ENFORCE e política Cedar estrita, com chamadas permitidas e negadas. Os
  testes de contrato e do avaliador Cedar passaram. O teste AWS está pendente:
  o endereço do VS Code deixou de resolver no DNS antes da execução.
* Aula 05 convertida: StartPolicyGeneration, leitura dos assets/findings,
  testes da intenção e criação estrita do rascunho em LOG_ONLY. A política
  manual continua ACTIVE. Testes verificam retomada, rejeição de findings
  e rascunhos excessivamente permissivos. Ainda não executada na AWS.
* Aula 99 preparada para limpar somente os recursos registrados das aulas
  01–05, com conferência de propriedade, hashes e dependências antes das
  exclusões. Testada com contratos SDK; ainda não executada na AWS.
* Passaram 65 testes focados nos notebooks SDK e no estado, e 701 testes na
  suíte completa. O lint e a validação dos 18 notebooks também passaram.
  O [aceite AWS parcial](aceite-notebooks-sdk.md)
  registra as versões efetivamente executadas e seus Request IDs.
* Aulas 06–16, verificadores de execução e remoção das dependências antigas
  ainda pendentes. O desenvolvimento permanece em `main`.

## Contas efêmeras — 04/11/2026

* A conta usada no aceite anterior foi encerrada, conforme informado pelo
  usuário. Suas evidências permanecem históricas; seus recursos e identificadores
  não são pré-requisitos de uma nova execução.
* O [roteiro de contas efêmeras](contas-efemeras.md) descreve preparação na AWS,
  obtenção do código, sessão, sequência SDK, retomada, evidências e limpeza.
* O estado diferencia execução ativa de execução limpa. A próxima aula 00
  arquiva uma execução limpa e cria novos nomes; execuções ainda ativas não
  podem ser descartadas para iniciar outra.
* O executor `scripts/run_sdk_notebooks.py` usa os próprios notebooks, exige
  conta esperada, interrompe em erro e não usa o verificador legado baseado
  em stacks. Credenciais temporárias e JWTs são removidos das saídas persistidas.
* Passaram 714 testes da suíte completa, lint e validação dos 18 notebooks.
  A execução do novo executor com `--validate-only` foi registrada como
  `STATIC_ONLY`, sem representar aceite AWS.
* O usuário disponibilizou o Code Editor operacional após a falha inicial.
  A execução foi retomada nele, usando a role da própria instância.
* As aulas 00–06 passaram na conta nova, começando sem recursos do workshop.
  A aula 05 foi corrigida para ler `definition.policy` e submeter o texto ao
  parser Cedar e aos contraexemplos antes de criar a política em `LOG_ONLY`.
* A aula 06 agora cria o Registry com aprovação manual e descoberta IAM.
  Foram comprovados READY, descoberta autenticada e negativa anônima.
* Passaram 725 testes, lint e validação de sintaxe/formato dos 18 notebooks.
  Os testes não substituem o aceite AWS, que registra hashes e Request IDs.
* A limpeza SDK 99 passou para 00–06, fechou a execução e arquivou 26 referências
  liberadas. A reconstrução 00–06 passou com novos IDs, incluindo nova geração.
* A aula 07 criou as quatro personas, mas a sessão do editor não permite
  SimulatePrincipalPolicy nem assumir nossas roles. O diagnóstico com a sessão
  fornecida confirmou as 16 decisões IAM, sem representar aceite do notebook.
  A [alternativa A](decisao-personas-conta-efemera.md) foi posteriormente
  aprovada e executada; nenhuma permissão do editor foi alterada.
* Passaram 734 testes, incluindo entrada oculta de credenciais e limpeza
  das personas por contrato SDK.
* A limpeza com personas concluiu `212b89261d98`, com 30 referências liberadas.
  Foi adicionada espera pela confirmação de agendamento do Secrets Manager,
  após observar consistência eventual na leitura. A falha e a retomada foram
  preservadas como evidência.
* O novo ciclo `41faf1babbbf` passou em 00–07 com a sessão `WSOpsRole`, recebida
  por entrada oculta. As 16 simulações IAM da aula 07 passaram no kernel AWS.
* A aula 08 foi convertida para publicar, submeter, aprovar, descobrir e invocar
  MCP com as personas. A limpeza foi ampliada para conferir o hash do registro
  antes de removê-lo. Seu aceite AWS passou: Publisher não aprovou; Approver
  aprovou; Consumer descobriu e invocou; sessão restrita à descoberta não invocou.
* A aula 09 foi renomeada e convertida para integração Runtime MCP–Gateway.
  As células criaram a permissão IAM, o target MCP e o permit Cedar. O teste
  AWS passou com ALLOW do analista e DENY do auditor.
* A aula 15 foi convertida para Memory de curto prazo, actor condicionado
  por IAM e uma visão sintética de dados por pessoa no DynamoDB. O evento
  guarda referência; revogar a linha autorizada não remove o documento
  canônico nem torna a referência um acesso permanente.
* IAM Access Analyzer validou as condições de actor e LeadingKeys sem findings,
  Request ID `1b5660a2-9323-42d7-a679-ce085b68beb3`. Os 757 testes e a
  reprodução/validação dos notebooks passaram. O teste AWS da aula 15 passou:
  isolamento de actor e partition key, referência preservada e fonte sem
  conteúdo após revogação da linha autorizada.
* As sessões dos perfis `containers`, `cognito` e `serverless` foram identificadas
  por STS em três contas distintas. Com a plataforma atual, estão disponíveis
  quatro contas para preparar os cenários; ainda não é aceite das integrações.
  As aulas 10–14 permanecem em conversão.
* A aula 16 agora cria uma KB MANAGED, corpus S3 com ACL, ingestão, conector
  nativo, permits Cedar vinculados ao sub e Runtime HTTP com Cognito. O agente
  tem Deny explícito de retrieval direto e gera somente depois de recuperar
  trechos autorizados pelo Gateway. Base, ingestão e conector passaram;
  a invocação Runtime falhou por ausência do SDK no ZIP. A
  [retomada restrita](decisao-pacote-rag-sdk.md) foi aprovada em 05/11/2026.
  A sessão retornou `ExpiredToken` na verificação STS e a conta foi encerrada
  antes da reconstrução.
* Em 05/11/2026, o usuário pediu um novo ciclo na conta `813782517426`.
  Código e kernel foram preparados em uma pasta limpa no editor AWS.
  A verificação anterior à criação identificou `AccessDenied` para
  `iam:SimulatePrincipalPolicy`; a jornada completa precisa de uma sessão
  autorizada pelo organizador, como no ciclo anterior. O usuário escolheu
  essa alternativa. A suíte no Python 3.12 revelou uma diferença na
  indentação da descrição MCP; após corrigi-la com `inspect.getdoc`,
  passaram 775 testes no editor AWS.
* A sessão fornecida para essa alternativa é `WSParticipantRole`. A leitura
  das policies confirmou a ausência de SimulatePrincipalPolicy e um Deny
  explícito de AssumeRole para as roles da jornada. A aula 00 passou,
  iniciando `a96b1de2499d` com zero recursos. A criação aguarda a
  [escolha de retomada](decisao-sessao-participante-20261105.md).

* Após a orientação de usar o ambiente existente, a revisão do workshop oficial
  identificou as três personas já permitidas pelo editor. 07–08 foram alinhadas
  a esse fluxo com testes reais; 15 usa Identity Pool com regras por sub.
  Nenhuma role do evento foi alterada. Passaram 778 testes de código, e 00–06
  passaram na conta atual com a sessão do editor. Reteste AWS restante em curso.

* 00–09 e 15 passaram no ciclo atual com a sessão do editor. A tabela da aula
  15 agora usa TableId na retomada/limpeza. A execução AWS confirmou sessões
  por Identity Pool, isolamento Memory/DynamoDB e revogação. O RAG passou,
  incluindo geração Nova Lite e ACL por pessoa. A limpeza 99 confirmou
  `CLEANED` e registro ativo vazio. A reconstrução `952f3855e8d9` passou nas
  12 aulas (00–09, 15–16), sem falhas, em 736,35 s. Passaram 793 testes de
  código e 45 testes específicos também no Python 3.12 do editor. Foram
  conferidos 194 arquivos de código, notebooks e dependências entre a pasta
  local e a cópia AWS, sem diferenças. 10–14 continuam pendentes de conversão.
