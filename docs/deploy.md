# Implantar a bancada dos módulos 00–06, 08, 10 e 13

Os primeiros módulos separam os conceitos para facilitar a observação local.
Este guia permite exercitar seus equivalentes na AWS: um supervisor na conta
A, um hub de ferramentas na conta C e um especialista Fraude na conta B.
O Gateway central aplica Policy, Identity delega chamadas e Registry publica
as capacidades aprovadas.

Na [jornada de aprendizagem](jornada.md), a primeira implantação sugerida é o
[laboratório 09, em uma conta](terraform/README.md). Use este ambiente quando
quiser aprofundar os módulos iniciais e a topologia apresentada no notebook 10.
Ele é diferente dos ambientes dos laboratórios 10, 11, 12 e 14.

## Como ler o fluxo

O usuário entra por uma aplicação de agente. O token destinado ao Gateway
identifica a pessoa e a aplicação chamadora. O hub autoriza a ferramenta;
para Graph ou Fraude, Identity obtém uma credencial destinada à API seguinte.
A busca no Registry usa IAM/STS, enquanto a chamada de ferramenta usa JWT.
Esses caminhos têm credenciais e responsabilidades diferentes.

## 1. Pré-requisitos

Prepare uma região com disponibilidade dos componentes, contas A/C/B, perfis AWS,
role do instrutor, tenant Entra e três usuários de teste: Riscos, Riscos+Fraude
e acesso à aplicação sem grant na fonte. Os OIDs dos usuários são entradas do
stack, sem descoberta de pessoas em diretórios produtivos.

O operador precisa de permissão para os stacks CloudFormation/IAM/AgentCore,
log delivery e uploads no bucket de artefatos. Para o módulo Entra opcional,
precisa das permissões de gerenciamento de aplicações e consentimento delegado
no tenant de teste. O helper de primeiro OBO exige `GetSecretValue` no segredo
do agente selecionado. O Gateway só recebe acesso ao seu próprio segredo.

As mudanças de infraestrutura passam pelos templates e pelo pipeline deste
projeto. As células de exercício usam os recursos já implantados. Uma falha de provider, região ou permissão deve ser
diagnosticada por leitura e corrigida no IaC. Não usar um SDK avulso como fallback.

## 2. Preparar as identidades Entra

Use outputs do IaC existente ou o [módulo Entra](../infra/entra/README.md).
O módulo fixa os access tokens em v2, portanto:

- `DiscoveryUrl`: URL v2 do tenant.
- `GatewayAudience`: **GUID** da aplicação Gateway, conforme `aud` do token v2.
- `CallerClaim`: `azp`.
- `SupervisorClientId`, `RisksClientId`, `FraudClientId`: aplicativos confidenciais.
- `GatewayClientId`: middle tier que troca o token para Graph/Fraude.
- `EntraSecretArn`: segredo JSON com chave `client_secret`, gerido pelo Terraform.

Não confundir o GUID da audiência com o scope `api://<GUID>/access_as_user`.
O caminho v1 do Gateway pode ser parametrizado separadamente, mas os Runtimes
e o módulo Entra entregues foram preparados para v2.

O instrutor autentica um usuário no frontend e executa o primeiro OBO:

```python
from santander_demo.cloud import login_confidential_agent
token = login_confidential_agent(config)
# Não imprimir token; ele permanece em memória.
```

A asserção inicial destina-se à API do agente. O agente usa seu segredo para obter
o token do Gateway; só então `azp` representa o agente confidencial. O módulo
não concede ao frontend público acesso delegado direto ao Gateway.

## 3. Construir o artefato local

```bash
uv sync --frozen
uv run python infra/generate.py
uv run cfn-lint infra/templates/*.json
uv run pytest -q
uv run python scripts/build_artifacts.py
```

O build gera `build/workshop.zip` para Linux ARM64/Python 3.12 e
`build/artifacts.json` com SHA-256. As dependências vêm do `uv.lock`.
Lambda, providers e Runtimes usam esse artefato. Nenhum build usa AWS.

## 4. Entender a ordem dos stacks

