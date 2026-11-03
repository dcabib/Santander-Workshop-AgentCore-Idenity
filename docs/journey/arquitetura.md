# Fronteiras do cenário

O fluxo usa três contas: Retail (origem), plataforma (hub) e Transaction
(fonte). A implantação atual exige também Lending, totalizando **quatro
contas**. Consulte a [matriz de requisitos](../contas-e-elegibilidade.md)
antes de executar; o cenário não funciona em conta única.

| Fronteira | Controle |
|---|---|
| Notebook AWS → Runtime agente | JWT Cognito e audiência do app |
| Runtime → Gateway plataforma | JWT da pessoa, Policy e workload Identity do agente |
| Plataforma → Gateway domínio | Interceptor JWT, authorizer e Policy do domínio |
| Gateway domínio → Runtime fonte | IAM/SigV4 da role do Gateway, JWT humano revalidado e ACL da fonte |
| Runtime fonte → DynamoDB/Memory | Role IAM, actor por issuer/sub e grants atuais |

Os destinos vêm dos outputs do IaC. Campos como `user_id` enviados pelo modelo
não substituem a pessoa autenticada. A restrição da aplicação Riscos também é
verificada na ferramenta genérica de tabelas, impedindo um caminho alternativo
para Fraude.

O Registry governa descoberta e a Policy governa execução. A aula consulta o
catálogo aprovado, mas cada chamada ainda exige os controles da cadeia.
