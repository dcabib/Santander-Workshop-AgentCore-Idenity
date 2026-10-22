# Critérios de aceite e registro de evidências

Local e cloud são colunas independentes. `PASS local` não significa que o serviço
AWS executou a regra. Não publicar tokens, emails, payloads de Graph ou segredo
em screenshots, outputs de notebook ou relatório.

| Prova | Local | AWS / fonte real |
|---|---|---|
| Protocolo MCP: initialize, list e call | Automático | Pendente |
| Riscos autorizado / Fraude negado ao usuário Riscos | Automático | Pendente |
| Mesmo usuário, caller Riscos vs supervisor | Automático | Pendente |
| Limite 50 aceita / 51 nega | Automático | Pendente |
| Claims ausentes, assinatura inválida, audiência/expiração | Automático | Pendente |
| Registry: papéis e estados | Modelo em memória | Pendente: IAM + serviço |
| Registro aprovado não concede execução | Automático | Pendente |
| Graph `/me`: igualdade exata do OID dos usuários A/B | Não simulado | Pendente |
| Supervisor A → Gateway/Registry C → Runtime B | Não simulado | Pendente |
| Databricks: usuário exato e grants distintos | Adapter com HTTP mock | Pendente em Azure |
| CloudFormation/Terraform | Validação estrutural | Deploy pendente |
| Geração de política pelo serviço a partir de português | Provider/contrato testados | Pendente de execução do stack policy-draft |

## Matriz live obrigatória

Obter tokens válidos de teste por **aplicações confidenciais distintas**. Todos
devem ter `aud` do Gateway, mesmo tenant e contexto delegado. Não modificar JWT
manualmente para simular outro caller em AWS.

| Caso | Usuário | Caller | Tool / entrada | Resultado esperado |
|---|---|---|---|---|
| P-SAN-01a | Riscos | Riscos | risco, 50 | Permite |
| P-SAN-01b | Riscos | Fraude | risco, 50 | Nega Cedar |
| P-SAN-02a | Riscos | Supervisor | fraude, 10 | Nega Cedar |
| P-SAN-02b | Ambos | Supervisor | fraude, 10 | Permite |
| P-SAN-03a | Ambos | Supervisor | risco, 51 | Nega Cedar |
| P-SAN-03b | Ambos | Supervisor | risco, limite ausente | Recusa de schema/policy identificada |
| P-SAN-04 | Ambos | Supervisor | ação fora da allowlist | Não autoriza |
| P-SAN-05 | Token válido sem claim obrigatória | — | risco | Nega |
| P-SAN-06 | Ambos | Riscos | fraude, 10 | Nega Cedar |

`probe_policy` valida o token, verifica ENFORCE e executa MCP. Só classifica
`POLICY_DENIAL_REPORTED` quando recebe uma indicação específica de tool não
permitida. Erro OAuth, falha de transporte, backend e mensagens desconhecidas
não são convertidos em sucesso de teste.

```python
from santander_demo.live import probe_policy
observation = await probe_policy(
    config, token, "riscos___consultar_risco",
    {"cliente_id": "SANT-DEMO-001", "max_registros": 51},
)
print(observation)  # tokens e resposta bruta não aparecem
```

**Prova de não execução no backend:** correlacionar request/trace do Gateway à
janela do backend e à decisão Policy, com teste positivo antes/depois para provar
a entrega dos logs. Isolar a sessão de ensaio, aguardar a propagação e confirmar
que não há lacunas/paginação. O helper retorna `backend_non_invocation=NOT_PROVEN`
até essa análise. Ausência de uma linha em logs incompletos não é prova.

O projeto envia logs de execução sintética no backend e configura log delivery
do Gateway. O alinhamento de IDs entre serviços e o formato final dos logs
precisam ser verificados no sandbox. `read_log_evidence` retorna somente IDs e
metadados permitidos, omitindo bodies/headers.

## Identity

1. Registrar `user_ref` pseudonimizado, audiência, versão e caller.
2. Executar Graph `/me` como A e B, comparando `id` com o OID esperado exato.
3. Confirmar que tokens M2M não passam como delegação de usuário.
4. Confirmar JWT de audiência errada/expirado recusado pelo Gateway real.
5. Confirmar chamada direta ao Runtime Fraude recusada mesmo com token
   destinado ao Runtime; o caminho autorizado contém o workload do Gateway.
6. Não afirmar que Graph prova Databricks.

O contrato `principal.getTag("tid"/"oid"/"azp"/"scp")` precisa ser validado em
Policy com tokens Entra reais. Se uma claim não estiver disponível, parar e
adaptar o contrato/IaC; não copiar identidade de argumentos de tool.

## Registry

Ler os estados preparados pelo stack e testar IAM via
`iam simulate-principal-policy` para cada role e ARN concreto: publisher não
aprova; consumer não publica nem aprova; approver aprova mas não publica.
Simulação IAM é evidência de configuração, não substitui um ensaio de IAM real
em um pipeline de publicação separado quando exigido pelo cliente.

Na busca, um registro recém-aprovado pode demorar a aparecer. Registrar essa
propagação, sem fallback para um endpoint não aprovado. Somente o endpoint
exato do Gateway em `config/local.json` recebe bearer.

## Multi-conta

`topology(config)` exige três contas distintas e confere os ARNs.
`invoke_supervisor(config, token)` chama o Runtime A e exige resultados de
Riscos/Fraude. A prova final inclui logs de A, C e B, mais o principal delegado
no destino. Configuração/ARNs sozinhos não são execução.

## Databricks Azure

Usar a tabela canário sintética preparada pelo IaC do cliente e dois usuários.
`SELECT current_user()` deve retornar exatamente a identidade prevista.
O usuário com grant consegue `SELECT 1 ... LIMIT 1`; o outro recebe erro de
permissão reconhecido. Indisponibilidade de warehouse, SQL inválido e erro
OAuth não contam como negativa de Unity Catalog.

Para preservar o humano, utilizar **federation account-wide de usuários**,
com a claim mapeada ao username Databricks. Federation de workload/service
principal não comprova esse requisito.

O notebook **12** é a prova integrada Gateway → MCP DBSQL. O adapter SQL REST
do 09 é apenas um teste isolado. A variante nativa AgentCore Identity →
Databricks depende da habilitação do modo público de token exchange na conta/
região; sua preparação está no [runbook](journey/README.md).

## Aceite do cenário integrado 12

| Caso | Evidência necessária |
|---|---|
| A/Riscos → Riscos | Runtime na origem, Registry APPROVED, principal SQL correto, SELECT e query ID |
| A/Fraude → Fraude | Mesmo usuário, outra aplicação, capacidade Fraude permitida |
| A/Fraude → Riscos | Negativa específica de Policy no hub e backend não executado |
| B/Riscos → Riscos | Outro OID, consulta de identidade correta e negativa real de grant no canário |
| Trace | Correlação comprovada dos três Gateways, Runtime e query/audit Databricks |
| Decisão | Responsáveis por quotas, budget, dados, governança e operação registrados |

`acceptance()` não promove erro de token, timeout, query pendente ou falta de
logs a PASS. O [procedimento de trace](journey/trace.md) deve ser concluído.
O contrato local de quotas e o notebook 13 não comprovam serviços gerenciados.

## Modelo de registro

```json
{
  "case": "P-SAN-02a",
  "environment": "AWS_LIVE",
  "status": "PENDING",
  "observed_outcome": null,
  "request_id": null,
  "trace_id": null,
  "backend_non_invocation": "NOT_PROVEN",
  "reviewer": null
}
```
