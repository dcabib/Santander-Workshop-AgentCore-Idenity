# Ícones e referência visual

Os SVGs desta pasta são ícones oficiais do pacote **AWS Architecture Icons**,
edição de 31/07/2026, disponibilizado em [aws.amazon.com/architecture/icons](https://aws.amazon.com/architecture/icons/).
`sources.json` registra a URL do pacote, o caminho de cada arquivo e seu SHA-256.
Os ícones foram extraídos sem alteração; nomes e marcas pertencem à AWS.
O ícone de Amazon Bedrock AgentCore identifica a família; o título do grupo
distingue Runtime, Gateway, Policy, Memory e Registry.

A composição segue os workshops de referência:

* [Hospedar um agente no Runtime](https://github.com/awslabs/agentcore-samples/tree/main/06-workshops/01-AgentCore-runtime/01-hosting-agent).
* [Arquitetura Runtime](https://github.com/awslabs/agentcore-samples/blob/main/06-workshops/01-AgentCore-runtime/images/runtime_architecture.png).
* [Transformar Lambda em ferramentas MCP](https://github.com/awslabs/agentcore-samples/tree/main/06-workshops/02-AgentCore-gateway/01-transform-lambda-into-mcp-tools).
* [Inbound OAuth com Cognito](https://github.com/awslabs/agentcore-samples/tree/main/06-workshops/03-AgentCore-identity/03-Inbound%20OAuth%20example).

Os desenhos do Santander foram compostos para o código deste projeto. O Runtime
usa deploy direto de ZIP em S3; ECR e CodeBuild não fazem parte desse fluxo.
Quadros delimitam contas ou serviços, retângulos tracejados detalham funções
ou configurações, setas contínuas representam chamadas e tracejadas indicam
configuração ou apoio. Negativas são identificadas em vermelho.
As arquiteturas legadas continuam indicando a exigência de quatro contas.
