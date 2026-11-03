# Correção da autenticação Gateway → Runtime MCP

Estado: alternativa A aprovada e implantada em 03/11/2026. Os três stacks
terminaram em UPDATE_COMPLETE. O teste do core passou contra os serviços AWS;
a execução integral dos notebooks ainda está pendente.

O stack `santander-workshop-core-bindings` chegou a CREATE_COMPLETE após a
correção Cedar. O teste real passou por preflight, negativa anônima, descoberta
MCP e consulta Lambda. A chamada `especialista___identidade_fonte` foi permitida
por Cedar e falhou ao autenticar no Runtime:

```text
Gateway request_id: 59960737-60ea-40de-b497-6e90dcefb833
Policy: ALLOW (AllowIdentityMemory)
MCP invocation failed: Authorization error when sending message

Runtime request_id: b05143c8-e659-4b00-831d-3aeb9673a5bf
HTTP 401
Transaction token required: authorizer has AllowedWorkloadConfiguration configured
```

A restrição `AllowedWorkloadConfiguration` é documentada para o target nativo
de Runtime HTTP. A agregação MCP usada nesta jornada aceita autenticação IAM
com assinatura SigV4 e não produz essa cadeia de transaction tokens.

## Alternativa A aprovada

1. Gateway mantém o authorizer Cognito e Cedar ENFORCE.
2. O target MCP usa `GATEWAY_IAM_ROLE`, serviço de assinatura `bedrock-agentcore`
   e permissão restrita ao ARN deste Runtime.
3. A resource policy do Runtime permite a role do Gateway e nega explicitamente
   as demais roles, inclusive quando tenham permissões próprias de invocação.
4. A trust policy da role é fixada no ARN exato do Gateway.
5. O interceptor valida o JWT humano e o envia em
   `X-Amzn-Bedrock-AgentCore-Runtime-Custom-User-Authorization`.
   O backend verifica assinatura, emissor, audiência e claims novamente antes
   da ACL DynamoDB. O header Authorization permanece disponível para SigV4.
6. Gateways federados continuam recebendo Authorization com JWT; a mudança
   IAM ocorre somente no salto do Gateway de domínio ao Runtime MCP.

O authorizer nativo do **Runtime MCP** passa de JWT para IAM. A validação
criptográfica do JWT humano permanece obrigatória no backend. Os agentes
HTTP e o agente RAG continuam usando authorizer JWT nativo.

O provider CloudFormation `runtime_boundary.py` gerencia a resource policy.
Seu Delete mantém a restrição até a exclusão do próprio Runtime. Não há
alterações avulsas de IAM nem remoção da proteção para liberar o teste.

Comandos propostos, somente pelo pipeline:

```bash
uv run python scripts/build_artifacts.py --banking
uv run python scripts/workshop_deploy.py gateway --execute
uv run python scripts/workshop_deploy.py backend --execute
uv run python scripts/workshop_deploy.py bindings --execute
uv run python scripts/workshop_check.py
```

Os testes devem comprovar invocação autorizada pelo Gateway, negativa direta no
Runtime, ACL independente e isolamento de Memory. Os 239 testes focados e
cfn-lint passaram; o IAM Access Analyzer ValidatePolicy retornou zero findings.
Essas verificações não substituem o aceite operacional após o deploy.

## Evidência após o deploy

`evidence/workshop-core.json` registra descoberta MCP, consulta Lambda,
identidade e consulta da fonte pelo Runtime, CreateEvent/ListEvents no Memory
e isolamento entre C e A usando o mesmo session_id.

* Entrada anônima: HTTP 401, request `5795df0c-dd37-49da-8220-0a1c0675e520`.
* Runtime direto: IAM DENY, request `9a354ae8-feba-49fa-9440-23251c5648c3`.
* Identidade humana recebida e verificada na fonte:
  request do Gateway `4c52da86-99bd-42dd-bd00-b77c056b98b0`.

O GetGatewayTarget acrescentou o header reservado
`x-amzn-bedrock-agentcore-policy-session-id` ao target com Policy. O preflight
aceita esse header específico, exige o header humano e rejeita headers extras.
Essa correção de comparação não modificou a infraestrutura.

## Alternativa B

Redesenhar a jornada com targets nativos de Runtime HTTP e JWT passthrough.
Esse caminho suporta a restrição de workload nativa, mas não agrega ferramentas:
cada target usa uma rota própria. Exigiria adaptar a descoberta e a federação
MCP das aulas.

## Referências AWS

* [Restringir o Runtime IAM à role do Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html#runtime-restrict-iam-gateway).
* [Target nativo de Runtime e comparação com agregação MCP](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-http-runtime.html).
* [Autenticação IAM para targets MCP](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-building-adding-targets-authorization.html#gateway-building-adding-targets-authorization-service-role).
* [Propagação de headers pelo interceptor](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-headers.html#gateway-headers-interceptor-propagation).
