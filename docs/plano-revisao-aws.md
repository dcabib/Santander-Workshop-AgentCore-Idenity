# Plano de revisão: workshop executado na AWS

Data: 03/11/2026. Base do projeto: `5cc367e`.

Este documento orienta a implementação solicitada. A investigação consultou o
código, os 17 notebooks, exemplos oficiais e APIs de leitura da AWS. O usuário
confirmou o ambiente e o escopo abaixo; a implementação está em andamento.

## Resultado esperado

A jornada utiliza recursos implantados na AWS desde o primeiro exercício.
Agentes e servidores MCP executam em AgentCore Runtime; ferramentas usam
Lambda ou Runtime; identidade, autorização, catálogo, armazenamento,
recuperação, memória e inferência usam seus serviços gerenciados.

Cognito é o provedor de identidade padrão quando não há Microsoft Entra ID.
Cada exercício de identidade explica a configuração correspondente no Entra e
as diferenças de protocolo. O pipeline implementa Cognito. Usar Entra exige adaptar o IaC e validar
o fluxo específico; uma falha de autenticação nunca ativa outro caminho.

Os notebooks ensinam os serviços: mostram código, contratos, recursos IaC,
permissões, chamadas, resultados esperados e evidências observadas.

Execução integral na AWS: CodeBuild executa os notebooks e publica evidências
em S3 privado. Projeto, roles e armazenamento pertencem ao IaC. Para uso
interativo, os mesmos notebooks podem ser abertos em um ambiente Jupyter AWS.
Os serviços do workshop não dependem de processos no computador do participante.

## Diagnóstico verificado

| Área | Situação encontrada | Trabalho necessário |
|---|---|---|
| Jornada e CLI | README apresenta AWS como opcional; `demo` e `matrix` instanciam `Workshop` em memória | Uma única jornada AWS, com preflight e invocação dos recursos implantados |
| Notebooks 00–06, 08, 10 e 13 | `WORKSHOP_MODE` assume `local`; algumas provas continuam simuladas mesmo com AWS selecionada | Reescrever os exercícios e seus geradores com resultados obtidos dos serviços |
| Notebook 07 | Ciclo de personas começa em `LocalLifecycle`; tem um pipeline AWS próprio | Ensinar e observar as transições reais no Registry, via IaC |
| Notebook 09 | Runtime, Gateway, Identity e Cognito já possuem Terraform; execução AWS é desativada inicialmente | Aproveitar o fluxo real, remover a alternativa simulada e integrar à jornada |
| Notebooks 11, 12 e 14 | Dependem de configurações externas; o agente do 12 executa no kernel | Provisionar os pré-requisitos escolhidos e hospedar os agentes no Runtime |
| Notebook 15 | `KnowledgeLab` armazena documentos e memória em dicionários | Implementar ingestão, revogação, exclusão e memória em serviços AWS |
| Notebook 16 | Já tem IaC Cognito/KB/Gateway/Policy, mas começa com `LocalCognitoRagLab` | Usar apenas os recursos implantados e executar a geração de resposta no Runtime |
| Identidade | Parte da solução exige `tid`, `oid`, `azp`, Entra e Graph | Definir contratos explícitos para JWT Cognito e Entra, sem fabricar claims Microsoft |
| Registry | O laboratório 07 usa `agent-registry`; outros cenários usam o namespace antigo | Migrar clientes, schemas, IAM, ARNs, providers e templates |
| Validação | `verify_notebooks.py` força execução offline; auditoria AWS atende apenas RAG, Terraform e Registry | Uma suíte AWS cobrindo todos os notebooks e suas dependências |

O perfil `default` respondeu ao STS para a conta `496714466045`. A configuração
existente usa `us-east-1`. Foram observados nove stacks do projeto em estados
`CREATE_COMPLETE`/`UPDATE_COMPLETE`, relativos a Registry e RAG, e os Runtimes
`santander_tf_lab_agent` e `registry_personas` em `READY`. Isso confirma a
existência dos recursos, mas não comprova funcionamento ponta a ponta.

