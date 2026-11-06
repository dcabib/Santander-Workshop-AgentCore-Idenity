# Registro de execução — 06/11/2026

Na conta `413816870411`, região `us-west-2`, foram executados os 17 notebooks
com código (13 da jornada e quatro extras), totalizando 186 células.
Os cinco notebooks de referência não têm código.
O run_id principal foi `5eb0ee2a8502`; 99 concluiu a limpeza e o registro
ficou `CLEANED`, sem recursos ativos.

A revisão semântica encontrou dois problemas mesmo com execução concluída:
A02 não preservava estado entre chamadas e A03 omitia quatro categorias da
cauda inferior na EDA. O checkout também não continha `docs/`, quebrando links
e testes. Veja [o relatório completo](../RELATORIO_NOTEBOOKS_2026-11-06.md).

As evidências anteriores às correções estão em `build/notebook-audit/`.
As novas execuções dos extras corrigidos ficam em `build/notebook-fixes/`.
Os dois extras passaram novamente: A02 comprovou a persistência e o primo 83;
A03 confirmou o resumo do agente e da ferramenta com 13 categorias atípicas e
a resposta 120. As sessões foram encerradas. A suíte local teve 192 testes
aprovados; os quatro testes adicionais de EDA também passaram.
Os guias recompostos e alterações editoriais não são uma nova execução da
jornada principal. O histórico citado anteriormente de 05/11 não estava
presente neste checkout; este guia registra somente a auditoria observada.

Os artefatos locais são ignorados pelo Git. Para certificar outra versão ou
conta, siga [o guia de validação](validacao.md) e preserve os próprios resultados.
