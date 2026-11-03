# Jornada das aulas

**Selecione o roteiro antes de abrir os notebooks.** Aulas 10–14 exigem quatro
contas na implantação atual; uma turma em conta única deve usar as aulas sem
fronteiras entre contas e acompanhar 10–14 como demonstração no ambiente
completo do instrutor. A aula 14 mostra três contas, mas não possui deploy
independente de três contas. Veja a [matriz de requisitos](contas-e-elegibilidade.md).

Abra os notebooks selecionados em ordem. Cada bloco explica o serviço e mostra o código
que realiza a chamada, a implementação do agente/ferramenta ou o recurso IaC.
Os resultados esperados aparecem como asserções executáveis.

| Grupo | O que observar |
|---|---|
| 00–01 | Estado real dos recursos, negativa anônima, listagem MCP, Lambda e Runtime |
| 02–03 | Pessoa Cognito, workload Identity, inferência Bedrock e diferença entre apps |
| 04–05 | Cedar ativo, parâmetros da consulta e geração de rascunho revisável |
| 06–08 | Registry, personas, versões e distinção descoberta/execução |
| 09 | Infraestrutura Terraform e fluxo de credenciais do workload |
| 10–12 | STS de quatro contas, Gateways federados e autorização em cada fronteira |
| 13–14 | Fonte simulada na AWS, grants independentes e agentes em conta de origem |
| 15–16 | Referências de Memory, isolamento, ACL e RAG gerenciado |

A autenticação padrão é Cognito. As notas Entra explicam como adaptar as
mesmas fronteiras, sem afirmar que o Cognito realiza OBO Microsoft. A fonte
simulada conserva o objetivo didático de identidade e autorização, mas sua
validação não substitui um teste no Databricks real.

Antes das aulas, siga [preparação](preparacao.md) e [deploy](deploy.md).
Para concluir, execute no [runner AWS](validacao.md) e examine as evidências.
