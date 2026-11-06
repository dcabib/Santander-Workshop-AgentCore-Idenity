# Identidade, autorização e dados

JWT autentica uma identidade. `iss` identifica o emissor, `sub` a pessoa e `aud`
a aplicação destinatária. Assinatura válida com audiência incorreta pode ser
negada. Cognito é o provedor real dos exercícios; Entra ID e OBO são comparações
conceituais, sem integração com um tenant externo.

IAM autoriza chamadas AWS. A identidade que invoca Runtime é distinta da role
usada pelo código hospedado. Cedar acrescenta decisões por principal, ação,
recurso e contexto ao Gateway. Uma negativa MCP pode aparecer em HTTP 200:
confira o erro e o conteúdo MCP, não apenas o código HTTP.

Registry governa publicação, aprovação e descoberta. Descobrir um endpoint não
concede autorização para invocá-lo.

Na aula 15, Memory armazena eventos com referências por actor e sessão; não há
estratégia de extração de longo prazo. A fonte deve revalidar o acesso após
revogação: uma referência antiga não concede acesso ao conteúdo.
Na aula 16, RAG usa documentos sintéticos e ACL nativa por usuário; confira
quais documentos foram recuperados e se a resposta usa somente esses conteúdos.