## Decisões confirmadas e entradas pendentes

1. Usar a configuração AWS existente: perfil `default`, conta `496714466045`,
   região `us-east-1`.
2. Manter múltiplas contas reais, usando `containers`, `cognito` e `serverless`;
   não haverá adaptação que represente uma única conta como isolamento entre contas.
3. Atualização solicitada pelo usuário: simular o workspace Databricks. O
   simulador será um serviço implantado na AWS, com dados sintéticos e
   autorização. Seus resultados não comprovam Databricks ou Unity Catalog reais.

Mapeamento adotado: `default` para plataforma; `containers` para Retail e origem
dos agentes nos cenários A → C → B; `cognito` para Transaction e fonte de dados;
`serverless` para Lending. O STS confirmou `containers=634124031262` e
`serverless=593273567455`, `cognito=008168963523`. Os quatro perfis foram
verificados via STS. O usuário substituiu explicitamente o perfil `dynamodb`
por `cognito`.

Todos os componentes do exercício, inclusive o simulador da fonte, executarão
na AWS. Uma integração futura com Databricks real terá configuração e evidências
próprias, sem reutilizar o status de aceite do simulador.

## Ordem de implementação

### 1. Base AWS e configuração do ambiente

Inventariar os recursos pertencentes ao projeto e seus respectivos stacks/state.
Preservar as configurações existentes e criar uma migração explícita para os
novos arquivos de ambiente, sem registrar credenciais no Git.

Definir um manifesto de laboratórios com dependências, recursos, parâmetros,
outputs e verificações. Usar outputs reais de CloudFormation/Terraform para
conectar os módulos; eliminar o preenchimento manual repetido de identificadores.
O preflight verifica conta, região, credenciais, serviços, permissões,
modelos e prontidão antes de executar o exercício.

Implementar no IaC o ambiente de notebooks e execução automatizada na AWS.
Credenciais de execução vêm de roles IAM. Artefatos e relatórios usam buckets
privados; o backend Terraform remoto terá criptografia e controle de concorrência.

Reutilizar os wrappers CloudFormation e Terraform existentes, ajustando-os para
a nova sequência. Builds, planos, aplicação, espera e inspeção de outputs serão
etapas visíveis. Não introduzir um segundo mecanismo que administre os mesmos
recursos fora desses wrappers.

### 2. Cognito e AgentCore Identity

Provisionar pools, usuários sintéticos, grupos, app clients, scopes, segredos e
credential providers pelo IaC. Distinguir login de pessoa, identidade de
aplicação, workload identity e autorização.

Validar assinatura, emissor, destinatário, validade, cliente, scopes e
`token_use` conforme o contrato de cada token. Vincular a identidade humana e a
aplicação autenticadas à decisão do backend; campos enviados pelo modelo não
estabelecem essas identidades.

O material explicará este mapeamento:

| Conceito | Cognito | Microsoft Entra ID |
|---|---|---|
| Emissor e chaves | User Pool, discovery URL e JWKS | Tenant, discovery URL e JWKS |
| Pessoa | `iss` + `sub` | `tid` + `oid`, conforme o token |
| Aplicação | App client; `client_id` ou `aud`, conforme o tipo de token | App registration; `azp`/`appid` e `aud`, conforme a versão |
| Permissão | Grupos/scopes e regras de autorização | Grupos/app roles/scopes e regras de autorização |
| M2M | `client_credentials` via Identity quando aplicável | `client_credentials` com app registration |
| Delegação ao destino | Fluxo OAuth suportado pelo provedor e contexto autenticado, com fronteiras documentadas | OBO específico do Entra quando a API de destino exige essa troca |

O endpoint de tokens do Cognito documenta `authorization_code`, `refresh_token`
e `client_credentials`. Não tratar M2M como OBO nem descrever uma chamada
Cognito como prova de Microsoft Graph `/me`. O exercício padrão consultará um
backend AWS que verifica o contexto autenticado. A explicação Entra mostrará
os consentimentos, scopes e trocas adicionais necessários.

