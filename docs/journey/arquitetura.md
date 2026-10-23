# Laboratório 14 — responsabilidades e limites de confiança

O [cenário integrado](README.md) combina conceitos estudados separadamente:
agentes com identidades próprias, autorização por conta e grants na fonte.
Esta página ajuda a ler o diagrama e a explicar por que cada controle existe.

## Uma chamada, várias decisões

| Fronteira | O que ela precisa decidir |
|---|---|
| Gateway Origem | Se a aplicação de login e o usuário podem entrar no agente escolhido |
| Runtime Riscos ou Fraude | Se o JWT e a workload são aceitos e qual capacidade aprovada corresponde à solicitação |
| Registry central | Quais versões de capacidades aprovadas o consumidor pode descobrir |
| Gateway Central | Se aquele usuário, por aquele agente, pode chamar a ferramenta com aqueles argumentos |
| Gateway Dados | Se a plataforma e o usuário podem usar a ferramenta SQL restrita |
| Databricks / Unity Catalog | Qual usuário a federação resolveu e se ele tem o grant exigido na tabela |

Os agentes deste laboratório são determinísticos: escolhem capacidades conhecidas
e consultas canário exatas. Isso torna as decisões reproduzíveis sem depender de
SQL gerado por um modelo. Eles não integram uma plataforma de agentes externa.

## Identidade muda de destinatário, não de pessoa

OBO emite tokens destinados à API seguinte. `aud` muda conforme o destino;
`azp` identifica a aplicação que pediu a troca. `tid` + `oid` acompanha a pessoa
no Entra. A claim mapeada no Databricks precisa corresponder exatamente ao usuário
na fonte; a consulta `current_user()` verifica esse resultado.

No Gateway Central, `azp` distingue Riscos de Fraude. No Gateway Dados, o ator já
é a aplicação Central. Portanto a autorização por agente é responsabilidade do
hub; a conta de dados conserva sua decisão sobre usuário, ferramenta e consulta.
A restrição de workload dos Runtimes e a autenticação JWT se complementam.
Os endpoints desta implementação são públicos autenticados.

## Descoberta é uma entrada para a execução

Os registros têm owner `dados`, versão `1.0.0` e instância do projeto. Publicar
cria uma versão pendente; aprovar torna essa versão disponível para descoberta.
O consumidor assume uma role com permissão de busca e valida o endpoint antes
de encaminhar uma credencial. Alterar ou remover uma aprovação no template não
revoga automaticamente um registro já aprovado: a mudança do registro precisa
seguir seu ciclo de vida no IaC.

## Autorizar ferramentas e autorizar dados

A/Fraude tentando Riscos deve parar na Policy central. B/Riscos pode passar
pelos Gateways e ainda receber uma negativa de `SELECT` no Unity Catalog.
Esses dois resultados ensinam controles diferentes. Um token válido, um registro
aprovado ou uma ferramenta listada não garante acesso ao dado.

A Policy de SQL aceita somente a consulta de identidade e o canário definido
para a capacidade. Ela não é um mecanismo genérico de análise de SQL arbitrário.
O módulo de federação Databricks não cria usuários nem concede grants de tabela.

## Limites que o exercício torna explícitos

O contador local de QPM, TPM e orçamento usa valores sintéticos em
[governance.py](../../src/santander_demo/governance.py). Ele demonstra o contrato
de uma cota; não mede faturamento AWS nem configura limites distribuídos.
Policy temporal tem semântica própria de sessão, descrita na documentação do
serviço, e não equivale a um orçamento mensal.

Os registros de chamada ajudam a investigar, mas não produzem um trace completo
por si só. A [correlação dos logs](trace.md) precisa associar eventos e consultas
reais. A execução local e os testes de unidade deixam as verificações cloud
pendentes até que as dependências do ambiente tenham sido exercitadas.

## Referências

- [Policy no AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)
- [Identity e OBO](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html)
- [Policy temporal](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-session-based-temporal.html)
- [Privilégios no Unity Catalog](https://learn.microsoft.com/pt-br/azure/databricks/data-governance/unity-catalog/manage-privileges/)
