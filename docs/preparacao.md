# Preparação

A **jornada completa** exige quatro contas AWS distintas.
Para 00–09 e 15–16, use a [implantação de conta única](conta-unica.md).
O código aceita `us-east-1` e `us-west-2`, sujeito à disponibilidade dos serviços
e às permissões da conta. **Não execute 10–14 em uma conta única.**
Leia primeiro a [matriz de contas e aulas](contas-e-elegibilidade.md), incluindo
a diferença entre as três contas do fluxo da aula 14 e as quatro exigidas
pela implantação atual. Para uma turma sem esse ambiente, selecione os
fundamentos e reserve 10–14 para demonstração do instrutor.

Copie `config/workshop.example.json` (jornada completa) ou
`config/workshop.single-account.example.json` (12 aulas) para
`config/aws.workshop.json` e preencha IDs e perfis.
Arquivos `config/aws.*.json` são ignorados pelo Git. Use referências ao
Secrets Manager; não inclua senhas, tokens ou chaves AWS.

Os nomes abaixo são os perfis usados no ambiente de referência; não vêm
pré-configurados na conta de outro participante.

| Domínio | Perfil do operador neste ambiente |
|---|---|
| Plataforma | `default` |
| Retail / agentes de origem | `containers` |
| Transaction / fonte | `cognito` |
| Lending | `serverless` |

O STS deve retornar o ID configurado em cada domínio. Contas duplicadas são
rejeitadas nos exercícios entre contas. No CodeBuild, perfis são substituídos
por roles de execução e roles observer declaradas no CloudFormation.

Antes de implantar ou iniciar a turma, confira a configuração:

```bash
uv run python scripts/workshop_prerequisites.py --runner
```

Esse comando não chama AWS. Antes da execução, use também `--check-aws` para
consultar STS e as dependências declaradas. Confirme permissões IAM/SCP, trust
das roles, disponibilidade dos serviços/modelos e quotas na região. Ter uma
conta e credenciais válidas, por si só, não prepara o workshop.

A autenticação da jornada utiliza Cognito, dois app clients confidenciais e
quatro usuários sintéticos. Senhas e segredos dos clients ficam no Secrets
Manager e são provisionados por custom resources do CloudFormation. Login de
workshop usa USER_PASSWORD_AUTH com SECRET_HASH. Para aplicações de usuários
finais, o fluxo indicado no material é authorization code com PKCE.

Os cenários Registry, Terraform e RAG possuem seus próprios stacks ou state.
`integrations` aponta para suas configurações e outputs. O preflight não cria
recursos e não escolhe recursos por aproximação de nome.

Use Python 3.12, `uv`, AWS CLI e, para a aula 09, Terraform compatível com
`infra/terraform_agentcore/versions.tf`. Execute `uv sync --frozen --extra banking`
no ambiente de desenvolvimento para preparar os comandos do pipeline.
A execução das aulas acontece no [runner AWS](deploy.md).

O simulador de Databricks integra a jornada obrigatória. Para substituí-lo por
Databricks real na AWS seria necessário adaptar o IaC e implementar/testar o
conector e a delegação; alterar apenas `source_kind` é rejeitado. Analogamente,
o provedor Entra exige adaptar authorizers, claims, políticas e OAuth; o pipeline
atual implementa Cognito e não faz uma substituição silenciosa de provedores.
