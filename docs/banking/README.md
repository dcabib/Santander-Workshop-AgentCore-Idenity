# Notebook 10 — Um agente central, três LOBs e quatro contas

Abra [`10_blog_multi_account_gateway_mcp.ipynb`](../../notebooks/10_blog_multi_account_gateway_mcp.ipynb).
Ele adapta o [artigo AWS de 24/09/2026](https://aws.amazon.com/blogs/machine-learning/build-a-multi-account-ai-agent-with-agentcore-gateway-and-mcp/)
para uma demonstração guiada pelo Jupyter. O notebook é a interface; o agente
Strands roda no AgentCore Runtime da conta de plataforma.

![Quatro contas com JWT até o Gateway e OAuth M2M nos MCPs das LOBs](arquitetura.png)

## O que está implementado

| Parte | Implementação nesta pasta |
|---|---|
| Plataforma | Gateway MCP com busca semântica, Identity OAuth `CLIENT_CREDENTIALS`, Policy `ENFORCE`, Guardrail e log delivery. |
| Agent Runtime | Strands + Bedrock; recebe o JWT do usuário no header `Authorization` e o encaminha ao Gateway. |
| Retail | Runtime MCP, tabelas Customers/Accounts/Balances e fixtures sintéticas da referência. |
| Transaction | Runtime MCP, tabelas Payments/Beneficiaries e fixtures sintéticas da referência. |
| Lending | Runtime MCP, tabelas Loans/CreditScores/EMISchedule e `Retrieve` em uma KB **já existente nessa conta**. |
| Registry | Três registros MCP aprovados por recursos CloudFormation, `AWS_IAM`, publicação e aprovação com roles separadas. |
| Notebook | Preflight das quatro contas, preparação de parâmetros, execução opcional do pipeline IaC, JWT verificado, MCP real, negativa Cedar, RAG, agente hospedado e evidência sanitizada. |

Os **16 schemas** do repositório estão expostos. O roteiro usa as 12 ferramentas
de consulta/cálculo; as três de escrita ficam sem `permit` e sem permissões IAM
de escrita. `delete_customer` tem `forbid` explícito e continua sendo o stub não
destrutivo da referência. A simulação de transferência do artigo não integra
este roteiro: ela usa várias chamadas sem uma transação distribuída.

As chamadas aos serviços são reais. Executar o notebook com `RUN_AWS=False`
valida arquivos e contratos localmente e marca as integrações como `NOT_RUN`;
não fabrica respostas do Bedrock, DynamoDB, Registry ou Gateway.

## Pré-requisitos

1. Quatro contas de sandbox distintas, na organização destinada ao laboratório,
   com perfis AWS CLI e região habilitada para AgentCore/Registry.
2. Acesso ao modelo Bedrock na conta de plataforma. Em inferência entre regiões,
   incluir no IAM o ARN do inference profile e **todos os ARNs de modelos destino**
   devolvidos por `bedrock get-inference-profile`. O arquivo de exemplo não adivinha
   esse conjunto.
3. Okta custom authorization server, audiência `lobfederation`, scope
   `lobfederation.invoke`, aplicação de login humano e aplicação M2M com
   `client_credentials`. As identidades são um pré-requisito gerido pelo IaC do
   tenant; este notebook não cria usuários ou aplicações Okta.
4. Segredo M2M no Secrets Manager da plataforma, gerido pelo IaC de identidade,
   no formato `{"client_secret": "..."}`. A configuração do notebook contém
   **somente o ARN**. Se usar CMK, adicionar ao IaC o acesso à chave específica.
5. Uma Bedrock Knowledge Base ativa e já ingerida na conta Lending, com documentos
   **sintéticos** de políticas de crédito. A implementação consulta a KB pelo
   execution role local. Bucket, PDFs, índice vetorial e ingestão são
   responsabilidades do IaC da fonte de dados e não são provisionados aqui.

O notebook substitui React/ECS/CloudFront do artigo. A aplicação web, a criação
da KB/OpenSearch e a configuração de avaliações contínuas não são parte desta
adaptação; a topologia central + três MCPs, a autenticação e as consultas estão.

## Preparar localmente

```bash
uv sync --frozen --extra banking
uv run --extra banking python infra/banking/generate.py
uv run --extra banking cfn-lint infra/banking/templates/*.json
uv run --extra banking python scripts/build_artifacts.py --banking
```

Selecione `.venv/bin/python` como kernel. Copie
[`config/banking.example.json`](../../config/banking.example.json) para
`config/local.banking.json` e preencha os identificadores. O token humano é
solicitado por `getpass` somente na etapa de execução; não o escreva no JSON.

O build usa o lockfile e gera `build/banking.zip` para Python 3.12/Linux ARM64.
O artefato serve aos Runtimes e providers; seu hash é conferido pelo pipeline.

## Implantar pelo notebook

Ative `RUN_AWS=True`. Use `DEPLOY_PHASE` na seguinte ordem, executando novamente
as células de configuração, sessões e preparação a cada etapa:

| Fase | Contas | Resultado |
|---|---|---|
| `bootstrap` | As quatro | Buckets de artefato versionados e privados. |
| `platform` | Plataforma | Gateway, provider M2M, engine, Guardrail e logs. Ainda sem tools permitidas. |
| `lobs` | As três LOBs | Tabelas, fixtures e Runtimes restritos ao workload do Gateway. Valida KB Lending por leitura. |
| `bindings` | Plataforma | Targets, políticas ativas e Registry com registros aprovados. |
| `agent` | Plataforma | Runtime Strands com acesso ao Bedrock, Registry e Guardrail. |

`prepare_phase` lê os outputs anteriores e escreve os parâmetros concretos em
`config/local.banking-*.json`. Mostra o comando antes de executá-lo.

- `RUN_PIPELINE=False`: apenas mostra os comandos e grava parâmetros locais.
- `RUN_PIPELINE=True`, `APPLY_CHANGESET=False`: publica artefato e prepara change sets.
- `RUN_PIPELINE=True`, `APPLY_CHANGESET=True`: aplica por CloudFormation.

Revise os change sets no CloudFormation antes de aplicar. Para um retry, ajuste
o template/parâmetros e use o mesmo pipeline. Não use `deploy.sh`, `cleanup.sh`,
`setup_gateway.py`, `register_agents.py` ou seeds avulsos do upstream: parte de
suas mutações não é gerida por CloudFormation.

Após implantação, configure `DEPLOY_PHASE=None`. O preflight exige a topologia
completa e `ENFORCE`. Só então as células de invocação são habilitadas.

## O que observar no ensaio

- **Identity:** Okta usa `cid`. Os authorizers verificam essa claim explicitamente
  com `CustomClaims`; `AllowedClients` verifica `client_id` e não deve ser usado
  como substituto de `cid`. A allowlist de headers passa `Authorization` para o
  agente JWT, conforme a [documentação de Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-header-allowlist.html).
- **Gateway:** três endpoints em contas distintas; todos os targets usam o mesmo
  provider M2M e scope aprovado. Nenhum segredo M2M entra no agente.
- **Policy:** lê o principal humano antes de obter a credencial técnica downstream.
  Um erro MCP genérico ou erro de login não comprova uma negativa Cedar.
- **Registry:** o agente requer as três capacidades aprovadas e só usa o endpoint
  de Gateway configurado. Não envia bearer para URLs arbitrárias do catálogo.
- **Dados:** DynamoDB e KB continuam nas LOBs; os resultados consultados passam
  para a plataforma e para o contexto do modelo.
- **M2M:** a identidade humana **não** chega às fontes neste fluxo. Para aplicar
  grants por usuário nas fontes seria necessário um cenário OBO separado.

O teste de agente exige resultados de ferramentas das três LOBs. Se o modelo não
as consultar ou alguma chamada falhar, o notebook não declara o cenário aprovado.
A evidência exportada contém nomes de tools/status e hash da resposta; não contém
JWT, prompts, argumentos nem conteúdo bancário.

## Remoção

Use a seção **Cleanup** do notebook ou o wrapper
`scripts/cleanup.py --scenario banking`, conforme o [procedimento](../cleanup.md). O padrão
somente lê o stack e mostra o plano; executar a remoção exige seu ARN exato.

Remova pelo CloudFormation nesta ordem: `agent`, `bindings`, três stacks de LOB,
`platform`, quatro `bootstrap`. Tabelas e buckets têm `Retain`; isso mantém os
dados/artefatos até uma decisão explícita de remoção. A KB, as identidades Okta e o
segredo M2M pertencem aos stacks que já os gerenciam.

## Origem

Código e fixtures dos MCPs adaptados de
[`sample-amazon-bedrock-agentcore-banking-mcp-multi-account`](https://github.com/aws-samples/sample-amazon-bedrock-agentcore-banking-mcp-multi-account/tree/f76491b63d005d1ad0c253396f58f67da021f94d),
commit `f76491b63d005d1ad0c253396f58f67da021f94d`.
Licença: [MIT-0, texto original](UPSTREAM-LICENSE). Alterações: nomes de tabelas
prefixados, empacotamento por IaC, aplicação restrita ao Gateway, autoria de
Registry separada de aprovação e roteiro de consultas.

O IAM usa a [Service Authorization Reference de AgentCore](https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-agentcore.html).
`CreateRegistry` não aceita restrição por ARN: somente essa ação do provider de
criação usa `Resource: "*"`, limitada à região. Operações sobre registros e
catálogos existentes usam ARNs da conta de plataforma.
