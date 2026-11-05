# Retomar as personas com uma sessão AWS autorizada

Status em 04/11/2026: **alternativa A aprovada pelo usuário: novo ciclo com
a sessão fornecida. Limpeza concluída e aulas 00–07 aprovadas na AWS.**

A execução `212b89261d98` terminou CLEANED, com 30 referências liberadas.
A aula 00 iniciou `41faf1babbbf`; as oito aulas passaram usando a sessão
`WSOpsRole`. A aula 07 criou novas personas e executou as 16 simulações
IAM esperadas, sem alteração da role do editor.

Durante a limpeza, a leitura imediata de `DescribeSecret` ainda não refletia
o agendamento já realizado. Uma nova consulta confirmou `DeletedDate`.
A célula passou a aguardar essa confirmação, sem repetir a exclusão nem
reduzir a janela de recuperação. A retomada concluiu o registro de limpeza.
Os relatórios da primeira tentativa e da retomada foram preservados.

## O que passou e onde parou

As aulas 00–06 passaram na conta nova, em `us-west-2`. A limpeza 99 passou,
fechou a execução `0f2344b88999` e a aula 00 iniciou `212b89261d98`.
Nessa segunda execução, 00–06 passaram novamente, incluindo nova geração
de política e novo Registry.

A aula 07 criou suas quatro roles, mas recebeu:

```text
AccessDenied when calling SimulatePrincipalPolicy:
no identity-based policy allows the iam:SimulatePrincipalPolicy action
```

A sessão do Code Editor não possui essa ação. Suas policies também autorizam
`sts:AssumeRole` somente para algumas roles com nomes fixos do evento e
roles `cdk-*`; elas não incluem as novas personas do workshop.
Renomear nossas roles para aproveitar essas permissões mudaria o desenho
para depender do ambiente e não foi usado como solução.

Com a sessão `WSOpsRole` fornecida pelo usuário, o diagnóstico somente de
leitura executou as 16 simulações da matriz e obteve os resultados esperados.
Isso confirma as policies das personas, mas **não representa execução
completa da aula 07 no kernel AWS**.

As trust policies das personas atuais apontam para a role do Code Editor,
que as criou. A troca de sessão não deve reescrever essa confiança
silenciosamente.

## A — Novo ciclo com a sessão temporária fornecida

1. Executar a limpeza 99 atualizada, que inclui as quatro personas e verifica
   tags, trust policies, hashes e dependências. Somente os recursos registrados
   da segunda execução são removidos; a role e os recursos do editor ficam
   fora desse conjunto.
2. Usar a sessão temporária fornecida pelo usuário na memória do executor,
   por entrada oculta. O código preparado recusa terminais que fariam eco,
   não cria arquivos de credenciais e restaura o ambiente do processo ao sair.
3. Executar 00–07 desde o início. Novos IDs e nomes são gerados e as novas
   personas confiam no principal IAM dessa sessão, conforme mostrado pela
   célula. Não há alteração avulsa das trust policies anteriores.
4. Retomar as aulas seguintes somente depois do aceite.

Comandos aprovados, executados no ambiente AWS:

```bash
uv run python scripts/run_sdk_notebooks.py \
  --expected-account 992742226465 --region us-west-2 --labs 99

uv run python scripts/run_sdk_notebooks.py \
  --expected-account 992742226465 --region us-west-2 \
  --prompt-credentials --labs 00 01 02 03 04 05 06 07
```

As credenciais já fornecidas serão usadas sem repeti-las na conversa,
nas células ou no histórico do shell. O STS confere a conta antes de abrir
os kernels. Se a sessão expirar, será necessário renová-la.

## B — Manter a sessão do editor e aguardar o organizador

O responsável pelo ambiente disponibiliza uma sessão que possa simular
políticas e assumir as personas da execução. Se optar por mudar a role
protegida do editor, isso pertence ao IaC do ambiente administrado por ele.
O repositório do workshop não modifica esse ambiente.

Após a correção, retomamos a aula 07 com os recursos e a confiança atuais.

## Por que a escolha é necessária

A instrução AGENTS.md fornecida pelo usuário determina, após um bloqueio:
“Diagnose with read-only commands”, apresente alternativas e “Wait for the
user's reply”. Este é um novo bloqueio concreto de permissões. Não houve
alteração da role protegida, troca de confiança ou remoção dos recursos
após essa negativa, até a aprovação explícita da alternativa A.

A alternativa A mantém a criação e limpeza nas células do projeto. Não
introduz CloudFormation, nomes fixos de roles do evento nem pré-deploy.

Validação preparada: 734 testes passaram, incluindo entrada oculta de
credenciais, restauração do ambiente, matriz de personas, retomada e
recusa de alterações inesperadas em policies e trust.
