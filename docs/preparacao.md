# Preparar o ambiente

Use Python 3.12 ou 3.13, `uv` e uma sessão AWS autorizada. Na raiz do projeto,
execute `./scripts/setup.sh` e selecione **Santander Workshop (.venv)**.
Abra [00_preflight](../notebooks/00_preflight.ipynb) e confira conta, região e ARN
retornados pelo STS antes de criar recursos.

A jornada foi executada em `us-west-2`. Credenciais válidas não comprovam
permissões, quotas, disponibilidade regional ou acesso aos modelos.
As aulas criam recursos por SDK, incluindo IAM, Cognito, Lambda, Gateway,
Runtime, Policy, Registry, Memory e RAG. A sessão precisa autorizar essas
operações e `iam:PassRole` nas roles próprias do exercício.
Um Deny do evento deve ser tratado com o administrador da conta.

Use a cadeia padrão de credenciais do boto3: role do ambiente, perfil ou sessão
temporária no processo. Não cole credenciais em células ou arquivos publicados.
Os [extras](../notebooks/20-Extras/README.md) têm dependências e kernel separados.
