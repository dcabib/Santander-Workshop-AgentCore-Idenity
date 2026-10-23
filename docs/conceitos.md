# Conceitos do workshop

Use esta página como apoio à [jornada](jornada.md). As definições abaixo descrevem
os papéis dos componentes; cada notebook mostra a implementação do seu cenário.

## Código, ferramentas e catálogo

| Conceito | O que significa no laboratório |
|---|---|
| Agente | Código que coordena uma tarefa. Pode seguir um fluxo determinístico ou usar um LLM para escolher ferramentas. |
| Runtime | Ambiente gerenciado que executa o código do agente ou servidor MCP. Hospedagem não concede autorização aos dados. |
| MCP | Protocolo para descobrir e chamar ferramentas. `initialize` abre a sessão, `tools/list` apresenta contratos e `tools/call` executa uma chamada. |
| Schema | Contrato de argumentos e tipos da ferramenta. Entrada válida ainda pode ser negada por uma política. |
| Gateway | Ponto de entrada para ferramentas e seus controles de autenticação e autorização. |
| Target | Destino conectado ao Gateway: por exemplo, Lambda, servidor MCP ou conector nativo. |
| Registry | Catálogo de capacidades e metadados. Aprovar um registro permite sua descoberta, sem conceder acesso à execução. |

Leia [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools),
[Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
e [Registry](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/registry.html).

## Identidade e credenciais

**Autenticação** verifica a credencial e sua identidade. **Autorização** decide
se essa identidade pode executar a ação solicitada.

Um **JWT** carrega claims assinadas: `iss` identifica o emissor, `aud` o destinatário
e `exp` a expiração. **JWKS** publica as chaves para verificar a assinatura.
Decodificar o conteúdo sem verificar a assinatura não autentica o chamador.

No Entra, `tid` + `oid` identifica a pessoa no tenant; `azp` em tokens v2 identifica
a aplicação chamadora. `sub` pode mudar entre aplicações. No cenário Okta, o
identificador da aplicação está em `cid`. Use o contrato do emissor de cada lab.

| Mecanismo | Finalidade |
|---|---|
| M2M / `client_credentials` | Autentica uma aplicação sem login humano. Usado nos destinos do 10 e no 15. |
| OBO / on-behalf-of | Obtém um token delegado para outra API em nome do usuário. Exige configuração e consentimento no IdP. |
| Scope | Permissão declarada no token. O destino verifica os scopes exigidos. |
| Workload identity | Identidade do software que está executando, distinta da pessoa e do registro consultado. |
| WAT | Token de identidade da workload usado pelo AgentCore Identity; não é o bearer OAuth do destino. |
| IAM/SigV4 | Autenticação e autorização de chamadas AWS com credenciais IAM e assinatura da requisição. |
| AssumeRole / STS | Sessão IAM temporária, inclusive entre contas, conforme trust policy e permissões. |

**Identity** gerencia identidades de workload e acesso a credenciais externas.
Não substitui as permissões do Gateway ou da fonte. O token de uma API não deve
ser reutilizado em outra audiência.

Leia [claims Entra](https://learn.microsoft.com/pt-br/entra/identity-platform/access-token-claims-reference),
[OBO](https://learn.microsoft.com/pt-br/entra/identity-platform/v2-oauth2-on-behalf-of-flow)
e [workload access tokens](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/get-workload-access-token.html).

## Regras e fronteiras

**Cedar** avalia principal, ação, recurso e contexto. Sem `permit` aplicável,
a chamada é negada; um `forbid` aplicável prevalece. Em AgentCore Policy,
**ENFORCE** aplica as decisões; **LOG_ONLY** permite observá-las sem usar a
negativa como bloqueio.

O **authorizer** do Gateway verifica o JWT; a **Policy** decide sobre a ferramenta
e seus argumentos; os **grants da fonte** decidem sobre o dado. Uma aprovação
na primeira fronteira não garante aprovação nas seguintes.

**Guardrails** tratam conteúdo de entrada e saída do modelo. Não substituem
Policy, ACL ou grants. **QPM**, **TPM** e **orçamento mensal** controlam dimensões
diferentes de consumo. Os contadores do laboratório 14 são locais e sintéticos.

Leia [Cedar](https://docs.cedarpolicy.com/policies/syntax-policy.html),
[Policy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)
e [Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html).

## Dados, documentos e memória

**RAG** combina recuperação de trechos e geração de resposta. A **ACL** define
quem pode acessar cada documento; relevância define quais documentos permitidos
uma busca retorna. Filtrar depois da geração é tarde demais para proteger o contexto.

**Ingestão** transfere conteúdo e metadados da fonte para a representação
pesquisável. **Memória** permite reutilizar informações entre interações.
Uma memória com referências precisa revalidar as permissões ao recuperar o conteúdo.

No Databricks, `current_user()` mostra a identidade reconhecida pela fonte.
Um grant como `SELECT` determina se ela pode consultar uma tabela. As tabelas
canário dos exercícios são sintéticas e tornam essa decisão verificável.

Leia [ACLs de Managed KB](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html),
[memória e RAG](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-ltm-rag.html)
e [privilégios do Unity Catalog](https://learn.microsoft.com/pt-br/azure/databricks/data-governance/unity-catalog/manage-privileges/).

## Implantação e evidência

**IaC** descreve infraestrutura em arquivos versionados. Um **provider** traduz
o contrato para APIs do serviço. No Terraform, **state** registra recursos,
**plan** propõe mudanças, **apply** executa o plano e **drift** indica divergências.
No CloudFormation, um **change set** permite revisar mudanças antes da aplicação.

Um **request ID** identifica uma chamada; um **trace** correlaciona chamadas
entre componentes. Uma resposta correta não comprova todos os saltos.
Da mesma forma, um teste local não comprova o comportamento do serviço gerenciado.

Continue em [validação](validacao.md) e [Terraform state](https://developer.hashicorp.com/terraform/language/state).
