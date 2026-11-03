# Correções de permissões do runner e da geração de rascunho

Estado: alternativa A aprovada pelo usuário em 03/11/2026 e aplicada pelo IaC.
O stack policy-draft chegou a CREATE_COMPLETE e o runner a UPDATE_COMPLETE.
As aulas 00–05 passaram em AWS_EXECUTION no build
`santander-workshop-notebooks:78e540fe-165c-4d61-a905-01f57e1f417b`.
O aceite integral e as novas verificações de correlação continuam pendentes.

A alternativa IAM/SigV4 foi implantada e passou no teste do core. As aulas 00
e 01 também passaram em CodeBuild, build
`santander-workshop-notebooks:e8beb579-394d-432b-baa1-3b7aa3fafd0a`.
O build parou na leitura de Workload Identity da aula 02, antes da inferência.

## Diagnóstico

O erro da aula 02 identifica a permissão e o recurso ausentes:

```text
AccessDeniedException — GetWorkloadIdentity
bedrock-agentcore:GetWorkloadIdentity
arn:aws:bedrock-agentcore:us-east-1:496714466045:workload-identity-directory/default
because no identity-based policy allows the action
```

O stack novo `santander-workshop-core-policy-draft` terminou em
`ROLLBACK_COMPLETE`. CloudTrail confirmou StartPolicyGeneration
(`f7eb4c54-8c5a-486f-8d7f-9f095090d5f9`) e GetPolicyGeneration. O serviço
retornou:

```text
policyGenerationId: san_draft_17ac360b0425-vf_1e0a1uw
status: GENERATE_FAILED
statusReasons: Insufficient permissions to call gateway with ID santander-workshop-core-aws-ykjmprnp1u
```

A documentação AWS exige `InvokeGateway` na role que solicita a geração para
validar as ações contra as ferramentas do Gateway. A role do provider possuía
as permissões de leitura de configuração, mas faltava essa ação.

## Alternativa A — corrigir o IaC e retomar

* Runner: permitir `GetWorkloadIdentity` e `GetWorkloadAccessToken` no diretório
  `default` da conta do workshop. As permissões dos workloads específicos
  continuam restritas aos ARNs declarados. A segunda ação atende ao fluxo M2M
  da aula 09. Nenhuma administração do diretório é concedida.
* Runner: permitir `ListPolicyGenerationAssets` para mostrar o código gerado
  na aula 05, além do estado da geração.
* Provider de rascunhos: permitir `InvokeGateway` somente no ARN do Gateway
  declarado. Não conceder CreatePolicy/UpdatePolicy ao provider.
* Provider: propagar o motivo de falha do serviço para o evento CloudFormation,
  sem imprimir payloads nem tokens.
* Recuperar apenas o stack novo de rascunho após verificar ROLLBACK_COMPLETE,
  descrição do template e remoção dos recursos. O único DELETE_SKIPPED aceito
  é o marcador `failed-<hash>` desse custom resource; rascunhos gerados,
  recursos alheios ou recursos ainda existentes impedem a recuperação.

A geração que falhou permanece no histórico do serviço, cuja API não oferece
DeletePolicyGeneration. As roles e a Lambda do stack falho já foram removidas
pelo rollback. Os demais stacks não precisam ser recriados.

Comandos aprovados:

```bash
uv run python scripts/build_artifacts.py --banking
uv run python scripts/workshop_deploy.py policy-draft --execute --recover-failed-create
uv run python scripts/workshop_runner.py deploy --execute --labs 00 01 02 03 04 05
uv run python scripts/workshop_runner.py run --execute
```

Gateway continua Cognito + Cedar ENFORCE. A entrada do Runtime MCP continua
restrita à role do Gateway, e o backend continua verificando o JWT humano e
as ACLs. Não há edição avulsa de IAM nem publicação automática do rascunho.

## Alternativa B — revisar o diff antes da aplicação

Manter essas correções sem deploy enquanto o usuário revisa as permissões e
a recuperação proposta. O aceite completo permanece pendente.

Editar roles diretamente criaria divergência do IaC e não faz parte das
alternativas executadas. A confirmação é exigida pelo protocolo de bloqueio
do AGENTS.md fornecido nesta conversa: “STOP. Do not improvise” e “Wait for
the user's reply”.

Referência: [permissões de Policy e validação no Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-permissions.html#policy-permissions-error-create-policy-invoke).
