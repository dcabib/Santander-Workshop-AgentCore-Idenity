# Referências de implementação

Este laboratório foi escrito para o escopo/conversa Santander fornecidos no
workspace. Usa como referências os notebooks públicos do projeto AWS Labs
[agentcore-samples](https://github.com/awslabs/agentcore-samples),
commit `2747451473d1fadbba18f5aee0524e533e3c2b2e` (08/10/2026).
O repositório de origem distribui seus exemplos sob Apache-2.0.
O [catálogo](referencias-notebooks-agentcore.md) relaciona os notebooks e adaptações.

Contratos adicionais consultados em 09/10/2026:

- [Especificação de recursos CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/cfn-resource-specification.html), versão 267.0.0.
- [MCP server targets, schema estático e OBO](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html).
- [Workload restriction de Runtime via Gateway](https://github.com/awslabs/agentcore-samples/blob/2747451473d1fadbba18f5aee0524e533e3c2b2e/01-features/07-centralize-and-govern-your-ai-infrastructure/01-gateway/04-advanced-concepts/gateway-enforced-access/agentcore-runtime/README.md).
- Modelos de API instalados pelo `boto3/botocore 1.43.110`, registrados em `uv.lock`.

O laboratorio adapta os padrões a IaC, sessões STS, negação por padrão,
segredos fora dos notebooks e asserções. Não replica as rotinas avulsas
de provisionamento/limpeza dos exemplos.

## Cenário do blog multi-account (notebook 10)

Os servidores em `src/santander_demo/banking/lobs/` e as fixtures em
`src/santander_demo/banking/data/fixtures.json` adaptam o repositório
[sample-amazon-bedrock-agentcore-banking-mcp-multi-account](https://github.com/aws-samples/sample-amazon-bedrock-agentcore-banking-mcp-multi-account),
commit `f76491b63d005d1ad0c253396f58f67da021f94d`.
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
O texto original de licença está em [docs/banking/UPSTREAM-LICENSE](docs/banking/UPSTREAM-LICENSE).
As adaptações e o escopo estão em [docs/banking/README.md](docs/banking/README.md).

O notebook 11 reutiliza esses MCPs/fixtures e adiciona Gateways por conta, OBO Entra
e Policy local. Seu escopo e referências estão em
[docs/federation/README.md](docs/federation/README.md).
