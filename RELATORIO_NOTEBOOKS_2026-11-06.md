# Verificação dos notebooks — 06/11/2026

## Correções posteriores à auditoria

Os problemas identificados abaixo foram corrigidos no projeto após a solicitação do usuário:

- **A02:** uma sessão compartilhada por conversa, com teste real de continuidade entre duas chamadas e encerramento em `finally`; erros de invocação não são ocultados.
- **A03:** helper reproduzível para as duas caudas IQR, preservação da resposta exploratória e comparação do JSON do agente e do JSON produzido na AWS com o CSV. A contagem é de categorias, sem mistura com a unidade de linhas.
- **Documentação:** 18 PNGs recuperados dos attachments, 18 SVGs gerados pelas fontes existentes e 14 ícones oficiais recuperados com verificação de hashes. Guias recompostos, links corrigidos e referências históricas diferenciadas do registro observado em 06/11.
- **Textos:** corrigidas as instruções de credenciais do A04, descrições copiadas dos extras e numeração antiga do bloco avançado.

A02 e A03 foram executados novamente na AWS. A02 preservou a variável `123` entre chamadas e retornou o primo **83**. A03 confirmou **13 categorias atípicas**, incluindo os quatro nomes omitidos e Shark, e **120** pessoas Kimberly/Crocodile. As sessões foram encerradas.

Verificação local: **192 testes pytest aprovados**, quatro testes específicos de EDA aprovados no ambiente dos extras, 18 notebooks principais válidos, lint dos arquivos novos/alterados de teste e análise aprovado, e nenhum link local quebrado no README, guias ou notebooks. Há um aviso de depreciação Pydantic no SDK.

O código executável dos outros 20 notebooks foi preservado. A jornada principal não foi recriada por causa das alterações editoriais. As cinco referências continuam sem código, com a implementação SDK explicitamente pendente.

Evidências posteriores: [execuções AWS](build/notebook-fixes/extras-run/report.json), [A02 executado](build/notebook-fixes/extras-run/A02_code_interpreter_agente.ipynb), [A03 executado](build/notebook-fixes/extras-run/A03_code_interpreter_analise.ipynb), [testes pytest](build/notebook-fixes/pytest.xml), [testes EDA](build/notebook-fixes/eda-tests.log) e [validação estática](build/notebook-fixes/static-validation.json).

## Auditoria original, antes das correções

Execução real na conta AWS `413816870411`, região `us-west-2`, sobre os notebooks deste checkout. Nesta primeira etapa, os notebooks originais não foram alterados. As cópias executadas, hashes e respostas higienizadas estão em `build/notebook-audit/`.

**Resultado:** 17 notebooks executáveis concluídos na AWS (186 células de código), e cinco referências sem células executáveis. A conclusão das células não significa que todas as explicações e respostas estejam corretas: foram confirmadas divergências no A02 e na EDA do A03, além de documentação ausente que quebra a suíte de testes.

Revisão do checkout: `5a652b3ee2de2e8660e62e6d887288a2396d3b7b`. Identificador desta execução: `5eb0ee2a8502`.

## Resultado por notebook

