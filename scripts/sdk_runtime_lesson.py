"""Runtime MCP com implantação de código explícita nas células."""

from scripts.aws_notebook_lessons import md, step

SERVER_SOURCE = '''import os

import boto3
from mcp.server.fastmcp import FastMCP

# Este processo só será iniciado pelo AgentCore Runtime na AWS.
mcp = FastMCP(host="0.0.0.0", port=8000, stateless_http=True)


@mcp.tool()
def workload_identity() -> dict:
    """Consulta STS na AWS usando a role do servidor MCP."""
    identity = boto3.client("sts").get_caller_identity()
    assert identity["Account"] == os.environ["WORKSHOP_ACCOUNT"]
    assert (":assumed-role/" + os.environ["WORKSHOP_ROLE_NAME"] + "/") in identity["Arn"]
    return {
        "execution": "AWS_AGENTCORE_RUNTIME",
        "account": identity["Account"],
        "principal": identity["Arn"],
        "run_id": os.environ["WORKSHOP_RUN"],
        "sts_request_id": identity["ResponseMetadata"]["RequestId"],
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
'''


def runtime():
    return [
        md("""
        ### Identidade do chamador e identidade do workload

        `Notebook → IAM/SigV4 → AgentCore Runtime → servidor MCP → STS`

        Nas aulas anteriores, uma pessoa usou Cognito para entrar no Gateway.
        Nesta aula, criaremos um servidor MCP no Runtime e o invocaremos com
        IAM/SigV4. A ferramenta consulta STS dentro da AWS. Seu resultado
        deve mostrar a role de execução do Runtime, diferente da identidade
        do participante que assinou a chamada.

        O Runtime hospeda o código e fornece credenciais temporárias à role.
        O Cognito identifica pessoas e aplicações. Uma identidade não se
        transforma automaticamente na outra; esta aula não implementa OBO.

        **Pré-requisito:** aula 00, uma conta e região com Runtime disponível.
        São usadas APIs S3 de criação, upload, leitura e exclusão, bloqueio de
        acesso público e criptografia; IAM para criar e passar a role;
        `CreateAgentRuntime`, consultas, invocação, encerramento de sessão e
        exclusão; CloudWatch Logs para consultar e definir retenção.

        Usaremos [implantação direta de código](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html).
        O ZIP é preparado no ambiente do notebook e enviado ao S3; o servidor
        só inicia na AWS. Não é necessário CloudFormation, ECR ou CodeBuild.
        """),
        *step(
            "Preparar os nomes e clientes",
            "Os nomes contêm o identificador da execução. A região e a conta "
            "vêm do STS e da sessão do notebook, sem referências ao ambiente "
            "do instrutor.",
            """
            import hashlib
            import time
            from botocore.exceptions import ClientError

            s3 = aws.client("s3")
            iam = aws.client("iam")
            control = aws.client("bedrock-agentcore-control")
            runtime_api = aws.client("bedrock-agentcore")
            logs = aws.client("logs")
            RUNTIME_NAME = NAME_PREFIX.replace("-", "_") + "_mcp"
            ROLE_NAME = NAME_PREFIX + "-runtime"
            BUCKET_NAME = NAME_PREFIX + "-" + ACCOUNT_ID + "-" + REGION
            BUCKET_ARN = f"arn:{PARTITION}:s3:::{BUCKET_NAME}"
            MARKER_KEY = "workshop-owner.json"
            marker = {"run_id": state.data["run_id"], "account": ACCOUNT_ID, "region": REGION}

            def owned(tags):
                assert all(tags.get(key) == value for key, value in TAGS.items()), "OWNERSHIP_MISMATCH"

            def wait_runtime(runtime_id):
                deadline = time.monotonic() + 420
                while time.monotonic() < deadline:
                    current = control.get_agent_runtime(agentRuntimeId=runtime_id)
                    if current["status"] == "READY":
                        return current
                    if current["status"] in {"CREATE_FAILED", "UPDATE_FAILED", "DELETING", "FAILED"}:
                        raise RuntimeError("RUNTIME_FAILED: " + str(current.get("failureReason", current["status"])))
                    time.sleep(5)
                raise TimeoutError("RUNTIME_NOT_READY")

            print({"runtime_name": RUNTIME_NAME, "artifact_bucket": BUCKET_NAME, "role": ROLE_NAME})
            """,
        ),
        *step(
            "Ler o código que executará no Runtime",
            "A ferramenta usa boto3 dentro do Runtime para consultar STS. "
            "Nenhuma chave AWS é enviada no ZIP ou nas variáveis de ambiente. "
            "O host 0.0.0.0 é o bind interno do processo gerenciado pela AWS; "
            "a entrada do Runtime será protegida por IAM.",
            "from IPython.display import Code\n\n"
            f"SERVER_SOURCE = {SERVER_SOURCE!r}\n"
            'display(Code(SERVER_SOURCE, language="python"), include=["text/html", "text/plain"])\n',
        ),
        *step(
            "Empacotar dependências ARM64 e código",
            "O Runtime de código Python exige wheels ARM64. Usamos as versões "
            "e hashes do uv.lock, sem iniciar o servidor no notebook. Cedar "
            "é removido deste pacote porque esta ferramenta usa MCP e STS. "
            "O ZIP tem permissões de leitura e timestamps fixos. Na retomada, "
            "o código, lockfile e hash devem corresponder ao artefato registrado.",
            """
            import subprocess
            import tempfile
            import zipfile

            artifact_dir = ROOT / "build" / "runtime-sdk" / state.data["run_id"]
            artifact_dir.mkdir(parents=True, exist_ok=True)
            archive_path = artifact_dir / "runtime.zip"
            source_hash = hashlib.sha256(SERVER_SOURCE.encode()).hexdigest()
            lock_hash = hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()
            artifact_entry = state.get("runtime.artifact")
            if artifact_entry:
                assert artifact_entry["source_hash"] == source_hash, "RUNTIME_SOURCE_CHANGED"
                assert artifact_entry["lock_hash"] == lock_hash, "RUNTIME_LOCK_CHANGED"
                if not archive_path.is_file():
                    downloaded = s3.get_object(
                        Bucket=artifact_entry["bucket"], Key=artifact_entry["key"],
                        ExpectedBucketOwner=ACCOUNT_ID,
                    )
                    archive_path.write_bytes(downloaded["Body"].read())
                assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == artifact_entry["sha256"]
            else:
                requirements = artifact_dir / "requirements.txt"
                subprocess.run([
                    "uv", "export", "--frozen", "--no-dev", "--no-emit-project",
                    "--prune", "cedarpy", "--output-file", str(requirements),
                ], cwd=ROOT, check=True, capture_output=True, text=True)
                with tempfile.TemporaryDirectory(dir=artifact_dir) as temporary:
                    package = Path(temporary)
                    subprocess.run([
                        "uv", "pip", "install", "--python-platform", "aarch64-manylinux2014",
                        "--python-version", "3.12", "--only-binary", ":all:",
                        "--require-hashes", "--target", str(package),
                        "-r", str(requirements),
                    ], cwd=ROOT, check=True)
                    (package / "main.py").write_text(SERVER_SOURCE)
                    files = sorted(path for path in package.rglob("*") if path.is_file())
                    assert sum(path.stat().st_size for path in files) < 750 * 1024 * 1024
                    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                        for path in files:
                            if "__pycache__" in path.parts or path.suffix == ".pyc":
                                continue
                            assert not path.is_symlink()
                            info = zipfile.ZipInfo(path.relative_to(package).as_posix(), (1980, 1, 1, 0, 0, 0))
                            info.external_attr = 0o100644 << 16
                            info.compress_type = zipfile.ZIP_DEFLATED
                            archive.writestr(info, path.read_bytes())
            artifact_bytes = archive_path.read_bytes()
            assert len(artifact_bytes) < 250 * 1024 * 1024
            artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
            OBJECT_KEY = "runtime/" + artifact_hash + ".zip"
            print({"zip_bytes": len(artifact_bytes), "sha256": artifact_hash, "architecture": "ARM64"})
            """,
        ),
        *step(
            "Criar o bucket dedicado e proteger o artefato",
            "O bucket nasce nesta célula. Bloqueamos acesso público e "
            "configuramos criptografia AES256 antes do upload. A propriedade "
            "é conferida pelo proprietário esperado e por um marcador da "
            "execução. Não reutilizamos buckets encontrados por nome.",
            """
            bucket_entry = state.get("runtime.bucket")
            if bucket_entry is None:
                # Buckets novos usam BucketOwnerEnforced por padrão no S3.
                options = {"Bucket": BUCKET_NAME}
                if REGION != "us-east-1":
                    options["CreateBucketConfiguration"] = {"LocationConstraint": REGION}
                s3.create_bucket(**options)
                bucket_entry = state.record(
                    "runtime.bucket", {"name": BUCKET_NAME, "arn": BUCKET_ARN}, lesson="03",
                )
            assert bucket_entry == {"name": BUCKET_NAME, "arn": BUCKET_ARN, "lesson": "03"}
            s3.head_bucket(Bucket=BUCKET_NAME, ExpectedBucketOwner=ACCOUNT_ID)
            bucket_ready = state.get("runtime.bucket_ready")
            if bucket_ready is None:
                s3.put_public_access_block(
                    Bucket=BUCKET_NAME, ExpectedBucketOwner=ACCOUNT_ID,
                    PublicAccessBlockConfiguration={
                        "BlockPublicAcls": True, "IgnorePublicAcls": True,
                        "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
                    },
                )
                s3.put_bucket_encryption(
                    Bucket=BUCKET_NAME, ExpectedBucketOwner=ACCOUNT_ID,
                    ServerSideEncryptionConfiguration={"Rules": [{
                        "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"},
                    }]},
                )
                s3.put_object(
                    Bucket=BUCKET_NAME, Key=MARKER_KEY,
                    Body=json.dumps(marker, sort_keys=True).encode(),
                    ContentType="application/json", ServerSideEncryption="AES256",
                    ExpectedBucketOwner=ACCOUNT_ID, IfNoneMatch="*",
                )
                state.record("runtime.bucket_ready", {"name": BUCKET_NAME, "marker": MARKER_KEY}, lesson="03")
            remote_marker = s3.get_object(
                Bucket=BUCKET_NAME, Key=MARKER_KEY, ExpectedBucketOwner=ACCOUNT_ID,
            )
            assert json.loads(remote_marker["Body"].read()) == marker, "BUCKET_OWNER_MARKER_CHANGED"
            import httpx
            anonymous_marker = httpx.get(
                f"https://{BUCKET_NAME}.s3.{REGION}.amazonaws.com/{MARKER_KEY}",
                timeout=30, follow_redirects=False,
            )
            assert anonymous_marker.status_code == 403, "EXPECTED_PRIVATE_ARTIFACT_BUCKET"
            assert anonymous_marker.headers.get("x-amz-request-id"), "EXPECTED_S3_REQUEST_ID"
            if artifact_entry is None:
                s3.put_object(
                    Bucket=BUCKET_NAME, Key=OBJECT_KEY, Body=artifact_bytes,
                    ContentType="application/zip", ServerSideEncryption="AES256",
                    ExpectedBucketOwner=ACCOUNT_ID, IfNoneMatch="*",
                )
                artifact_entry = state.record("runtime.artifact", {
                    "bucket": BUCKET_NAME, "key": OBJECT_KEY, "sha256": artifact_hash,
                    "source_hash": source_hash, "lock_hash": lock_hash,
                }, lesson="03")
            assert artifact_entry["bucket"] == BUCKET_NAME and artifact_entry["key"] == OBJECT_KEY
            uploaded = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY, ExpectedBucketOwner=ACCOUNT_ID)
            assert uploaded["ServerSideEncryption"] == "AES256"
            assert hashlib.sha256(uploaded["Body"].read()).hexdigest() == artifact_hash
            print({"bucket": BUCKET_NAME, "artifact_key": OBJECT_KEY, "integrity": "VERIFIED"})
            """,
        ),
        *step(
            "Criar a role de execução do servidor MCP",
            "A trust policy permite ao serviço AgentCore assumir esta role "
            "para o nome de Runtime desta execução e nesta conta. A policy "
            "permite ler somente o ZIP e escrever os logs desse Runtime. "
            "STS GetCallerIdentity não exige uma permissão adicional.",
            """
            runtime_trust = {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole", "Condition": {
                    "StringEquals": {"aws:SourceAccount": ACCOUNT_ID},
                    "ArnLike": {"aws:SourceArn": (
                        f"arn:{PARTITION}:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:runtime/{RUNTIME_NAME}-*"
                    )},
                },
            }]}
            role_entry = state.get("runtime.role")
            if role_entry is None:
                created = iam.create_role(
                    RoleName=ROLE_NAME, AssumeRolePolicyDocument=json.dumps(runtime_trust),
                    Tags=[{"Key": key, "Value": value} for key, value in TAGS.items()],
                )["Role"]
                role_entry = state.record(
                    "runtime.role", {"name": created["RoleName"], "arn": created["Arn"]}, lesson="03",
                )
            role = iam.get_role(RoleName=ROLE_NAME)["Role"]
            owned({tag["Key"]: tag["Value"] for tag in role["Tags"]})
            assert role["Arn"] == role_entry["arn"] and role["AssumeRolePolicyDocument"] == runtime_trust
            log_prefix = f"arn:{PARTITION}:logs:{REGION}:{ACCOUNT_ID}:log-group:/aws/bedrock-agentcore/runtimes/{RUNTIME_NAME}-*"
            runtime_policy = {"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Action": "s3:GetObject", "Resource": BUCKET_ARN + "/" + OBJECT_KEY},
                {"Effect": "Allow", "Action": "logs:CreateLogGroup", "Resource": log_prefix},
                {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                 "Resource": log_prefix + ":log-stream:*"},
                {"Effect": "Allow", "Action": "logs:DescribeLogStreams", "Resource": log_prefix},
            ]}
            try:
                existing = iam.get_role_policy(RoleName=ROLE_NAME, PolicyName="Lesson03Runtime")["PolicyDocument"]
            except iam.exceptions.NoSuchEntityException:
                existing = None
            if existing is None:
                iam.put_role_policy(
                    RoleName=ROLE_NAME, PolicyName="Lesson03Runtime",
                    PolicyDocument=json.dumps(runtime_policy),
                )
                # Propagação da role e da policy antes de criar o Runtime.
                time.sleep(10)
            else:
                assert existing == runtime_policy, "RUNTIME_ROLE_POLICY_CHANGED"
            print({"runtime_role": role_entry["arn"], "code_read_scope": BUCKET_ARN + "/" + OBJECT_KEY})
            """,
        ),
        *step(
            "Criar o Runtime MCP usando o ZIP",
            "CreateAgentRuntime recebe o código no S3, a versão Python, a role "
            "e o protocolo MCP. Sem authorizer JWT configurado, a entrada usa "
            "IAM/SigV4. PUBLIC descreve o modo de rede do workload; não torna "
            "a API de invocação anônima. A espera consulta o status da criação.",
            """
            artifact_config = {"codeConfiguration": {
                "code": {"s3": {"bucket": BUCKET_NAME, "prefix": OBJECT_KEY}},
                "runtime": "PYTHON_3_12", "entryPoint": ["main.py"],
            }}
            environment = {
                "WORKSHOP_RUN": state.data["run_id"], "WORKSHOP_ACCOUNT": ACCOUNT_ID,
                "WORKSHOP_ROLE_NAME": ROLE_NAME,
            }
            runtime_entry = state.get("runtime.instance")
            if runtime_entry is None:
                created = control.create_agent_runtime(
                    agentRuntimeName=RUNTIME_NAME, agentRuntimeArtifact=artifact_config,
                    roleArn=role_entry["arn"], networkConfiguration={"networkMode": "PUBLIC"},
                    protocolConfiguration={"serverProtocol": "MCP"},
                    lifecycleConfiguration={"idleRuntimeSessionTimeout": 300, "maxLifetime": 1800},
                    environmentVariables=environment, tags=TAGS,
                    description="Servidor MCP criado na aula 03 do workshop Santander",
                    clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + "-runtime-create")),
                )
                runtime_entry = state.record("runtime.instance", {
                    "id": created["agentRuntimeId"], "arn": created["agentRuntimeArn"],
                    "name": RUNTIME_NAME, "role_arn": role_entry["arn"],
                }, lesson="03")
            current = wait_runtime(runtime_entry["id"])
            owned(control.list_tags_for_resource(resourceArn=runtime_entry["arn"])["tags"])
            assert current["agentRuntimeArn"] == runtime_entry["arn"]
            assert current["roleArn"] == role_entry["arn"]
            assert current["agentRuntimeArtifact"] == artifact_config
            assert current["protocolConfiguration"] == {"serverProtocol": "MCP"}
            assert not current.get("authorizerConfiguration"), "EXPECTED_IAM_AUTHORIZATION"
            assert current["environmentVariables"] == environment
            print({"runtime_id": runtime_entry["id"], "status": current["status"], "authorization": "IAM_SIGV4"})
            """,
        ),
        *step(
            "Verificar que a entrada exige autenticação",
            "Enviamos initialize sem assinatura ao mesmo endpoint que será "
            "invocado pelo SDK. Uma negativa precisa ter status de autenticação "
            "e Request ID da AWS; timeout ou erro 500 não contam como proteção.",
            """
            from urllib.parse import quote
            import httpx

            RUNTIME_URL = (
                f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/"
                + quote(runtime_entry["arn"], safe="") + "/invocations?qualifier=DEFAULT"
            )
            initialize = {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                           "clientInfo": {"name": "santander-runtime", "version": "1"}},
            }
            denied = httpx.post(
                RUNTIME_URL, json=initialize, timeout=30, follow_redirects=False,
                headers={"Accept": "application/json, text/event-stream"},
            )
            assert denied.status_code in {401, 403}, f"RUNTIME_ANONYMOUS: HTTP {denied.status_code}"
            assert denied.headers.get("x-amzn-requestid")
            print({"case": "runtime_anonymous", "http_status": denied.status_code,
                   "request_id": denied.headers["x-amzn-requestid"]})
            """,
        ),
        *step(
            "Invocar MCP com IAM e observar a identidade do workload",
            "Boto3 assina InvokeAgentRuntime com as credenciais do participante. "
            "A ferramenta faz outra chamada, ao STS, usando a role do Runtime. "
            "Comparamos as identidades e guardamos somente Request IDs. "
            "O parser lê JSON ou eventos SSE completos, sem cortar texto até "
            "encontrar uma chave. Encerramos a sessão ao concluir o exercício.",
            """
            def mcp_result(response, request_id):
                raw = response["response"].read().decode()
                if response["contentType"].startswith("text/event-stream"):
                    events = []
                    for block in raw.replace("\\r\\n", "\\n").split("\\n\\n"):
                        lines = [line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")]
                        if lines:
                            events.append(json.loads("\\n".join(lines)))
                    matched = [event for event in events if event.get("id") == request_id]
                    assert len(matched) == 1, "EXPECTED_ONE_MCP_RESPONSE"
                    message = matched[0]
                else:
                    message = json.loads(raw)
                assert message["id"] == request_id and "error" not in message, "MCP_REQUEST_FAILED"
                return message["result"]

            session_id = str(uuid.uuid4())
            requests = [
                initialize,
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "workload_identity", "arguments": {}}},
            ]
            for request in requests:
                response = runtime_api.invoke_agent_runtime(
                    agentRuntimeArn=runtime_entry["arn"], runtimeSessionId=session_id,
                    qualifier="DEFAULT", contentType="application/json",
                    accept="application/json, text/event-stream",
                    payload=json.dumps(request).encode(),
                )
                result = mcp_result(response, request["id"])
                native_id = response["ResponseMetadata"]["RequestId"]
                assert native_id
                if request["method"] == "tools/list":
                    assert "workload_identity" in [tool["name"] for tool in result["tools"]]
                if request["method"] == "tools/call":
                    assert not result.get("isError"), "RUNTIME_TOOL_FAILED"
                    data = result.get("structuredContent")
                    if data is None:
                        texts = [item["text"] for item in result["content"] if item["type"] == "text"]
                        assert len(texts) == 1
                        data = json.loads(texts[0])
                    assert data["execution"] == "AWS_AGENTCORE_RUNTIME"
                    assert data["run_id"] == state.data["run_id"] and data["account"] == ACCOUNT_ID
                    assert (":assumed-role/" + ROLE_NAME + "/") in data["principal"]
                    assert data["principal"] != identity["Arn"] and data["sts_request_id"]
                    print({"case": "runtime_workload_identity", "status": "PASS",
                           "runtime_request_id": native_id, "result": data})
            try:
                stopped = runtime_api.stop_runtime_session(
                    agentRuntimeArn=runtime_entry["arn"], runtimeSessionId=session_id, qualifier="DEFAULT",
                )
                print({"runtime_session": "STOPPED", "request_id": stopped["ResponseMetadata"]["RequestId"]})
            except runtime_api.exceptions.ResourceNotFoundException as error:
                # O serviço pode ter encerrado a sessão de um servidor stateless.
                # A resposta comprova ausência, não o sucesso de uma nova exclusão.
                print({"runtime_session": "ALREADY_TERMINATED_OR_NOT_FOUND",
                       "request_id": error.response["ResponseMetadata"]["RequestId"]})
            """,
        ),
        *step(
            "Consultar os logs criados pelo Runtime",
            "O serviço cria o grupo de logs durante a execução. Consultamos "
            "o nome exato e definimos sete dias de retenção; não tentamos criar "
            "novamente um grupo que o serviço já criou. Os logs entram no "
            "registro para a limpeza da aula 99.",
            """
            log_name = "/aws/bedrock-agentcore/runtimes/" + runtime_entry["id"] + "-DEFAULT"
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                page = logs.describe_log_groups(logGroupNamePrefix=log_name)
                matches = [group for group in page.get("logGroups", []) if group["logGroupName"] == log_name]
                if matches:
                    break
                time.sleep(5)
            else:
                raise TimeoutError("RUNTIME_LOG_GROUP_NOT_FOUND")
            state.record("runtime.logs", {"name": log_name, "runtime_id": runtime_entry["id"]}, lesson="03")
            logs.put_retention_policy(logGroupName=log_name, retentionInDays=7)
            print({"log_group": log_name, "retention_days": 7})
            """,
        ),
        md("""
        ### O que comprovamos

        O código e as dependências foram enviados ao S3 e executados no Runtime.
        IAM/SigV4 protege a invocação. A ferramenta consultou STS usando a
        identidade do workload na AWS, distinta da identidade do participante.

        No Entra ID, a identidade humana continua vindo do provedor. Para que
        um workload use uma API em nome da pessoa, é necessário configurar o
        fluxo de delegação e suas permissões; a role IAM do Runtime por si só
        não realiza uma troca de token Microsoft.

        **Aceite:** Runtime READY, chamada anônima negada e ferramenta MCP
        retornando a identidade esperada e Request IDs de Runtime e STS.
        A sessão foi encerrada, mas o Runtime e o bucket permanecem para as
        próximas aulas. A limpeza deve remover o Runtime antes do artefato.
        """),
    ]
