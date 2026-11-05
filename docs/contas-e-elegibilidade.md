# Contas necessárias e seleção das aulas

A jornada SDK validada usa **uma conta AWS**: **00–09 → 15–16 → 99 (limpeza)**.
As células criam, inspecionam e usam os serviços durante o notebook. Ela não
exige CloudFormation nem recursos da solução preparados antes da aula 00.
Uma conta precisa ter sessão autorizada, permissões, quotas, serviços e modelos
disponíveis na região. Consulte o [roteiro de contas efêmeras](contas-efemeras.md).

## Matriz dos notebooks atuais

| Notebooks | Contas no fluxo | Contas exigidas | Execução no Workshop Studio com uma conta |
|---|---|---|---|
| 00–09 | Uma conta AWS | **1** | Jornada SDK; criação durante as células |
| 15–16 | Uma conta AWS | **1** | Memory e RAG; dependem das aulas SDK anteriores |
| 13 | Plataforma + fonte em Transaction | **4 distintas** no legado atual | Não executar; conversão pendente |
| 14 | Retail → plataforma → Transaction | **4 distintas** no legado atual | Não executar; conversão pendente |
| 90 (antiga 10) | Plataforma + Retail + Transaction + Lending | **4 distintas** | Bloco final multiconta; não executar |
| 91 (antiga 11) | Agente central na plataforma + três domínios | **4 distintas** | Bloco final multiconta; não executar |
| 92 (antiga 12) | Plataforma → Transaction | **4 distintas** no legado atual | Bloco final multiconta; não executar |
| 99 | Recursos SDK desta execução | **1** | Limpeza explícita depois da jornada SDK |

Os três notebooks específicos de multiconta estão no final da sequência:

* [90 — Quatro contas e fronteiras](../notebooks/90_multiconta_santander.ipynb).
* [91 — Agente central e três domínios](../notebooks/91_multiconta_agente_central_gateway_mcp.ipynb).
* [92 — Gateways, Identity e Policy por conta](../notebooks/92_multiconta_gateways_identity_policy.ipynb).

**13 e 14 também precisam das quatro contas do ambiente legado.** Elas não
fazem parte da seleção de conta única. Na 14, Lending não participa da chamada,
mas continua sendo dependência do manifesto e da federação atuais. Na 92,
o desenho mostra duas contas, mas a implementação exige quatro preparadas.
Perfis diferentes apontando para o mesmo ID não atendem a esse requisito.

Pessoas sintéticas A/B/C/D e personas IAM do Registry não são contas AWS;
ambas podem existir dentro da mesma conta do participante.

## O que executar na turma

Execute 00–09 e 15–16 em ordem, leia as validações e só então use 99 para remover
os recursos SDK registrados. Não use “Run All” na coleção inteira. A limpeza 99
não remove o ambiente legado multiconta nem o editor do evento.

Com uma, duas ou três contas, reserve 13–14 e 90–92 para leitura guiada.
Com quatro contas, esses cenários ainda precisam da implantação legada e das
integrações indicadas; não foram convertidos nem revalidados na jornada SDK.
A renomeação não cria contas nem altera permissões.

## Compatibilidade dos IDs antigos

A numeração visível mudou de **10 → 90**, **11 → 91** e **12 → 92**.
O manifesto, as chamadas nas células e os relatórios históricos conservam os
IDs legados 10, 11 e 12. Isso mantém os requisitos de quatro contas e os recursos
referenciados sem alterar o código AWS.

Os verificadores de notebooks aceitam os números novos e antigos. Por exemplo,
a checagem abaixo valida somente o formato e a sintaxe, sem chamar a AWS:

```bash
uv run python scripts/verify_notebooks.py --validate-only --labs 90 91 92
```

Nos scripts antigos de pré-requisitos e deploy, os IDs continuam sendo 10, 11
e 12. Esses scripts pertencem ao legado e não são necessários para iniciar a
jornada SDK. O [aceite SDK](aceite-notebooks-sdk.md) cobre somente as aulas e
as execuções registradas; leitura de código ou renomeação não representa PASS
operacional de um cenário multiconta.
