# Evidências entre contas

O aceite da aula 14 exige a implantação atual de quatro contas, embora a
chamada percorra três. Sem esse ambiente, registre a aula como não executada;
uma demonstração do instrutor não é evidência de execução na conta do participante.

Registre a execução CodeBuild, contas confirmadas pelo STS, ARNs dos recursos,
request_id do exercício e IDs nativos devolvidos pelo Gateway. O Runtime e a
Lambda registram correlação sem bearer, senha ou payload privado.

Para interpretar uma negativa, identifique a fronteira: autenticação,
Policy ou ACL da fonte. Timeout e erro genérico não devem ser classificados
como autorização negada. Compare `verified_subject` com o `sub` do JWT validado.

A fonte desta jornada é `AWS_SIMULATED_DATABRICKS`. Não há query ID ou audit log
Databricks real; não fabrique esses identificadores. Uma integração real
precisaria de histórico de consultas e evidência própria de grants.

[Validação](../validacao.md)
