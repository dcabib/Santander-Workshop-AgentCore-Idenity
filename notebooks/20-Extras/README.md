# Apêndices — exemplos oficiais AgentCore validados na AWS

Esta pasta reúne adaptações dos workshops de
[`awslabs/agentcore-samples/06-workshops`](https://github.com/awslabs/agentcore-samples/tree/0d46da96306fa692c9887d0461252bf5aeeee6c3/06-workshops).
O upstream removeu essa pasta em 05/11/2026. A referência foi fixada na última
revisão anterior à remoção: `0d46da96306fa692c9887d0461252bf5aeeee6c3`.

Os exercícios são independentes das aulas Santander. Uma conta AWS em
`us-west-2` basta para os exemplos selecionados, desde que a sessão tenha as
permissões indicadas. Nenhum deles usa CloudFormation ou exige implantação
prévia: as células criam e usam os recursos AWS.

| Notebook | Serviços e resultado verificado |
|---|---|
| [A01 — Arquivos e estatísticas](A01_code_interpreter_arquivos.ipynb) | Code Interpreter: enviar/listar arquivos e executar Python com `exitCode=0` |
| [A02 — Agente e cálculo](A02_code_interpreter_agente.ipynb) | Bedrock + Code Interpreter: cálculo real e resposta **83** |
| [A03 — Análise de dados](A03_code_interpreter_analise.ipynb) | Bedrock + Code Interpreter: análise do CSV e resposta **120** |
| [A04 — Ações no Browser](A04_browser_acoes.ipynb) | Browser + IAM: **28 ações SUCCESS**, duas capturas PNG e limpeza |

Consulte o [relatório de validação](VALIDACAO.md) para o resultado de cada
execução, os bloqueios dos outros exemplos e as limitações do levantamento.
**Inventário e análise estática não equivalem a execução na AWS.**
O [catálogo](catalogo.json) identifica explicitamente os exemplos não executados.

## Preparar um kernel próprio

No terminal do ambiente de notebooks, entre nesta pasta e execute:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-kernel.txt
.venv/bin/python -m ipykernel install --user \
  --name agentcore-appendices \
  --display-name "AgentCore Apêndices (Python 3.12)"
```

Selecione **AgentCore Apêndices (Python 3.12)**. Esse kernel evita misturar as
dependências dos exemplos oficiais com as da jornada principal.
Configure `AWS_DEFAULT_REGION=us-west-2` e use a sessão autorizada do evento,
um perfil AWS ou credenciais temporárias no ambiente do processo.
Não cole chaves, senhas ou tokens nas células.

Execute cada notebook de cima para baixo. A primeira célula mostra conta,
região e identidade; confira esses dados antes das células de criação.
O notebook coordena as chamadas Python; inferência, execução de código,
arquivos da sessão e navegador são serviços AWS.

## Permissões e contas efêmeras

A01 exige iniciar, invocar e encerrar sessões de Code Interpreter.
A02 e A03 também exigem invocar o modelo Bedrock e seu inference profile.
A04 exige criar/remover Browser, sessões, role e policy IAM próprias, além de
`iam:PassRole` para `bedrock-agentcore.amazonaws.com`.
As políticas efetivas do Workshop Studio variam entre eventos.

A01 e A03 encerram suas sessões na última célula. A02 usa sessões com contexto
`with`. A04 gera nomes exclusivos e remove sua sessão, Browser, role e policy.
Se houver uma falha, execute as células de limpeza dos recursos que chegaram
a ser criados. A limpeza 99 da jornada principal não conhece estes recursos.
Se a conta expirar, comece uma execução nova na próxima conta; não reutilize IDs.

## Modelos atualizados

A solicitação de substituir modelos descontinuados foi aplicada às cópias
avaliadas: Claude 3.7 Sonnet foi substituído por **Claude Sonnet 4.6**;
Claude 3.5 Haiku, por **Claude Haiku 4.5**.
Os modelos de destino foram consultados no Bedrock e estavam `ACTIVE`.
O [registro da atualização](MODELOS.md) separa a disponibilidade do modelo
do funcionamento completo do notebook.

## Origem, dados e licenças

[sources.json](sources.json) registra caminhos, revisão e hashes dos originais.
As explicações em português, diagramas, verificações e ajustes de portabilidade
são adaptações deste projeto. O CSV sintético tem 299.130 linhas e é o arquivo
original do workshop, compartilhado por A01 e A03.
As licenças estão em [LICENSE.upstream](LICENSE.upstream) e
[NOTICE.upstream](NOTICE.upstream). Os ícones pertencem à AWS;
[aws-icon-sources.json](assets/aws-icon-sources.json) registra sua origem.
