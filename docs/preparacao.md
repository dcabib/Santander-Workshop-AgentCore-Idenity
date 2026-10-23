# Preparar o ambiente

O primeiro exercício é [00 — Preflight](../notebooks/00_preflight.ipynb).
Você pode começar sem conta AWS ou tenant Microsoft: o padrão dos notebooks
executa somente os contratos locais.

## Instalar e abrir

Use Python 3.12 ou 3.13, [uv](https://docs.astral.sh/uv/getting-started/installation/)
e um editor compatível com Jupyter, como VS Code com a extensão Jupyter.
Na raiz do repositório:

```bash
uv sync --frozen --extra banking
uv run santander-demo demo
uv run santander-demo matrix
```

O extra `banking` instala os SDKs usados também pelos laboratórios avançados.
Abra o notebook 00 e selecione `.venv/bin/python` como kernel. Execute as células
na ordem; o notebook reutiliza o pacote Python do repositório. Mantenha notebooks,
`src/`, `config/` e `docs/` na mesma estrutura de pastas.

Uma célula final limpa as variáveis do exercício. Para repetir o laboratório,
recomece pela preparação. As imagens estão incorporadas nos notebooks.

## Entender os controles

| Controle | Onde aparece | Efeito |
|---|---|---|
| `WORKSHOP_MODE=local` | 00–06, 08, 10 e 13 | Bancada local; é o padrão |
| `WORKSHOP_MODE=aws` | 00–06, 08, 10 e 13 | Usa `config/local.json`; defina antes de iniciar o kernel |
| `RUN_AWS=False` | 07, 09, 11, 12, 14 e 16 | Mantém as chamadas AWS desativadas |
| `DEPLOY_PHASE` | Cenários CloudFormation | Seleciona uma fase; siga a tabela do guia daquele cenário |
| `RUN_PIPELINE=False` | Cenários com deploy no notebook | Não executa o wrapper IaC |
| `APPLY_CHANGESET=False` | Cenários com deploy no notebook | Mantém a aplicação do plano desativada |
| `RUN_AGENT=False` | 12 e 09 | Mantém a etapa opcional com modelo desativada |
| `RUN_BUILD=False` | 09 | Não reconstrói os ZIPs |
| `CLEANUP_EXECUTE=False` | Limpeza | Não remove recursos cloud |

Depois de alterar controles, reexecute a célula que os define e as etapas
dependentes. `Run All` com os padrões não implanta nada. O notebook 15 é local.
No 16, `DEPLOY_PHASE` escolhe o provisionamento; depois mantenha `RUN_PIPELINE=False`
para executar consultas. Nos 11, 12 e 14, `DEPLOY_PHASE=None` libera o ensaio.

## Escolher um ambiente AWS

O [laboratório 09](terraform/README.md) é a primeira implantação recomendada:
uma conta, Cognito, Runtime, Gateway, Identity e Lambda. O exemplo usa `us-east-1`;
o perfil e o ID esperado da conta são preenchidos na configuração local.
Os testes de referência desse laboratório usaram `default` nessa região.

Cada cenário tem configuração e ciclo de vida próprios:

| Laboratórios | Arquivo local | Guia |
|---|---|---|
| 00–06, 08, 10 e 13 | `config/local.json` | [Integração dos fundamentos](deploy.md) |
| 07 | `config/local.registry.json`, gerado pelo pipeline | [Quatro personas](registry/README.md) |
| 09 | `config/local.terraform.json` | [Terraform](terraform/README.md) |
| 11 | `config/local.banking.json` | [Agente central](banking/README.md) |
| 12 | `config/local.federation.json` | [Gateways federados](federation/README.md) |
| 14 | `config/local.journey.json` | [Fonte Databricks integrada](journey/README.md) |
| 16 | `config/local.rag.json`, gerado pelo pipeline | [RAG](rag/README.md) |

Use nomes de projeto e state separados para ambientes diferentes. Um perfil AWS
autentica o operador; ele não substitui os tokens de usuário Entra/Okta/Cognito.
Verifique disponibilidade dos serviços e do modelo na região antes do deploy.
Os guias multi-conta indicam quantas contas e quais identidades são necessárias.

Configurações locais contêm identificadores, endpoints e ARNs. Tokens e senhas
não devem ser copiados para células ou JSONs. O Terraform pode guardar segredos
no state e no plano binário: mantenha esses arquivos protegidos e fora do Git.

## Construir, aplicar e encerrar

O build é local. O deploy passa pelo wrapper Terraform ou CloudFormation do
cenário, com revisão do plano. Providers e custom resources declarados no IaC
administram seus recursos; não use ajustes manuais para resolver divergências.
Serviços implantados e inferência têm custos.

Consulte [validação](validacao.md) para conferir resultados e
[limpeza](cleanup.md) para remover o ambiente correto e identificar retenções.
Continue pela [jornada](jornada.md).
