# Identidades Entra para a bancada 00–09

Este módulo prepara um tenant Entra de laboratório para estudar usuário,
aplicação e delegação nos notebooks iniciais. Ele pertence ao
[guia de implantação da bancada](../../docs/deploy.md#2-preparar-as-identidades-entra);
os cenários 11 e 12 têm topologias de identidade próprias.

## Entender as duas trocas

O frontend público autentica a pessoa e recebe uma asserção destinada à API do
agente. O agente confidencial usa seu segredo para fazer OBO até a API do Gateway.
O novo token identifica esse agente em `azp`. AgentCore Identity faz a próxima
troca em nome do Gateway para Graph ou Fraude.

O módulo cria APIs Gateway/Fraude, três agentes confidenciais, o frontend,
grants delegados e segredos dos middle tiers no Secrets Manager da conta hub.
A permissão Graph é `User.Read`. Usuários e grupos de teste já devem existir;
o módulo não concede acesso a fontes de dados.

No exercício, `login_confidential_agent` executa o primeiro OBO no host do
instrutor com leitura temporária do segredo. Numa aplicação hospedada, essa
operação pertence à workload do agente e à sua role. O client ID do frontend
público não é prova da identidade técnica de um agente confidencial.

## Configurar e aplicar

Preencha `tenant_id`, `aws_profile`, `aws_region`, `hub_account_id` e
`secret_expiration` (ISO 8601) em `config/local.entra.tfvars`. A autenticação usa
a cadeia do provider AzureAD; não coloque senhas em argumentos. Os OIDs dos
usuários entram depois nos parâmetros do hub.

Configure o backend protegido antes de aplicar: o state contém os segredos,
mesmo que os outputs os ocultem. Não compartilhe state, tfvars, planos ou
credenciais. Se as aplicações já forem geridas por outro IaC, use seus outputs
em vez de criar outro conjunto.

```bash
terraform -chdir=infra/entra init
terraform -chdir=infra/entra validate
mkdir -p build
terraform -chdir=infra/entra plan -var-file=../../config/local.entra.tfvars -out=../../build/entra.tfplan
terraform -chdir=infra/entra apply ../../build/entra.tfplan
terraform -chdir=infra/entra output -json hub_identity_parameters
```

Revise tenant, conta e alterações entre `plan` e `apply`. Admin consent, MFA e
acesso condicional precisam permitir o fluxo escolhido; o módulo não desativa
esses controles. Use os outputs como entrada do CloudFormation da bancada.

Para encerrar, revise `plan -destroy` no mesmo backend e aplique pelo Terraform
somente aos recursos exclusivos desse laboratório. A [limpeza](../../docs/cleanup.md)
explica a ordem das dependências AWS.

## Aprofundar

- [Fluxo OBO no Entra](https://learn.microsoft.com/pt-br/entra/identity-platform/v2-oauth2-on-behalf-of-flow)
- [Claims dos access tokens](https://learn.microsoft.com/pt-br/entra/identity-platform/access-token-claims-reference)
- [Conceitos de identidade do workshop](../../docs/conceitos.md)
