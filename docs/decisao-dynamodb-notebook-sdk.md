# Aula 15 — tabela DynamoDB nas permissões do evento

Status: correção aplicada ao fluxo SDK do projeto; aula 15 aprovada na AWS.
A correção faz parte da execução dos notebooks já autorizada pelo usuário.
Nenhuma policy do evento foi alterada.

## Erro e diagnóstico

Na conta `813782517426`, região `us-west-2`, as aulas 00–09 passaram com
a sessão do editor. A aula 15 criou o Identity Pool e o AgentCore Memory,
mas `CreateTable` retornou:

```text
AccessDeniedException: not authorized to perform: dynamodb:TagResource
on resource: arn:aws:dynamodb:us-west-2:813782517426:table/santander-a96b1de2499d-memory-source
because no identity-based policy allows the dynamodb:TagResource action
```

`DescribeTable` confirmou `ResourceNotFoundException`, Request ID
`ET80QNQQEQ62KR6BEHI2I1JNORVV4KQNSO5AEMVJF66Q9ASUAAJG`.

O statement `DynamoDBAccess` da policy do editor permite CreateTable,
DescribeTable, DeleteTable e as operações de dados usadas pela aula.
Não inclui TagResource ou ListTagsOfResource. A criação com tags exige
a permissão adicional mesmo sem uma chamada explícita a TagResource.

## A — Definir a tabela sem tags no notebook

Correção em [sdk_memory_lesson.py](../scripts/sdk_memory_lesson.py) e
[sdk_cleanup_lesson.py](../scripts/sdk_cleanup_lesson.py), reproduzida nas
aulas 15 e 99:

* CreateTable não envia o parâmetro opcional Tags.
* O registro guarda o TableId imutável retornado pela criação, além de ARN
  e nome. DescribeTable deve confirmar esse mesmo ID antes de qualquer uso.
* A limpeza confere TableId e conteúdo de todas as linhas. Uma tabela
  recriada com o mesmo nome ou com dados desconhecidos é recusada.
* As condições IAM de actor Memory e LeadingKeys DynamoDB permanecem.
  Os testes negativos e de revogação permanecem nas células.
* Estados históricos que usavam tags continuam tendo sua propriedade
  conferida por tags na limpeza; não são convertidos silenciosamente.

Esta passa a ser a definição da tabela no código. Não haverá criação manual,
adoção de outra tabela ou correção avulsa de policies. A tabela não terá
metadados de tags; sua propriedade nesta jornada será conferida pelo
identificador retornado pela AWS e pelo registro da execução.

Passaram 12 testes de Memory/limpeza, incluindo substituição de TableId,
drift de fonte, role, evento, federação e mapeamento. Ruff e a geração dos
notebooks também passaram. O restante da suíte havia passado em 778 testes
antes deste ajuste de tabela.

Reteste das aulas 15–16 com a sessão do editor:

```bash
uv run python scripts/run_sdk_notebooks.py \
  --expected-account 813782517426 --region us-west-2 \
  --labs 15 16 \
  --output build/notebook-runs/ephemeral-20261105-native-002
```

O relatório `ephemeral-20261105-native-002/report.json` registra PASS para
a aula 15. O Identity Pool emitiu sessões por pessoa; passaram o isolamento
Memory/DynamoDB, a negativa anônima e a revogação na fonte. O registro da
tabela contém o TableId retornado pela AWS. A limpeza 99 e a reconstrução
completa também passaram. A nova tabela recebeu outro TableId, e a aula 15
passou novamente: `ephemeral-20261105-rebuild-001/report.json`.

## B — Manter tags com permissão concedida pelo organizador

O responsável pelo ambiente concede TagResource e ListTagsOfResource no
escopo da tabela pelo mecanismo que administra o evento. A definição com
tags pode então ser preservada. O código do workshop não altera as roles
protegidas do editor.

Não continuar com alterações avulsas: isso separaria a definição do notebook
dos recursos efetivamente criados e comprometeria a retomada e a limpeza.
