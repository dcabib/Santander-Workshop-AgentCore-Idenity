# Roteiro consolidado — Santander

A trilha principal é o [notebook 12](../notebooks/12_cenario_santander_integrado.ipynb):
dois agentes hospedados na conta A, Gateway central e Gateway da conta B chegando
ao MCP Databricks. A implantação fica fora do horário da apresentação.
O [runbook](journey/README.md) prepara as três contas e os dois usuários.

## Demo de 30 minutos

| Minutos | Mostrar | Mensagem |
|---|---|---|
| 0–4 | Diagrama e audiências | Pessoa preservada, aplicação muda em cada salto |
| 4–8 | Registry e agentes Riscos/Fraude | Descobrir uma capacidade não autoriza executá-la |
| 8–14 | A/Riscos e A/Fraude permitidos | Dois agentes reais em Runtime, cada qual com sua tool |
| 14–18 | A/Fraude tenta Riscos | A mesma pessoa não elimina a restrição da aplicação |
| 18–23 | B/Riscos sem SELECT | Gateway permite; Unity Catalog nega o dado |
| 23–27 | Request ID → Gateways → query ID | Identidade e origem da consulta, com limites de evidência visíveis |
| 27–30 | Matriz de decisão | Complementar Databricks; definir quotas/consumo e responsabilidades |

Se o sandbox não tiver sido ensaiado, apresente a matriz Cedar **local** e
declare o caminho cloud pendente. Não projete respostas esperadas como
observações reais. Databricks deixou de ser uma extensão opcional: é o gate
central de aceite da Sessão 1.

## Workshop — quatro horas

| Minutos | Atividade | Material |
|---|---|---|
| 0–20 | Objetivo Santander, fronteiras e situação do ambiente | 12, diagrama e preflight |
| 20–65 | Entra/OBO, identidade de pessoa e aplicação | 12; 02/03 para aprofundar conceitos |
| 65–100 | Policy por agente/tool/usuário e SQL aprovado | 12; 04 como exercício Cedar |
| 100–115 | Intervalo | — |
| 115–150 | Registry, owner, versão, instância e AssumeRole | 12; 06/07 como exercício de governança |
| 150–195 | Fluxo multi-conta, MCP Azure e dois usuários | 12, casos A/B e negativa de agente |
| 195–220 | Logs, query ID, fonte e atribuição de decisão | 12 e procedimento de trace |
| 220–240 | QPM/TPM/budget, Runtime versus Gateway e decisão | Contrato de quotas e matriz de responsabilidades |

Não é necessário executar quatorze notebooks na sessão. O 10 é referência do
artigo com Strands/M2M; o 11 mostra autonomia de autorização em quatro contas.
O 12 combina o cenário principal com OBO e origem em uma conta de negócio.

## Preparação do instrutor

Validar os [critérios de aceite](aceite.md), aprovar records por change set,
confirmar dois usuários com grants distintos e aquecer o warehouse. Ensaiar
as negativas e preservar evidências sanitizadas. Não projetar resultados
brutos MSAL, bearers ou dados reais.

O demo runner é determinístico: isso permite isolar decisões de segurança.
O uso de LLM/K2 real pode ser acrescentado após esses controles estarem
comprovados. O cliente não precisa confundir sucesso de inferência com
sucesso de autorização.

## Sessões próprias

- [Sessão 2 — quatro horas](ingestao/sessao-2.md), usando o notebook 13 para
  lifecycle, ACL, revogação e memória.
- [Harness — uma hora online](harness/sessao-online.md), com referência
  AgentCore Harness e confirmação da versão/produto homologado.