### 3. Runtime, Gateway e Policy

Implantar desde os fundamentos um agente e um MCP no Runtime, ferramenta Lambda,
Gateway, Identity, engine Policy em `ENFORCE` e logs. Adaptar o fluxo Terraform
existente e os templates CloudFormation sem atribuir o mesmo recurso aos dois.

Reescrever os laboratórios 00–05 para executar chamadas reais: descoberta MCP,
invocação, identidade humana/aplicação, regras Cedar, geração de rascunho e
publicação pelo IaC. Mostrar como um mesmo usuário pode receber decisões
diferentes conforme o agente autenticado.

As negativas precisam vir da fronteira ensinada. Uma rejeição de rede ou
credencial não comprova uma regra Cedar. Correlacionar a decisão do Gateway/Policy
e os registros de execução do backend para demonstrar se a ferramenta executou.

### 4. Registry e composição

Usar `agent-registry-control` e `agent-registry` em toda a solução. Atualizar
schemas de registros e descoberta, IAM, ARNs e custom resources conforme a API
atual. Inspecionar a propriedade dos recursos existentes antes de qualquer
migração; reconciliação e criação passam pelo IaC.

Os laboratórios 06–08 mostrarão criação, publicação, submissão, revisão, decisão,
descoberta e consumo reais, com permissões distintas por persona. Aprovação de
catálogo não concede invocação automaticamente.

As transições do catálogo são gerenciadas por fases IaC revisáveis. O notebook
mostra o descriptor, o código do provider e os parâmetros da fase, além de
consultar o estado resultante no serviço.

Depois, implantar os cenários 10–14 conforme as decisões de contas e fonte de
dados. Todos os agentes ficam no Runtime, inclusive o laboratório 12. Identidade
e permissões são verificadas em cada fronteira; os relatórios identificam as
contas efetivamente envolvidas.

### 5. Ingestão, memória e RAG

Substituir o laboratório 15 por S3, ingestão em Bedrock Knowledge Bases e
AgentCore Memory. O fluxo deve demonstrar inclusão, atualização, revogação,
exclusão e reingestão, aguardando a propagação antes de conferir o resultado.
Os documentos e ACLs de exercício serão geridos por fases do IaC.

A memória usará o principal autenticado para estabelecer actor/session e
guardar referências que são reautorizadas antes de recuperar conteúdo.
Não persistir na memória respostas ou trechos restritos que possam reaparecer
após uma revogação. Demonstrar isolamento entre pessoas e revalidação do acesso.

Adaptar o laboratório 16 para usar Cognito, Identity, Gateway, Policy, KB e
Bedrock desde a primeira chamada. Hospedar a orquestração RAG no Runtime.
Preservar a matriz A/B/C/D, a tentativa de falsificar o usuário e a negativa de
retrieval direto. Examinar os documentos e o contexto efetivamente recebido pelo
modelo, com citações verificáveis.

### 6. Reescrita didática dos 17 notebooks

Atualizar as fontes em `scripts/generate_*notebook*.py`,
`scripts/generate_notebooks.py`, `scripts/notebook_learning.py` e os geradores de
diagramas antes de regenerar os notebooks. Reescrever README, preparação,
jornada, deploy, conceitos, validação e limpeza para o mesmo fluxo.

Cada etapa terá:

1. Objetivo e explicação do serviço AWS utilizado.
2. Diagrama e fronteira de identidade/permissão relevante.
3. Código do agente, ferramenta ou integração, com explicação dos parâmetros.
4. Recursos IaC e permissões que materializam o exemplo.
5. Plano e aplicação pelo wrapper do projeto, com outputs reais.
6. Código de chamada ao serviço e resultado esperado.
7. Testes de sucesso e negativas, com observado × esperado × PASS/FAIL.
8. Logs, diagnóstico e limpeza pelo IaC.

Helpers continuarão úteis para repetição, mas as partes que ensinam o serviço
aparecerão no notebook. Exemplo: o laboratório de Gateway mostra o handler
Lambda, o schema MCP, o authorizer, as regras Cedar e o código de chamada; não
se resume a executar uma função que imprime `PASS`.

