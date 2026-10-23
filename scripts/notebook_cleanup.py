"""Células de encerramento compartilhadas pelos geradores dos doze notebooks."""

from pprint import pformat
from textwrap import dedent

import nbformat as nb

COMMON_NAMES = [
    "lab",
    "cloud",
    "config",
    "token",
    "identity",
    "MODE",
    "CLEANUP_TARGET",
    "CLEANUP_EXECUTE",
    "CLEANUP_CONFIRM_STACK_ID",
    "_cleanup_command",
    "_cleanup_subprocess",
    "_cleanup_sys",
]
LOCAL_NAMES = {
    "07": ["flow", "packages", "keys", "package", "record", "agent_record", "rejected",
           "rejected_key", "changed", "registry_lab", "registry_config", "review", "review_path",
           "pipeline", "expect_denial", "result", "records", "phase", "persona", "key",
           "kind", "record_states", "iam_rows", "RUN_AWS", "RUN_PIPELINE"],
    "00": ["versions"],
    "01": ["names", "params", "read", "write", "session", "answer", "result", "payload"],
    "02": ["proof", "wrong_audience"],
    "03": ["permitted", "restricted", "before"],
    "04": ["rows", "row"],
    "05": ["cedar", "generation_id", "draft", "asset"],
    "06": ["registry", "states"],
    "08": ["result", "local_results"],
    "10": [],
    "13": ["delegated", "user_jwt", "proof", "target"],
    "11": [
        "schemas",
        "rows",
        "lob",
        "tools",
        "templates",
        "path",
        "template",
        "plans",
        "plan",
        "command",
        "capabilities",
        "mcp",
        "names",
        "readable",
        "customer_id",
        "observations",
        "tool",
        "policies",
        "gateway_arn_for_display",
        "rules",
        "denial",
        "prompt",
        "agent_result",
        "observed_lobs",
        "evidence",
        "target",
    ],
    "12": [
        "matrix",
        "templates",
        "plans",
        "plan",
        "identity_evidence",
        "observations",
        "lob",
        "tool",
        "denials",
        "customer",
        "denial",
        "auth_evidence",
        "agent_result",
        "observed",
        "evidence",
        "target",
    ],
    "14": [
        "matrix",
        "templates",
        "plans",
        "plan",
        "command",
        "rows",
        "row",
        "token_a",
        "token_b",
        "environment",
        "sessions",
        "quota_demo",
        "report",
        "target",
        "phase",
        "case",
        "result",
    ],
    "15": ["knowledge_report", "sources", "source", "target"],
    "16": [
        "documents",
        "items",
        "acl",
        "rules",
        "matrix",
        "row",
        "spoof",
        "chunks",
        "claims",
        "arguments",
        "bad_claims",
        "tampered",
        "model_request",
        "templates",
        "command",
        "config",
        "environment",
        "identity_environment",
        "authorization_boundary",
        "admin",
        "caller",
        "model",
        "identity_api",
        "wat",
        "issued",
        "live_rows",
        "live_report",
        "started",
        "token_a",
        "label",
        "expected",
        "live_config",
        "login_token",
        "metadata",
        "decision",
        "request",
        "source_uri",
        "corpus",
        "output_path",
        "query_user",
        "tokens",
        "show_checks",
        "checks",
        "acl_checks",
        "observed",
        "passed",
        "stage",
        "injected",
        "domain",
        "document_id",
        "policy_name",
        "statement",
        "identity_resources",
        "data_resources",
        "access_resources",
        "policy_resources",
        "EXPECTED_DOCUMENTS",
    ],
}
LIVE_NAMES = [
    "sessions",
    "environment",
    "user_token",
    "RUN_AWS",
    "DEPLOY_PHASE",
    "RUN_PIPELINE",
    "APPLY_CHANGESET",
    "RUN_AGENT",
    "CONFIG_PATH",
    "LIVE",
]
SCENARIOS = {
    "registry_workflow": """
O notebook 07 tem ambiente próprio em uma conta. Remova os stacks na ordem
**approve → submit → publish → foundation → bootstrap**, usando o prefixo do
deploy (padrão `registry-personas`). Cada fase tem um template de mesmo nome.
Excluir a aprovação não reverte o estado de um registro: quem remove os registros
é o stack `publish`. Os providers ficam disponíveis até o fim de `foundation`.

O bucket versionado de artefatos é preservado por `Retain`, inclusive seus custos.
A service-linked role criada pelo serviço não é apagada pelo workshop.
Consulte o [guia do ciclo de vida](../docs/registry/README.md#limpeza).
""",
    "rag": """
O notebook 16 possui stacks próprios, em uma conta AWS. Remova na ordem:

1. Template `access-cognito`, stack terminado em `-rag-access`.
2. Template `data`, stack terminado em `-rag-data`.
3. Template `identity`, stack terminado em `-rag-identity`.
4. Template `bootstrap`, stack terminado em `-rag-bootstrap`.

Use o prefixo escolhido no deploy e o ARN real de cada stack. A KB, sua fonte e
o bucket de documentos usam `RetainExceptOnCreate`; o bucket de artefatos usa
`Retain`. A remoção normal de um ambiente criado com sucesso preserva esses
recursos e seus custos. O descarte requer uma alteração explícita no IaC.
As quatro identidades e seus segredos são recursos exclusivos do stack
`identity`. Consulte o [runbook do RAG](../docs/rag/README.md).
""",
    "journey": """
O notebook 14 possui um ambiente próprio em três contas. Remova, nesta ordem:

1. `origin-bindings` na origem.
2. `riscos-agent` e `fraude-agent` na origem.
3. `registry` na plataforma e `platform-bindings` na plataforma.
4. `data-bindings` no domínio de dados.
5. Os três stacks `*-gateway`, cada um em sua conta.
6. `bootstrap` em cada conta, após revisar os buckets retidos.

Use o nome real e o ARN revisado de cada stack. O wrapper não remove os
aplicativos Entra, a federation Databricks, tabelas, grants ou segredos
externos. Esses recursos pertencem ao IaC dos seus proprietários.
O notebook 15 é um exercício local; não cria recursos cloud.
Consulte o [runbook integrado](../docs/journey/README.md).
""",
    "workshop": """
Os notebooks **00–06, 08, 10 e 13 compartilham o ambiente**. Remova os stacks somente
ao encerrar toda a trilha, depois de salvar as evidências.

1. Atualize `origin` com `EnableRuntime=false` pelo `scripts/deploy.py`.
2. Remova `registry`; preserve o output de `policy-draft`, se utilizado,
   antes de remover seu stack. O histórico de geração usa `Retain`.
3. Atualize `hub` com `EnableFraud=false` pelo `scripts/deploy.py`.
4. Remova `fraud-runtime`, depois `hub` e, por último, `origin`.
5. Remova os stacks `bootstrap` somente após revisar os artefatos retidos.

Para cada remoção, use o template correspondente e o **nome real do stack**
implantado. Os nomes de template acima não determinam os nomes dos stacks.
Buckets usam `Retain`; aplicações e segredos Entra seguem o Terraform que os
gerencia. O notebook 13 não é proprietário do workspace, warehouse ou grants
Databricks. Consulte o [runbook da trilha](../docs/deploy.md#9-limpeza).
""",
    "banking": """
Ao encerrar o notebook 11, siga a ordem inversa das dependências:

| Ordem | Templates dos stacks | Contas |
|---|---|---|
| 1 | `agent` | Plataforma |
| 2 | `bindings` | Plataforma |
| 3 | `retail-banking`, `transaction-banking`, `lending-wealth` | Respectivas LOBs |
| 4 | `platform` | Plataforma |
| 5 | `bootstrap` | Cada uma das quatro contas |

Execute uma remoção por vez e aguarde sua conclusão. Tabelas, fixtures e
buckets têm `Retain`: remover os stacks não elimina todos os dados nem todos
os custos. KB, documentos, identidades Okta e segredo M2M continuam sob o
IaC dos respectivos proprietários. Consulte o
[runbook do cenário](../docs/banking/README.md#remoção).
""",
    "federation": """
Ao encerrar o notebook 12, siga a ordem inversa das dependências:

| Ordem | Templates dos stacks | Contas |
|---|---|---|
| 1 | `registry` | Plataforma |
| 2 | `platform-bindings` | Plataforma |
| 3 | `retail-banking-bindings`, `transaction-banking-bindings`, `lending-wealth-bindings` | LOBs |
| 4 | `retail-banking-backend`, `transaction-banking-backend`, `lending-wealth-backend` | LOBs |
| 5 | `platform-gateway` e os três templates `*-gateway` das LOBs | Quatro contas |
| 6 | `bootstrap` | Cada uma das quatro contas |

Execute uma remoção por vez e aguarde sua conclusão. Tabelas, fixtures e
buckets têm `Retain`; identidades Entra, grants, segredos e KB são geridos
pelos stacks de seus proprietários. Remover esta trilha não remove o
ambiente do notebook 11. Consulte o
[runbook da federação](../docs/federation/README.md) e o
[procedimento de cleanup](../docs/cleanup.md).
""",
}


