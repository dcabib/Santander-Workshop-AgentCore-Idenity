# Executar o workshop em contas efêmeras

Cada conta começa uma construção nova. Os recursos da solução são criados
pelas células dos notebooks, usando os IDs retornados pela AWS. Não se
reutilizam pool Cognito, buckets, roles, endpoints, políticas ou arquivos de
configuração de um evento anterior.

**Estado atual:** 00–09, 15–16 e 99 têm o formato SDK. Na conta de
05/11/2026, 00–09, 15 e 16 passaram usando a sessão do editor, incluindo federação
Cognito e [tabela com TableId](decisao-dynamodb-notebook-sdk.md).
O RAG confirmou geração no Runtime e isolamento por ACL.
99 confirmou a limpeza completa, e os 12 notebooks passaram novamente
em uma reconstrução do zero com novos identificadores;
10–14 continuam em migração. Os resultados
de contas encerradas são históricos e não substituem um novo ciclo.

A jornada usa as três personas previstas no workshop oficial de Registry:
`admin_persona`, `publisher_persona` e `consumer_persona`. O editor do evento
permite assumi-las. Em outra conta, o organizador precisa conceder
`sts:AssumeRole` nesses três ARNs. O código não exige `iam:SimulatePrincipalPolicy`.
Nomes já usados por outra execução são recusados antes da criação; mantenha
uma jornada ativa por conta e limpe-a pela aula 99 antes de recomeçar.

A exclusão da fonte Bedrock MANAGED é assíncrona e pode exceder cinco
minutos. Sua célula de limpeza aguarda até 14 minutos. Se essa espera
expirar, execute novamente 99: a célula acompanha a exclusão existente
ou confirma a ausência do ID registrado antes de seguir. Não apague o
arquivo de estado nem execute 00 para abandonar recursos ainda registrados.

A aula 15 usa Cognito Identity Pool para emitir sessões por pessoa, com
mapeamento explícito de sub e recusa de login anônimo ou sem regra.
Isso não exige AssumeRole pela sessão do participante. Veja a
[revisão para as permissões do evento](decisao-sessao-participante-20261105.md).

## 1. Abrir um ambiente de execução na AWS

Use um ambiente de notebooks na AWS ou o AWS CloudShell na região escolhida.
O Code Editor fornecido pelo evento é uma conveniência; seu domínio, usuário
de sistema e role não fazem parte dos requisitos do código.

No CloudShell, o terminal executa os mesmos arquivos `.ipynb` usando o executor
do projeto. Para acompanhar as células interativamente, use Jupyter/VS Code
no ambiente AWS disponível. Nenhum agente, ferramenta ou modelo executa
como serviço no computador do participante.

O acesso à conta e ao ambiente precisa estar disponível antes da aula. Uma
falha de inicialização do editor do evento deve ser tratada pelo responsável
por esse ambiente; `setup.sh` não corrige sua infraestrutura.

## 2. Obter a versão do código a ser demonstrada

Use o repositório ou um pacote de código fornecido pelo instrutor. Confira a
versão antes de testar. Um clone do GitHub só contém o que foi publicado;
alterações ainda em revisão precisam estar no pacote entregue para o teste.

Comece em uma pasta nova, sem copiar `.venv`, `build`, credenciais ou arquivos
privados de outro evento. O arquivo `uv.lock` pertence ao código e deve ser
preservado. O histórico de identificadores pode ser guardado como evidência,
mas nunca editado para adotar recursos de outra conta.

Dentro da pasta do projeto:

```bash
# CloudShell: instalar uv no ambiente do usuário, se ainda não estiver disponível.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

./scripts/setup.sh
```

Esse script instala dependências e registra **Santander Workshop (.venv)**.
Ele não cria recursos AWS. Não é necessário executar scripts de deploy,
CloudFormation, Terraform ou um runner CodeBuild antes das aulas SDK.

## 3. Conferir sessão, conta e região

Use a identidade autorizada do ambiente AWS. CloudShell e ambientes com role
de execução evitam depender de credenciais copiadas de outro evento.
Credenciais temporárias fornecidas pelo organizador são usadas na sessão,
nunca coladas nas células nem guardadas no repositório.

```bash
export AWS_DEFAULT_REGION="us-west-2"
aws sts get-caller-identity
```

Confira os 12 dígitos da conta com o organizador. Escolha a região antes da
criação: recursos de outra região não são adotados automaticamente.

Se a sessão expirar, renove-a pelo mecanismo do ambiente, reinicie o kernel e
retome a aula. Não apague o registro para resolver uma expiração. Exportar
variáveis em um terminal não atualiza um kernel que já estava aberto.

Contas efêmeras continuam sujeitas a permissões, restrições do evento,
quotas e disponibilidade regional. STS funcionar não comprova autorização
para todas as APIs. As aulas mostram as operações necessárias e não alteram
roles protegidas do ambiente para contornar uma negativa.

Se o organizador fornecer uma sessão temporária diferente da role do editor,
o executor aceita `--prompt-credentials`. Os três valores são lidos em entrada
oculta, ficam apenas na memória do processo e dos kernels e não são guardados
em arquivo. A opção recusa um terminal incapaz de ocultar a entrada. Não cole
os valores no comando ou nas células.

