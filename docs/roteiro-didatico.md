# Conteúdo didático dos notebooks

Cada aula começa com um desenho próprio, objetivos, pré-requisitos e uma
explicação dos serviços AWS usados naquele cenário. As seções de validação
ficam junto das chamadas e dos asserts que produzem a evidência. Depois de
executá-las, o participante compara o resultado esperado, sua interpretação
e o alcance do teste.

As células executáveis foram preservadas nesta revisão. A análise usa o
[aceite AWS de 05/11/2026](aceite-notebooks-sdk.md) como referência histórica
para 00–09, 15–16 e 99. Os outputs de uma nova execução são a evidência da
conta do participante. As aulas 13–14 e 90–92 continuam identificadas como legado
de quatro contas, pendente de conversão e novo teste.

## Como editar e regenerar

* `scripts/notebook_curriculum.py`: objetivos, papel dos serviços, critérios
  de validação, leitura dos resultados e perguntas para discussão.
* `scripts/notebook_architecture.py`: componentes, fronteiras de conta e
  relações dos 18 desenhos.
* `scripts/notebook_architecture_svg.py`: composição SVG, ícones e conectores.
* `scripts/sdk_*_lesson.py`: explicações de cada passo e código executável.
* `scripts/generate_aws_notebooks.py`: composição dos notebooks distribuídos.

O roteiro associa cada validação a um trecho único da célula existente.
A geração interrompe se esse trecho deixar de existir ou se tornar ambíguo.
Isso exige revisar a explicação quando a implementação da aula muda.

Para atualizar desenhos, instale `rsvg-convert` (librsvg) e `pngquant` na máquina de edição e execute:

```bash
uv run python scripts/notebook_architecture.py
uv run python scripts/generate_aws_notebooks.py
```

Para modificar apenas os textos:

```bash
uv run python scripts/generate_aws_notebooks.py
```

O diretório `docs/diagramas/aulas/` contém SVG editável e PNG. As posições
e rotas são explícitas no gerador, com ícones oficiais AWS incorporados no SVG. A imagem
PNG também é incorporada como attachment Markdown de cada notebook, para
ser exibida no VS Code/Jupyter mesmo ao copiar o notebook isoladamente.
O renderizador não é uma dependência da execução do workshop. Os assets já
estão no Git. Veja as [fontes dos ícones e referências visuais](diagramas/icons/README.md).

## Como conduzir a aula

1. Percorra o desenho e identifique as identidades e as fronteiras de autorização.
2. Leia o que será criado e o que foi construído em aulas anteriores.
3. Apresente o código antes da chamada AWS e aguarde o estado de prontidão.
4. Execute a validação e leia os campos que comprovam o resultado.
5. Compare casos permitidos e negados e discuta os limites da evidência.

Uma negativa esperada é parte do teste. Erro de rede, credencial expirada ou
falha de backend não comprovam autorização correta. De modo semelhante,
HTTP 200 não basta para declarar sucesso de uma chamada MCP: examine também
o resultado ou erro do protocolo, como fazem os asserts das aulas.

## Ordem e nomes do bloco multiconta

Os arquivos 10, 11 e 12 foram renomeados para 90, 91 e 92 para aparecerem
no final, antes da limpeza 99. Títulos e arquiteturas usam essa nova numeração.
A jornada de conta única permanece 00–09, 15–16 e limpeza 99; 13–14 continuam
identificados como dependentes do legado de quatro contas.

`src/santander_demo/notebook_catalog.py` mantém a correspondência dos nomes.
Os IDs internos 10, 11 e 12 no manifesto e nas células legadas permanecem
estáveis, preservando requisitos, recursos e evidências. Os verificadores
`verify_notebooks.py` e `audit_notebooks.py` aceitam os números 90, 91 e 92
como aliases desses IDs. Os geradores gravam apenas os novos nomes.
Os relatórios históricos preservam os nomes usados na execução original.
