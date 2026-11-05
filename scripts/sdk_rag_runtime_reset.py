"""Reconstrução explícita somente do pacote, role e Runtime RAG registrados."""

from scripts.aws_notebook_lessons import step


def reset():
    return step(
        "Reconstrução opcional: remover somente o Runtime RAG",
        "Este passo só executa com WORKSHOP_CLEANUP_SCOPE=rag-runtime. "
        "Depois da verificação completa de propriedade, exclui o Runtime "
        "RAG, seus logs, sua role e seu ZIP. A base, a fonte, a ingestão, o "
        "conector, as políticas e as demais aulas permanecem disponíveis. "
        "A próxima execução de 16 reconstrói o agente com o código atual.",
        """
        if globals().get("CLEANUP_SCOPE", "all") == "rag-runtime":
            entry = state.get("rag.runtime")
            if entry:
                control.delete_agent_runtime(agentRuntimeId=entry["id"])
                wait_deleted(lambda: control.get_agent_runtime(agentRuntimeId=entry["id"]),
                             control.exceptions.ResourceNotFoundException)
                state.forget("rag.runtime", expected=entry)
            entry = state.get("rag.logs")
            if entry:
                logs.delete_log_group(logGroupName=entry["name"])
                page = logs.describe_log_groups(logGroupNamePrefix=entry["name"])
                assert not any(group["logGroupName"] == entry["name"] for group in page["logGroups"])
                state.forget("rag.logs", expected=entry)
            entry = state.get("rag.runtime_role")
            if entry:
                names = iam.list_role_policies(RoleName=entry["name"])["PolicyNames"]
                if entry["policy_name"] in names:
                    iam.delete_role_policy(RoleName=entry["name"], PolicyName=entry["policy_name"])
                iam.delete_role(RoleName=entry["name"])
                wait_deleted(lambda: iam.get_role(RoleName=entry["name"]), iam.exceptions.NoSuchEntityException)
                state.forget("rag.runtime_role", expected=entry)
            entry = state.get("rag.artifact")
            if entry:
                s3.delete_object(Bucket=entry["bucket"], Key=entry["key"], ExpectedBucketOwner=ACCOUNT_ID)
                try:
                    s3.get_object(Bucket=entry["bucket"], Key=entry["key"], ExpectedBucketOwner=ACCOUNT_ID)
                except s3.exceptions.NoSuchKey:
                    state.forget("rag.artifact", expected=entry)
                else:
                    raise AssertionError("RAG_ARTIFACT_STILL_PRESENT")
            print({"cleanup_scope": "rag-runtime", "status": "CONFIRMED",
                   "execution_status": state.data["status"],
                   "preserved_resources": sorted(state.data["resources"])})
        """,
    )
