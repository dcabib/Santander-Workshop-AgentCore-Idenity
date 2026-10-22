# Cleanup dos notebooks

Todos os notebooks terminam com duas etapas: uma célula opcional para planejar
ou executar a remoção de um stack pelo IaC e uma célula que limpa o estado local.
Executar todas as células com os valores padrão limpa apenas as variáveis do
exercício; o cleanup de nuvem permanece `NOT_RUN`.

O cenário **journey** do notebook 12 usa templates em `infra/journey/templates`;
a ordem de remoção está no [runbook integrado](journey/README.md#remoção).
O notebook 13 é inteiramente local e usa as mesmas células de encerramento.
Os módulos Terraform novos mantêm seu próprio state e ciclo de vida.

## Estado local

A célula final remove as referências a tokens, resultados, clientes e controles
do exercício, fecha o cliente de controle AWS quando presente e verifica o
resultado. Pode ser repetida. Sessões MCP usam `async with` e encerram seus
transportes ao sair do bloco.

Evidências, configurações, templates, diagramas e notebooks ficam preservados.
A remoção de variáveis não revoga tokens nem garante apagamento de todas as
cópias em memória. Depois de salvar as evidências sanitizadas, limpe os outputs
e encerre o kernel. Para repetir o laboratório, execute novamente desde o início.

## Remoção por CloudFormation

O wrapper do projeto é `scripts/cleanup.py`. Ele opera **um stack por vez** e
não descobre automaticamente qual ambiente deve ser removido.

Por padrão, apenas consulta STS e CloudFormation. Verifica a conta do perfil,
o nome e ARN do stack, a região e a igualdade do template implantado com o
arquivo do cenário selecionado. Exibe retenções declaradas e bloqueios, sem
expor parâmetros ou valores de segredos.

Exemplo a preencher com os identificadores reais do laboratório:

```bash
uv run python scripts/cleanup.py \
  --scenario banking --template agent \
  --profile PERFIL_PLATAFORMA --account ID_DA_CONTA --region REGIAO \
  --stack NOME_REAL_DO_STACK
```

Os cenários são `workshop` (00–09), `banking` (10) e `federation` (11).
O template deve existir no diretório IaC correspondente.

Depois de revisar o plano e as dependências, execute o mesmo comando
acrescentando `--execute --confirm-stack-id ARN_EXATO_DO_PLANO`. O wrapper
refaz as verificações, solicita `DeleteStack` pelo ARN e aguarda
`stack_delete_complete`. Excluir um stack remove seus recursos conforme o
template; não é um change set de atualização.

Também é possível preencher `CLEANUP_TARGET` na célula do notebook. Mantenha
`CLEANUP_EXECUTE=False` durante a preparação; para aplicar, use o ARN retornado
em `CLEANUP_CONFIRM_STACK_ID` e altere `CLEANUP_EXECUTE=True`.

Uma conta, região, nome ou template divergente impede a preparação.
Proteção de término ou estado não estável impede a execução. O wrapper não
desativa proteções, não força exclusões e não esvazia buckets ou tabelas.
Em caso de erro, preserve o diagnóstico e corrija o IaC ou os identificadores.

## Ordem por trilha

### Notebooks 00–09: ambiente compartilhado

Não remova a infraestrutura ao terminar um notebook intermediário.
Ao concluir toda a trilha:

1. Atualize `origin` com `EnableRuntime=false` pelo `scripts/deploy.py`,
   usando os parâmetros do ambiente e o fluxo de revisão de change set.
2. Remova `registry`. Se usou `policy-draft`, preserve seu output antes da
   remoção do stack; o histórico de geração permanece retido.
3. Atualize `hub` com `EnableFraud=false` pelo mesmo pipeline.
4. Remova `fraud-runtime`, depois `hub` e depois `origin`.
5. Remova os stacks `bootstrap` após revisar os artefatos e as evidências.

Os passos 1 e 3 são atualizações, não exclusões. O wrapper de cleanup deve
ser usado somente para os passos de remoção.
[Parâmetros e implantação da trilha](deploy.md).

### Notebook 10

Remova `agent` → `bindings` → os três stacks das LOBs
(`retail-banking`, `transaction-banking`, `lending-wealth`) → `platform`
→ os quatro `bootstrap`. A cada etapa use o perfil da conta do stack.
[Runbook](banking/README.md).

### Notebook 11

Remova `registry` → `platform-bindings` → os três `*-bindings` das LOBs
→ os três `*-backend` → os quatro `*-gateway` → os quatro `bootstrap`.
[Runbook](federation/README.md).

Os termos acima são nomes de templates; informe os nomes reais dos stacks
criados para seu ambiente.

## O que continua existindo

`Retain` preserva buckets de artefatos, tabelas/fixtures das trilhas bancárias
e o histórico de geração de políticas. O plano lista as retenções declaradas
no template; recursos condicionais podem não estar presentes no stack.
A exclusão do stack não comprova eliminação de todos os recursos ou custos.

Identidades, grants e segredos Entra/Okta, Knowledge Base e sua fonte,
workspace/warehouse Databricks e permissões de dados seguem o IaC de seus
proprietários. O wrapper não os remove. Para o módulo Entra opcional da trilha
original, revise `terraform plan -destroy` no backend correto e aplique pelo
Terraform após a revisão prevista no [runbook do módulo](../infra/entra/README.md).