| Ordem | Conta | Template | Entradas e resultado |
|---|---|---|---|
| 1 | A, B e C | `bootstrap` | Bucket privado, criptografado e versionado em cada conta. |
| 2 | A | `origin` com `EnableRuntime=false` | Cria role estável do supervisor; permite STS somente para o Consumer em C. |
| 3 | C | `hub` com `EnableFraud=false` | Gateway, Lambda, Graph OBO, Policy e logs. |
| 4 | B | `fraud-runtime` | Código MCP; audiência Fraude; cliente Gateway; workload restrito ao ARN do Gateway. |
| 5 | C | atualização de `hub`, `EnableFraud=true` | Inclui MCP target com endpoint/schema, OBO e policy Fraude. |
| 6 | C | `registry` | Catálogo, roles, descriptors e fixtures de estados. Confia no role de A já existente. |
| 7 | A | atualização de `origin`, `EnableRuntime=true` | Instancia supervisor com configuração do hub e role criado na etapa 2. |
| 8 (opcional) | C | `policy-draft` | Gera rascunho a partir de RawText para o notebook 05; não publica políticas. |

Para Registry, aprovar o change set significa aprovar **os descriptors concretos
incluídos nele**. Os recursos `Capability*Approval` aprovam somente esses registros.
Publisher e Approver têm IAM distinto, embora um administrador do pipeline possa
implantar ambas as funções. Em produção, separe os aprovadores de change set.

## 5. Preparar os parâmetros

Arquivos locais `config/local.<stack>.json` são objetos de strings e são ignorados
pelo Git. Exemplos completos, ainda com placeholders, estão em `config/parameters/`.
Substitua os valores antes de chamar o pipeline. O template exige todos os campos
sem default; um placeholder não é um identificador válido.

Parâmetros específicos:

- **origin inicial:** Project, HubAccount, ArtifactBucket, DiscoveryUrl,
  GatewayAudience, SupervisorClientId, EnableRuntime=false.
- **hub:** os outputs de identidade, ArtifactBucket, LambdaKey (preenchido pelo
  pipeline), RisksUserOid, BothUserOid, NoGrantUserOid. Na segunda aplicação,
  FraudEndpoint/FraudScope e EnableFraud=true.
- **fraud-runtime:** ArtifactBucket, RuntimeKey (pipeline), DiscoveryUrl,
  RuntimeAudience (GUID Fraude API), GatewayClientId e GatewayArn.
- **registry:** ArtifactBucket, ProviderKey (pipeline), GatewayUrl,
  OperatorRoleArn (role existente do instrutor) e SupervisorRoleArn (output de A).
- **origin final:** mesmos parâmetros mais RuntimeKey (pipeline),
  EnableRuntime=true e WorkshopConfig (JSON serializado como string).
- **policy-draft:** ArtifactBucket, ProviderKey (pipeline), PolicyEngineId,
  PolicyEngineArn, GatewayArn e RawText contendo a intenção/claims/ações exatas.
  O output PolicyGenerationId é lido pelo notebook 05 via `POLICY_GENERATION_ID`.

O endpoint MCP do Runtime usa o ARN percent-encoded:

```python
from urllib.parse import quote
fraud_endpoint = (
    f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/"
    f"{quote(fraud_runtime_arn, safe='')}/invocations?qualifier=DEFAULT"
)
```

O target Fraude fornece o schema em IaC. Isso evita uma sincronização inicial
que precisaria de credencial M2M quando nenhum usuário está presente.

Use os outputs reais e [aws.example.json](../config/aws.example.json) para montar
`config/local.json`. No `WorkshopConfig` do Runtime supervisor:

- `profile` deve ser `null`, pois o Runtime usa seu execution role;
- campos de login/segredos do instrutor podem ser `null` quando opcionais;
- durante a primeira criação, `supervisor_runtime_arn` pode ser um marcador;
  após obter o output, atualizar o JSON local e o stack via IaC;
- nunca incluir tokens, valores de segredo ou chaves.

## 6. Revisar e aplicar

Substitua os identificadores pelos valores do seu ambiente:

