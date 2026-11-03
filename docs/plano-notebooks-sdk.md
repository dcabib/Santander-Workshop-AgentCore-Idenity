# Correção da jornada: construir a solução dentro dos notebooks

## Requisito

Os participantes devem criar, configurar e testar os recursos AWS durante
a execução das aulas. Não haverá criação por CloudFormation nem implantação
prévia escondida em `setup.sh`, scripts, CLI ou runner.

Esta decisão substitui o desenho de pré-deploy descrito nos planos anteriores.
**Este documento é um plano; a migração e o aceite operacional ainda não foram
concluídos.** As aulas 04–16 ainda contêm dependências de stacks.

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
* Aula 99 preparada para limpar somente os recursos registrados das aulas
  01–03, com conferência de propriedade, hashes e dependências antes das
  exclusões. Testada com contratos SDK; ainda não executada na AWS.
* 40 testes focados nos novos notebooks e no estado passaram. O lint e a
  validação dos 18 notebooks também passaram. O [aceite AWS parcial](aceite-notebooks-sdk.md)
  registra as versões efetivamente executadas e seus Request IDs.
* Aulas 04–16, verificadores de execução e remoção das dependências antigas
  ainda pendentes. O desenvolvimento permanece em `main`.