Remover `WORKSHOP_MODE`, a alternativa `local`, simuladores usados pela jornada,
flags que desativam o caminho AWS e mensagens que aprovam simulações. Eliminar
fallback para dados, modelos, políticas, catálogo ou memória em processo.
Fixtures de testes internos não serão uma modalidade executável do workshop.

Não fazer substituição cega da palavra `local`: `local.*` é também sintaxe
Terraform e termos como política de uma conta podem descrever recursos reais.

### 7. Deploy e validação de ponta a ponta

Executar verificações de código, IaC e geração dos notebooks; depois aplicar os
stacks na ordem do manifesto e executar os laboratórios em kernels novos na AWS.
Repetir a jornada para conferir reexecução, idempotência e propagação dos serviços.

Expandir a auditoria para cobrir:

| Grupo | Prova exigida na AWS |
|---|---|
| 00–01 | Credenciais válidas, recursos prontos, MCP initialize/list/call e execução do backend |
| 02–03 | Login Cognito, JWT válido, workload identity, autenticação outbound e diferença de permissão por pessoa/aplicação |
| 04–05 | ALLOW/DENY nativos, rascunho gerado pelo serviço, revisão/publicação pelo IaC e negativa sem execução da ferramenta |
| 06–08 | Estados reais do Registry, descoberta, invocação autorizada e descoberta sem permissão de invocação |
| 09 | Deploy Terraform, Runtime → Identity → Gateway → Lambda, uso da ferramenta pelo modelo e plano sem mudanças inesperadas |
| 10–12 | Chamadas reais entre os domínios/contas escolhidos e negativas em cada Gateway |
| 13–14 | Fonte escolhida, principal reconhecido, restrição de dados e correlação até a consulta |
| 15 | Ingestão, alteração de ACL, exclusão, isolamento de memória e revogação respeitada após propagação |
| 16 | Matriz A/B/C/D, falsificação negada, acesso direto negado, trechos/citações autorizados e modelo real |

Além disso, testar chamadas sem autenticação, tokens inválidos, cliente/audiência
inadequados e scopes insuficientes onde esses controles se aplicam.

O relatório de aceite conterá versão do código, conta/região, recursos, horário,
request/trace/query IDs, esperado, observado e resultado. Não conterá tokens ou
senhas. Falta de configuração, `NOT_RUN`, timeout e evidência incompleta impedem
o aceite do laboratório obrigatório.

Validar drift e o plano de limpeza por IaC. Não remover automaticamente o
ambiente operacional que será utilizado no workshop.

## Critérios de conclusão

Todos os laboratórios obrigatórios definidos no escopo precisam estar
implantados e aprovados na AWS. Nenhuma etapa da jornada pode recorrer a
simulação como alternativa ou resultado de sucesso.

O Cognito precisa permitir percorrer a jornada sem tenant Entra. A explicação
Entra deve ser tecnicamente correta e identificar o que exige um ambiente
Microsoft para ser executado.

Infraestrutura e dados de preparação pertencem ao pipeline IaC. Diante de falha,
diagnosticar por leitura e corrigir a fonte do IaC. Qualquer mutação de recursos
fora desse caminho exige aprovação explícita, conforme a regra do projeto.

## Referências consultadas

