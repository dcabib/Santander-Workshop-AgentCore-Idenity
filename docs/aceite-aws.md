# Aceite operacional AWS — 03/11/2026

**Alcance:** este aceite é do pacote de fonte e do build abaixo, no ambiente
de referência de **quatro contas**. Não comprova funcionamento em qualquer
conta AWS nem em conta única. As aulas 10–14 exigem quatro contas no IaC
atual; a aula 14 demonstra um fluxo de três. Veja a
[matriz de contas e elegibilidade](contas-e-elegibilidade.md).
As mudanças posteriores de pré-requisitos e seleção não foram executadas nesse
build; os hashes deste aceite identificam a versão histórica testada.

**Resultado: PASS.** As 17 aulas foram executadas em CodeBuild contra os serviços
implantados na AWS. A auditoria confirmou os hashes dos notebooks distribuídos,
as 89 células de código executadas e a ausência de saídas de erro.

Build final: `santander-workshop-notebooks:8d38b903-937c-4ed5-9b81-a99a57f6bc88`.
Fonte do runner: SHA-256
`0659fb574a7d9eb4d080a7d400fcc69dca19909d50807d6235a5e43119e52c02`.

[Logs da execução final](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/santander-workshop-core-runner-Log-BTRwVSJ0HYVV/log-events/8d38b903-937c-4ed5-9b81-a99a57f6bc88).
Os artefatos permanecem no bucket privado do pipeline:
`s3://santander-workshop-core-bootstrap-artifacts-ks2ktj0fwn4w/evidence/8d38b903-937c-4ed5-9b81-a99a57f6bc88/notebooks.zip`.

## Escopo verificado

| Área | Evidência observada |
|---|---|
| Identidade | Cognito, JWT válido, token inválido/anônimo negado, workload Identity e audiências distintas |
| Runtime e Gateway | Inferência Bedrock e MCP na AWS; entrada do backend restrita à role do Gateway por IAM; JWT humano revalidado na fonte |
| Policy | ALLOW/DENY nativos, logs correlacionados com o backend e políticas ativas iguais ao contrato IaC |
| Registry | Publicação, submissão, revisão por digest, descoberta e invocação; descoberta sem permissão de execução negada |
| Quatro contas | Plataforma `496714466045`, Retail `634124031262`, Transaction `008168963523`, Lending `593273567455`; região `us-east-1` |
| Agentes de origem | Runtimes Riscos/Fraude descobertos no Registry, descriptors conferidos contra IaC e negativa para a audiência da outra aplicação |
| Memory e fonte | Referências por pessoa, isolamento e reautorização após atualização, revogação, exclusão e reingestão |
| RAG | Matriz A/B/C/D, falsificação negada, retrieval direto negado, contexto autorizado, citações, cobertura e logs nativos |

## Ciclo de vida

As cinco fases reutilizaram a sessão `aula15-20261103-675ffc8a`.

| Fase | Build CodeBuild | Resultado |
|---|---|---|
| baseline | `bfbef894-97b8-4e46-a0f0-15caeb028e37` | PASS — referência e versão 1 |
| updated | `024986dc-be95-4d3b-bd85-dc5430eb9eab` | PASS — mesma referência recupera versão 2 |
| revoked | `7467be16-d34a-4f64-a1e2-24cbfcee4a14` | PASS — referência permanece, conteúdo revogado não retorna |
| deleted | `84c90f1c-d046-477f-beb8-8b1b1834a3f9` | PASS — documento excluído não retorna |
| reingested | `9096e902-e648-49e5-be96-b39388468ae6` | PASS — mesma referência recupera versão 3 |
| Restauração | `fb6554ca-5735-406e-a0ca-28c92788952b` | PASS — baseline restaurado antes da rodada final |

O job nativo da exclusão registrou um documento removido e zero falhas.
O backend e a Knowledge Base terminaram em `UPDATE_COMPLETE`, com
`LifecycleStage=baseline`.

## Código, IaC e evidências

* 599 testes passaram; Ruff, cfn-lint e validação estática dos 17 notebooks passaram.
* Terraform confirmou `drift: NONE`, com state remoto em S3.
* Planos somente leitura de 39 stacks confirmaram igualdade dos templates
  implantados com o IaC e ausência de bloqueios de limpeza. Essa comparação
  não equivale à detecção nativa de drift de cada propriedade CloudFormation.
* A rodada anterior de 16 aulas também passou, assim como as cinco fases
  individuais e a restauração. O ambiente permanece implantado para uso.

Índices coletados pelo pipeline:
`evidence/workshop-final-acceptance.json`,
`evidence/workshop-final-audit.json`,
`evidence/workshop-lifecycle.json`,
`evidence/workshop-kb-deletion.json` e
`evidence/workshop-cleanup-plans.json`.
São evidências de execução privadas, não arquivos destinados ao Git.

## Limites do aceite

Databricks é o **simulador hospedado na AWS** solicitado para esta jornada,
implementado com Runtime e DynamoDB. O aceite não comprova Databricks SQL
Warehouse ou Unity Catalog reais. Cognito é o provedor implantado; o material
explica as correspondências com Entra ID, cuja integração exige configuração
e validação próprias.

O código e os notebooks estão preparados para desenvolvimento. O versionamento
do material é separado da publicação da fonte no runner e da execução de um
novo aceite na AWS.
