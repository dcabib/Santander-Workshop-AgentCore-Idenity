# Santander — Workshop Amazon Bedrock AgentCore

**A jornada de conta única (00–09, 15–16 e limpeza 99) foi validada na AWS.
Os cenários de múltiplas contas 10–14 ainda estão em conversão.**
A nova jornada não exige CloudFormation, um runner CodeBuild ou um arquivo
privado de configuração antes do primeiro notebook.

Os notebooks explicam o serviço, mostram a criação e configuração, aguardam a
resposta da AWS e executam testes permitidos e negados. Agentes, ferramentas,
inferência, dados e memória executam na AWS. O notebook é o roteiro e o cliente
dessas APIs. Não há opção de execução dos serviços fora da AWS.

O provedor padrão é Amazon Cognito, com comparações ao Microsoft Entra ID sem
confundir os protocolos. A fonte Databricks será um **simulador com dados
sintéticos hospedado na AWS**; não representa um SQL Warehouse ou Unity Catalog
real.

As contas são **efêmeras**: cada evento começa a construção novamente, com
sessão autorizada, registro próprio e nomes exclusivos. O
[roteiro de contas efêmeras](docs/contas-efemeras.md) cobre preparação na AWS,
execução das células, retomada, evidências e limpeza. O código não depende
do domínio ou da role do Code Editor fornecido pelo evento.

## Estado da conversão

| Aula | Construção durante o notebook | Situação |
|---|---|---|
| 00 | STS, conta/região e versão do SDK; inicializar registro de IDs | Testada na AWS |
| 01 | Cognito, usuários sintéticos, IAM, Lambda, Gateway JWT e target MCP | Testada na AWS, incluindo invocação MCP |
| 02 | Pessoa, aplicações Cognito e comparação com Entra ID | Testada na AWS, com negativas e chamada permitida |
| 03 | Runtime MCP, artefato ARM64 e identidade IAM | Testada na AWS, incluindo invocação e logs |
| 04 | Engine, associação ENFORCE, Cedar e matriz de autorização | Testada na AWS: um ALLOW e dois DENY |
| 05 | Geração AWS de política, findings, testes e rascunho LOG_ONLY | Testada na AWS, mantendo a política ACTIVE |
| 06 | Registry, aprovação manual e descoberta IAM | Testada na AWS, incluindo negativa anônima |
| 07 | Três personas oficiais e chamadas reais de autorização | Testada na conta atual com as três personas oficiais |
| 08 | Publicação, aprovação, descoberta e invocação por personas | Testada na AWS, incluindo negativas entre personas |
| 09 | Integração Runtime, Gateway e Identity | Testada na AWS: analista permitido e auditor negado |
| 10–14 | Integrações e fronteiras entre contas | Migração pendente; o legado exige quatro contas |
| 15 | Memory por actor e concessão atual na fonte sintética | Testada na AWS, incluindo isolamento e revogação |
| 16 | KB MANAGED, ACL nativa, conector Gateway e geração no Runtime | Testada na AWS: geração por pessoa e negativas de acesso |
| 99 | Limpeza SDK dos recursos criados nas aulas 01–09 e 15–16 | Testada na AWS para toda a jornada SDK |

Em 05/11/2026, **00–09, 15 e 16 passaram** na conta atual com a sessão do editor.
As aulas 07–08 agora usam as três personas previstas no workshop oficial;
a aula 15 validou federação Cognito, isolamento entre pessoas e revogação.
A tabela usa [TableId na retomada e limpeza](docs/decisao-dynamodb-notebook-sdk.md).
O Runtime RAG gerou respostas Nova Lite limitadas à ACL de cada pessoa.
A limpeza completa e a reconstrução do zero passaram. Os 12 notebooks foram
executados novamente, sem falhas, em aproximadamente 12 minutos.
Passaram também 793 testes de código.
Consulte a [revisão das sessões](docs/decisao-sessao-participante-20261105.md).

Os relatórios, versões e Request IDs estão no
[aceite das aulas SDK](docs/aceite-notebooks-sdk.md). O documento separa
os resultados da conta atual do histórico de contas encerradas.

As aulas 10–14 ainda contêm o fluxo antigo de implantação. **Não execute
“Run All” na coleção inteira.** O [plano da conversão](docs/plano-notebooks-sdk.md)
registra o escopo e a ordem das mudanças.

## Preparar o kernel

No terminal do seu ambiente de notebooks na AWS, dentro deste repositório:

```bash
./scripts/setup.sh
```