def cleanup_cells(notebook_id, scenario):
    names = COMMON_NAMES + LOCAL_NAMES[notebook_id[:2]]
    if scenario != "workshop":
        names += LIVE_NAMES
    cloud_text = f"""
## Limpeza — recursos do laboratório

{SCENARIOS[scenario].strip()}

**Na próxima célula**, `CLEANUP_TARGET=None` manterá a remoção desativada e
imprimirá `cloud_cleanup: NOT_RUN`. Para revisar um stack real, preencha o
alvo indicado no comentário e mantenha `CLEANUP_EXECUTE=False`. O script
`scripts/cleanup.py` consultará STS e CloudFormation, exigirá correspondência
exata entre template implantado e fonte local e mostrará o ARN, as retenções
declaradas e eventuais bloqueios. Essa preparação faz somente leituras.

Após revisar o plano e a ordem acima, copie seu ARN para
`CLEANUP_CONFIRM_STACK_ID` e habilite `CLEANUP_EXECUTE` para remover **esse
stack** pelo wrapper IaC. O script aguarda a exclusão pelo CloudFormation,
respeita `Retain` e não desativa proteções. Falhas devem ser resolvidas no
IaC. A execução padrão deste notebook não remove recursos em nuvem.
"""
    cloud_code = f"""
import subprocess as _cleanup_subprocess
import sys as _cleanup_sys

# Preencha somente para um stack do laboratório, após encerrar a trilha:
# {{"template": "TEMPLATE", "stack": "NOME_REAL", "profile": "PERFIL",
#   "account": "ID_DA_CONTA", "region": "REGIAO"}}
CLEANUP_TARGET = None
CLEANUP_EXECUTE = False
CLEANUP_CONFIRM_STACK_ID = ""

if CLEANUP_TARGET is None:
    print({{"cloud_cleanup": "NOT_RUN", "reason": "Nenhum stack selecionado"}})
else:
    assert set(CLEANUP_TARGET) == {{"template", "stack", "profile", "account", "region"}}
    _cleanup_command = [
        _cleanup_sys.executable, str(ROOT / "scripts/cleanup.py"),
        "--scenario", "{scenario}",
    ]
    for _cleanup_key, _cleanup_value in CLEANUP_TARGET.items():
        _cleanup_command.extend(["--" + _cleanup_key, _cleanup_value])
    if CLEANUP_EXECUTE:
        assert CLEANUP_CONFIRM_STACK_ID, "Revise o plano e informe o ARN exato do stack"
        _cleanup_command.extend(["--execute", "--confirm-stack-id", CLEANUP_CONFIRM_STACK_ID])
    _cleanup_subprocess.run(_cleanup_command, cwd=ROOT, check=True)
"""
    names += ["_cleanup_key", "_cleanup_value"]
    local_text = """
### Limpeza — estado local do notebook

Vamos remover as variáveis de dados, tokens, clientes e configuração criadas
por este exercício. As sessões MCP abertas com `async with` já foram encerradas
ao sair de seus blocos; o cliente de controle de `cloud`, quando presente,
também será fechado. A célula verificará que os nomes listados deixaram
de existir e exibirá `cleanup_local: PASS`; ela pode ser repetida.

Os notebooks, diagramas, templates e arquivos de evidências serão preservados.
Esta limpeza remove referências do namespace; não revoga tokens nem apaga
outputs ou todas as cópias que possam existir na memória do processo.
Após salvar as evidências, limpe as saídas e encerre o kernel para terminar
a sessão. Para repetir o laboratório, recomece pela preparação do ambiente.
"""
    local_code = f"""
import json as _cleanup_json

if globals().get("cloud") is not None:
    cloud.control.close()
_cleanup_names = {pformat(sorted(set(names)), width=88, compact=True)}
_cleanup_removed = [name for name in _cleanup_names if name in globals()]
for _cleanup_name in _cleanup_names:
    globals().pop(_cleanup_name, None)
assert not any(name in globals() for name in _cleanup_names)
print(_cleanup_json.dumps({{
    "cleanup_local": "PASS",
    "removed_variables": len(_cleanup_removed),
    "files": "PRESERVED",
}}, ensure_ascii=False))
del _cleanup_name, _cleanup_names, _cleanup_removed, _cleanup_json
"""
    return [
        nb.v4.new_markdown_cell(dedent(cloud_text).strip()),
        nb.v4.new_code_cell(dedent(cloud_code).strip(), metadata={"tags": ["cleanup_cloud"]}),
        nb.v4.new_markdown_cell(dedent(local_text).strip()),
        nb.v4.new_code_cell(dedent(local_code).strip(), metadata={"tags": ["cleanup_local"]}),
    ]
