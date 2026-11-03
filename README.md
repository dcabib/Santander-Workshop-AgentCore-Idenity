# Santander — Workshop Amazon Bedrock AgentCore

**Revisão em andamento: os recursos devem ser criados durante as aulas, com
chamadas SDK visíveis. O workshop completo ainda não está pronto neste formato.**
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

## Estado da conversão

| Aula | Construção durante o notebook | Situação |
|---|---|---|
| 00 | STS, conta/região e versão do SDK; inicializar registro de IDs | Testada na AWS |
| 01 | Cognito, usuários sintéticos, IAM, Lambda, Gateway JWT e target MCP | Testada na AWS, incluindo invocação MCP |
| 02 | Pessoa, aplicações Cognito e comparação com Entra ID | Testada na AWS, com negativas e chamada permitida |
| 03 | Runtime MCP, artefato ARM64 e identidade IAM | Testada na AWS, incluindo invocação e logs |
| 04–09 | Policy, Registry e integração | Migração pendente |
| 10–14 | Integrações e fronteiras entre contas | Migração pendente; o legado exige quatro contas |
| 15–16 | Memory, RAG e ACLs | Migração pendente |
| 99 | Limpeza SDK dos recursos criados nas aulas 01–03 | Código preparado; ainda não executado na AWS |

No teste de 03/11/2026, a aula 01 criou pool, app client, segredo, usuários,
grupo de logs e role Lambda em `us-west-2`. O
[ajuste Cognito aprovado](docs/decisao-cognito-notebook-sdk.md) foi aplicado.
A [alternativa Lambda aprovada](docs/decisao-lambda-notebook-sdk.md) também
foi aplicada: Lambda e Gateway foram criados, e as negativas JWT retornaram 401.
A [retomada sem ampliar permissões](docs/decisao-propagacao-iam-gateway-sdk.md)
foi autorizada e passou: target READY e Lambda invocada por MCP. A aula 02
também passou, assim como a criação e invocação do Runtime na aula 03.
Consulte as versões e Request IDs no
[aceite das aulas SDK](docs/aceite-notebooks-sdk.md).

As aulas 04–16 ainda contêm o fluxo antigo de implantação. **Não execute
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

A jornada planejada de conta única inclui 00–09 e 15–16. Os cenários 10–14
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
- `scripts/sdk_cleanup_lesson.py`: exclusão dos recursos da execução, com
  conferência de propriedade e dependências.
- `src/santander_demo/notebook_state.py`: persistência de IDs; não chama APIs AWS.
- `scripts/generate_aws_notebooks.py`: gera os notebooks a partir dessas fontes.

```bash
uv run python scripts/generate_aws_notebooks.py
uv run pytest -q tests/test_notebook_state.py tests/test_sdk_preflight.py tests/test_sdk_gateway.py tests/test_sdk_identity.py tests/test_sdk_runtime.py
```

Os notebooks distribuídos não contêm saídas executadas. A limpeza é uma etapa
explícita: [99_cleanup_sdk.ipynb](notebooks/99_cleanup_sdk.ipynb) mostra as
chamadas de exclusão e recusa dependências ainda não contempladas. Os recursos
permanecem disponíveis entre aulas e podem gerar cobrança até serem removidos.

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
