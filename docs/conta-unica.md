# Jornada de conta única na AWS

Esta implantação seleciona as **12 aulas 00–09 e 15–16**, com serviços e
execução de notebooks na AWS. As aulas 10–14 continuam exigindo quatro contas
e não fazem parte dessa jornada. Não são simuladas como múltiplas contas.

O código aceita `us-east-1` e `us-west-2`. Disponibilidade dos serviços/modelos,
quotas e permissões da conta precisam ser verificadas antes do deploy.
O [teste na conta participante](diagnostico-conta-unica.md) encontrou bloqueios
de Secrets Manager e `iam:PassRole` na role do evento. Essa tentativa ainda
não possui aceite operacional.

## Preparar a configuração

Use um checkout separado quando já existir uma implantação: o state Terraform,
os outputs e os artefatos de uma turma não podem substituir os de outra.

Copie `config/workshop.single-account.example.json` para
`config/aws.workshop.json`, preencha somente o ID de `platform` e mantenha os
três domínios com `id: null`. A opção `topology: single-account` define a seleção
padrão de 12 aulas. Omitir `topology` preserva o comportamento da jornada completa.

Credenciais temporárias ficam no ambiente do operador; `profile: null` usa
essa sessão. Elas não pertencem aos arquivos JSON nem ao artefato do CodeBuild.

```bash
uv sync --frozen --extra banking
uv run python scripts/workshop_prerequisites.py --runner
uv run python scripts/build_artifacts.py --banking
uv run python scripts/workshop_deploy.py all --execute
```

O núcleo inclui Cognito, Gateway/Policy, Runtime MCP, dados sintéticos, Memory,
agente e geração de rascunho. Os controles JWT, Cedar e IAM permanecem exigidos.

## Implantar as integrações das 12 aulas

Registry (06–08), Terraform (09) e RAG (15–16) usam seus próprios pipelines,
na mesma conta e região declaradas no workshop:

```bash
uv run python scripts/registry_deploy.py bootstrap --region us-west-2 --execute
uv run python scripts/registry_deploy.py foundation --region us-west-2 --execute
uv run python scripts/registry_deploy.py publish --region us-west-2 --execute
uv run python scripts/registry_deploy.py submit --region us-west-2 --execute
# Confira o bundle e os digests antes de aprovar:
uv run python scripts/registry_deploy.py approve --region us-west-2 \
  --review build/registry-review-candidate.json --execute
```

Para Terraform, preencha `config/aws.terraform.json` a partir do exemplo com
o mesmo ID e região, `profile: null` e o backend S3 do novo bootstrap.
Siga [Terraform](terraform/README.md) para build, init, validate, plan e apply.
Não migre o state do ambiente de referência para essa conta.

```bash
uv run python scripts/rag_deploy.py bootstrap --region us-west-2 --execute
uv run python scripts/rag_deploy.py identity --region us-west-2 --execute
uv run python scripts/rag_deploy.py data --region us-west-2 --execute
uv run python scripts/rag_deploy.py access --region us-west-2 --execute
uv run python scripts/workshop_deploy.py rag-agent --execute
```

## Implantar e executar o runner

```bash
uv run python scripts/workshop_runner.py deploy --execute
```

Passe o output `RoleArn` desse stack à fundação Registry para permitir as
sessões das personas pelo CodeBuild:

```bash
uv run python scripts/registry_deploy.py foundation --region us-west-2 \
  --runner-arn ARN_DA_ROLE_RUNNER --execute
uv run python scripts/workshop_runner.py deploy --execute
uv run python scripts/workshop_runner.py run --execute
uv run python scripts/workshop_runner.py status --build-id ID_RETORNADO
uv run python scripts/workshop_runner.py fetch --build-id ID_RETORNADO
```

Não há roles observer nessa topologia. Para começar apenas pelo núcleo, use
`deploy --labs 00 01 02 03 04 05 --execute`: Registry, Terraform e RAG não serão
empacotados nem concederão permissões ao runner. Amplie a seleção por um novo
deploy antes de executar outras aulas. `run --labs` só aceita subconjuntos da
seleção já implantada.

## Validação

Um plano com `ACCOUNTS_CONFIGURED` não comprova operação. O aceite requer
CodeBuild concluído, as 12 aulas em `PASS / AWS_EXECUTION`, hashes correspondentes
às fontes e evidências nativas. Bloqueios de permissão, região ou serviço são
relatados; não são convertidos em testes simulados ou aulas aprovadas.

A fonte Databricks permanece um simulador hospedado na AWS. A aula 15 valida
o estado de ingestão atual; testar todas as transições exige também o pipeline
de ciclo de vida descrito em [ingestão](ingestao/README.md).
