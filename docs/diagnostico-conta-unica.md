# Teste da jornada de conta única — 03/11/2026

**Resultado: implantação bloqueada por permissões do evento; nenhum notebook
executado.** A jornada selecionada é 00–09 e 15–16, na conta participante
`456332459064`, região `us-west-2`. As aulas 10–14 permanecem fora desse escopo.

O código, templates, documentação e notebooks foram preparados para conta
única em um checkout separado, sem reutilizar state ou outputs do ambiente de
referência. Os artefatos são Linux ARM64/Python 3.12. Credenciais temporárias
não foram gravadas na configuração, fonte ou evidências.

## Evidências da implantação

| Etapa | Resultado observado |
|---|---|
| STS | Conta configurada; sessão `WSParticipantRole/Participant` |
| Registry, AgentCore Policy e Knowledge Bases | APIs de listagem acessíveis em us-west-2 |
| Bootstrap principal | `santander-workshop-core-bootstrap`: CREATE_COMPLETE |
| Bootstrap Registry | `registry-personas-bootstrap`: CREATE_COMPLETE |
| Bootstrap RAG | `santander-rag-rag-bootstrap`: CREATE_COMPLETE |
| Identidade Cognito | `santander-workshop-core-identity`: ROLLBACK_COMPLETE |
| Fundação Registry | `registry-personas-foundation`: ROLLBACK_COMPLETE |
| Terraform | Backend S3/lock inicializado; validate passou; plano de 24 criações, zero alterações/exclusões; apply não executado |
| CodeBuild e notebooks | Runner não implantado; zero aulas executadas |

Os dois stacks que falharam têm todos os recursos listados em DELETE_COMPLETE.
Os bootstraps e o bucket do state permanecem disponíveis. Os planos de
recuperação foram consultados sem executar exclusões.

O artefato principal tem SHA-256
`02085c6533575d26a56f922652d17af59b608bbdb4d4298fb6d07f34125d82a8`.
Os logs, configurações e planos ficam em `build/` e `evidence/`, ignorados pelo
Git. O aceite histórico de quatro contas não comprova essa nova implantação.

## Bloqueios confirmados pela AWS

1. Na identidade, `SecretA`–`SecretD` falharam com:

   ```text
   not authorized to perform: secretsmanager:GetRandomPassword
   because no identity-based policy allows the action
   ```

   Request ID de `SecretA`: `2fb4edea-22fc-4975-afd1-2aad9dbf8e34`.
   O CloudFormation usa essa API para gerar senhas aleatórias. As três policies
   anexadas à role não contêm permissões para Secrets Manager.

2. No Registry, `RiskTool` e `RegistryProvider` falharam com HTTP 403:

   ```text
   not authorized to perform: iam:PassRole
   ```

   Request ID de `RiskTool`: `dd8aba7d-403f-47bb-a4af-4609d0cfe5eb`.
   A condição `iam:PassedToService` da policy do evento não inclui
   `lambda.amazonaws.com`. Também não inclui `codebuild.amazonaws.com`,
   necessário posteriormente para implantar o runner.

3. `ProtectWorkshopRoles` nega explicitamente alterações nas roles `WS*`.
   A sessão participante não pode corrigir a própria role. Há também uma
   negação de role chaining, com exceções para personas do workshop original;
   ela não autoriza assumir diretamente as personas deste projeto.
   As aulas propostas usam as personas a partir da role CodeBuild declarada
   no IaC. Não renomeie roles para contornar essas restrições.

A simulação IAM do operador retornou `AccessDenied`. A análise das policies
é documental; não equivale a uma simulação completa com SCPs/contexto.

## Alternativas para retomar

**A — O responsável pelo evento ajusta o IaC das permissões.** Integrar as
permissões necessárias na definição que administra `WSParticipantRole`,
usando uma identidade autorizada. O IaC dessa role não está neste repositório.
Pontos identificados para revisão:

* `secretsmanager:GetRandomPassword` em `Resource: "*"`, pois a API não opera
  sobre um segredo existente.
* Gerenciamento dos segredos gerados pelos stacks de identidade, incluindo
  CreateSecret, DescribeSecret, GetSecretValue, PutSecretValue, UpdateSecret,
  DeleteSecret, TagResource e UntagResource, restrito aos recursos do workshop.
* `iam:PassRole` para as roles do projeto usadas por Lambda e CodeBuild,
  condicionado aos respectivos serviços.
* `iam:UpdateAssumeRolePolicy` nas roles do projeto: o Gateway restringe sua
  trust policy ao ARN exato após a primeira criação. Essa ação não aparece
  nos grants lidos da role participante.

Esta lista cobre os bloqueios observados e dependências identificadas; novas
etapas ainda precisam ser testadas. As proteções das roles do evento permanecem
sob controle do administrador. Não ampliar privilégios alterando policies
compartilhadas por um caminho alternativo.

**B — Usar uma role/perfil de implantação autorizado na mesma conta.**
Informar sua referência e manter `us-west-2`, o IaC e o mesmo escopo de 12 aulas.
A conta será conferida novamente por STS antes de qualquer retomada.

Depois da escolha e da correção das permissões:

1. Conferir os dois stacks vazios e os planos de recuperação.
2. Recuperá-los pelo wrapper `scripts/cleanup.py`, conferindo template e ARN
   exato, e recriar pelas fases `identity` e `foundation` dos pipelines.
3. Retomar o núcleo, Registry, Terraform e RAG; implantar o runner para as
   12 aulas; executar, coletar e auditar as evidências.

Criar senhas avulsas, usar a role protegida como role de serviço ou editar IAM
fora da definição do evento não resolve a ausência de uma implantação
reproduzível. A retomada aguarda a escolha exigida pela regra de AGENTS.md.
