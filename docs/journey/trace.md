# Seguir uma chamada até a fonte

No [laboratório 14](README.md), quatro resultados de negócio precisam ser
explicados: duas consultas permitidas, uma negativa na Policy e uma negativa
na fonte. O trace conecta esses resultados aos componentes que os produziram.

## O que uma resposta permite concluir

[evidence.py](../../src/santander_demo/journey/evidence.py) registra o identificador
da requisição, usuário pseudonimizado, agente, ferramenta, hash da consulta e
IDs HTTP ou de consulta quando disponíveis. Um ID gerado no cliente identifica
a tentativa; sozinho, não demonstra que todos os serviços a processaram.

| Caso | Prova necessária |
|---|---|
| A / Riscos | Identidade esperada na fonte e canário Riscos permitido |
| A / Fraude | Identidade esperada na fonte e canário Fraude permitido |
| A / Fraude → Riscos | Decisão da Policy central e ausência comprovada de execução downstream |
| B / Riscos | Consulta de identidade permitida; canário Riscos negado por grant |

## Correlacionar as observações

1. Execute um caso e guarde o resumo sanitizado. Preserve IDs recebidos dos
   serviços; não invente um query ID quando o MCP não o fornecer.
2. Leia os logs dos Runtimes e dos três Gateways. Procure relações entre request
   UUID, IDs HTTP e eventos do próximo componente. Proximidade de horário ajuda
   a pesquisar, mas não comprova a relação sozinha.
3. Consulte o histórico/audit do Databricks usando o ID observado. Confirme
   usuário, consulta canário e resultado. Use o acesso de auditoria autorizado;
   o usuário B deve continuar sem o grant que estamos testando.
4. Para a negativa central, execute um caso permitido antes e depois. Confirme
   que os logs chegaram e cobrem a janela completa antes de concluir que o
   backend não foi chamado. Uma busca vazia não é prova suficiente.
5. Registre as fontes, IDs e a conclusão por fronteira. No caso B, separe a
   consulta de identidade da consulta ao canário: uma pode funcionar enquanto
   a outra registra uma falha de autorização.

## Interpretar a completude

`acceptance()` mantém `PENDING_EVIDENCE` enquanto faltam observações obrigatórias.
Não altere os indicadores manualmente para fazer o resumo passar. Se o serviço
não expuser um identificador necessário, registre a limitação e a cobertura
realmente obtida.

Ao compartilhar uma evidência, inclua horário UTC, versão do código, cenário,
fronteira, resultado e IDs reais. Exclua JWTs, segredos, conteúdo dos documentos
e dados de usuários. O projeto exporta resumos para revisão; não instala
conectores para ferramentas externas de observabilidade ou governança.

Volte ao [guia de validação](../validacao.md) para comparar evidência local,
integração real e correlação.