- [Workshops oficiais AgentCore](https://github.com/awslabs/agentcore-samples/tree/main/06-workshops).
- [Gateway: Lambda como ferramenta MCP com Cognito](https://github.com/awslabs/agentcore-samples/blob/main/06-workshops/02-AgentCore-gateway/01-transform-lambda-into-mcp-tools/01-gateway-target-lambda-oauth.ipynb).
- [Identity: autenticação de entrada com Cognito](https://github.com/awslabs/agentcore-samples/blob/main/06-workshops/03-AgentCore-identity/03-Inbound%20Auth%20example/inbound_auth_runtime_with_strands_and_bedrock_models.ipynb).
- [Runtime, Memory e isolamento por identidade](https://github.com/awslabs/agentcore-samples/blob/main/06-workshops/04-AgentCore-memory/03-advanced-patterns/03-memory-identity-runtime-integration/runtime_memory_identity_integration.ipynb).
- [Policy: autoria em linguagem natural](https://github.com/awslabs/agentcore-samples/blob/main/06-workshops/08-AgentCore-policy/02-Natural-Language-Policy-Authoring/NL-Authoring-Policy.ipynb).
- [Registry: sequência por personas](https://github.com/awslabs/agentcore-samples/tree/main/06-workshops/10-Agent-Registry/00-getting-started/step-by-step).
- [Cognito: grants do endpoint de tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/token-endpoint.html).
- [AgentCore Identity: troca de tokens OBO](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html).
- [Registry: migração obrigatória de namespace e schemas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/registry-faq.html).

Os exemplos oficiais são referências de funcionamento e didática. Alguns ainda
incluem SDKs antigos, criação avulsa de recursos ou experimentos no computador.
A adaptação seguirá as APIs atuais e os requisitos deste projeto: implantação
por IaC e execução dos cenários na AWS.

## Andamento da revisão

- Backend recuperado pelo pipeline após aprovação explícita: `CREATE_COMPLETE`.
- Bootstrap, Cognito, Gateway e agente da plataforma implantados; agente atualizado.
- Bloqueio observado em `bindings`: a API rejeita `JWT_PASSTHROUGH` para target MCP
  com HTTP 400. O stack novo terminou em `ROLLBACK_COMPLETE`.
- Correção aprovada e Gateway atualizado: interceptor REQUEST valida e encaminha
  Authorization aos destinos declarados, conforme documentação AWS. JWT, Cedar
  ENFORCE, workload permitido e ACL da fonte continuam exigidos.
- Recuperação de `bindings` autorizada pelo usuário (alternativa A): o target
  MCP chegou a `CREATE_COMPLETE`. A criação das cinco políticas falhou com HTTP
  400: `expected single entity uid or template slot, found set of entity uids`.
  O CloudFormation iniciou outro rollback. Nenhuma mutação avulsa foi realizada.
- Segunda correção preparada: `principal is AgentCore::OAuthUser` no escopo e
  conjunto explícito de pessoas com `.contains(principal)` no `when`. Preserva
  emissor, audiência, pessoa, ferramenta e limites. Parser Cedar, verificação de
  tipos conforme schemas MCP, 216 testes de regressão e cfn-lint passaram.
  O gerador passa a rejeitar sintaxe Cedar inválida antes de gravar templates.
- Nova recuperação de `bindings` autorizada (A) e concluída: `CREATE_COMPLETE`.
- Teste real: preflight, autenticação, descoberta MCP e consulta Lambda passaram.
  O Runtime MCP negou a autenticação: `Transaction token required: authorizer has
  AllowedWorkloadConfiguration configured`. A Policy do Gateway registrou ALLOW.
- Alternativa IAM aprovada pelo usuário e implantada: resource policy restringe
  Runtime à role do Gateway; SigV4 autentica o workload e o backend verifica
  o JWT humano em header separado. Ver [decisão de autenticação MCP](decisao-autenticacao-mcp.md).
- Gateway, backend e bindings em UPDATE_COMPLETE. O teste AWS do core passou:
  acesso anônimo negado, invocação direta IAM negada, consultas pelo Gateway,
  identidade humana verificada na fonte e isolamento do AgentCore Memory.
  Evidências em `evidence/workshop-core.json`.
- As 17 aulas, geradores, CLI, guias e diagramas foram adaptados à jornada AWS.
  Verificação estática não foi registrada como aceite operacional.
- State Terraform migrado pelo wrapper para S3 privado/versionado/criptografado,
  com locking S3. O plano confirmou `drift: NONE`.
- Bootstrap, Gateway, backend e bindings dos três domínios implantados. Os
  testes individuais passaram nas quatro contas, incluindo negativa IAM direta,
  identidade humana na fonte e isolamento de Memory.
- Runner CodeBuild implantado. Aulas 00 e 01 passaram em AWS_EXECUTION no build
  `e8beb579-394d-432b-baa1-3b7aa3fafd0a`. A aula 02 parou antes da inferência
  por falta de GetWorkloadIdentity no diretório default.
- Agente RAG implantado; execução ponta a ponta ainda pendente.
- Correções de permissões aprovadas (alternativa A) e aplicadas: policy-draft
  em CREATE_COMPLETE e runner em UPDATE_COMPLETE. Aulas 00–05 passaram em
  AWS_EXECUTION no build `78e540fe-165c-4d61-a905-01f57e1f417b`, conforme
  [decisão de permissões](decisao-permissoes-runner-rascunho.md).
- Ciclo da aula 15 implementado em cinco fases IaC, com atualização, revogação,
  exclusão e reingestão, reusando a referência do Memory e consultando a KB via
  Gateway. Execução das fases na AWS ainda pendente.
- Federação, dois agentes da origem e três observers em CREATE_COMPLETE.
  As personas do Registry aceitam a role do runner por atualização do IaC.
- As capacidades de Riscos e Fraude foram publicadas, submetidas e aprovadas em
  stacks próprios. A revisão conferiu descriptors/digests e os authorizers
  reais dos Runtimes; os registros dos fundamentos foram preservados.
- Build `675ffc8a-0c38-4237-9153-4760b31159f2`: 16 aulas (00–14 e 16)
  passaram em AWS_EXECUTION. Inclui logs nativos de Policy/backend, comparação
  das políticas ativas com IaC, execução das capacidades descobertas, negativas
  de audiência, RAG com contexto/citações/cobertura e decisões nativas.
- Última validação: 599 testes passaram, cfn-lint passou e 17 notebooks válidos
  estaticamente. O aceite estático permanece distinto da execução AWS.
- As cinco fases da aula 15 passaram com a mesma sessão de Memory. O job
  nativo confirmou exatamente um documento excluído e zero falhas; a referência
  antiga recuperou a versão 3 após reingestão. A restauração de baseline passou
  no build `fb6554ca-5735-406e-a0ca-28c92788952b`.
- Planos de limpeza somente leitura de 39 stacks confirmaram templates iguais
  às fontes IaC, sem bloqueios. Terraform confirmou `drift: NONE`.
- Rodada final `8d38b903-937c-4ed5-9b81-a99a57f6bc88` concluída com as 17 aulas
  em PASS/AWS_EXECUTION. Auditoria MATCH: hashes correspondentes, 89 células
  executadas e nenhuma saída de erro. Baseline confirmado nos dois stacks de
  dados. Ver [relatório de aceite AWS](aceite-aws.md).

Referência adicional: [propagação de Authorization pelo interceptor](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-headers.html#gateway-headers-interceptor-propagation).

### Revisão dos pré-requisitos após o aceite

A [matriz de contas](contas-e-elegibilidade.md) explicita que 10–14 exigem
quatro contas no manifesto/IaC atuais. A aula 14 percorre três contas, mas
depende da federação completa. Os fundamentos 00–09 e 15–16 não exigem
fronteiras entre contas; seus stacks e integrações continuam obrigatórios.
O runner completo mantém a exigência de quatro contas mesmo com `--labs`.

README, guias, notebooks e diagramas mostram esses limites antes da execução.
O planejamento lista bloqueios por aula sem chamar AWS. A execução confere
toda a seleção antes do primeiro kernel e antes de iniciar CodeBuild.
Contas ausentes/repetidas bloqueiam a seleção e não produzem PASS.

Validação desta revisão: 614 testes passaram, Ruff passou e os 17 notebooks
passaram na validação estática. Esta revisão não fez deploy nem nova execução
de aulas na AWS; o aceite operacional acima pertence ao pacote histórico
identificado pelo build. A nova fonte do runner precisa ser publicada pelo
pipeline para executar esses novos notebooks na AWS.
