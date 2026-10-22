# Guia visual dos notebooks

**Comece pela [galeria navegável](index.html).** Ela abre diretamente no navegador,
funciona sem servidor e permite percorrer, ampliar e baixar os dez diagramas.

Cada notebook contém sua imagem como um anexo Markdown incorporado. O PNG continua
visível mesmo se você copiar somente o arquivo `.ipynb`. Os links para os demais
materiais pressupõem a estrutura de pastas do projeto.

| Notebook | O que o diagrama explica | Imagens |
|---|---|---|
| [00 · Preflight](../../notebooks/00_preflight.ipynb) | O que roda localmente e o que depende de configuração e ensaio na AWS. | [PNG](png/00_preflight.png) · [SVG](svg/00_preflight.svg) |
| [01 · Gateway](../../notebooks/01_gateway_targets.ipynb) | Uma entrada MCP para Lambda Riscos/K2 e Runtime Fraude, com autorização antes da execução. | [PNG](png/01_gateway_targets.png) · [SVG](svg/01_gateway_targets.svg) |
| [02 · Identity e OBO](../../notebooks/02_identity_entra_obo.ipynb) | O usuário, as duas trocas OBO, as audiências dos tokens e a prova no Graph. | [PNG](png/02_identity_entra_obo.png) · [SVG](svg/02_identity_entra_obo.svg) |
| [03 · Identidade do agente](../../notebooks/03_identity_agente_mcp.ipynb) | O mesmo usuário recebe decisões diferentes conforme a aplicação que age por ele. | [PNG](png/03_identity_agente_mcp.png) · [SVG](svg/03_identity_agente_mcp.svg) |
| [04 · Policy e Cedar](../../notebooks/04_policy_cedar.ipynb) | Identidade, ação, recurso e limite de entrada precisam passar juntos pela regra. | [PNG](png/04_policy_cedar.png) · [SVG](svg/04_policy_cedar.svg) |
| [05 · Autoria de políticas](../../notebooks/05_policy_autoria.ipynb) | Intenção → rascunho Cedar → revisão e testes → publicação por IaC. | [PNG](png/05_policy_autoria.png) · [SVG](svg/05_policy_autoria.svg) |
| [06 · Governança do Registry](../../notebooks/06_registry_governanca.ipynb) | Papéis distintos de publicação, aprovação e consumo; estados do catálogo. | [PNG](png/06_registry_governanca.png) · [SVG](svg/06_registry_governanca.svg) |
| [07 · Descoberta e execução](../../notebooks/07_registry_descoberta_execucao.ipynb) | Descobrir no Registry, validar o destino e solicitar execução pelo Gateway. | [PNG](png/07_registry_descoberta_execucao.png) · [SVG](svg/07_registry_descoberta_execucao.svg) |
| [08 · Arquitetura entre contas](../../notebooks/08_santander_multi_conta.ipynb) | Conta A: supervisor. Conta C: hub. Conta B: especialista de Fraude. | [PNG](png/08_santander_multi_conta.png) · [SVG](svg/08_santander_multi_conta.svg) |
| [09 · Databricks e evidências](../../notebooks/09_databricks_e_evidencias.ipynb) | Troca de token, chamada SQL e verificação da identidade e dos grants na fonte. | [PNG](png/09_databricks_e_evidencias.png) · [SVG](svg/09_databricks_e_evidencias.svg) |

## Como ler

As cores identificam os pilares: **azul = Identity**, **roxo = Policy**,
**laranja = Gateway** e **verde-azulado = Registry**. Verde indica permissão;
vermelho, bloqueio. As setas mostram a direção de cada interação. Os contornos
agrupam ambientes, contas ou serviços; setas tracejadas destacam relações de
suporte, credencial ou controle.

A faixa superior de cada imagem identifica seu estado: lógica local ou arquitetura
ainda a validar. A faixa escura inferior resume o aprendizado. Os fluxos de AWS,
Entra e Databricks representam a implementação preparada; **não são evidência de
implantação ou de integração validada**.

Identity apoia a obtenção da credencial; quem chama o target é o Gateway. Da mesma
forma, no notebook 09 o adapter obtém o token e chama o SQL Warehouse. O endpoint
de troca de tokens não encaminha a consulta. A extensão Databricks está separada
do caminho Gateway nesta entrega.

## Formatos e edição

- **PNG:** 2400 × 1500 pixels, pronto para apresentações e documentos.
- **SVG:** vetorial, com texto selecionável, títulos e descrições acessíveis.
- **Notebooks:** PNG incorporado, sem depender de links externos para exibir a figura.
- **Galeria:** HTML local, responsivo, com seleção por notebook, ampliação e downloads.

Os ícones são ilustrações conceituais feitas para este material; não são o conjunto
oficial de ícones de arquitetura AWS ou Microsoft. Nenhum serviço externo é
consultado para renderizar ou visualizar a galeria.

## Regenerar

A galeria agora reúne **00–13**. As arquiteturas adicionais ficam em
[banking](../banking/arquitetura.png), [federação](../federation/arquitetura.png),
[cenário integrado](../journey/arquitetura.png) e [ingestão](../ingestao/arquitetura.png).
Para regenerar as imagens e notebooks 12/13:

```bash
uv run --extra banking python scripts/generate_journey_notebooks.py
```

A fonte dos diagramas e seus textos está em
[`scripts/generate_diagrams.py`](../../scripts/generate_diagrams.py). O layout da
galeria está em [`scripts/templates/diagrams.html`](../../scripts/templates/diagrams.html).

Na raiz do projeto, com `rsvg-convert` do pacote **librsvg** disponível:

```bash
python3 scripts/generate_diagrams.py
```

Isso atualiza SVG, PNG, manifesto, galeria e a célula de imagem de cada notebook.
**As demais células, seu código e seus outputs são preservados.**

Para atualizar apenas SVG, manifesto e galeria, sem renderizar ou alterar notebooks:

```bash
python3 scripts/generate_diagrams.py --svg-only
```

O gerador completo de notebooks, `scripts/generate_notebooks.py`, também incorpora
as imagens existentes. Ele recria os notebooks a partir da fonte e limpa outputs;
use o gerador de diagramas quando quiser atualizar somente as figuras.
