# Workshop Santander — AgentCore

Implementação executável do [plano](plano-demo-workshop-santander.md), com foco em
Identity, Policy, Gateway e Registry. Todos os exemplos usam dados sintéticos:
`SANT-DEMO-001` na trilha original e C001–C008 nos cenários bancários.

**Comece pelo [notebook 12 — cenário Santander integrado](notebooks/12_cenario_santander_integrado.ipynb).**
Ele reúne o fluxo pedido: agentes Riscos/Fraude em Runtime na conta de origem →
Gateway central → Gateway da conta de dados → MCP Databricks Azure. Cada conta
tem Gateway/Policy e a delegação passa por AgentCore Identity.

**Pronto localmente:** quatorze notebooks, diagramas, protocolo MCP, JWT,
Cedar, testes e exercícios de quotas/ACL. **Preparado para implantação:**
CloudFormation, Terraform Entra e federation de usuários Databricks.
**Nenhum recurso foi implantado.** O ensaio AWS/Entra/Databricks continua dependente
dos ambientes de teste e da habilitação do token exchange nativo.

**Aderência ao escopo Santander:** parcial. A
[revisão da conversa e do HTML](revisao-aderencia-santander.md) foi a base das
adequações. O [estado por demanda](docs/adequacoes-santander.md), o
[runbook integrado](docs/journey/README.md) e a
[matriz de decisões](docs/journey/decisoes.md) descrevem a implementação atual
e as provas cloud ainda pendentes.

## Entenda pelos diagramas

