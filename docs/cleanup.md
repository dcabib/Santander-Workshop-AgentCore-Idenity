# Encerrar os laboratórios

A última etapa de cada notebook encerra o exercício local. A remoção da
infraestrutura é uma operação separada, feita pelo mesmo IaC que a criou.
Não exclua um ambiente compartilhado ao terminar um notebook intermediário.

## Limpeza local

As células de limpeza fecham clientes quando aplicável e removem referências a
tokens, resultados e controles. As sessões MCP encerram seus transportes ao
sair de `async with`. Evidências sanitizadas e arquivos do projeto permanecem.

Remover uma variável não revoga um token nem garante apagar todas as cópias em
memória. Salve as evidências necessárias, limpe os outputs e encerre o kernel.
Para repetir o exercício, execute o notebook desde o início. Com os valores
padrão, a remoção cloud permanece `NOT_RUN`.

## CloudFormation: conferir antes de excluir

[scripts/cleanup.py](../scripts/cleanup.py) opera um stack por vez. O modo padrão
é somente leitura: confere STS, conta, região, nome, ARN e igualdade do template
implantado com o template do cenário. Mostra retenções e bloqueios sem imprimir
segredos.

```bash
uv run --frozen --extra banking python scripts/cleanup.py \
  --scenario banking --template agent \
  --profile PERFIL_PLATAFORMA --account ID_DA_CONTA --region REGIAO \
  --stack NOME_REAL_DO_STACK
```

Substitua os identificadores pelo ambiente que você implantou. Os cenários
aceitos são `workshop`, `banking`, `federation`, `journey` e `rag`.
Após revisar o resultado, repita o comando com
`--execute --confirm-stack-id ARN_EXATO_DO_PLANO`. O wrapper refaz as verificações
e solicita a exclusão por CloudFormation usando o ARN.

Nos notebooks, os controles equivalentes são `CLEANUP_TARGET`,
`CLEANUP_EXECUTE` e `CLEANUP_CONFIRM_STACK_ID`. Proteção de término, template
diferente ou estado incompatível impedem a execução. O wrapper não desativa
proteções nem esvazia recursos retidos.

## Ordem de remoção por ambiente

Os nomes abaixo identificam templates; use os nomes reais dos stacks e o perfil
da conta correspondente a cada um.

| Laboratório | Ordem |
|---|---|
| 00–06, 08, 10 e 13 | Atualizar `origin` com `EnableRuntime=false`; remover `registry` e eventual `policy-draft`; atualizar `hub` com `EnableFraud=false`; remover `fraud-runtime`, `hub`, `origin` e `bootstrap` |
| 07 | `approve` → `submit` → `publish` → `foundation` → `bootstrap`; veja o [guia Registry](registry/README.md#limpeza) |
| 11 | `agent` → `bindings` → três LOBs → `platform` → quatro `bootstrap` |
| 12 | `registry` → `platform-bindings` → três bindings das LOBs → três backends → quatro Gateways → quatro `bootstrap` |
| 14 | `origin-bindings` → dois agentes → `registry` e `platform-bindings` → `data-bindings` → três Gateways → `bootstrap` |
| 15 | Somente limpeza local |
| 16 | Template `access-cognito` (stack terminado em `-access`) → `data` → `identity` → `bootstrap` |

As duas atualizações de 00–06, 08, 10 e 13 usam [scripts/deploy.py](../scripts/deploy.py)
com revisão de change set; são necessárias para remover dependências. O wrapper
de cleanup executa apenas os passos de exclusão.

## Terraform: laboratório 09

No mesmo checkout, configuração e state usados no deploy:

```bash
uv run --frozen --extra banking python scripts/terraform_deploy.py plan-destroy
uv run --frozen --extra banking python scripts/terraform_deploy.py destroy
```

Revise o plano entre os comandos. O wrapper aplica o plano salvo e o Terraform
calcula a ordem das dependências. O bucket exclusivo de artefatos declara
`force_destroy=true`: suas versões também são apagadas, mantendo o versionamento
habilitado até a exclusão. Use esse bucket apenas para artefatos do laboratório.
Veja os detalhes no [guia Terraform](terraform/README.md).

## O que pode permanecer

`Retain` preserva buckets de artefatos, tabelas dos cenários bancários e histórico
de geração de políticas. No laboratório 16, KB, fonte e bucket documental usam
`RetainExceptOnCreate`: são removidos em rollback da criação, mas preservados
na exclusão normal de uma implantação concluída. A remoção dos stacks pode,
portanto, deixar recursos e custos.

Identidades Entra/Okta, grants, fontes externas e infraestrutura Databricks
seguem o IaC dos seus proprietários. Para módulos Terraform do projeto, revise
`plan -destroy` no backend correto antes de aplicar. Recursos retidos precisam
de uma decisão explícita de destino e reconciliação pelo IaC; não os apague
manualmente como parte do encerramento do notebook.
