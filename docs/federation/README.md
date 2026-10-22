# Notebook 11 — Gateway, Identity e Policy em cada conta

Este é o cenário para demonstrar **autonomia de autorização entre contas**:
o Gateway da plataforma chama Gateways de negócio, e cada Gateway de negócio
chama apenas seu MCP local. Há quatro Gateways, quatro providers Identity e
quatro Policy engines em `ENFORCE`.

![Arquitetura com um Gateway por conta](arquitetura.png)

[Abrir notebook](../../notebooks/11_gateways_por_conta_identity_policy.ipynb) ·
[Ampliar SVG](arquitetura.svg) · [Configuração](../../config/federation.example.json)

## O caminho de uma consulta

1. O usuário autentica no Entra. O agente Strands executa no **kernel do notebook**
   e usa Bedrock com o perfil da plataforma.
2. O **Gateway Plataforma** valida o JWT e sua Policy autoriza usuário, aplicação,
   ferramenta e parâmetros. Seu **Identity** faz OBO para a audiência do Gateway Retail.
3. O **Gateway Retail** valida o novo JWT e aplica a **Policy de Retail**.
   Seu **Identity local** faz outro OBO para a audiência do MCP Retail.
4. O **Runtime MCP Retail** exige JWT para sua audiência, aplicação do Gateway
   Retail e workload hospedado nesse Gateway. Sua execution role consulta somente
   as tabelas locais.

Transaction e Lending repetem o mesmo desenho. A plataforma não recebe permissão
IAM para ler as tabelas nem invocar diretamente os MCPs das outras contas.
Os resultados autorizados retornam ao notebook e ao modelo da plataforma.

O Gateway é o ponto de entrada **das ferramentas de cada conta**. O cliente/agent
roda no notebook neste lab; não há um novo Runtime HTTP de agente exposto na
plataforma. Hospedar esse cliente como aplicação é uma extensão separada.

## Quem valida o quê

| Componente | Responsabilidade neste lab |
|---|---|
| Entra | Autenticar usuário, conceder delegação e emitir JWT para cada audiência |
| Authorizer de cada Gateway | Assinatura, issuer/expiração/audiência e claims exatas `tid`, `azp`, `ver`, `scp` |
| Policy local | Usuário `oid` permitido, tenant, aplicação, scope, tool e negativas por parâmetro |
| AgentCore Identity local | Usar o segredo da aplicação daquele Gateway para obter o token do próximo destino via OBO |
| Runtime local | JWT e aplicação locais, além da restrição ao workload do Gateway da própria conta |
| Registry na plataforma | Descobrir contratos aprovados que apontam para o Gateway da plataforma |

Identity intermedeia a troca; a decisão de executar a ferramenta pertence à Policy.
Encontrar uma ferramenta no Registry ou em `tools/list` não concede autorização.
As allowlists pertencem aos stacks de cada conta e podem divergir.

## Tokens: o usuário permanece, a audiência e o ator mudam

Todos os tokens de usuário usam Entra **v2** e um único scope delegado
`access_as_user`. `tid` + `oid` identificam a pessoa ao longo do fluxo.
`sub` pode mudar entre aplicações; não o compare entre audiências.

| Trecho | `aud` esperado | `azp` esperado |
|---|---|---|
| Notebook → Gateway Plataforma | App ID Gateway Plataforma | App ID login público |
| Plataforma → Gateway Retail | App ID Gateway Retail | App ID Gateway Plataforma |
| Retail → MCP Retail | App ID Runtime Retail | App ID Gateway Retail |
| Plataforma → Gateway Transaction | App ID Gateway Transaction | App ID Gateway Plataforma |
| Transaction → MCP Transaction | App ID Runtime Transaction | App ID Gateway Transaction |
| Plataforma → Gateway Lending | App ID Gateway Lending | App ID Gateway Plataforma |
| Lending → MCP Lending | App ID Runtime Lending | App ID Gateway Lending |

Os targets usam `GrantType=TOKEN_EXCHANGE`; o provider configura o grant Entra
`JWT_AUTHORIZATION_GRANT` e `requested_token_use=on_behalf_of`. Não há fallback
para `CLIENT_CREDENTIALS`. Cada provider e segredo pertence à conta/região de seu
Gateway. Scopes solicitados no OBO: `api://<app-do-destino>/.default`.

