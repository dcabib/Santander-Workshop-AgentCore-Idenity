# Diagnóstico da conta de participante em us-west-2

Consulta realizada em 03/11/2026, às 18:31 UTC, usando a sessão temporária
fornecida para o teste. Credenciais foram usadas em memória e não foram
incluídas neste documento, na configuração do projeto ou nas evidências.

**Resultado: pré-requisitos bloqueados; zero notebooks executados.**
A consulta AWS foi somente leitura. Não houve implantação nem alteração de
recursos.

| Verificação | Resultado observado |
|---|---|
| STS | Conta `456332459064`, role `WSParticipantRole`, sessão `Participant` |
| Região solicitada | `us-west-2` |
| Modelo Nova Lite | Disponibilidade regional e entitlement disponíveis; autorização `AUTHORIZED` |
| CloudFormation | Um stack ativo inspecionado; nenhum com os prefixos do workshop `santander-` ou `registry-personas-` |
| CodeBuild | Zero projetos na região |
| AgentCore Gateway | Zero Gateways na região |
| AgentCore Runtime | Zero Runtimes na região |
| Validação da configuração | `WORKSHOP_REGION: esta jornada foi preparada para us-east-1` |
| Topologia | Uma conta fornecida; o runner e as aulas 10–14 exigem quatro na implementação atual |

A disponibilidade do modelo não comprova inferência ou execução das aulas.
Não foram testadas permissões de criação, quotas suficientes para a implantação,
nem as integrações Registry, Terraform e RAG nessa conta.

O bloqueio regional acima vem do validador do projeto; não é uma conclusão de
que os serviços AWS sejam indisponíveis em `us-west-2`. Trocar apenas a região
ou reutilizar os outputs do ambiente de referência não instala os recursos
nesta conta e não produz um aceite válido.

## Caminhos possíveis

**A — Preparar uma jornada de conta única em us-west-2 pelo IaC.**
Adaptar e validar o suporte regional e a implantação do runner com dependências
selecionáveis. Preparar as integrações necessárias e executar 00–09 e 15–16.
As aulas 10–14 ficam fora da execução do participante, com demonstração do
instrutor no ambiente completo. Essa versão do runner ainda não está
implementada; a preparação é necessária antes do deploy.

**B — Executar a jornada completa no ambiente de referência.**
Usar as quatro contas preparadas em `us-east-1`, após conferir as sessões e
publicar a fonte atualizada pelo pipeline. Isso testa o ambiente de referência,
não a conta de participante fornecida.

**C — Preparar a jornada completa em us-west-2.**
Disponibilizar três outras contas e respectivas roles/perfis, adaptar e validar
o suporte regional e implantar todas as dependências pelo IaC antes de executar
as 17 aulas.

Não será aplicado um ajuste avulso na nuvem para contornar os pré-requisitos.
A decisão do caminho segue o protocolo de bloqueio do AGENTS.md fornecido pelo
responsável pelo projeto.

Evidência privada: `evidence/account-readiness-us-west-2.json`, com IDs de
requisição e resultados de leitura. Ela não é um relatório de aceite operacional.
