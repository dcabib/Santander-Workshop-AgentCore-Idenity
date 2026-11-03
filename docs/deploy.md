# Implantação por IaC

**Este guia inclui o ambiente completo em quatro contas AWS distintas.**
Para implantar somente 00–09 e 15–16 em uma conta, siga
[conta única](conta-unica.md). Antes de seguir os comandos, confira a
[matriz de contas e aulas](contas-e-elegibilidade.md). Com menos de quatro
contas, os cenários 10–14 não executam com este IaC.

Todos os recursos usam os pipelines do projeto. Não crie recursos avulsos por
CLI ou console. As fases geram parâmetros a partir dos outputs exatos e
confirmam conta e região pelo STS antes de aplicar o CloudFormation.

## Jornada principal

Prepare `config/aws.workshop.json`, conforme [preparação](preparacao.md), e gere
os artefatos Linux ARM64:

```bash
uv run python scripts/build_artifacts.py --banking
uv run python scripts/workshop_deploy.py all --execute
```

A ordem é bootstrap → identity → gateway → backend → bindings → agent →
policy-draft. Bootstrap contém o bucket privado. Identity pertence à plataforma;
os demais domínios compartilham o mesmo emissor de identidade.
Nos domínios, `all` implanta bootstrap, gateway, backend e bindings. Os agentes
específicos da origem são fases explícitas.

Para revisar um change set sem executá-lo, selecione a fase e omita `--execute`:

```bash
uv run python scripts/workshop_deploy.py bindings
```

**Bloco multi-conta (aulas 10–14):** implante os três domínios em contas
separadas da plataforma e, em seguida, as conexões e agentes entre contas.
O fluxo origem → hub → fonte usa três contas, mas a federação deste pipeline
inclui Lending e exige as quatro.

```bash
uv run python scripts/workshop_deploy.py all --domain retail-banking --execute
uv run python scripts/workshop_deploy.py all --domain transaction-banking --execute
uv run python scripts/workshop_deploy.py all --domain lending-wealth --execute
uv run python scripts/workshop_deploy.py federation-bindings --execute
uv run python scripts/workshop_deploy.py agent-riscos --domain retail-banking --execute
uv run python scripts/workshop_deploy.py agent-fraude --domain retail-banking --execute
```

`Gateway` valida JWT e executa Cedar em ENFORCE. Targets Lambda usam IAM. Para
o Runtime MCP, `GATEWAY_IAM_ROLE` assina a chamada com SigV4; a resource policy
nega invocação por qualquer outra role. A trust policy da role é fixada no ARN
do Gateway por um segundo change set após sua primeira criação.

O interceptor propaga o JWT humano verificado em um header separado da assinatura
IAM; o backend valida assinatura/claims e a ACL DynamoDB. Entre Gateways
federados, a propagação usa Authorization e authorizer JWT. Essa cadeia declara
audiência compartilhada; não é token exchange OBO do Microsoft Entra ID.

`AllowedWorkloadConfiguration` exige transaction tokens emitidos pelo caminho de
target nativo de Runtime HTTP. O workshop usa agregação MCP e a restrição IAM
documentada em [Runtime OAuth](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html#runtime-restrict-iam-gateway).
O provider `runtime_boundary.py` gerencia essa policy pelo CloudFormation e
mantém a restrição até a exclusão do Runtime no teardown.

## Integrações

[Registry](registry/README.md), [Terraform](terraform/README.md) e
[RAG](rag/README.md) reutilizam seus pipelines. Depois do RAG implantado:

```bash
uv run python scripts/workshop_deploy.py rag-agent --execute
```

Depois de implantar os dois agentes da origem, publique suas capacidades no
mesmo Registry, em stacks próprios:

```bash
uv run python scripts/workshop_catalog.py publish --execute
uv run python scripts/workshop_catalog.py submit --execute
```

Leia `build/workshop-origin-bundle.json`: confira Runtime ARN, Gateway da
plataforma, emissor Cognito e audiência específica de cada agente contra os
outputs do IaC. Revise os digests e decisões em
`build/workshop-origin-review-candidate.json` antes de aplicar:

```bash
uv run python scripts/workshop_catalog.py approve \
  --review build/workshop-origin-review-candidate.json --execute
```

A aula 14 descobre esses registros, verifica o estado APPROVED e valida os
descriptors completos antes de enviar credenciais aos Runtimes. Os registros
dos fundamentos não são substituídos. Remova as fases origin-approve,
origin-submit e origin-publish antes dos agentes correspondentes no teardown.

## Runner de notebooks na AWS

O runner empacota uma whitelist do projeto e configurações de identificadores,
substitui perfis por roles, envia a fonte por hash ao S3 privado e aplica o
CodeBuild pelo CloudFormation. Não inclui `.aws`, state, ambientes Python ou
credenciais. Para uma execução parcial, passe `--labs 00 01 04` no deploy.
O runner inclui as contas, integrações e permissões exigidas pela seleção.
Registry, Terraform e RAG só entram quando usados. Seu deploy rejeita IDs
ausentes/repetidos antes de enviar a fonte ao S3. Seu `run` aceita apenas
subconjuntos da seleção implantada e consulta os pré-requisitos antes do build.
Para ampliar as aulas, faça novo deploy. As roles observer abaixo são
necessárias quando a seleção inclui 10–14:

```bash
uv run python scripts/workshop_runner.py deploy --execute
uv run python scripts/workshop_deploy.py observer --domain retail-banking --execute
uv run python scripts/workshop_deploy.py observer --domain transaction-banking --execute
uv run python scripts/workshop_deploy.py observer --domain lending-wealth --execute
```

O output `RoleArn` do stack runner deve ser passado ao pipeline Registry para
que suas personas aceitem a role de execução:

```bash
uv run python scripts/registry_deploy.py foundation --profile default   --runner-arn ARN_DA_ROLE_RUNNER --execute
uv run python scripts/workshop_runner.py deploy --execute
uv run python scripts/workshop_runner.py run --execute
uv run python scripts/workshop_runner.py status --build-id ID_RETORNADO
uv run python scripts/workshop_runner.py fetch --build-id ID_RETORNADO
```

O segundo deploy atualiza a fonte com os outputs finais. `run` executa as aulas;
`status` e `fetch` consultam o build exato. Um build com erro não conta como aceite.
Os recursos permanecem disponíveis para o workshop.

## Recuperação e logs

O Runtime cria seu grupo de logs automaticamente. O custom resource
`RuntimeLogRetention` gerencia apenas a retenção, sem tentar criar o grupo e
sem apagar logs na exclusão. Há testes para nome exato e preservação no Delete.

Uma criação do backend que termine em ROLLBACK_COMPLETE pode ser recuperada
pelo flag `--recover-failed-create`, somente após diagnóstico e aprovação da
recuperação. O wrapper verifica dono, fase, estado e ausência de recursos
restantes antes de recriar esse stack. Ele não é um reset geral do ambiente.
