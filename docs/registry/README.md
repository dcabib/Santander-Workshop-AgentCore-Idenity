# Agent Registry — governança e consumo

As aulas 06–08 usam o catálogo AWS e sessões STS das personas Developer,
Publisher, Approver e Consumer. `agent-registry-control` administra registros;
`agent-registry` faz descoberta. O namespace anterior do AgentCore não deve ser
usado para novos recursos Registry.

O IaC em `infra/registry_workflow` separa fundação, publicação, submissão e
aprovação. A publicação prepara os descritores MCP/AGENT e seus digests. O
approver confere o bundle e fornece um arquivo de decisão ligado àqueles
digests; a versão aprovada torna-se descobrível. A aula lê os estados e o
histórico pelo SDK, mostra o provider e testa consumo real.

```bash
uv run python scripts/build_artifacts.py --banking
uv run python scripts/registry_deploy.py bootstrap --profile default --execute
uv run python scripts/registry_deploy.py foundation --profile default --execute
uv run python scripts/registry_deploy.py publish --profile default --execute
uv run python scripts/registry_deploy.py submit --profile default --execute
# Revise build/registry-bundle.json e os digests antes da fase seguinte.
uv run python scripts/registry_deploy.py approve --profile default   --review build/registry-review-candidate.json --execute
```

A configuração resultante é `config/aws.registry.json`. Em ambientes existentes,
consulte os stacks e versões antes de repetir fases. O pipeline preserva a
referência do catálogo recuperado e aceita `--runner-arn` para declarar a trust
policy das personas que serão utilizadas pelo CodeBuild.

Descoberta não concede invocação: a aula compara um consumidor autorizado com
uma persona que pode descobrir, mas não executar. A simulação IAM da tabela de
permissões complementa chamadas reais e não é descrita como tentativa de escrita.

[Implantação da jornada](../deploy.md) · [Validação AWS](../validacao.md)