O lab verifica `scp == "access_as_user"` exatamente. Configure esse único scope
delegado nas APIs. Tokens com scopes adicionais falham fechados; adapte o contrato
Cedar/authorizers e seus testes se o tenant exigir outros scopes.

Entre Gateways, `azp` valida a aplicação do token; não comprova sozinho a
origem de rede da chamada. A restrição de workload configurada neste lab aplica-se
ao trecho Gateway local → Runtime. Os endpoints são públicos autenticados;
isolamento de rede privado não faz parte desta implementação.

## Pré-requisitos reais

São pré-requisitos, **não criados por estes templates**:

- Quatro sandboxes AWS diferentes, mesma região compatível com Gateway, Policy,
  Identity e Registry; perfis CLI e permissões CloudFormation para cada conta.
- Um tenant Entra com oito aplicações: login público, quatro APIs/aplicações de
  Gateway e três APIs de Runtime. APIs expõem `access_as_user`, usam
  `requested_access_token_version=2` e o URI `api://<client-id>`.
- Sete grants delegados com consentimento administrativo conforme a tabela acima:
  login → plataforma; plataforma → três Gateways; cada Gateway de negócio → MCP local.
- Quatro credenciais de aplicação, uma por Gateway, guardadas no Secrets Manager
  da respectiva conta como JSON `{"client_secret": "..."}`. A aplicação identifica
  o próprio Gateway e também atua como cliente confidencial no OBO seguinte.
  As APIs de Runtime não precisam de segredo neste desenho.
- Aplicações, grants, consentimento e segredos sob o IaC da equipe de identidade.
  O módulo antigo `infra/entra` prepara outro cenário; **não configura esta topologia**.
- Usuário de teste habilitado nas quatro allowlists. Device Code precisa ser
  permitido pelo tenant; alternativamente use um access token obtido pelo fluxo
  interativo aprovado da aplicação de login.
- Knowledge Base ativa **com ingestão concluída** na conta Lending, contendo
  documentos sintéticos. Ela e sua fonte de documentos permanecem no IaC da fonte.
- O perfil da plataforma precisa de `bedrock:InvokeModel*` nos recursos do modelo,
  `bedrock:ApplyGuardrail` no guardrail criado e `SearchRegistryRecords` no Registry.
  Os perfis de preflight precisam ler stacks e configurações AgentCore.

Use o modelo/inference profile autorizado no sandbox. O notebook não altera
permissões dos perfis. Segredos com CMK própria exigem a permissão KMS correspondente
no IaC; o template atual assume a chave gerenciada padrão do Secrets Manager.

## Preparação e implantação pelo IaC

```bash
uv sync --frozen --extra banking
uv run --extra banking python infra/federation/generate.py
uv run --extra banking cfn-lint infra/federation/templates/*.json
uv run --extra banking python scripts/build_artifacts.py --banking
cp config/federation.example.json config/local.federation.json
```

Preencha somente identificadores e ARNs. Use um `project` diferente do notebook 10.
O ZIP banking é compartilhado; reconstrua-o para incluir `whoami` e o entrypoint
atualizado. Os fixtures C001–C008 são sintéticos.

O notebook prepara parâmetros com outputs reais dos stacks. O wrapper é
`scripts/banking_deploy.py --scenario federation`; ele confere STS, carrega apenas
templates conhecidos, verifica o hash do artefato e usa CloudFormation.

| Fase | Stacks | Recursos |
|---|---|---|
| `bootstrap` | 4 | Buckets de artefatos |
| `gateways` | 4 | Gateway, Identity OBO, Policy engine e logs; guardrail na plataforma |
| `backends` | 3 | Runtimes MCP, DynamoDB e fixtures locais |
| `domain-bindings` | 3 | Cada Gateway de negócio → seu Runtime + Policies locais |
| `platform-bindings` | 1 | Gateway Plataforma → três Gateways + Policies da plataforma |
| `registry` | 1 | Catálogo, três registros e decisões de aprovação |

São **13 templates reutilizados em 16 stacks**. Crie primeiro um change set por
fase e revise-o. A preparação de change set inclui upload do artefato ao bucket
do stack quando necessário. A aplicação ocorre exclusivamente pelo wrapper IaC.
Nenhuma correção direta via SDK/CLI faz parte do roteiro.

