# Execução AWS dos notebooks com criação por SDK

Em 03/11/2026, as aulas **00, 01, 02 e 03 passaram** no ambiente de notebooks AWS,
na conta `456332459064`, região `us-west-2`, execução `6825d3096100`.
O código mostrado nas células criou os recursos. Não foram usados stacks ou
outputs CloudFormation na execução dessas aulas.

Este aceite é parcial: não comprova o funcionamento das aulas seguintes nem
da limpeza. O [aceite da arquitetura anterior](aceite-aws.md) é independente.

| Aula | Versão do notebook executada — SHA-256 | Resultado |
|---|---|---|
| 00 | `541c37c71a80637483767b60462ae71dc6ce8a591afb418f99f5332de228685c` | STS, região, SDK e registro de IDs |
| 01 | `af6138dea00bc4083933ef99166c22380144007a9cd8c9aaef9516501f45d110` | Gateway, target e invocação MCP na Lambda |
| 02 | `b476e41187a9624c6cf0e551e27261cdc7059180ce9d55ba3bd79c8c309bcb57` | Identidade humana, audiências e negativas JWT |
| 03 | `7b284e80a536e506b5297644e3faa1b3c40b84bf466bb4f4578ed7a8b6248524` | Código ARM64 implantado no Runtime, MCP e identidade IAM |

## Evidências das chamadas

| Verificação | Resultado | Request ID AWS |
|---|---|---|
| Gateway sem token | HTTP 401 | `4d7adf16-4496-43de-b5a8-89d12d8151c7` |
| Gateway com JWT malformado | HTTP 401 | `5f551ed8-149b-4bd4-9d64-e3e31ca38212` |
| Ferramenta autenticada pela interface MCP | Lambda executada, risco sintético `low` para `cliente-001` | `aaf0aa76-06a3-443e-b7bf-ea7f30354c76` |
| JWT assinado, emitido para outra aplicação | HTTP 403; erro MCP `-32002`, `insufficient_scope` | `620f186a-450b-49a5-8fbd-951bf01ef306` |
| Audiência alterada sem nova assinatura | HTTP 403; erro MCP `-32002`, `insufficient_scope` | `7f85a14b-d9b1-4661-94a5-27202452d21e` |
| Runtime sem assinatura IAM | HTTP 403 | `92a7296c-1abc-4736-87f0-54e54e48c353` |
| Invocação da ferramenta MCP no Runtime | Identidade da role de execução, diferente da identidade do participante | `42d002fd-2fde-4d10-800e-90570b99ec20` |
| STS consultado pelo servidor MCP dentro do Runtime | Role `santander-6825d3096100-runtime` | `047d231d-6753-4ee4-a988-3b345cb8537f` |

Na aula 02, os dois logins tiveram assinatura, issuer, expiração e audiência
verificados com JWKS antes dos testes negativos. O `sub` permaneceu igual e
`aud` mudou entre aplicações. Após as negativas, o token da aplicação aceita
invocou novamente a Lambda com sucesso.

O teste inicial da aula 02 esperava HTTP 401 e foi corrigido após observar
HTTP 403 na AWS. A verificação exige o erro MCP de autorização e o Request ID;
erros de rede ou de serviço não contam como uma negativa de autorização.

A aula 03 criou seu bucket, enviou um ZIP ARM64 de aproximadamente 27 MB,
criou a role e o Runtime e invocou o código por IAM/SigV4. O marcador do bucket
foi conferido por leitura autenticada e recusado em acesso anônimo antes do
upload do código. O hash do objeto S3 foi comparado ao ZIP.

Na primeira execução, `StopRuntimeSession` informou que a sessão não existia
ou já havia terminado. A célula passou a registrar essa ausência separadamente
de uma exclusão bem-sucedida; outras negativas continuam interrompendo a aula.
A reexecução completa passou e configurou sete dias de retenção no grupo de
logs criado pelo Runtime.

## Limites deste resultado

* A aula 01 precisou das correções Cognito e Lambda autorizadas e da retomada
  após propagação IAM. Seu sucesso não prova uma execução sem interrupções
  em qualquer conta AWS.
* As reexecuções usaram os identificadores persistidos e conferiram os recursos
  criados. Não foi feita uma segunda implantação do zero em outra conta.
* Os recursos permanecem na AWS para as próximas aulas. A limpeza 99 ainda
  precisa de teste real antes do aceite completo.
* Nenhum token, senha ou credencial integra este relatório.
