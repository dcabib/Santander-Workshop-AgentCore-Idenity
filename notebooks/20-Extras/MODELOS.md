# Atualização de modelos e nova execução

Em 05/11/2026, o Bedrock rejeitou Claude 3.7 Sonnet com
`ResourceNotFoundException: This model version has reached the end of its life`.
A consulta do catálogo em `us-west-2` confirmou os modelos de destino como
`ACTIVE`, assim como os inference profiles usados:

| Referência antiga | Modelo aplicado |
|---|---|
| `us.anthropic.claude-3-7-sonnet-20250219-v1:0` | `us.anthropic.claude-sonnet-4-6` |
| `anthropic.claude-3-5-haiku-20241022-v1:0` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |

Foram atualizados **12 notebooks** nas cópias de avaliação: nove de Memory,
um de observabilidade com LlamaIndex Runtime e dois de observabilidade com
Arize/OpenLIT. A alteração do modelo não muda IAM, políticas ou a configuração
de Memory.

## Resultado da reexecução

Foram reexecutados os **nove exemplos Memory** com o modelo atualizado.
Os oito exemplos LlamaIndex — pesquisa, investimentos, documentos jurídicos e
conhecimento médico, com memória curta e longa — invocaram Sonnet 4.6:
**16 chamadas `ConverseStream` retornaram HTTP 200**.
Depois, os oito falharam no pareamento de ferramentas no histórico.
Sete receberam:

```text
ValidationException: The number of toolResult blocks at messages.2.content
exceeds the number of toolUse blocks of previous turn.
```

O exemplo jurídico de memória longa recebeu a variante
`Expected toolResult blocks ... for the following Ids`, também no histórico.
As oito memórias criadas receberam `DeleteMemory` HTTP 202 na limpeza original.

O nono exemplo, de nutrição com memória episódica, parou antes de chamar o
modelo: `ModuleNotFoundError: No module named 'langchain'`. Seu
`requirements.txt` instala `langchain-aws`, mas não o pacote `langchain`
importado pela célula seguinte. Nenhum recurso AWS foi criado nesse teste.

O erro de fim de vida foi eliminado. O erro seguinte pertence à reconstrução
do histórico pela integração LlamaIndex: os metadados de chamadas de
ferramentas não chegam à conversa no formato esperado pelo Converse.
Não foram removidas chamadas de ferramentas nem substituída a persistência
AWS por memória no processo para ocultar esse problema.

O [catálogo](catalogo.json) e o [relatório](VALIDACAO.md) registram também os
resultados dos exemplos de memória longa e dos demais testes.
Um notebook interrompido não é aprovado; somente os quatro exercícios
completamente validados estão distribuídos como `.ipynb` neste apêndice.

Os exemplos Arize e OpenLIT exigem configuração externa que não foi fornecida.
O Runtime de observabilidade depende do fluxo de build/implantação cuja
permissão `iam:PassRole` para CodeBuild foi negada nesta sessão.
Eles têm atualização preparada, mas não validação completa na AWS.

## Reproduzir a alteração nos originais

[modelos-atualizados.json](modelos-atualizados.json) identifica os 12 arquivos,
suas células e hashes originais. Para preparar uma cópia da revisão de
referência, use:

```bash
git clone --filter=blob:none --no-checkout \
  https://github.com/awslabs/agentcore-samples.git /tmp/agentcore-reference
git -C /tmp/agentcore-reference checkout 0d46da96306fa692c9887d0461252bf5aeeee6c3
python atualizar_modelos.py /tmp/agentcore-reference/06-workshops
python atualizar_modelos.py /tmp/agentcore-reference/06-workshops --execute
```

Esse checkout é apenas a referência oficial; não cria uma branch no projeto
Santander. O script verifica os hashes antes de editar, remove resultados
antigos das cópias e não chama AWS. O
[patch equivalente](modelos-ativos.patch) permite revisar as substituições.
Após aplicar, execute os notebooks novamente: alterar o ID do modelo não
certifica compatibilidade das dependências ou dos demais serviços.