Os targets usam schemas MCP estáticos: criação não depende de um token humano
nem de uma sincronização com credencial M2M. Alterações de contrato exigem
regenerar e implantar os bindings/Registry por IaC. Não execute
`SynchronizeGatewayTargets` sobre esses targets estáticos.

## O que apresentar na demo

1. Mostre os quatro Gateways com Policy em `ENFORCE`.
2. Consulte C003 passando pela plataforma: Retail, Transaction e Lending.
3. Execute `whoami` nas três LOBs **através da plataforma**. O Runtime verifica
   assinatura/JWKS e retorna um hash de `tid:oid`, `aud` e `azp`, sem devolver o token.
   Compare com o JWT inicial: mesma pessoa, ator local e audiência final corretos.
4. Consulte `get_profile(C007)`: o contrato nega na plataforma.
5. Consulte `get_profile(C008)`: a plataforma permite; o contrato Retail nega.
6. Envie o JWT da plataforma diretamente ao Gateway Retail: espera-se HTTP 401/403.
7. Opcionalmente faça uma pergunta ao agente Strands, usando as capacidades do
   Registry. Os nomes incluem duas camadas, por exemplo
   `retail___backend___get_profile`.

Os casos C007/C008 são **regras didáticas restritas a `get_profile`**, não uma regra
geral de isolamento desses clientes. Outras tools de consulta podem acessar seus
fixtures. Escritas ficam sem `permit` e sem IAM de escrita; `delete_customer`
continua um stub não destrutivo com `forbid`.

## Evidências e limites

`LOCAL_CEDAR_ONLY` prova a lógica das Policies, não troca tokens nem chama AWS.
`OFFLINE_PREPARATION` valida a execução local do notebook. `AWS_READ_ONLY`
verifica configuração. `AWS_LIVE` identifica chamadas realmente realizadas.

Uma negativa só é classificada como Policy quando a resposta reporta
`tool call not allowed`. Erros genéricos de OAuth, rede ou MCP ficam
`UNCLASSIFIED_ERROR`. Mesmo uma negativa de Policy requer os logs das contas
para atribuir o salto e comprovar que o backend não executou.
O notebook fornece os quatro log groups; correlacione a janela de execução,
Gateway/target e decisão em CloudWatch. Não exporte tokens ou logs brutos com dados.

A restrição de Runtime ao workload **do Gateway local** é configuração verificável
no preflight. Um teste de bypass com token válido para aquele Runtime, mas sem o
workload autorizado, ainda precisa de ensaio controlado. Rejeitar uma audiência
errada não comprova sozinho essa proteção adicional.

O notebook não foi implantado neste ambiente. A composição Gateway→Gateway,
os dois OBOs gerenciados, o encaminhamento de Authorization ao MCP e as decisões
em serviços AWS precisam ser ensaiados nos sandboxes. Nenhum resultado local
deve ser apresentado como evidência dessas integrações.

Para remover, use CloudFormation na ordem inversa: Registry → bindings da plataforma
→ bindings das LOBs → backends → Gateways → bootstrap. Tabelas/fixtures e buckets
são retidos. Identidades/segredos/KB seguem os stacks de seus proprietários.

A seção **Cleanup** do notebook usa `scripts/cleanup.py --scenario federation`.
O wrapper prepara um plano somente leitura e exige confirmação do ARN do stack
para executar sua remoção. A célula seguinte limpa as variáveis locais.
Veja o [procedimento completo](../cleanup.md).

## Referências consultadas

- [Artigo de origem: agente multi-account com Gateway e MCP](https://aws.amazon.com/blogs/machine-learning/build-a-multi-account-ai-agent-with-agentcore-gateway-and-mcp/)
- [MCP server targets: OAuth/OBO, schemas estáticos e Gateway como destino](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html)
- [Identity: On-Behalf-Of token exchange](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html)
- [Policy: principais OAuth, claims como tags e match de scopes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/example-policies-principal.html)
- [Runtime: encaminhamento de headers](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-header-allowlist.html)
- [Notebooks oficiais AgentCore](https://github.com/awslabs/agentcore-samples)
