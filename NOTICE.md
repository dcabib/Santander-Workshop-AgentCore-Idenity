# Atribuição dos exemplos e licenças

O workshop usa exemplos públicos como referência e os adapta para laboratórios
em português, código testável e infraestrutura gerenciada por IaC. A sequência
de aprendizagem está no [README](README.md); este arquivo preserva a atribuição
das fontes de implementação.

## Exemplos AgentCore

Referência: [AWS Labs — agentcore-samples](https://github.com/awslabs/agentcore-samples),
commit `2747451473d1fadbba18f5aee0524e533e3c2b2e`.
O repositório distribui seus exemplos sob Apache-2.0.

O cenário Databricks também consulta o
[sample nativo de OBO](https://github.com/awslabs/agentcore-samples/tree/f33b4f14ea46cae2379196948073a6bb4d0e21cf/03-integrations/data-platforms/databricks-dbsql-native-obo),
commit `f33b4f14ea46cae2379196948073a6bb4d0e21cf`.
As adaptações usam sessões STS, validação de tokens, políticas restritas,
segredos fora dos notebooks e provisionamento pelo IaC do projeto.

## Exemplo bancário multi-conta

Os servidores em [banking/lobs](src/santander_demo/banking/lobs/) e os dados em
[fixtures.json](src/santander_demo/banking/data/fixtures.json) adaptam
[sample-amazon-bedrock-agentcore-banking-mcp-multi-account](https://github.com/aws-samples/sample-amazon-bedrock-agentcore-banking-mcp-multi-account/tree/f76491b63d005d1ad0c253396f58f67da021f94d),
commit `f76491b63d005d1ad0c253396f58f67da021f94d`.

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

O texto original da licença MIT-0 permanece em
[docs/banking/UPSTREAM-LICENSE](docs/banking/UPSTREAM-LICENSE).
Os laboratórios [11](docs/banking/README.md) e [12](docs/federation/README.md)
reutilizam esses MCPs e dados sintéticos. As adaptações incluem empacotamento
ARM64, nomes de recursos por projeto, consultas restritas, governança do Registry
e, no laboratório 12, Gateways por conta com OBO Entra.

As referências conceituais e de APIs aparecem junto dos exercícios e no
[guia de conceitos](docs/conceitos.md).
