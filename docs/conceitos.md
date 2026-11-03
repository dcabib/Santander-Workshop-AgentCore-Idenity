# Identidade e autorização

Autenticação comprova quem chama; autorização decide o que a chamada pode
fazer. O workshop usa JWT Cognito assinado, IAM/SigV4, Policy Cedar e ACL na
fonte como controles distintos. Gateway e agentes têm authorizer JWT. O
Runtime MCP aceita apenas a role IAM do Gateway, por resource policy; seu
backend também verifica o JWT da pessoa recebido em um header separado.

| Conceito | Cognito da jornada | Adaptação para Entra ID |
|---|---|---|
| Emissor/chaves | User Pool, discovery URL, JWKS | Tenant, discovery URL, JWKS |
| Pessoa | `iss` + `sub` | `tid` + `oid` conforme o token |
| Aplicação | `aud` do ID token, app client confidencial | `azp`/`appid` e `aud` conforme versão |
| Workload | AgentCore Identity + role do Runtime | O mesmo serviço, com emissor e fluxo adaptados |
| Entrada | Assinatura, issuer, audience, validade, token_use | Assinatura, issuer, audience, validade e claims Entra |
| Delegação | JWT propagado a destinos com audiência compartilhada | OBO quando a API de destino exigir token com outra audiência |
| M2M da aula Terraform | Identity obtém `client_credentials` | Aplicação/credential provider equivalente |

Cognito não implementa o fluxo Microsoft OBO. A propagação do JWT mantém a pessoa
para o destino que foi configurado para aceitar aquela audiência; não troca
o token para Microsoft Graph. M2M identifica o workload, sem fabricar uma
identidade humana. O material não apresenta esses fluxos como equivalentes.

O agente chama Bedrock Converse dentro do Runtime e só pode usar ferramentas
anunciadas pelo Gateway. O modelo não escolhe credenciais nem usuário. O
servidor estabelece a correlação; a fonte deriva o principal do JWT verificado.

Policy examina pessoa, aplicação, ação, recurso e parâmetros. `tools/list`
não garante permissão para todos os valores de `tools/call`. A fonte mantém
uma ACL independente: um permit Cedar não concede um grant de dados ausente.

Agent Registry governa descritores e versões aprovadas. As personas de
desenvolvimento, publicação, aprovação e consumo têm políticas IAM distintas.
Uma entrada aprovada pode ser descoberta por alguém sem permissão de execução.

Memory isola eventos por actor e sessão. O actor deriva de issuer/sub, e o
conteúdo gravado é uma referência. Cada recuperação lê o grant atual e só então
busca os dados. Compartilhar um session_id não compartilha a memória de outra pessoa.

No RAG, o contexto de ACL é vinculado à pessoa autenticada antes de chegar ao
Knowledge Base. A geração recebe somente trechos autorizados. A role do agente
possui Deny para retrieval direto, para que o caminho governado não seja contornado.