| Notebook | Execução | Comparação com a descrição e o resultado |
|---|---|---|
| [00_preflight](notebooks/00_preflight.ipynb) | Aprovada | STS, execução NEW e SDK_AVAILABLE. |
| [01_gateway_targets](notebooks/01_gateway_targets.ipynb) | Aprovada | Gateway/target READY; negativas 401; MCP executou Lambda com risk=low. |
| [02_identity_entra_obo](notebooks/02_identity_entra_obo.ipynb) | Aprovada | Mesmo sub com audiências distintas; duas negativas 403 e controle positivo. |
| [03_identity_agente_mcp](notebooks/03_identity_agente_mcp.ipynb) | Aprovada | Runtime MCP consultou STS com role própria, distinta da sessão do participante. |
| [04_policy_cedar](notebooks/04_policy_cedar.ipynb) | Aprovada | Cedar: um ALLOW e dois DENY pela pessoa/parâmetro. |
| [05_policy_autoria](notebooks/05_policy_autoria.ipynb) | Aprovada | Geração revisada com um caso positivo e dez contraexemplos; LOG_ONLY preservou ACTIVE. |
| [06_registry_governanca](notebooks/06_registry_governanca.ipynb) | Aprovada | Registry READY, aprovação manual e descoberta IAM; chamada anônima negada. |
| [07_registry_personas](notebooks/07_registry_personas.ipynb) | Aprovada | Três personas IAM reais; permissões de catálogo/Runtime corresponderam aos papéis. |
| [08_registry_descoberta_execucao](notebooks/08_registry_descoberta_execucao.ipynb) | Aprovada | Publicação/aprovação/descoberta; publisher não aprovou; descoberta isolada não concedeu invocação. |
| [09_integracao_runtime_gateway_identity](notebooks/09_integracao_runtime_gateway_identity.ipynb) | Aprovada | Gateway → Runtime: analista ALLOW e auditor DENY; STS mostrou a role do workload. |
| [13_databricks_e_evidencias](notebooks/13_databricks_e_evidencias.ipynb) | Sem código | Referência de fonte sintética; implementação SDK pendente. |
| [14_cenario_santander_integrado](notebooks/14_cenario_santander_integrado.ipynb) | Sem código | Referência de arquitetura integrada; implementação SDK pendente. |
| [15_ingestao_acl_memoria](notebooks/15_ingestao_acl_memoria.ipynb) | Aprovada | Isolamento de actor/partição; referência persistiu após revogação, sem conteúdo da fonte. |
| [16_rag_managed_identity_policy](notebooks/16_rag_managed_identity_policy.ipynb) | Aprovada | Dois documentos indexados; spoof negado; retrieval direto negado; respostas/fonte R1 e F1 conferidas. |
| [A01_code_interpreter_arquivos](notebooks/20-Extras/A01_code_interpreter_arquivos.ipynb) | Aprovada | Dois arquivos enviados/listados; estatísticas de 299.130 linhas; exitCode=0. |
| [A02_code_interpreter_agente](notebooks/20-Extras/A02_code_interpreter_agente.ipynb) | Aprovada | Primo 83 correto. Divergência: estado não persiste entre chamadas. |
| [A03_code_interpreter_analise](notebooks/20-Extras/A03_code_interpreter_analise.ipynb) | Aprovada | Resposta 120 correta. Divergência: EDA informou nove outliers e omitiu quatro. |
| [A04_browser_acoes](notebooks/20-Extras/A04_browser_acoes.ipynb) | Aprovada | 28 ações SUCCESS; dois PNGs de 49.675 bytes; Browser e IAM removidos. |
| [90_multiconta_santander](notebooks/90_multiconta_santander.ipynb) | Sem código | Referência de quatro contas; não há chamadas STS executáveis. |
| [91_multiconta_agente_central_gateway_mcp](notebooks/91_multiconta_agente_central_gateway_mcp.ipynb) | Sem código | Referência de agente central/domínios; não há invocações executáveis. |
| [92_multiconta_gateways_identity_policy](notebooks/92_multiconta_gateways_identity_policy.ipynb) | Sem código | Referência de autorização em dois Gateways; não há testes executáveis. |
| [99_cleanup_sdk](notebooks/99_cleanup_sdk.ipynb) | Aprovada | Limpeza dos recursos registrados e encerramento da execução. |

## Como foi verificado

- Instalação da jornada com `uv sync --frozen --extra banking`.
- Kernel separado para os extras, com as versões de `requirements-kernel.txt`. As células `%pip` originais também foram executadas.
- Execução das células em ordem, com interrupção em erro. Comparação das saídas com os objetivos, tabelas de validação e limites declarados.
- Conferência independente do CSV e teste adicional de continuidade de estado da ferramenta A02.
- Testes do repositório, inspeção de referências locais e conferência de integridade das cópias executadas.

