# Decisões propostas para a Sessão 1

**Proposta para o piloto: complementar a stack Databricks.** AgentCore controla
agentes/tools e os pontos de entrada AWS; Unity Catalog continua autorizando o
dado como o usuário. A troca de uma camada depende do ensaio, e não apenas de
conseguir retornar uma consulta. Esta é uma proposta técnica a deliberar com o
cliente, não uma decisão já acordada.

## Managed Gateway versus adapter em Runtime

| Critério | MCP direto no AgentCore Gateway — notebook 12 | Adapter próprio em Runtime |
|---|---|---|
| OBO | Identity e target `TOKEN_EXCHANGE`; depende do modo público nativo habilitado | Código faz a troca suportada pelo IdP e chama o MCP; equipe mantém tokens, retries e protocolos |
| Autorização | Cedar por usuário/aplicação/tool e parâmetros | Gateway continua recomendado na entrada; adapter não deve transformar prompt em autorização |
| Databricks | Endpoint aprovado; grants reais permanecem na fonte | Mesma obrigação de preservar humano e verificar `current_user()` |
| SQL | Nesta demo, queries canário exatas | Pode oferecer tools de negócio, evitando SQL livre; exige contrato e testes |
| Operação | Menos código de proxy; verificar limites e roteamento cross-cloud | Maior flexibilidade de transformação; maior responsabilidade de manutenção |
| Quando escolher | Caminho principal se os quatro ensaios e trace passarem | Requisito que o managed target não atenda, com justificativa e IaC próprios |

O Gateway autentica sua entrada e autentica a saída segundo o protocolo do
target. O Databricks valida seu token e autoriza o dado. Isso não elimina
firewalls/egress, políticas do workspace, disponibilidade do warehouse ou
admin consent. O cenário público autenticado não prova rota privada Azure/AWS.

## Onde fica cada responsabilidade

| Responsabilidade | Camada proposta | Prova/limite |
|---|---|---|
| SSO e grupos corporativos | Entra, provisionamento/SCIM e gestão BDAG do cliente | OIDs e memberships reais; não aceitar grupos passados no prompt |
| Usuário + agente + tool | Policy do Gateway central | `azp` de cada Runtime é diferente; negativo troca somente o agente |
| Entrada do domínio | Gateway + Policy da conta B | Caller da plataforma e allowlist local; autonomia do domínio |
| Delegação | AgentCore Identity / Entra / federation Databricks | Prova SQL exata; sem fallback para conta compartilhada |
| Dados | Unity Catalog + grants/BDAGs | A permite, B nega, no mesmo canário |
| Catálogo | Registry central; owner/version/instance por capacidade | Aprovação não concede execução. Consumer cross-account somente leitura |
| Proteção de conteúdo/modelos | Neural Trust ou Bedrock Guardrails conforme padrão Santander | Este lab não substitui Neural Trust nem integra seu endpoint |
| Trace técnico | AgentCore logs/spans + Dynatrace | Propagar correlação e correlacionar com query ID; conector Dynatrace a configurar |
| Governança | Watsonx.governance | Consumir evidências e inventário conforme contrato do cliente; sem conector entregue |
| Avaliação contínua | SanEval | Usar os quatro casos positivos/negativos como suíte de regressão; sem integração SanEval entregue |

## QPM, TPM e orçamento mensal

O código `governance.py` e a seção 8 do notebook demonstram o contrato de
contagem por **agente + tool**, incluindo negação e mudança de janela. São
reservas e custos sintéticos, sem medição de LLM ou cobrança de cloud.

| Controle | O que a documentação atual sustenta | Decisão proposta |
|---|---|---|
| Quota Gateway | Há quotas por Gateway/conta e APIs. Elas protegem o serviço | Não apresentar como contrato comercial de QPM/TPM por agente/tool |
| Cedar normal | Decide sobre a chamada atual | Não representa um contador temporal |
| Policy temporal/Dogwood | `count`/`sum`, histórico **por sessão**, janela máxima **24h** | Útil para ordem/limites de uma conversa; não é budget mensal global |
| Troca de sessão | Uma nova sessão inicia novo histórico temporal | Não usar esse mecanismo sozinho para quota que deve sobreviver à troca de sessão |
| Multi-conta | A documentação atual não suporta propagação temporal cross-account/cross-region | O notebook 12 usa Cedar pontual; não promete contador temporal fim a fim |
| QPM/TPM e budget do cliente | O HTML relata controles no Databricks AI Gateway | Preservá-los enquanto confirmar endpoint, dimensões suportadas e medição real |
| Tokens e custos de modelos | Medição no gateway/model provider usado pelo cliente, incluindo Neural Trust quando aplicável | Somar consumo em store confiável, reconciliar reservas e uso; não confiar em valores declarados pelo agente |

Para aceitar um controle global novo, o piloto precisa medir duas sessões
simultâneas, dois workers, reinício, concorrência, retries idempotentes, fronteira
de minuto/mês e falha do contador. Precisa ainda esclarecer quais tokens entram
no TPM e qual tarifa converte uso em custo. O contrato em memória do notebook
não atende sozinho esses critérios produtivos.

Fontes: [Policy temporal](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-temporal.html)
e [quotas AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html),
consultadas em 09/10/2026. A disponibilidade temporal regional não altera seus
limites de sessão/conta.

## Endpoint Databricks e decisão de substituir

Na documentação Azure consultada, os MCPs passam pelo **Unity Gateway** usando
`/ai-gateway/mcp-services/...`. `system.ai.dbsql` é beta; `system.ai.genie_one_mcp`
é GA nessa documentação. Os endpoints legados continuam disponíveis.

O endpoint `/api/2.0/mcp/sql` **bypassa Unity Gateway**: não oferece, por essa
rota, seus registros de tracing e controles MCP de Unity Catalog, embora as
permissões do warehouse/tabela continuem aplicadas. Portanto, sucesso no endpoint
legado não demonstra equivalência aos controles do desenho original.

O notebook 12 implementa DBSQL, porque permite verificar SQL/identidade/grant
deterministicamente. Genie permanece uma extensão: requer space, schemas,
scopes e critérios próprios; não se troca apenas a URL no mesmo contrato SQL.
O cliente deve confirmar qual produto/versão chama de “AI Gateway” em seu desenho
e quais controles estão efetivamente habilitados.

## Contrato externo do K2

O produto e Santalk/LangGraph permanecem intactos. Cada instância poderá consumir
o Gateway central com um token delegado emitido para sua própria aplicação.
O contrato exige:

1. Aplicação/identidade distinta da instância, correlacionada a owner e caso de uso.
2. JWT validado, OBO para o hub e credenciais obtidas por Identity; nunca nome de
   agente ou OID recebido no prompt como substituto de identidade.
3. Descoberta somente de records APPROVED, com versão e endpoint permitidos.
4. Request ID e contexto de trace sem bearer/PII em logs.
5. Roteamento por tool, com grants de fonte preservados e erros propagados.

Os dois agentes determinísticos são substitutos de demonstração. Não há conector
do K2 implementado nem migração de seu estado para Runtime.
