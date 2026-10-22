# Referências de notebooks — workshop Santander

**Data da análise:** 09/10/2026.  
**Repositório:** [awslabs/agentcore-samples](https://github.com/awslabs/agentcore-samples).  
**Commit consultado:** [`2747451473d1fadbba18f5aee0524e533e3c2b2e`](https://github.com/awslabs/agentcore-samples/commit/2747451473d1fadbba18f5aee0524e533e3c2b2e), de 08/10/2026.  
**Plano correspondente:** [demo e workshop](plano-demo-workshop-santander.md).

Os links abaixo apontam para arquivos `.ipynb` na versão consultada. As notas resultam da leitura das células relevantes de código e Markdown; outputs salvos nos notebooks não foram tratados como prova de execução no ambiente Santander. Nenhum notebook foi executado nesta preparação.

## Seleção principal

A sequência recomendada de leitura/adaptação é **G1/G2 → I5 → I4 → P1/P3 → P2 → R1/R2 → R3 → G5**. I1/I2 ajudam a explicar autenticação M2M. Databricks entra como extensão para fechar o requisito de identidade até o dado.

Cada notebook Santander do plano combina trechos dessas referências. Não é um compromisso de executar integralmente todos os exemplos da AWS.

## Identity

### I1 — 1 Entra ID Inbound Auth.ipynb

**Notebook:** [1 Entra ID Inbound Auth.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/03-AgentCore-identity/08-IDP-examples/EntraID/1%20Entra%20ID%20Inbound%20Auth.ipynb)  
**Uso:** Comparação.  
**Seções úteis:** Learning Objective 2; MSAL; invocação do Runtime.

Entra inbound no Runtime. A célula MSAL usa acquire_token_for_client: demonstra aplicação/M2M, apesar do título da seção mencionar authorization code.

### I2 — 2 Entra ID with AgentCore Gateway.ipynb

**Notebook:** [2 Entra ID with AgentCore Gateway.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/03-AgentCore-identity/08-IDP-examples/EntraID/2%20Entra%20ID%20with%20AgentCore%20Gateway.ipynb)  
**Uso:** Base de inbound.  
**Seções úteis:** Learning Objective 2; Learning Objective 3.

Entra inbound no Gateway com target Lambda. O token é obtido com client_credentials; adaptar para usuário quando a demonstração exigir delegação.

### I3 — 3 Entra ID with AgentCore Gateway Auth Code Flow.ipynb

**Notebook:** [3 Entra ID with AgentCore Gateway Auth Code Flow.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/03-AgentCore-identity/08-IDP-examples/EntraID/3%20Entra%20ID%20with%20AgentCore%20Gateway%20Auth%20Code%20Flow.ipynb)  
**Uso:** Complemento.  
**Seções úteis:** Create Identity Provider; Validate locally; OneNote Integration Agent.

USER_FEDERATION e consentimento 3LO. Reaproveitar provider/callback e reduzir o destino a uma leitura de perfil de teste; o original escreve no OneNote.

### I4 — runtime_with_entra_id_obo_and_mcp.ipynb

**Notebook:** [runtime_with_entra_id_obo_and_mcp.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/03-AgentCore-identity/13-entra-obo-mcp-runtime/runtime_with_entra_id_obo_and_mcp.ipynb)  
**Uso:** Principal — Identity.  
**Seções úteis:** Architecture; Steps 3–9; Security considerations.

Usuário → agente → MCP → Graph. Transporte MCP usa identidade M2M e a chamada Graph usa token OBO em header separado. Comprovar ambos os papéis ao adaptar para domínios/contas.

### I5 — obo_token_exchange_microsoft.ipynb

**Notebook:** [obo_token_exchange_microsoft.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/02-AgentCore-gateway/18-Outbound_Auth_OBO_Microsoft/obo_token_exchange_microsoft.ipynb)  
**Uso:** Principal — Identity + Gateway.  
**Seções úteis:** Steps 2–5; Compare User Token vs OBO Token.

Custom OAuth2 provider com JWT_AUTHORIZATION_GRANT, target com TOKEN_EXCHANGE e requested_token_use=on_behalf_of. Focar no Graph /me e em claims sanitizadas.

## Policy

### P1 — AgentCore-Policy-Demo.ipynb

**Notebook:** [AgentCore-Policy-Demo.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/08-AgentCore-policy/01-Getting-Started/AgentCore-Policy-Demo.ipynb)  
**Uso:** Principal — Policy.  
**Seções úteis:** Steps 3–4: Policy Engine, Cedar e ALLOW/DENY.

Associar o engine ao Gateway em ENFORCE; adaptar limite de coverage_amount para parâmetros da consulta sintética. Retirar fallback de ignorar findings e verificar negação sem permit aplicável.

### P2 — NL-Authoring-Policy.ipynb

**Notebook:** [NL-Authoring-Policy.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/08-AgentCore-policy/02-Natural-Language-Policy-Authoring/NL-Authoring-Policy.ipynb)  
**Uso:** Principal — autoria.  
**Seções úteis:** Generate policy from natural language; findings; criação a partir do Cedar gerado.

Gerar, revisar e testar políticas. Usa a base de P1. A promoção deve passar pelo pipeline; findings precisam ser tratados.

### P3 — policy_for_agentcore_tutorial.ipynb

**Notebook:** [policy_for_agentcore_tutorial.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/08-AgentCore-policy/03-Fine-Grained-Access-Control/policy_for_agentcore_tutorial.ipynb)  
**Uso:** Principal — autorização fina.  
**Seções úteis:** Parts 4–8: principal tags, department, groups, principal ID e condições combinadas.

Adaptar Cognito M2M/trigger para claims reais do Entra. Revisar matching de grupos, semântica de sub e a função que reconfigura o authorizer para Cognito.

## Gateway

### G1 — 01-gateway-target-lambda-oauth.ipynb

**Notebook:** [01-gateway-target-lambda-oauth.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/02-AgentCore-gateway/01-transform-lambda-into-mcp-tools/01-gateway-target-lambda-oauth.ipynb)  
**Uso:** Principal — fundamento.  
**Seções úteis:** Gateway OAuth inbound; Lambda target; MCP client.

Schema de tools e IAM outbound para Lambda. Trocar pedidos/e-commerce por consultar_risco com dados sintéticos e eliminar a impressão do token completo.

### G2 — 01-mcp-server-target.ipynb

**Notebook:** [01-mcp-server-target.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/02-AgentCore-gateway/05-mcp-server-as-a-target/01-mcp-server-target.ipynb)  
**Uso:** Principal — integração MCP.  
**Seções úteis:** Steps 3–5: Runtime MCP, outbound auth, target e tools.

Conectar MCP existente e verificar nome target___tool. Separar autenticação de aplicação da delegação de usuário. Prompts/resources e conflitos de URI são opcionais.

### G3 — Lab-02-diagnostics-agent.ipynb

**Notebook:** [Lab-02-diagnostics-agent.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/02-AgentCore-gateway/12-agents-as-tools-using-mcp/Lab-02-diagnostics-agent.ipynb)  
**Uso:** Complemento de G5.  
**Seções úteis:** Steps 7–10: agente Lambda, Gateway e invocação.

Padrão de agente exposto como tool. Sua infraestrutura de diagnóstico não é necessária ao caso Santander; adaptar apenas o contrato do especialista.

### G4 — Lab-03b-remediation-agent-fgac.ipynb

**Notebook:** [Lab-03b-remediation-agent-fgac.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/02-AgentCore-gateway/12-agents-as-tools-using-mcp/Lab-03b-remediation-agent-fgac.ipynb)  
**Uso:** Comparação de arquitetura.  
**Seções úteis:** Personas; interceptor; testes SRE/Approver.

Autorização por Lambda interceptor. Usar para entender o exemplo G5 e a migração para Policy; não adotá-lo como implementação principal da autorização Santander.

### G5 — Lab-05-multi-agent-orchestration.ipynb

**Notebook:** [Lab-05-multi-agent-orchestration.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/02-AgentCore-gateway/12-agents-as-tools-using-mcp/Lab-05-multi-agent-orchestration.ipynb)  
**Uso:** Principal — composição.  
**Seções úteis:** Central Gateway; targets; supervisor local.

Orquestra especialistas por MCP. Depende dos Labs 02, 03a, 03b e 04. O fluxo mistura IAM/M2M e interceptor; não comprova OBO nem multi-conta completo.

### G6 — 01-gateway-observability.ipynb

**Notebook:** [01-gateway-observability.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/02-AgentCore-gateway/06-gateway-observability/01-gateway-observability.ipynb)  
**Uso:** Apoio — evidências.  
**Seções úteis:** Application logs; trace delivery; invalid token; agent traces; CloudTrail.

Configurar telemetria via IaC e reaproveitar consultas/evidências. Instrumentação de Gateway não garante trace completo dentro do Databricks ou outros sistemas externos.

### G7 — 02-cross-account.ipynb

**Notebook:** [02-cross-account.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/02-AgentCore-gateway/16-vpc-egress/02-self-managed-lattice/02-cross-account.ipynb)  
**Uso:** Condicional — rede.  
**Seções úteis:** Cross-Account via AWS RAM; Steps 3–6.

Gateway em A acessa API Gateway privada em B via VPC Lattice/RAM. Usa API key. Não é uma demonstração de delegação de usuário entre agentes.

### G8 — 01-gateway-search.ipynb

**Notebook:** [01-gateway-search.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/02-AgentCore-gateway/03-search-tools/01-gateway-search.ipynb)  
**Uso:** Opcional — busca de tools.  
**Seções úteis:** Fundamentals; built-in Gateway semantic search tool.

Busca x-amz-bedrock-agentcore-search dentro do Gateway. Contrastar responsabilidades com Registry. Não reproduzir centenas de tools nem prometer o ganho de latência do exemplo.

## Registry

### R1 — getting-started-registry-end-to-end.ipynb

**Notebook:** [getting-started-registry-end-to-end.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/10-Agent-Registry/00-getting-started/end-to-end/01-registry-end-to-end/getting-started-registry-end-to-end.ipynb)  
**Uso:** Principal — governança.  
**Seções úteis:** Steps 1–6: registry, personas, records, governance tests e semantic search.

Admin/Publisher/Consumer e aprovação manual. Substituir usuários IAM/chaves por papéis temporários e adaptar operações administrativas ao fluxo IaC autorizado.

### R2 — registry-end-to-end-oauth.ipynb

**Notebook:** [registry-end-to-end-oauth.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/10-Agent-Registry/00-getting-started/end-to-end/02-registry-end-to-end-oauth/registry-end-to-end-oauth.ipynb)  
**Uso:** Principal — busca autenticada.  
**Seções úteis:** Sections 2–5: OAuth registry, records, login, search e negative tests.

Busca CUSTOM_JWT com Cognito. Variante Entra precisa ser testada. Trocar mensagens de sucesso por asserções de resultado; não presumir dois tipos de auth simultâneos.

### R3 — discovery-and-invocation-at-runtime.ipynb

**Notebook:** [discovery-and-invocation-at-runtime.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/10-Agent-Registry/01-advanced/discovery-and-invocation-at-runtime/discovery-and-invocation-at-runtime.ipynb)  
**Uso:** Principal — descoberta em execução.  
**Seções úteis:** Steps 2d–4: semantic search, orchestrator e três cenários.

Supervisor monta conexões a partir dos descriptors. Adaptar pedidos para Riscos/Fraude, preservar o caminho com Policy e revisar autenticação de MCP/A2A no código e utils.py.

### R4 — registry_synchronize_mcpserver.ipynb

**Notebook:** [registry_synchronize_mcpserver.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/10-Agent-Registry/01-advanced/registry-synchronize-mcpserver/registry_synchronize_mcpserver.ipynb)  
**Uso:** Complemento — publicação.  
**Seções úteis:** Sections 4–5: sincronização de MCP OAuth/IAM.

Importar metadados de endpoint protegido. OAuth de sincronização usa CLIENT_CREDENTIALS; isso não demonstra identidade do usuário na execução da tool.

### R5 — 04-admin-approval-workflow.ipynb

**Notebook:** [04-admin-approval-workflow.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/06-workshops/10-Agent-Registry/00-getting-started/step-by-step/04-admin-approval-workflow.ipynb)  
**Uso:** Complemento de governança.  
**Seções úteis:** Manual Approval Workflow; rejeição; configuração do Registry.

Aproveitar aprovação/rejeição. O exemplo também habilita autoApproval; manter aprovação manual no cenário Santander.

## Databricks

### D1 — databricks_dbsql_agentcore_gateway.ipynb

**Notebook:** [databricks_dbsql_agentcore_gateway.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/03-integrations/data-platforms/databricks-dbsql-agentcore-gateway/databricks_dbsql_agentcore_gateway.ipynb)  
**Uso:** Extensão — conexão Databricks.  
**Seções úteis:** OAuth2 provider; MCP DBSQL target; sample query.

Cognito inbound e Databricks CLIENT_CREDENTIALS outbound. Serve para conexão e contrato MCP; não satisfaz a comprovação de BDAGs do usuário.

### D2 — databricks_dbsql_per_user_delegation.ipynb

**Notebook:** [databricks_dbsql_per_user_delegation.ipynb](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/03-integrations/data-platforms/databricks-dbsql-per-user-delegation/databricks_dbsql_per_user_delegation.ipynb)  
**Uso:** Extensão — delegação Databricks.  
**Seções úteis:** Steps 2–7: Entra, interceptor, token exchange e current_user().

RFC 8693 por interceptor. Documentado para workspace Databricks em AWS. Adaptar/testar Azure e corrigir falha de troca para recusa explícita, sem passagem silenciosa para credencial de serviço.

## Constatações que mudam a adaptação

| Referência | O código mostra | Consequência para a demo |
|---|---|---|
| I1 | `acquire_token_for_client` na seção apresentada como obtenção de authorization code. | Explicar o fluxo que o código realmente executa: aplicação/M2M. |
| I4 | Token M2M em `Authorization` do MCP e token Graph delegado em header separado. | Documentar duas credenciais e suas audiências; não apresentar a configuração como uma única cadeia automática de token. |
| I5 | Callback local/SageMaker e provider customizado para OBO no Gateway. | Preparar redirect URI e ambiente do apresentador antes da sessão; testar a configuração exata do provider. |
| P1/P2 | Fallback `IGNORE_ALL_FINDINGS` após erro de criação de política. | Retirar esse fallback da versão Santander e tratar os findings. |
| P1 | Parágrafo sobre engine vazio contradiz a descrição de negação e a célula seguinte. | Validar default deny com chamada real em `ENFORCE` sem política aplicável. |
| P3 | `like "*admins*"`, claims sintéticas de Cognito M2M e função que reescreve o authorizer. | Definir matching inequívoco e mapeamento Entra; não copiar a reconfiguração de Cognito para o ambiente Entra. |
| G5 | Interceptor faz controle de papéis e parte do outbound usa M2M. | Adotar Policy como controle declarativo e tratar preservação de usuário como trabalho adicional. |
| R1 | Criação de IAM users/access keys e operações administrativas por SDK. | Usar sessões/papéis temporários e a implantação/governança autorizada por IaC. |
| R2 | Mensagem final de sucesso dos testes negativos é impressa sem asserção global. | Validar explicitamente códigos HTTP e falhar o teste quando o resultado divergir. |
| R3 | Exemplo combina MCP e A2A, com credenciais diferentes para cada caminho. | Verificar que todas as chamadas do cenário escolhido passam pelo controle pretendido. |
| D1 | Target com `grantType: CLIENT_CREDENTIALS`. | Comprova autenticação de serviço; não prova identidade do usuário final. |
| D2 | Falha da troca retorna o corpo original sem substituir a credencial de saída. | Esse tratamento pode deixar a chamada prosseguir com credencial de serviço; substituir por recusa explícita no desenho adaptado. |
| D2 | A verificação declara sucesso quando há `@` no resultado de `current_user()`. | Comparar com a identidade esperada pelo mapeamento configurado; aparência de e-mail é evidência insuficiente. |

Esses pontos são observações sobre a versão fixada. A correção/adaptação deve preservar o objetivo didático e ser validada antes de uso com o cliente.

## Dependências locais dos exemplos

Copiar apenas o `.ipynb` não basta para vários desses exemplos:

| Referência | Arquivos/módulos associados a considerar |
|---|---|
| I3 | `oauth2_callback_server.py` e dependências do diretório. |
| I4 | `requirements.txt`, código de agente/MCP gerado no notebook e orientação `ENTRA_SETUP.md`. |
| I5 | `token_callback_server.py`, configuração do ambiente e utilitários de Gateway. |
| P1 | `scripts/agent_with_tools.py`, scripts de setup/deploy e `requirements.txt`. |
| P2 | Configuração/base de P1 e bibliotecas de Policy do starter toolkit. |
| P3 | `setup-gateway.py`, `gateway_config.json` e configuração do trigger Cognito do exemplo. |
| G1/G2 | `utils`, schemas/servidor MCP e, em G2, `gateway_mcp_client.py` e diretório `mcpservers`. |
| G5 | Labs prévios e pacote `lab_helpers`, incluindo configuração e parâmetros compartilhados. |
| R3 | `utils.py`, código e requisitos dos agentes, descriptors e arquivo de cleanup. |

Durante a implementação, revisar também os helpers antes de reutilizá-los e fixar versões compatíveis. Células de instalação, provisionamento, alteração de políticas e cleanup precisam ser separadas da experiência de apresentação.

## Referência complementar para Databricks nativo

O repositório também contém um README específico para troca nativa de token no Gateway. Ele é complemento documental, não um notebook selecionado:

- [Databricks per-user identity with native AgentCore Gateway token exchange](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/03-integrations/data-platforms/databricks-dbsql-native-obo/README.md).

O README consultado no mesmo commit informa habilitação por conta/região para a troca sem autenticação de cliente. Confirmar essa condição antes da implementação. Para o Santander, validar o comportamento em Databricks/Azure, o mapeamento de usuários e os grants do Unity Catalog.

O caminho nativo é candidato a reduzir código de adaptação, quando disponível e compatível. O interceptor de D2 só deve ser considerado com tratamento de falha corrigido, teste de identidade efetiva e implantação por IaC.

## Adequações — notebooks 12 e 13

O cenário integrado 12 usa a revisão
[`f33b4f14ea46cae2379196948073a6bb4d0e21cf`](https://github.com/awslabs/agentcore-samples/tree/f33b4f14ea46cae2379196948073a6bb4d0e21cf)
do repositório. Foram relidos README, `working-config.json` e o verificador de
identidade de [Databricks native OBO](https://github.com/awslabs/agentcore-samples/tree/f33b4f14ea46cae2379196948073a6bb4d0e21cf/03-integrations/data-platforms/databricks-dbsql-native-obo).
O código Santander foi escrito para seu fluxo multi-conta; não executa os
scripts de provisionamento avulso do sample.

Diferenças deliberadas: infraestrutura em CloudFormation/Terraform; comparação
do principal baseada em JWT verificado; SQL canário exato; dois agentes e dois
usuários; schema MCP estático restrito; erros de OAuth/rede não viram provas de
Policy; exportação sanitizada não declara trace completo sem os logs.

O notebook 13 demonstra um contrato local de ingestão/ACL/memória. A sessão
Harness usa [getting started](https://github.com/awslabs/agentcore-samples/tree/f33b4f14ea46cae2379196948073a6bb4d0e21cf/01-features/01-harness/00-getting-started)
e [Gateway integration](https://github.com/awslabs/agentcore-samples/tree/f33b4f14ea46cae2379196948073a6bb4d0e21cf/01-features/01-harness/01-advanced-examples/02-gateway-integration)
como referências; não foram implantados.
