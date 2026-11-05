# Santander — Workshop Amazon Bedrock AgentCore

Os [apêndices oficiais AgentCore](notebooks/apendices/README.md) têm kernel próprio, exemplos selecionados por execução real na AWS e relatórios de cobertura.

Construa e teste os serviços AWS **durante as células dos notebooks**.
A jornada executável usa uma conta AWS: **00–09 → 15–16 → 99 (limpeza)**.
Agentes, ferramentas, modelos, dados e memória executam na AWS; o notebook
apresenta o código e chama as APIs. Não há pré-deploy, stack CloudFormation,
Terraform ou configuração privada do instrutor.

## Começar no VS Code/Jupyter da AWS

No terminal, dentro da pasta deste repositório:

```bash
./scripts/setup.sh
```

Selecione o kernel **Santander Workshop (.venv)** e abra
[00_preflight.ipynb](notebooks/00_preflight.ipynb). Confira conta, região e
identidade antes de seguir. O setup instala dependências e registra o kernel;
os recursos da solução começam a ser criados na aula 01.

Use uma sessão autorizada, serviços e modelos disponíveis, permissões e quotas
suficientes. Uma conta AWS qualquer não vem automaticamente habilitada.
Veja [preparação](docs/preparacao.md) e o [ciclo completo em contas efêmeras](docs/contas-efemeras.md).

## Escolher a sequência

| Aulas | Conteúdo | Situação |
|---|---|---|
| 00–01 | Sessão AWS, Cognito, IAM, Lambda, Gateway e MCP | Construção SDK |
| 02–03 | Pessoa/aplicação, comparação Entra ID, Runtime e identidade IAM | Construção SDK |
| 04–05 | Policy Engine, Cedar, geração e revisão de rascunho | Construção SDK |
| 06–08 | Registry, aprovação, personas e descoberta versus execução | Construção SDK |
| 09 | Integração Runtime, Gateway e identidades | Construção SDK |
| 15–16 | Memory, autorização da fonte, RAG MANAGED e ACL nativa | Construção SDK |
| 99 | Exclusão dos recursos registrados desta execução | Limpeza SDK explícita |
| 13–14 e 90–92 | Fonte simulada e arquiteturas entre contas | **Referências não executáveis; conversão SDK pendente** |

Os três cadernos específicos de multiconta ficam no fim: 90, 91 e 92
(antigas aulas 10, 11 e 12). Os desenhos do bloco avançado representam a
arquitetura histórica de **quatro contas distintas**. Ter essas contas não
basta: a criação e a limpeza SDK desses cinco cenários ainda não foram
implementadas. O código de infraestrutura anterior foi retirado.
Leia a [matriz de contas](docs/contas-e-elegibilidade.md) antes de selecionar aulas.

Cognito é o provedor de identidade usado nos exercícios; as comparações com
Microsoft Entra ID explicam as diferenças de audiência, claims e OBO.
Databricks aparece como **contrato de uma fonte sintética na AWS** nas referências;
o workshop não fornece um workspace, SQL Warehouse ou Unity Catalog real.

## Entender e validar

Cada notebook começa com arquitetura, objetivos e papel dos serviços.
As etapas mostram código, chamadas, validação e análise do resultado.

* [Mapa dos guias](docs/README.md)
* [Jornada e dependências entre aulas](docs/jornada.md)
* [Conceitos de identidade e autorização](docs/conceitos.md)
* [Validação e evidências](docs/validacao.md)
* [Limpeza e retomada](docs/cleanup.md)
* [Conteúdo didático e edição dos notebooks](docs/roteiro-didatico.md)
* [Aceite AWS registrado em 05/11/2026](docs/aceite-notebooks-sdk.md)

O aceite registra execução de 00–09 e 15–16, limpeza 99 e reconstrução do zero.
É evidência daquela versão e conta; uma revisão de documentação não equivale
a nova execução AWS. Cada turma deve guardar seus próprios resultados.

```bash
uv run python scripts/verify_notebooks.py --validate-only
uv run pytest -q
```

Esses comandos verificam material e código, sem criar recursos AWS. Para
executar as células pelo terminal na AWS, use a seleção explícita descrita
no [guia de validação](docs/validacao.md).

## Organização do projeto

| Caminho | Finalidade |
|---|---|
| `notebooks/` | Aulas SDK e referências avançadas identificadas |
| `scripts/` | Setup, fontes das células, geração e verificação dos notebooks |
| `src/santander_demo/` | Estado da execução, contratos SDK, endpoints e catálogo |
| `tests/` | Testes da jornada SDK e integridade das evidências |
| `docs/` | Guias atuais, desenhos e registros históricos SDK |
| `.workshop/` | IDs por conta/região e histórico; gerado, fora do Git |
| `build/`, `evidence/` | Artefatos e resultados; gerados, fora do Git |
| `.venv/` | Ambiente Python preparado pelo setup; fora do Git |

Não apague `.workshop/` para reiniciar: ele permite conferir a propriedade
e limpar os recursos corretos. A aula 99 fecha a execução; a próxima aula 00
arquiva o registro e gera novos nomes. Contas diferentes têm registros próprios.

Os notebooks são publicados sem outputs; as saídas da turma ficam no editor
ou nos artefatos de evidência. Não publique tokens, senhas nem credenciais.
A revisão dos diretórios está descrita em [estrutura do repositório](docs/estrutura.md).

Referência: [workshops oficiais AgentCore](https://github.com/awslabs/agentcore-samples/tree/main/06-workshops).