## Problemas encontrados

### A03: execução aprovada, análise exploratória incompleta

A resposta à pergunta Kimberly/Crocodile foi **120**, coincidente com a contagem independente no CSV. As análises usaram Code Interpreter na AWS; o CSV tem **299.130 registros**, quatro colunas e zero valores ausentes.

Contudo, o resumo gerado para a primeira pergunta declarou **“Outliers Identified (9 total)”**. Para `Name`, o código calculou apenas a cauda superior, embora apresentasse o resumo como total de outliers.

Aplicando IQR nas frequências por categoria, os limites de `Name` são **139,5** e **207,5**. Há oito nomes acima do limite e quatro abaixo:

| Nome omitido | Frequência |
|---|---:|
| James Flores | 137 |
| Linda Allen | 132 |
| Joshua Martinez | 132 |
| Donald Jackson | 120 |

Somando a categoria Shark, há **13 categorias fora dos limites**, não nove. Também não faz sentido apresentar nove categorias como “0.003% of data” dividindo por 299.130 linhas: são unidades diferentes. Esta é uma falha semântica da resposta observada, mesmo com todos os asserts do notebook aprovados.

**Sugestão:** calcular explicitamente as duas caudas e verificar o resumo contra os resultados numéricos. A validação atual confirma chamadas da ferramenta e a resposta final 120, mas não a exatidão da EDA. A resposta de um modelo pode variar em nova execução.

Evidências: [A03 executado](build/notebook-audit/extras-run/A03_code_interpreter_analise.ipynb) e [contagem independente](build/notebook-audit/csv-independent-results.json).

### A02: promessa de estado persistente contradiz a ferramenta

O cálculo demonstrado retornou corretamente **83**, com chamada real de Code Interpreter. Entretanto, `SYSTEM_PROMPT` diz: **“The sandbox maintains state between executions, so you can refer to previous results”**.

A ferramenta `execute_python` abre um novo `with code_session(...)` a cada chamada. `clearContext=False` não preserva variáveis entre sessões distintas.

Foi reproduzido na AWS com o código original da ferramenta:

1. Primeira chamada: `persist_audit_value = 123; print(persist_audit_value)` → stdout `123`, `exitCode=0`.
2. Segunda chamada: `print(persist_audit_value)` → `NameError`, `exitCode=1`, `isError=True`.

**Sugestão:** reutilizar uma sessão ao longo da conversa e encerrá-la ao final, ou corrigir o prompt para informar que as chamadas são independentes. O exercício de primo passa porque resolve a tarefa em uma chamada.

Evidência: [teste adicional de continuidade](build/notebook-audit/A02-state-continuity-check.ipynb).

### Checkout sem documentação e diagramas externos

O diretório `docs/` referenciado pelo README, notebooks e geradores não existe neste checkout. Foram identificadas **73 ocorrências de links locais quebrados**, apontando para **49 arquivos distintos**.

Os diagramas incorporados como attachments nos notebooks continuam disponíveis. O problema é a ausência dos arquivos externos, guias e aceite histórico referenciados.

A suíte teve **62 aprovados, 75 falhas e 54 erros**, totalizando 191 testes. Todos os 129 resultados adversos registrados no XML decorrem de `FileNotFoundError` para PNGs em `docs/diagramas/aulas/`. Isso impede validar a geração e vários testes de comportamento, que constroem os notebooks antes de executar seus casos.

Como diagnóstico adicional, o projeto foi copiado para `/tmp` e os **18 PNGs existentes nos attachments** foram extraídos para os caminhos externos esperados somente nessa cópia. Sem alterar código ou testes, a suíte então teve **191 aprovados**, com um aviso de depreciação do SDK. Isso confirma a causa da quebra de testes neste checkout. Os testes são locais e não substituem as execuções AWS.

