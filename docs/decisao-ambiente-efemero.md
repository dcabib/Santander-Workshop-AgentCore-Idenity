# Executar a jornada na nova conta efêmera

Status em 04/11/2026: **o usuário disponibilizou o Code Editor operacional;
execução retomada por esse ambiente**. A navegação retornou HTTP 200 e o STS
do terminal confirmou a conta `992742226465`, usando a role da instância.
O diagnóstico abaixo registra a falha anterior; não é um bloqueio atual.

## Diagnóstico somente de leitura

STS confirmou a conta `992742226465`, região `us-west-2`, com a sessão
autorizada fornecida. A consulta inicial de Gateways não retornou recursos.

O Code Editor dessa conta está na instância `i-02de4967573108f4f`.
Os checks EC2 estão `ok` e o agente SSM está Online, mas o acesso pelo
CloudFront retorna HTTP 504.

O console de inicialização da instância registrou:

```text
chown: invalid user: ‘participant:participant’
Failed to run module scripts-user
Failed to start cloud-final.service
```

O script de inicialização falhou em 04/11/2026 às 09:19 UTC, logo após o boot.
Esperar a propagação DNS não resolve a ausência do usuário exigido pelo script.
Não foram alterados usuário do sistema, role, security group ou configuração
do editor.

## A — Executar os mesmos notebooks no AWS CloudShell

Usar uma sessão CloudShell em `us-west-2`, com a identidade autorizada da conta,
e entregar o código atual como pacote de fontes para teste. Isso não publica
alterações no GitHub e não usa o editor que falhou.

O [roteiro de contas efêmeras](contas-efemeras.md) contém preparação, sessão,
construção, retomada e limpeza. O executor preparado chama somente as células:

```bash
./scripts/setup.sh
uv run python scripts/run_sdk_notebooks.py \
  --expected-account 992742226465 --region us-west-2 \
  --labs 00 01 02 03 04 05
```

Após concluir os testes da seleção e examinar os recursos, a limpeza também
usa suas células:

```bash
uv run python scripts/run_sdk_notebooks.py \
  --expected-account 992742226465 --region us-west-2 --labs 99
```

O executor rejeita conta incorreta e notebooks ainda não convertidos,
interrompe na primeira falha, registra hashes e resultados e remove
credenciais/JWTs das saídas persistidas. Não procura stacks ou recursos da
conta anterior e não cria serviços por fora das células.

Passaram 77 testes focados em notebooks SDK, estado e executor. Isso valida
os contratos do código, não a execução na nova conta.

## B — Aguardar a recriação do Code Editor pelo organizador

O responsável pelo ambiente corrige a imagem ou a inicialização que deveria
criar/configurar o usuário e disponibiliza o editor. Depois executamos a mesma
seleção SDK desde o notebook 00.

Esta opção depende de uma correção na infraestrutura externa do evento.
Criar manualmente o usuário que faltou não comprova que o restante da
instalação esteja correto e não será usado como atalho.

## Escopo da escolha

A regra de AGENTS.md fornecida pelo usuário exige aprovação explícita para
mutação de infraestrutura fora dos scripts do projeto. A escolha permite
definir o ambiente de execução após a falha concreta do editor, sem presumir
autorização para reparar os recursos externos do evento.

As credenciais ficam fora dos arquivos do projeto. Não haverá commit ou push
durante esta retomada. O estado atualizado de cada aula está no
[aceite SDK](aceite-notebooks-sdk.md); as alternativas acima registram
o diagnóstico anterior à disponibilização do editor.
