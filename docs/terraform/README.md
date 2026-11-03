# Terraform — Runtime, Gateway e Identity

A aula 09 consulta uma implantação Terraform independente da fundação
CloudFormation. O Runtime executa a orquestração e a inferência; Identity obtém
um token Cognito M2M para o Gateway, que invoca a ferramenta Lambda por IAM.
A aula verifica conteúdo retornado e IDs nativos da execução.

O fluxo M2M autentica a aplicação. Ele não representa delegação humana nem OBO
Microsoft. Para Entra, seria necessário adaptar o app registration, provider e
contrato do token, preservando essa distinção.

```bash
uv run python scripts/terraform_build.py
uv run python scripts/terraform_deploy.py preflight --config config/aws.terraform.json
uv run python scripts/terraform_deploy.py init --config config/aws.terraform.json
uv run python scripts/terraform_deploy.py validate --config config/aws.terraform.json
uv run python scripts/terraform_deploy.py plan --config config/aws.terraform.json
uv run python scripts/terraform_deploy.py apply --config config/aws.terraform.json
```

O state usa o bucket privado, criptografado e versionado do bootstrap
CloudFormation, com lockfile S3. A configuração `backend.stack` identifica esse
stack e `backend.key` identifica o state da turma. Para migrar uma implantação
existente cujo state ainda está no diretório de trabalho, o pipeline fornece:

```bash
uv run python scripts/terraform_deploy.py migrate-state --config config/aws.terraform.json
```

A migração confirma conta/projeto/região, preserva uma cópia privada e recusa
sobrescrever um state remoto existente. Usa `terraform init -migrate-state`
dentro do wrapper; não cria recursos fora do IaC.

Revise o plano antes de aplicar. O wrapper aceita somente o plano correspondente
aos hashes da configuração, IaC e artefatos. Estado, planos e segredos não vão ao
Git. O ID da conta é conferido tanto pelo wrapper quanto pelo provider AWS.
O grupo de logs criado pelo Runtime é adotado por um bloco `import` declarativo
no segundo plano, nunca por `terraform import` avulso.

O notebook usa os outputs declarados em `integrations.terraform.outputs` e
executa no runner AWS. `terraform_notebook_check.py` delega ao mesmo executor;
não existe flag para retornar respostas simuladas.

[Implantação](../deploy.md) · [Evidências](../validacao.md)