Esse script instala dependências e registra o kernel; não cria recursos AWS.
Selecione **Santander Workshop (.venv)** no VS Code. Abra
[00_preflight.ipynb](notebooks/00_preflight.ipynb) e confira conta, região e
identidade antes das aulas de criação.

A aula inicial usa a sessão AWS autorizada do ambiente. O arquivo `.workshop/`
guarda somente os identificadores dos recursos criados e permite reiniciar o
kernel. Ele é gerado durante a execução, fica fora do Git e não contém senhas,
chaves ou tokens. Senhas sintéticas são guardadas no Secrets Manager.

## Contas e permissões

A jornada validada de conta única inclui 00–09 e 15–16. Os cenários 10–14
precisam de contas distintas para demonstrar fronteiras reais. A versão antiga
desses notebooks exige quatro contas, mesmo quando o fluxo ilustrado mostra
três; esse requisito ainda precisa ser revisto na conversão.

Uma conta AWS arbitrária não está automaticamente habilitada: é necessário ter
permissões para as APIs da aula, passar as roles aos serviços, disponibilidade
dos serviços na região, quotas e acesso ao modelo quando usado. Cada aula
explica suas operações. Uma negativa de IAM é um bloqueio a diagnosticar com o
responsável pela conta, não um motivo para alterar roles protegidas do evento.

## Código e validação

- `scripts/sdk_notebook_lessons.py`: contexto AWS e estrutura das novas aulas.
- `scripts/sdk_gateway_lesson.py`: chamadas de criação e testes da aula 01.
- `scripts/sdk_identity_lesson.py`: comparação de aplicações, validação de
  assinatura e audiência, com negativas no Gateway.
- `scripts/sdk_runtime_lesson.py`: código MCP, artefato ARM64, criação e
  invocação do Runtime e identidade IAM do workload.
- `scripts/sdk_policy_lesson.py`: engine e Cedar criados nas células, com
  teste de pessoa, cliente sintético e claims verificadas.
- `scripts/sdk_policy_authoring_lesson.py`: geração no serviço AWS, findings,
  contraexemplos e criação do rascunho somente em LOG_ONLY.
- `scripts/sdk_registry_lesson.py`: criação do Registry, aprovação manual
  e descoberta autenticada por IAM.
- `scripts/sdk_registry_personas_lesson.py`: três personas oficiais com trust e
  permissões limitadas ao catálogo e Runtime desta execução.
- `scripts/sdk_memory_lesson.py`: referências no Memory e autorização atual na fonte sintética.
- `scripts/sdk_rag_lesson.py`: corpus, ACL, ingestão, conector nativo e agente RAG.
- `scripts/sdk_cleanup_lesson.py`: exclusão dos recursos da execução, com
  conferência de propriedade e dependências.
- `src/santander_demo/notebook_state.py`: persistência de IDs; não chama APIs AWS.
- `scripts/generate_aws_notebooks.py`: gera os notebooks a partir dessas fontes.
- `scripts/run_sdk_notebooks.py`: executa uma seleção explícita das células
  SDK no ambiente AWS, confere a conta e registra evidências sem pré-deploy.

```bash
uv run python scripts/generate_aws_notebooks.py
uv run pytest -q tests/test_notebook_state.py tests/test_sdk_*.py
```

Os notebooks distribuídos não contêm saídas executadas. A limpeza é uma etapa
explícita: [99_cleanup_sdk.ipynb](notebooks/99_cleanup_sdk.ipynb) mostra as
chamadas de exclusão e recusa dependências ainda não contempladas. Os recursos
permanecem disponíveis entre aulas e podem gerar cobrança até serem removidos.
Após a limpeza, a próxima aula 00 arquiva os IDs liberados e inicia outra
execução com novos nomes. Uma conta diferente sempre recebe seu próprio
registro; o histórico de outra conta não é reaproveitado como configuração.

## Material da arquitetura anterior

`infra/`, `scripts/aws_notebook_lessons.py`, os scripts antigos de deploy/runner
e os guias de implantação permanecem no repositório durante a migração.
**Eles não são pré-requisitos da nova jornada SDK.** Não use seu aceite como
prova de que os novos notebooks funcionam.

O [aceite anterior](docs/aceite-aws.md) refere-se a outra versão, com recursos
pré-implantados em quatro contas. A nova jornada precisa de seu próprio aceite,
começando em uma conta sem recursos do workshop e criando-os nas células.

## Referência

[Workshops oficiais AgentCore](https://github.com/awslabs/agentcore-samples/tree/main/06-workshops).
A referência didática é a criação, inspeção, uso e remoção dos serviços durante
os notebooks. Veja o [plano da conversão](docs/plano-notebooks-sdk.md) para as
referências específicas estudadas.
