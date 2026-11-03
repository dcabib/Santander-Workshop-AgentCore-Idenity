# Aula 01 — bloqueio Cognito e alternativa preparada

Status em 03/11/2026: **alternativa A aprovada e aplicada na AWS**.
O notebook atualizou o cliente e criou os usuários, avançando até a criação
da Lambda. A execução encontrou um [novo bloqueio de tags Lambda](decisao-lambda-notebook-sdk.md).
O login e a chamada MCP ocorrem depois dessa etapa e ainda não foram validados
nesta execução.

## Falha observada

Executamos a nova aula 01 pelo kernel do VS Code na AWS, na conta
`456332459064`, região `us-west-2`. As células criaram o User Pool, o app client
e o segredo de senhas sintéticas. A célula de usuários parou:

```text
AccessDeniedException: cognito-idp:AdminGetUser
because no identity-based policy allows the cognito-idp:AdminGetUser action
```

Role: `workshop-resources-ec2-CodeEditorInstanceRole-3DJSoNBtcmKi`.
Pool: `us-west-2_qtKSAoq8D`.

O diagnóstico somente de leitura também confirmou a negativa para `ListUsers`.
A policy Cognito consultada permite `AdminCreateUser`, `AdminSetUserPassword`,
`UpdateUserPoolClient` e `InitiateAuth`; não contém grants para `AdminGetUser`,
`ListUsers` ou `AdminInitiateAuth`. Isso é uma leitura das policies disponíveis,
não uma simulação completa de SCPs ou de todas as operações futuras.

Não foram criados usuários, Lambda ou Gateway por esta execução. Não alteramos
permissões da role do VS Code. Ela tem proteção explícita contra alterações
nas próprias policies.

## A — Usar o fluxo de autenticação Cognito do usuário

Código preparado em
[`scripts/sdk_gateway_lesson.py`](../scripts/sdk_gateway_lesson.py):

1. Novos app clients usam `ALLOW_USER_PASSWORD_AUTH`. Para o cliente já criado,
   uma célula visível chama `UpdateUserPoolClient` para substituir o fluxo
   administrativo anterior. O Client ID e os tempos de validade permanecem.
2. `AdminCreateUser` retorna os atributos da pessoa. O notebook salva o `sub`
   antes de configurar a senha; a retomada usa esse registro. Um nome já
   existente sem registro gera erro, sem adoção automática.
3. `AdminSetUserPassword` configura a senha sintética no primeiro cadastro.
   Um marcador de conclusão guarda somente username e pool ID. O notebook
   não lista pessoas nem consulta `AdminGetUser`.
4. `InitiateAuth(USER_PASSWORD_AUTH)` autentica a pessoa com a senha armazenada
   no Secrets Manager. O notebook valida assinatura, issuer, audiência,
   expiração, tipo de token e o `sub` esperado.
5. Retomar a execução sequencial da aula, conferindo o teste negativo JWT
   e a chamada MCP que precisa retornar o Request ID da Lambda na AWS.

Essa alternativa usa um fluxo nativo Cognito. O pool continua com cadastro
restrito ao administrador; os tokens não são impressos. Nenhuma policy do
ambiente precisa ser ampliada. A criação dos recursos continua visível nas
células, sem CloudFormation.

Os testes de contrato usam o modelo do SDK instalado, verificam retomada sem
recriação, migração do fluxo sem mudar a audiência e rejeição de recursos de
outra execução. A configuração foi aplicada na AWS após a escolha do usuário;
o aceite da aula permanece pendente por causa do bloqueio posterior.

## B — Manter o fluxo administrativo e ajustar o ambiente

O administrador da conta pode avaliar e conceder `AdminGetUser` e
`AdminInitiateAuth`, com escopo no pool, pelo mecanismo que administra as
permissões do evento. Depois, o notebook pode manter a primeira implementação.
Essa alternativa depende de ação externa e não autoriza editar a role protegida
diretamente pelo notebook.

## Estado e risco

Os IDs dos recursos criados estão em `.workshop/`, fora do Git. Alterar
roles protegidas ou fazer uma correção avulsa na conta perderia a relação entre
o material didático e as permissões administradas pelo evento. Por isso a
execução parou no bloqueio, conforme a regra de AGENTS.md.

O notebook 00 passou novamente com a versão revisada. A aula 01 e a limpeza 99
ainda não têm aceite AWS completo. As aulas 02–16 permanecem em migração.
