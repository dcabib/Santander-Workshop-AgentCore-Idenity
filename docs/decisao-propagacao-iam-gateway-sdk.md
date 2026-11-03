# Aula 01 — criação do target e AssumeRole

Status em 03/11/2026: **alternativa A autorizada e concluída; aula 01 passou na AWS**.

A definição Lambda sem tags foi aprovada e aplicada. A função ficou ativa,
o Gateway ficou READY e as chamadas sem token e com token inválido retornaram
HTTP 401 com Request IDs AWS.

`CreateGatewayTarget` retornou:

```text
ValidationException: Gateway service is not authorized to perform AssumeRole
on Gateway role. Update trust policy and retry
```

O diagnóstico somente de leitura confirmou:

* O Gateway usa a role `santander-6825d3096100-gateway`.
* A trust policy aceita `bedrock-agentcore.amazonaws.com`, restringe
  `aws:SourceAccount` à conta `456332459064` e `aws:SourceArn` ao ARN exato
  do Gateway `santander-6825d3096100-gateway-bgamhbmu8p`.
* A policy de execução permite `lambda:InvokeFunction` somente na função
  `santander-6825d3096100-customer-risk`.
* Não há permissions boundary nessa role e a lista de targets está vazia.

A trust policy foi restringida imediatamente antes da tentativa. Propagação
IAM é uma hipótese, não uma causa confirmada. O diagnóstico não comprova que
o serviço já consegue assumir a role.

## Conferência adicional do diagnóstico

A [documentação de permissões do Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-prerequisites-permissions.html)
orienta usar `bedrock-agentcore.amazonaws.com`, `aws:SourceAccount` e,
depois da criação, o ARN do Gateway em `aws:SourceArn`. A configuração lida
está de acordo com essa orientação; não encontramos uma justificativa para
ampliar a trust policy.

O [helper do workshop de referência](https://github.com/awslabs/agentcore-samples/blob/7282ec3b839736d55d199f4c726136c342e33b3c/06-workshops/02-AgentCore-gateway/utils.py)
usa um ARN mais amplo e uma espera após criar a role. Isso não comprova que
o ARN exato seja incompatível e não justifica copiar suas permissões amplas.

A tentativa de consultar `cloudtrail:LookupEvents` em `us-west-2` foi negada
por ausência de permissão na role do editor. Não foi possível obter o evento
de AssumeRole para confirmar a causa. Essa leitura não modificou recursos e
não originou um pedido adicional de alteração de permissões.

## A — Repetir a mesma criação após propagação, sem ampliar a trust policy

A revisão em `scripts/sdk_gateway_lesson.py`:

1. Consulta as policies antes de gravar. Na retomada, não regrava policies
   idênticas nem reinicia a propagação da trust policy já correta.
2. Repete somente a mensagem específica de AssumeRole em
   `CreateGatewayTarget`, até 12 tentativas, com intervalos de cinco segundos.
   A duração inclui também a latência das chamadas AWS.
3. Mantém o mesmo payload e client token de idempotência. Confere novamente
   a trust policy após o erro e não a amplia.
4. Para se a policy divergir, se ocorrer outro erro ou se as tentativas acabarem.

Os testes verificam o limite, a igualdade dos parâmetros, a ausência de
reescrita da trust policy e a interrupção imediata para outras negativas.
O usuário autorizou essa retomada. A revisão foi enviada ao ambiente de
notebooks e a aula 01 foi iniciada com SHA-256
`af6138dea00bc4083933ef99166c22380144007a9cd8c9aaef9516501f45d110`.
O target `2RQCVH3IJU` ficou READY. O usuário autenticado descobriu a ferramenta
e a invocou via MCP; a Lambda retornou Request ID
`aaf0aa76-06a3-443e-b7bf-ea7f30354c76`. A trust policy e a permissão de
invocação permaneceram restritas aos mesmos recursos. O sucesso da retomada
é compatível com a hipótese de propagação, mas não identifica a causa pelo
CloudTrail.

## B — Manter a execução parada e investigar com o responsável pela conta

Investigar o AssumeRole do serviço e as restrições efetivas antes de outra
tentativa. Não removeremos `SourceAccount`, não ampliaremos `SourceArn` e não
trocaremos a role para contornar a negativa sem uma decisão específica.

O bloqueio desta decisão foi resolvido pela retomada autorizada. Gateway,
Lambda e target permanecem registrados para as próximas aulas.
