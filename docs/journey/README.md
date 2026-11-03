# Cenário integrado: origem → plataforma → fonte

**Aula 14: três contas no fluxo; quatro contas exigidas pela implantação
atual.** Retail é a origem, plataforma é o hub e Transaction é a fonte.
Lending é uma dependência da federação e do preflight compartilhados.
Com apenas uma, duas ou três contas, esta aula não executa com o IaC atual;
reserve-a para demonstração no ambiente completo. Veja a
[matriz de contas](../contas-e-elegibilidade.md).

A aula 14 combina dois agentes hospedados em Retail, Gateway da plataforma e
fonte em Transaction. Os app clients Supervisor e Riscos distinguem a mesma
pessoa: a aplicação Riscos não recebe permissão para Fraude. O modelo e suas
ferramentas executam no Runtime, com destinos estabelecidos pelo IaC.

O workspace Databricks foi explicitamente substituído por um simulador na AWS.
O Runtime MCP verifica o JWT, consulta grants DynamoDB e devolve dados
sintéticos. O campo `verified_subject` permite comparar a identidade da fonte
com o login; isso não é evidência de `current_user()` em Databricks real.

Uma futura integração real deve usar workspace Databricks na AWS, SQL Warehouse,
federação/token exchange suportados e provas próprias de usuário/grants.
Os templates antigos de Entra/Databricks não são a implantação desta jornada.

[Arquitetura](arquitetura.md) · [Evidências](trace.md) · [Deploy](../deploy.md)
