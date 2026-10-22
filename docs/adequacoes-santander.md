# Adequações ao pedido Santander — 09/10/2026

O [notebook 12](../notebooks/12_cenario_santander_integrado.ipynb) reúne a
demonstração principal: dois agentes hospedados na conta A, Gateway em cada
uma das três contas, Registry central e delegação até o MCP Databricks Azure.
O código, a infraestrutura como código e o material foram implementados.
**A execução integrada nos serviços ainda não foi realizada.**

Esta matriz atualiza as lacunas da [revisão da conversa e do HTML](../revisao-aderencia-santander.md).
“Implementado” indica material/código disponível; a última coluna separa a
prova que ainda depende do ambiente Santander.

| Demanda | Adequação entregue | Prova ou decisão ainda pendente |
|---|---|---|
| D01 — Usuário + agente + tool | Dois Runtimes e aplicações Entra distintas; Cedar por `tid`, `oid`, `azp`, tool e SQL aprovado. Matriz local de oito casos e testes de protocolo MCP. | A/Riscos permitido; mesmo A com agente Fraude negado em Riscos pelo hub real. |
| D02 — Entra/OBO preservando grants | WAT ligado ao usuário, OBO por salto, federation Databricks de usuários e comparação exata de principal. | Dois humanos reais; A com SELECT, B sem SELECT; comprovar decisão do Unity Catalog. |
| D03 — MCP Databricks via Gateway | Target MCP DBSQL nativo no Gateway da conta de dados, token exchange RFC 8693 pelo Identity. | Habilitação AWS do modo público de token exchange; endpoint/schema Azure e grants reais. |
| D04 — Negócio A → central → negócio B | Agentes executam em Runtime na origem e descobrem capacidades no Registry central antes da chamada. | Três contas reais, permissões IAM e chamadas entre as fronteiras. |
| D05 — Gateway por domínio | Três Gateways, três engines Policy `ENFORCE` e credenciais Identity locais. | Negativas atribuídas à Policy correta, com evidência de não execução downstream. |
| D06 — Hospedagem de agentes | Riscos e Fraude hospedados em Runtime; identidade do agente vem do deployment. O fluxo é determinístico para isolar autorização. | Invocação do Runtime pela origem e restrição de workload no serviço. O notebook 10 conserva o exemplo com LLM/Strands. |
| D07 — Registry governado | Owner, versão e instância; publicação pendente, aprovação em fase separada e consumer cross-account somente leitura. | Publicar, aprovar e descobrir no Registry gerenciado com os papéis corretos. |
| D08 — Trace até a query | Coleta sanitizada de request IDs, usuário pseudonimizado, agente/tool, hash da query e IDs observados da fonte; [procedimento de correlação](journey/trace.md). | Correlacionar logs/spans e audit Databricks. O aceite permanece `PENDING_EVIDENCE` sem essa prova. |
| D09 — QPM/TPM/budget | Exercício local por agente/tool e [divisão de responsabilidades](journey/decisoes.md). Limites temporais de Policy documentados. | Escolher enforcement e medição do piloto. O contador em memória não é controle produtivo nem faturamento. |
| D10 — Complementar ou substituir Databricks | Matriz Gateway gerenciado versus adapter Runtime; proposta de complementar a stack atual e explicação dos endpoints legados/Unity Gateway. | Deliberação do cliente após o ensaio e inventário dos controles efetivos. |
| D11 — K2 intacto e externo | Contrato de identidade, instância, descoberta e correlação documentado; substitutos sintéticos para a demonstração. | Implementar o conector real apenas quando seu contrato e ambiente estiverem disponíveis. |
| D12 — Coexistência da stack | Posicionamento de Neural Trust, Dynatrace, Watsonx.governance e SanEval na matriz de responsabilidades. | Conectores/transportes não instalados; confirmar versões e padrões Santander. |
| D13 — Didática e agenda | [Roteiro](roteiro.md) de demo de 30 minutos e workshop de quatro horas; 14 notebooks e [galeria](diagramas/index.html#12_cenario_santander_integrado). | Ensaio do apresentador no sandbox com as quatro chamadas de aceite. |

## Outras sessões do programa

* **Ingestão, ACL e memória:** o [notebook 13](../notebooks/13_ingestao_acl_memoria.ipynb)
  executa um contrato local com documentos sintéticos, versões, exclusão,
  revogação e isolamento de memória por usuário. A [Sessão 2](ingestao/sessao-2.md)
  tem agenda e contratos das quatro fontes. SharePoint, Databricks Silver/Gold,
  SQL on-prem, BDA, KB/OpenSearch e Memory AWS ainda precisam de conectores e ensaio.
* **Harness:** há [roteiro de uma hora](harness/sessao-online.md), referências e
  critérios de release/rollback. Não houve implantação do produto. A versão
  homologada e sua integração ao pipeline IaC precisam ser confirmadas.
* **Context e Neptune:** dependências/decisões da Sessão 2 estão explícitas.
  Não se presume qual produto foi chamado de “AWS Context” na conversa.

## Validação e próximo ensaio

**138 testes, 14 notebooks e 94 células passaram localmente**, com cleanup de
nuvem desativado. Os dez novos templates CloudFormation e dois módulos Terraform
passaram na validação estrutural. O [relatório de validação](validacao.md)
registra evidências e limites.

Para executar na nuvem, preencher a [configuração](../config/journey.example.json)
com perfis/IDs das três contas, aplicações/usuários Entra, ARNs de segredos e
endpoint Azure. Preparar federation, warehouse e grants pelo IaC de seus
proprietários e confirmar a habilitação nativa de token exchange.
Seguir então as fases do [runbook](journey/README.md). Nenhum resultado local
substitui as quatro chamadas reais e a revisão dos logs.
