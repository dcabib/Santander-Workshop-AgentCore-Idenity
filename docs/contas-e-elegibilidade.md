# Contas necessárias e seleção das aulas

**O workshop completo não funciona em uma conta AWS qualquer.** A implantação
atual foi validada em **quatro contas distintas**, em `us-east-1`, com os stacks,
roles, integrações e acesso aos serviços preparados antes da turma.

O participante não deve executar as 17 aulas com “Run All” se esse ambiente
não estiver disponível. Perfis diferentes apontando para o mesmo ID de conta
não atendem aos cenários entre contas.

## Matriz da implementação atual

“Contas no fluxo” descreve a chamada ensinada. “Contas exigidas” inclui as
dependências reais do manifesto e do IaC distribuídos.

| Aulas | Contas no fluxo | Contas exigidas pelo notebook atual | Preparação adicional |
|---|---|---|---|
| 00–05 | 1: plataforma | 1 | Core; agente na 02; geração de rascunho na 05 |
| 06–08 | 1: plataforma | 1 | Registry, personas IAM, registros aprovados e Runtime; agente na 08 |
| 09 | 1: plataforma | 1 | Implantação Terraform, state remoto e outputs |
| 10–11 | 4: plataforma + Retail + Transaction + Lending | **4 distintas** | Stacks de cada conta; federação e agente central na 11 |
| 12 | 2: plataforma → Transaction | **4 distintas** | Preflight do bloco multi-conta e federação completa |
| 13 | 2: identidade na plataforma + fonte em Transaction | **4 distintas** | Preflight do bloco multi-conta; simulador da fonte na AWS |
| 14 | **3: Retail → plataforma → Transaction** | **4 distintas** | Federação completa, agentes Riscos/Fraude na origem e registros aprovados |
| 15 | 1: plataforma | 1 | Core, Memory e stacks RAG; ciclo de vida pelo IaC |
| 16 | 1: plataforma | 1 | RAG gerenciado, ingestão/ACL e Runtime RAG |

Na aula 14, as três contas do desenho são A (origem/Retail), C
(hub/plataforma) e B (fonte/Transaction). Lending não participa dessa chamada,
mas é uma dependência da implantação atual: `federation-bindings` declara os
três Gateways de domínio, e o manifesto 10–14 verifica as quatro contas.
**Ter apenas três contas não basta para executar essa aula com o pipeline atual.**
Uma versão independente com três contas exigiria alterar e validar o IaC e o
manifesto; ela não está implementada.

Os usuários sintéticos A/B/C/D das aulas de identidade e RAG são pessoas.
Não representam quatro contas AWS. As personas Developer/Publisher/Approver/
Consumer do Registry são roles IAM e também podem existir na mesma conta.

## O que executar durante a turma

| Ambiente disponível | Roteiro |
|---|---|
| Uma conta com os stacks das aulas preparados | Selecionar 00–09 e 15–16 em um ambiente de notebooks na AWS. Os serviços e integrações de cada aula continuam obrigatórios. |
| Duas ou três contas | O bloco 10–14 continua bloqueado na implementação atual; não repetir IDs para satisfazer a configuração. |
| Quatro contas, integrações e roles preparadas | Executar a jornada completa depois do preflight. |
| Apenas uma conta vazia ou sem permissões para implantar os serviços | Fazer a preparação por IaC antes das aulas; a existência da conta não é um aceite de prontidão. |

Sem as quatro contas, reserve 10–14 para **demonstração do instrutor no
ambiente completo** ou leitura guiada do código. Retire essas aulas da seleção
do participante. Uma aula não executada não recebe PASS e não entra no aceite.

Para os notebooks sem requisito multi-conta, mantenha as quatro chaves em
`accounts`, mas use `{"id": null, "profile": null}` nos domínios indisponíveis.
Preencha `platform` e configure as integrações usadas na mesma conta. Não
copie IDs, ARNs ou perfis do ambiente de referência para uma nova turma.

## Restrição adicional do runner CodeBuild

**O runner do projeto é uma implantação completa de quatro contas.** Seu
empacotamento/IAM depende de Registry, Terraform, RAG e das roles observer dos
três domínios. Isso também vale para `deploy --labs 00 01` e `run --labs 00 01`.
`--labs` seleciona exercícios; não reduz os pré-requisitos de implantação desse
runner.

Para uma turma com uma conta, a seleção de fundamentos acima usa um ambiente
de notebooks na AWS com seus stacks e permissões preparados. Não existe hoje
um pipeline de CodeBuild simplificado para conta única.

## Conferir antes de iniciar

O planejamento abaixo só lê a configuração e mostra os bloqueios por aula.
Não chama a AWS, não implanta e não inicia builds:

```bash
uv run python scripts/workshop_prerequisites.py
uv run python scripts/workshop_prerequisites.py --labs 14
uv run python scripts/workshop_prerequisites.py --runner --labs 00 01
```

`ACCOUNTS_CONFIGURED` significa apenas IDs presentes e distintos onde exigidos.
`BLOCKED` identifica contas ausentes ou duplicadas e termina com erro.
Para consultar STS e as dependências declaradas, somente leitura:

```bash
uv run python scripts/workshop_prerequisites.py --runner --check-aws
```

Depois de preparar apenas as aulas sem fronteiras entre contas, execute esta
seleção **dentro do ambiente de notebooks AWS**, não no computador do operador:

```bash
uv run python scripts/verify_notebooks.py --labs 00 01 02 03 04 05 06 07 08 09 15 16
```

O verificador confere os pré-requisitos de toda a seleção antes de iniciar o
primeiro notebook. O runner também verifica a seleção efetiva antes de
`StartBuild`, incluindo as aulas salvas no projeto CodeBuild quando `--labs`
não é informado. Não há remoção automática de aulas incompatíveis.

O preflight não substitui testes operacionais: credenciais podem expirar,
serviços/modelos e quotas precisam estar disponíveis, políticas IAM/SCP e as
relações de confiança precisam permitir as operações. Cada aula continua
exigindo respostas reais dos serviços.

## Alcance do aceite registrado

O [aceite de 03/11/2026](aceite-aws.md) corresponde ao build e ao pacote de
fonte registrados, no ambiente de referência de quatro contas. Ele não
certifica execução em uma conta nova, em outra região ou com menos contas.
Alterações posteriores nos notebooks exigem uma nova execução para um aceite
dos novos hashes.
