# Ver a jornada pelos diagramas

A [galeria navegável](index.html) apresenta os 17 laboratórios na mesma ordem
pedagógica do [guia de aprendizagem](../jornada.md). Abra o HTML no navegador;
ele funciona localmente, permite ampliar a imagem e baixar os arquivos.

Cada notebook também incorpora sua figura como anexo Markdown: SVG nos
laboratórios 07 e 09, PNG nos demais. A imagem acompanha o arquivo `.ipynb`; os links
para código e outros guias pressupõem a estrutura de pastas do projeto.

## Ler antes de executar

Siga as setas para identificar quem faz cada chamada. Os contornos separam
contas, ambientes ou serviços. Azul destaca Identity; roxo, Policy; laranja,
Gateway; verde-azulado, Registry. Leia também os rótulos: as cores são apoio,
não substituem a descrição de cada decisão.

Identity obtém a credencial, enquanto o chamador usa essa credencial para
acessar o destino. No notebook 13, o adapter chama SQL REST; no 14, o caminho
integrado termina num MCP Databricks. Os dois desenhos respondem a etapas
diferentes da aprendizagem.

As imagens explicam arquitetura e contratos. Elas não comprovam implantação
ou autorização: essa conclusão vem dos [testes e evidências](../validacao.md).

## Imagens na ordem da jornada

| Laboratório | Formatos |
|---|---|
| [00 · Primeira execução](../../notebooks/00_preflight.ipynb) | [SVG](svg/00_preflight.svg) · [PNG](png/00_preflight.png) |
| [01 · Gateway e ferramentas](../../notebooks/01_gateway_targets.ipynb) | [SVG](svg/01_gateway_targets.svg) · [PNG](png/01_gateway_targets.png) |
| [02 · Identidade e OBO](../../notebooks/02_identity_entra_obo.ipynb) | [SVG](svg/02_identity_entra_obo.svg) · [PNG](png/02_identity_entra_obo.png) |
| [03 · Identidade do agente](../../notebooks/03_identity_agente_mcp.ipynb) | [SVG](svg/03_identity_agente_mcp.svg) · [PNG](png/03_identity_agente_mcp.png) |
| [04 · Autorização Cedar](../../notebooks/04_policy_cedar.ipynb) | [SVG](svg/04_policy_cedar.svg) · [PNG](png/04_policy_cedar.png) |
| [05 · Autoria de políticas](../../notebooks/05_policy_autoria.ipynb) | [SVG](svg/05_policy_autoria.svg) · [PNG](png/05_policy_autoria.png) |
| [06 · Governança do catálogo](../../notebooks/06_registry_governanca.ipynb) | [SVG](svg/06_registry_governanca.svg) · [PNG](png/06_registry_governanca.png) |
| [07 · Quatro personas](../../notebooks/07_registry_personas.ipynb) | [SVG](../registry/arquitetura.svg) · [PNG](../registry/arquitetura.png) |
| [08 · Descoberta e execução](../../notebooks/08_registry_descoberta_execucao.ipynb) | [SVG](svg/08_registry_descoberta_execucao.svg) · [PNG](png/08_registry_descoberta_execucao.png) |
| [09 · Implantação com Terraform](../../notebooks/09_terraform_runtime_gateway_identity.ipynb) | [SVG](../terraform/arquitetura.svg) |
| [10 · Arquitetura entre contas](../../notebooks/10_santander_multi_conta.ipynb) | [SVG](svg/10_santander_multi_conta.svg) · [PNG](png/10_santander_multi_conta.png) |
| [11 · Agente central e três áreas](../../notebooks/11_blog_multi_account_gateway_mcp.ipynb) | [SVG](../banking/arquitetura.svg) · [PNG](../banking/arquitetura.png) |
| [12 · Gateway por conta](../../notebooks/12_gateways_por_conta_identity_policy.ipynb) | [SVG](../federation/arquitetura.svg) · [PNG](../federation/arquitetura.png) |
| [13 · Identidade na fonte](../../notebooks/13_databricks_e_evidencias.ipynb) | [SVG](svg/13_databricks_e_evidencias.svg) · [PNG](png/13_databricks_e_evidencias.png) |
| [14 · Cenário integrado](../../notebooks/14_cenario_santander_integrado.ipynb) | [SVG](../journey/arquitetura.svg) · [PNG](../journey/arquitetura.png) |
| [15 · Ingestão, ACL e memória](../../notebooks/15_ingestao_acl_memoria.ipynb) | [SVG](../ingestao/arquitetura.svg) · [PNG](../ingestao/arquitetura.png) |
| [16 · RAG por usuário](../../notebooks/16_rag_managed_identity_policy.ipynb) | [SVG](../rag/arquitetura.svg) · [PNG](../rag/arquitetura.png) |

## Formatos

SVG é vetorial e pode ser ampliado; PNG é útil em apresentações e documentos.
Os ícones são ilustrações conceituais deste material. A galeria não consulta
serviços externos para navegar ou exibir as figuras.

## Atualizar o material

Os diagramas 00–06, 08, 10 e 13 vêm de
[generate_diagrams.py](../../scripts/generate_diagrams.py). Com `rsvg-convert`
do pacote librsvg instalado, execute da raiz:

```bash
uv run --frozen --extra banking python scripts/generate_diagrams.py
```

Esse comando atualiza as figuras 00–06, 08, 10 e 13, seus anexos e a galeria completa. Para
07, 09, 11, 12 e 14–16, use o gerador do notebook correspondente em [scripts](../../scripts/).
O layout da galeria está em [diagrams.html](../../scripts/templates/diagrams.html),
e a ordem compartilhada em [notebook_learning.py](../../scripts/notebook_learning.py).
Depois de editar textos ou figuras, regenere e execute a
[verificação dos notebooks](../validacao.md#executar-a-verificação-local).