```bash
uv run python scripts/deploy.py hub \
  --profile PERFIL_C --region REGIAO --account CONTA_C \
  --stack santander-hub --parameters config/local.hub.json
```

Por padrão, o script valida a conta do perfil, publica o artefato identificado
por hash no bucket IaC e cria um **change set sem executar**. Examine as mudanças.
Acrescente `--execute` para executar pelo mesmo pipeline.

O script não cria/atualiza recursos AgentCore via SDK. Os providers Registry são
invocados pelo CloudFormation e mantêm IDs/estado no stack.

Obtenha os outputs por leitura:

```bash
aws --profile PERFIL_C --region REGIAO cloudformation describe-stacks \
  --stack-name santander-hub --query 'Stacks[0].Outputs'
```

O log group Fraude é descoberto por `logs describe-log-groups` na conta B depois
da criação do Runtime; não inventar um nome antes de verificar. Preencha a
configuração com o resultado.

## 7. Executar os exercícios na AWS

Defina `WORKSHOP_MODE=aws` **antes de iniciar o kernel**. Execute o preflight.
Não execute todos os notebooks de forma não interativa em modo AWS: eles pedem
credenciais de teste em memória nos pontos de invocação.

```bash
uv run santander-demo preflight --config config/local.json
```

Depois siga os [pontos de verificação](validacao.md). Compare casos permitidos
e negados e observe a fronteira responsável. Uma falha de integração mantém
o item pendente.
Não trocar ENFORCE por LOG_ONLY nem remover audience/workload restrictions.

## 8. Registry: atualização, rollback e remoção

Esta bancada compartilhada ainda usa o namespace preview `bedrock-agentcore`
para o Registry, com descontinuação anunciada pela AWS para 30/10/2026.
O [laboratório 07](registry/README.md) usa o namespace atual `agent-registry`
em um ambiente independente. Ele não migra automaticamente os catálogos desta
bancada; consulte o [guia de migração](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/registry-faq.html).

Esta implementação gerencia Registry por custom resources do CloudFormation.
[registry_handler.py](../infra/providers/registry_handler.py) implementa:

- token idempotente derivado do stack/recurso/propriedades;
- Create e Update por substituição quando o conteúdo muda, mantendo o anterior
  durante o rollback;
- submissão e decisão em recursos separados, com roles diferentes;
- polling limitado e erro em estado `*_FAILED`;
- Delete idempotente, limitado ao ID físico registrado;
- decisão já aplicada não é revertida por Delete da aprovação; remover a
  capacidade exige remover/substituir o registro;
- alterar APPROVED → REJECTED exige nova versão do registro, não reescrita silenciosa.

Um catálogo substituído só é removido após seus registros, pelas dependências do
stack. Revise mudanças de nomes/versão: elas podem criar novos registros e afetar
a propagação da busca.

## 9. Limpeza

Todos os notebooks incluem limpeza de variáveis locais e uma célula de remoção
opcional pelo wrapper `scripts/cleanup.py`. O padrão desse wrapper é um plano
somente leitura. Consulte [cleanup.md](cleanup.md) para preparar e executar
uma remoção com a conta, o template e o ARN do stack conferidos.

O histórico de geração de `policy-draft` usa `Retain`, pois a API consultada não
expõe `DeletePolicyGeneration`. Preserve o output/stack como registro de autoria;
um rascunho não concede acesso. Não confundir a remoção do stack com a exclusão
desse histórico no serviço.

Remova os stacks pelo CloudFormation na ordem: origin Runtime, registry,
hub sem target Fraude, fraud-runtime, hub, origin role. Mantenha o bucket de
artefatos e logs necessários enquanto revisar as evidências. Os buckets
bootstrap usam `Retain`; não esvaziar buckets/versionamento automaticamente.

Para as aplicações/segredos de laboratório geridos pelo módulo Entra, revisar
`terraform plan -destroy` no mesmo backend e executar pelo Terraform quando
autorizado. Não destruir identidades ou infraestrutura compartilhada do cliente.

## Aprofundar

- [OBO e token exchange no Identity](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html)
- [Targets MCP no Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html)
- [Change sets do CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html)
- [Guia de conceitos](conceitos.md)
