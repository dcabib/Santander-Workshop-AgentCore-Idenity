# Limpeza pelo IaC

Os notebooks não apagam recursos ao terminar. O ambiente permanece disponível
para as aulas. A limpeza é uma operação separada, após revisão das dependências.

`scripts/cleanup.py` consulta a conta, região, ARN do stack, template implantado,
proteções e políticas de retenção. Sem `--execute`, apenas apresenta o plano.
Use `--scenario aws_workshop` para os templates da nova jornada. O parâmetro
`--confirm-stack-id` exige o ARN exato observado; uma proteção ativa ou um
template divergente interrompem a exclusão.
`--profile` é opcional: quando omitido, o wrapper usa a sessão AWS do ambiente,
mantendo a conferência explícita de conta e região.

Ordem de dependências: runner/observers; fases do catálogo origin-approve,
origin-submit e origin-publish; agentes de origem; bindings federados;
agentes e bindings de cada domínio; backends; Gateways; identidade da plataforma;
bootstrap por último. Registry, RAG e Terraform têm seus próprios recursos e
devem ser tratados pelos respectivos pipelines. Antes de remover, confira quem
consome seus outputs e a retenção de fontes, state, logs e evidências.

O bucket bootstrap é retido. Não o remova enquanto guardar state Terraform ou
evidências necessárias. O custom resource de retenção preserva logs do Runtime.
Não desative proteções nem apague recursos diretamente para contornar uma falha.
Diagnostique com comandos de leitura e siga o protocolo de aprovação do projeto.

A trilha Terraform oferece `plan-destroy` e `destroy`: o segundo somente aplica
o plano revisável correspondente aos inputs e hashes atuais. A migração do
backend para S3 não é uma operação de destruição da implantação.