Abra a [galeria visual dos quatorze notebooks](docs/diagramas/index.html#12_cenario_santander_integrado) no navegador.
Cada imagem explica os componentes, o fluxo da chamada e o aprendizado do laboratório.
Use **Ampliar** para apresentar, ou baixe **PNG** para slides e **SVG** para editar.
As imagens também estão incorporadas na abertura de cada notebook.

No macOS, a partir desta pasta:

```bash
open docs/diagramas/index.html
```

O [índice de imagens](docs/diagramas/README.md) reúne os links por notebook.

## Executar agora

**Trilha principal:** [notebook 12](notebooks/12_cenario_santander_integrado.ipynb).
Inclui dois agentes distinguíveis, SQL canário restrito, usuário com/sem grant,
Registry cross-account e exportação de evidências. O padrão é offline.

**Sessão 2:** [notebook 13 — ingestão, ACL e memória](notebooks/13_ingestao_acl_memoria.ipynb).
Exercita localmente documentos sintéticos, revogação e exclusão.
[Agenda da Sessão 2](docs/ingestao/sessao-2.md) ·
[Sessão online Harness](docs/harness/sessao-online.md).

**Referência — Gateway em cada conta:** abra
[11_gateways_por_conta_identity_policy.ipynb](notebooks/11_gateways_por_conta_identity_policy.ipynb).
Quatro Gateways, Identity OBO e Policy independentes; a plataforma pode permitir
uma chamada que a conta de negócio bloqueia. Inclui diagrama, verificações de
identidade no destino e implantação por CloudFormation.
[Runbook e arquitetura](docs/federation/README.md). O agente executa no notebook,
com Bedrock e ferramentas na AWS; as oito aplicações Entra são pré-requisitos.

**Cenário do artigo AWS:** abra
[10_blog_multi_account_gateway_mcp.ipynb](notebooks/10_blog_multi_account_gateway_mcp.ipynb).
Ele implementa um agente Strands central consultando três LOBs em quatro contas,
com Gateway, Identity M2M, Policy, Registry e RAG. Use
`uv sync --frozen --extra banking` e siga o [runbook específico](docs/banking/README.md).
A execução real requer sandbox, aplicações Okta e uma KB já ingerida em Lending.

A trilha original `00`–`09` continua disponível:

```bash
uv sync --frozen
uv run santander-demo demo
uv run santander-demo matrix
```

Abra [00_preflight.ipynb](notebooks/00_preflight.ipynb) no VS Code e selecione
`.venv/bin/python` como kernel. Siga `00` a `09`; o padrão é local e não solicita
credenciais. `LOCAL_SIMULATION` identifica resultados que não provam AWS.

```bash
uv run --extra banking pytest -q
uv run --extra banking python scripts/verify_notebooks.py
uv run cfn-lint infra/templates/*.json
```

As cópias executadas e evidências ficam em `evidence/`; os notebooks de origem
permanecem sem outputs. A validação registrada está em [docs/validacao.md](docs/validacao.md).
O [relatório de validação](docs/validacao.md) registra a execução mais recente;
`evidence/notebooks.json` contém o resultado e o hash de cada notebook.

Todos os notebooks incluem **Cleanup**: remoção opcional de stacks pelo
CloudFormation e limpeza das variáveis locais. O cleanup de nuvem fica desativado
por padrão; [veja a ordem e os recursos retidos](docs/cleanup.md).

## O que foi implementado

| Componente | Implementação |
|---|---|
| Identity | No 12, Entra/JWKS, OBO por agente e Gateway, WAT ligado ao usuário e token exchange nativo para Databricks. Graph/Fraude são referências dos módulos iniciais. |
| Policy | Cedar compartilhado entre laboratório e IaC; três engines `ENFORCE` no 12; usuário, caller, tool e consulta canário exata. |
| Gateway | No 12, entrada dos agentes, hub central e entrada da conta de dados; targets MCP e autenticação por salto. |
| Registry | Estados, papéis, owner/versão/instância e busca IAM via STS; providers CloudFormation separados para catálogo, publicação e decisão. |
| Agentes | No 12, Riscos e Fraude hospedados na origem, cada qual com aplicação Entra e Identity OBO próprios. Não requer LLM para demonstrar autorização. |
| Evidências | No 12, request ID, agente/tool, usuário pseudonimizado, hash de query e query ID observado; trace completo depende de correlação dos logs. |
| Databricks | No 12, Gateway → MCP DBSQL com Identity nativo, principal exato e teste com dois usuários. O adapter SQL REST do 09 continua como prova isolada. |
| Quotas | Contrato local de QPM/TPM/budget e divisão de responsabilidades; não é medição cloud. |
| Ingestão | No 13, lifecycle, ACL e memória isolada locais; conectores e serviços reais são a próxima etapa. |

No cenário integrado, **AgentCore Identity** participa das trocas delegadas
entre os componentes. As allowlists de usuários usam `tid` + `oid`; a aplicação
usa `azp` no caminho Entra v2 provisionado. A Policy central distingue os dois
agentes. A conta de dados valida a plataforma e aplica sua autorização local;
os grants da fonte são exercitados como o usuário.

![Agentes na conta A, Registry e Gateway central, Gateway na conta B e MCP Databricks Azure.](docs/journey/arquitetura.png)

[Ampliar esta arquitetura](docs/journey/arquitetura.svg) ·
[Ver o fluxo OBO até o Graph](docs/diagramas/svg/02_identity_entra_obo.svg)

## Implantação e ensaio

- [Runbook do cenário integrado](docs/journey/README.md): pré-requisitos, identidades e implantação em fases.
- [Runbook dos módulos iniciais](docs/deploy.md): trilha original 00–09.
- [Critérios de aceite](docs/aceite.md): provas necessárias antes de chamar a demo de integrada.
- [Roteiro do instrutor](docs/roteiro.md): agenda e narrativa.
- [Configuração do cenário integrado](config/journey.example.json): somente identificadores; nunca tokens.
- [Referências AWS](referencias-notebooks-agentcore.md): notebooks analisados no commit fixado.

## Limites desta entrega

1. A execução AWS e o mapeamento nativo das claims para Policy ainda precisam ser
   validados. Testes locais não comprovam IAM, integração gerenciada ou multi-conta.
2. Databricks Azure depende da federation e dos grants do cliente; não foi executado.
3. K2 é uma tool sintética, sem modificação ou integração ao Santalk/LangGraph.
4. A geração de políticas em linguagem natural tem pipeline IaC de rascunho e
   revisão, mas ainda não foi executada no serviço. Não publica políticas automaticamente.
5. Registry usa AWS_IAM; a variante Registry+Entra e o padrão I4 com credenciais
   técnicas/delegadas em headers separados ficam como extensões.
6. Dynatrace, Watsonx e SanEval têm posicionamento documentado, sem conectores
   instalados. Ingestão/Memory têm exercício local; Context e o produto Harness
   homologado precisam de confirmação antes dos ensaios das sessões próprias.