**Sugestão:** restaurar os diagramas necessários à distribuição a partir dos attachments e restaurar/corrigir os guias e links ausentes, ou tornar os geradores independentes desses arquivos. Esta falha da suíte não equivale a falha de todas as aulas já publicadas: os arquivos `.ipynb` existentes foram executados diretamente.

Evidências: [XML no checkout original](build/notebook-audit/pytest.xml), [log original](build/notebook-audit/pytest.log), [XML na cópia temporária com diagramas](build/notebook-audit/pytest-with-embedded-diagrams.xml), [log da cópia](build/notebook-audit/pytest-with-embedded-diagrams.log) e [links ausentes](build/notebook-audit/broken-links.json).

### Ajustes editoriais menores

- O A04 ainda contém “create the credential files in your terminal”, embora as células usem a cadeia padrão de credenciais e a abertura oriente a não salvar credenciais.
- O texto de origem dos extras A01 e A03 menciona adaptações do Browser e do cálculo de primo, que pertencem a outros extras.
- O 00 ainda menciona o bloco legado como “10–14”; os notebooks de multiconta publicados agora são 90–92, além de 13–14.

## Intercorrências do ambiente

Na primeira tentativa, a aula 03 falhou ao chamar `uv export` por escrita bloqueada no cache do `uv` pelo sandbox. A repetição autorizada fora do sandbox passou, sem alteração no notebook.

O ambiente reiniciou durante a primeira tentativa da aula 05 e do A03. A aula 05 registrou `KeyboardInterrupt`; isso não foi tratado como defeito do notebook. As etapas foram retomadas e concluídas. A sessão interrompida do A03 foi encerrada explicitamente; o registro está em `interrupted-session-cleanup.json`.

## Referências sem execução

Os notebooks **13, 14, 90, 91 e 92** contêm apenas Markdown e diagramas. Seus metadados declaram `REFERENCE_ONLY` e conversão SDK pendente. Não demonstram Databricks real ou chamadas entre quatro contas e não podem receber aprovação de execução AWS. Essa limitação está explicitada no README e nos próprios notebooks.


## Evidências e limpeza

- [Índice consolidado e hashes](build/notebook-audit/report.json).
- [Histórico das tentativas](build/notebook-audit/attempts.json), incluindo o bloqueio do sandbox e a interrupção do ambiente.
- [Cópias executadas](build/notebook-audit/executed/), com as fontes iguais às publicadas.
- [Conferência independente do CSV](build/notebook-audit/csv-independent-results.json).
- [Teste de continuidade do A02](build/notebook-audit/A02-state-continuity-check.ipynb).
- [Revisão das respostas RAG](build/notebook-audit/rag-answer-review.json).
- [Resultado da limpeza 99](build/notebook-audit/cleanup-run/report.json).
- [Resultados da suíte](build/notebook-audit/pytest.xml) e [links locais ausentes](build/notebook-audit/broken-links.json).

A aula 99 passou em **15 minutos e 49 segundos**. A exclusão da fonte MANAGED levou aproximadamente **9 minutos e 10 segundos**, dentro do limite de 14 minutos declarado na célula; a etapa seguinte de remoção da base e demais recursos RAG levou cerca de 2 minutos e 19 segundos. O registro final ficou em **`CLEANED`, com zero recursos registrados**.

O Secrets Manager conserva a janela de recuperação de sete dias prevista na aula; gerações de políticas expiram no serviço após sete dias. Essas retenções são limites declarados do exercício, não exclusões instantâneas. Os extras concluíram suas próprias células de limpeza. O Browser criado no A04 foi também confirmado ausente pela API.

Não foram corrigidos os notebooks nesta tarefa: os problemas foram preservados e relatados. Resultados por modelo representam as respostas desta execução, e não uma garantia sobre todas as respostas futuras.