Uma sessão nova pode mudar o principal confiável das personas. Não reescreva
trust policies nem edite o registro para forçar uma retomada: use o ciclo
de limpeza e reconstrução aprovado ou preserve a identidade autorizada
original. O [diagnóstico da aula 07](decisao-personas-conta-efemera.md)
mostra um caso real dessa diferença.

## 4. Construir os recursos durante as aulas

Abra `notebooks/00_preflight.ipynb`, selecione o kernel e execute as células.
O notebook identifica a conta pelo STS e cria `.workshop/<conta>-<região>.json`.
Esse arquivo contém somente IDs e referências, fica fora do Git e não
depende de uma configuração privada do instrutor.

Continue em ordem pela seleção já convertida:

| Aula | O que será construído ou demonstrado |
|---|---|
| 00 | Sessão, região, SDK e registro próprio da conta |
| 01 | Cognito, pessoas sintéticas, IAM, Lambda, Gateway e target |
| 02 | Outra aplicação Cognito e negativas de audiência/assinatura |
| 03 | Bucket, artefato, role e Runtime MCP; identidade do workload |
| 04 | Engine, Cedar, ENFORCE e decisões por pessoa/parâmetro |
| 05 | Geração de rascunho na AWS, revisão e LOG_ONLY |
| 06 | Registry com aprovação manual, descoberta IAM e negativa anônima |
| 07 | Três personas do workshop oficial; STS e testes reais de leitura permitida/negada |
| 08 | Registro MCP, submissão, aprovação, descoberta e invocação com sessões IAM |
| 09 | Target Runtime no Gateway, assinatura IAM e autorização Cedar por pessoa |
| 15 | Identity Pool, sessões por pessoa, Memory por actor e revogação na fonte |
| 16 | Base MANAGED, corpus e ACL nativa, conector, Cedar e geração no Runtime; validada na AWS |

Cada criação aparece em uma célula, seguida de consulta de estado e uso do
serviço. Uma retomada confere os recursos registrados antes de reutilizá-los.
Um registro copiado e renomeado para outra conta é rejeitado.

Para teste sequencial pelo terminal **na AWS**, execute os mesmos notebooks:

```bash
read -r -p "ID da conta AWS conferido com o organizador: " WORKSHOP_ACCOUNT_ID
uv run python scripts/run_sdk_notebooks.py \
  --expected-account "$WORKSHOP_ACCOUNT_ID" \
  --region "$AWS_DEFAULT_REGION" \
  --labs 00 01 02 03 04 05 06 07 08 09 15 16
```

O executor apenas abre os notebooks e executa suas células. Ele não implanta
recursos por fora delas, não consulta stacks e interrompe na primeira falha.
A seleção inteira é conferida antes do primeiro kernel, e cada notebook
confere novamente a conta esperada.

As evidências em `build/notebook-runs/` incluem os notebooks executados,
SHA-256 das fontes, resultado, conta, região e identidade. Evidência de uma
conta expirada não comprova o funcionamento da conta atual. Uma validação
com `--validate-only` confere sintaxe/material e nunca representa aceite AWS.

## 5. Retomar ou trocar de conta

Na mesma conta/região, preserve `.workshop/` e repita a célula interrompida
ou a aula. Não reutilize tokens de um kernel anterior.

Em outra conta, volte à aula 00. O STS seleciona outro arquivo de estado e
outro identificador de execução. Não é preciso excluir o histórico da conta
anterior nem conhecer seus nomes de recursos.

Se a conta anterior já foi encerrada pelo organizador, registre isso como
limitação do teste. Não tente acessar ou limpar a conta substituta com os
IDs antigos. A nova execução começa desde a criação dos recursos.

## 6. Limpar antes de encerrar o evento

Execute `99_cleanup_sdk.ipynb` enquanto a conta e a sessão ainda estiverem
disponíveis. Leia os IDs exibidos: a limpeza verifica propriedade, conteúdo
e dependências e exclui somente os recursos registrados desta execução.

Pelo terminal AWS, a seleção explícita de 99 solicita a mesma limpeza:

```bash
uv run python scripts/run_sdk_notebooks.py \
  --expected-account "$WORKSHOP_ACCOUNT_ID" \
  --region "$AWS_DEFAULT_REGION" \
  --labs 99
```

Não existe limpeza automática ao executar a seleção de aulas. Ela poderia remover
recursos que o participante ainda está estudando. O segredo tem janela de
recuperação de sete dias, e assets de geração de políticas expiram em sete
dias conforme o serviço; esses limites são exibidos na aula.

Após a limpeza confirmada, o registro fica fechado. Na próxima execução da
aula 00, ele é arquivado em `.workshop/history/` e um novo prefixo é escolhido,
inclusive na mesma conta. Isso evita reutilizar nomes ainda reservados pela
janela de recuperação dos segredos. Uma execução com recursos pendentes
não pode ser reiniciada dessa forma.

Guarde as evidências sem credenciais antes de o organizador encerrar a conta.
O fechamento da conta não substitui o teste das chamadas de limpeza.

## 7. Cenários com múltiplas contas

Uma única conta efêmera atende somente à jornada de conta única. Os cenários
10–14 precisam das contas distintas declaradas em cada aula; seus acessos
devem permanecer válidos durante a construção e o teste.

O legado ainda exige quatro contas: plataforma, Retail, Transaction e Lending.
Esse bloco está em migração e não deve ser incluído no executor SDK atual.
Não use três perfis apontando para a mesma conta como teste de isolamento
entre contas.
