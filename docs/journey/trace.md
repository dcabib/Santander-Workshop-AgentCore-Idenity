# Prova de ponta a ponta — procedimento de ensaio

O notebook exporta observações reais em `evidence/journey-live.json` somente
quando executado na AWS. A versão local chama-se `journey-local.json` e declara
`NOT_RUN`. Nenhum resultado local deve ser copiado para a evidência live.

## Cadeia de evidências

| Etapa | Identificadores/evidência | O que confirma |
|---|---|---|
| Entrada | OID verificado convertido em `user_ref`, request UUID | Qual pessoa iniciou a chamada sem publicar seu e-mail |
| Runtime Origem | Evento `santander_journey`, agente fixo no deployment, request UUID | Qual agente hospedado executou a orquestração |
| OBO ao hub | JWT de saída verificado; `azp` do agente, mesmo tid/oid/claim mapeada | Delegação manteve a pessoa e identificou a aplicação |
| Gateway central | `hub_gateway_request_ids` reais de `x-amzn-requestid` | Liga a chamada ao log do Gateway; não é request ID do Identity |
| Conta de dados | Logs/spans com relação pai/filho ou request/trace IDs propagados | Correlaciona a fronteira B à chamada do hub |
| MCP Databricks | `identity_query_id`, `query_id`, principal comparado exatamente | A fonte recebeu a identidade esperada e executou a query identificada |
| Query history/audit | Registro do Databricks para o query ID, fonte, status e timestamp | Confirma a consulta na fonte e sua decisão de acesso |

O request ID também é enviado em `_meta` MCP. A propagação desse metadado por
todos os serviços deve ser observada, não presumida. `gateway_log_correlation_verified`
fica falso nos resultados automáticos. A aplicação não fabrica um trace ID
para apresentar uma correlação que os serviços não registraram.

Os templates entregam APPLICATION_LOGS dos três Gateways. Isso não é equivalente
a habilitar todos os traces. Para usar spans, habilite a configuração de
observabilidade da conta pelo seu IaC, conforme
[AgentCore Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html).
O notebook não altera preferências de observabilidade da conta.

## Procedimento

1. Registre início/fim do teste em UTC. Execute A/Riscos e conserve a evidência
   sanitizada. Confirme que há query ID; se o MCP omitir o ID, o trace permanece
   incompleto e precisa de associação comprovada no audit da fonte.
2. Consulte os logs dos três Gateways e do Runtime por APIs de leitura. Use os
   IDs HTTP do hub e o request UUID. Busque a relação com as chamadas da conta
   de dados; não correlacione apenas por proximidade de horário.
3. Consulte query history/audit Databricks pelo ID observado. Confirme status,
   usuário esperado e canário correto. Faça isso na interface/consulta aprovada
   pelo owner; não amplie grants de B para ler logs administrativos.
4. Guarde um registro de revisão com os IDs dos eventos/spans, query ID, fonte,
   resultado e revisor. Redija uma conclusão com a cobertura comprovada. Não
   edite booleans no notebook para contornar `PENDING_EVIDENCE`.
5. Para a negativa do hub, faça positivo antes e depois. Confirme a decisão
   específica de Policy e a ausência da chamada downstream na mesma janela,
   com cobertura de logging completa. Uma busca vazia, sem assegurar ingestão
   dos logs e correlação, não comprova “backend não executado”.
6. Repita B/Riscos. Separe a consulta de identidade permitida da consulta ao
   canário negada; a primeira deve existir no audit, a segunda pode registrar
   falha de autorização em vez de query executada.

`acceptance()` é uma verificação conservadora de completude das observações
automáticas. Ela não assina nem substitui a revisão dos logs. Até essa revisão,
o status agregado continua **PENDING_EVIDENCE**, mesmo quando os quatro resultados
de negócio estão corretos.

## Exportação para as ferramentas do cliente

Contrato mínimo: request/trace/span IDs reais, timestamps UTC, conta/domínio,
instância, agente, user_ref, tool, decisão, Policy ID quando disponível,
query ID e identificação/versionamento da fonte.

Dynatrace recebe a telemetria técnica; Watsonx.governance recebe inventário e
evidências de controle; SanEval reutiliza os casos como avaliação contínua.
Formato/transportes e conectores dependem das versões do cliente e não foram
instalados neste laboratório.
