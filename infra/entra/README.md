Módulo opcional para um **tenant Entra de laboratório**. Cria APIs Gateway/Fraude,
três agentes confidenciais, um frontend público de login, grants delegados e
segredos dos middle tiers no Secrets Manager da conta hub. A permissão Graph é somente `User.Read`.
Não cria usuários, grupos, BDAGs nem integra o tenant de produção do Santander.

O frontend recebe uma asserção destinada à API do agente. O agente usa seu segredo
para OBO até a API do Gateway; esse segundo token tem o `azp` do agente confidencial.
O Gateway faz outro OBO via AgentCore Identity até Graph/Fraude. Não use um
`client_id` de cliente público como prova de identidade técnica de um agente.

O helper `login_confidential_agent` executa o primeiro OBO no host do instrutor,
com leitura temporária do segredo pelo perfil AWS. Em produção, essa etapa deve
residir no workload do agente, usando seu role e armazenamento aprovado.

Use um backend Terraform protegido já aprovado pela equipe antes de `apply`.
O estado contém o valor do segredo, mesmo que outputs sejam ocultos. Não
versione state, `.tfvars`, planos binários ou arquivos de credenciais.

```bash
terraform -chdir=infra/entra init
terraform -chdir=infra/entra validate
terraform -chdir=infra/entra plan -var-file=../../config/local.entra.tfvars -out=../../build/entra.tfplan
# Após revisão do plano e com o tenant/conta corretos:
terraform -chdir=infra/entra apply ../../build/entra.tfplan
terraform -chdir=infra/entra output -json hub_identity_parameters
```

Variáveis: `tenant_id`, `aws_profile`, `aws_region`, `hub_account_id` e
`secret_expiration` (ISO8601). A autenticação AzureAD usa a cadeia normal do
provider; não coloque senhas em argumentos. Os OIDs de três usuários de teste
existentes entram posteriormente nos parâmetros do stack hub.

Se já houver aplicações geridas pelo IaC do cliente, use seus outputs e não
aplique este módulo. Admin consent, políticas de acesso condicional e MFA devem
ser compatíveis com o fluxo de login escolhido; o código não os altera.
