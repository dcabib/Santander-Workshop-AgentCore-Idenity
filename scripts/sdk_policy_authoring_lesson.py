"""Autoria assistida: geração AWS, revisão e política somente em observação."""

from scripts.aws_notebook_lessons import md, step
from scripts.sdk_policy_lesson import policy


def authoring():
    # Reutilizamos células visíveis, não um helper que provisione serviços.
    policy_cells = policy()
    dependencies = next(c for c in policy_cells if c.cell_type == "code" and "def owned(tags)" in c.source)
    authentication = next(c for c in policy_cells if c.cell_type == "code" and "jwks = jwt.PyJWKClient" in c.source)
    verification = next(c for c in policy_cells if c.cell_type == "code" and "def mcp_message" in c.source)
    return [
        md("""
        ### Da intenção em linguagem natural a uma política revisável

        `Intenção → geração no AgentCore Policy → Cedar e findings → testes → LOG_ONLY`

        **Pré-requisito:** aula 04 concluída, com engine ACTIVE, Gateway ENFORCE
        e política manual ACTIVE. Esta aula usa **uma conta AWS**. A geração
        é feita pelo serviço AgentCore Policy; não executamos um modelo no
        notebook. A sessão precisa de `StartPolicyGeneration`, operações de
        consulta, `InvokeGateway` para o contexto da ferramenta e `CreatePolicy`.

        O serviço gera um rascunho. Revisão de código, validação contra o schema
        e testes têm papéis diferentes. A nova política será criada em
        **LOG_ONLY**, para observação; a regra manual da aula 04 continua
        decidindo as chamadas. A aula não promove automaticamente texto gerado
        para ACTIVE.

        Os assets gerados expiram após sete dias. Uma política criada a partir
        deles permanece até sua exclusão. Usaremos o schema do target real,
        criado na aula 01, para dar contexto à geração.
        """),
        md("### Conferir as dependências construídas nas aulas anteriores"),
        dependencies,
        *step(
            "Conferir a política que continua protegendo a ferramenta",
            "Antes de gerar algo novo, lemos o engine e a regra manual. "
            "O modo ENFORCE do Gateway e o modo ACTIVE da política não "
            "serão alterados por esta aula.",
            """
            engine_entry = state.require("policy.engine", lesson="04")
            active_entry = state.require("policy.customer", lesson="04")
            engine = control.get_policy_engine(policyEngineId=engine_entry["id"])
            assert engine["policyEngineArn"] == engine_entry["arn"]
            assert engine["status"] == "ACTIVE"
            owned(control.list_tags_for_resource(resourceArn=engine_entry["arn"])["tags"])
            assert gateway["policyEngineConfiguration"] == {
                "arn": engine_entry["arn"], "mode": "ENFORCE",
            }
            assert active_entry["engine_id"] == engine_entry["id"]
            active = control.get_policy(policyEngineId=engine_entry["id"], policyId=active_entry["id"])
            assert active["policyArn"] == active_entry["arn"]
            assert active["status"] == "ACTIVE" and active["enforcementMode"] == "ACTIVE"
            assert hashlib.sha256(
                active["definition"]["cedar"]["statement"].encode(),
            ).hexdigest() == active_entry["statement_sha256"]
            print({"engine_id": engine_entry["id"], "existing_policy": active_entry["id"]})
            """,
        ),
        *step(
            "Escrever a intenção e iniciar a geração na AWS",
            "O texto usa os IDs efetivamente criados, o nome MCP completo "
            "e o parâmetro da ferramenta. Não contém senha, token ou dados "
            "de clientes reais. StartPolicyGeneration recebe também o ARN "
            "do Gateway, que fornece o contexto do schema.",
            """
            INTENT = (
                "Generate a Cedar permit policy for exactly this authorization: "
                f"principal must be AgentCore::OAuthUser::{json.dumps(analyst_entry['sub'])}; "
                f"action must be AgentCore::Action::{json.dumps(TOOL_NAME)}; "
                f"resource must be AgentCore::Gateway::{json.dumps(gateway_entry['arn'])}. "
                "The principal must have OAuth tags iss, aud and token_use. "
                f"principal.getTag(\\\"iss\\\") must equal {json.dumps(ISSUER)}, "
                f"principal.getTag(\\\"aud\\\") must equal {json.dumps(CLIENT_ID)}, "
                "and principal.getTag(\\\"token_use\\\") must equal \\\"id\\\". "
                "context.input.customer_id must equal \\\"cliente-001\\\". "
                "Do not grant access to other people, tools, gateways, issuers, audiences or customers."
            )
            print(INTENT)
            intent_sha256 = hashlib.sha256(INTENT.encode()).hexdigest()
            generation_entry = state.get("policy.generation")
            if generation_entry is None:
                generated = control.start_policy_generation(
                    policyEngineId=engine_entry["id"],
                    name=NAME_PREFIX.replace("-", "_") + "_draft",
                    resource={"arn": gateway_entry["arn"]}, content={"rawText": INTENT},
                    clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + ":policy-generation")),
                )
                generation_entry = state.record("policy.generation", {
                    "id": generated["policyGenerationId"], "arn": generated["policyGenerationArn"],
                    "engine_id": engine_entry["id"], "gateway_arn": gateway_entry["arn"],
                    "intent_sha256": intent_sha256,
                }, lesson="05")
            assert generation_entry["engine_id"] == engine_entry["id"]
            assert generation_entry["gateway_arn"] == gateway_entry["arn"]
            assert generation_entry["intent_sha256"] == intent_sha256, "GENERATION_INTENT_CHANGED"
            deadline = time.monotonic() + 300
            while True:
                generation = control.get_policy_generation(
                    policyEngineId=engine_entry["id"], policyGenerationId=generation_entry["id"],
                )
                assert generation["policyGenerationArn"] == generation_entry["arn"]
                assert generation["resource"] == {"arn": gateway_entry["arn"]}
                if generation["status"] == "GENERATED":
                    break
                if generation["status"] != "GENERATING":
                    raise RuntimeError("POLICY_GENERATION_FAILED: " + str(generation["statusReasons"]))
                if time.monotonic() >= deadline:
                    raise TimeoutError("POLICY_GENERATION_TIMEOUT")
                time.sleep(5)
            print({"generation_id": generation_entry["id"], "status": generation["status"]})
            """,
        ),
        *step(
            "Ler o Cedar gerado e examinar os findings",
            "ListPolicyGenerationAssets retorna o código, a intenção associada "
            "e os findings. Exibimos todos os assets. Este exercício espera "
            "uma única regra sem findings. A API pode usar definition.cedar "
            "ou definition.policy; este último também admite Dogwood. "
            "Só prosseguimos se o texto puder ser analisado como Cedar "
            "e passar os contraexemplos da próxima célula. Uma extensão "
            "incompatível exige revisão; não usamos IGNORE_ALL_FINDINGS.",
            """
            assets = []
            page = control.list_policy_generation_assets(
                policyEngineId=engine_entry["id"], policyGenerationId=generation_entry["id"],
            )
            while True:
                assets.extend(page.get("policyGenerationAssets", []))
                if not page.get("nextToken"):
                    break
                page = control.list_policy_generation_assets(
                    policyEngineId=engine_entry["id"], policyGenerationId=generation_entry["id"],
                    nextToken=page["nextToken"],
                )
            for asset in assets:
                print(json.dumps({
                    "asset_id": asset["policyGenerationAssetId"],
                    "intent_fragment": asset["rawTextFragment"],
                    "definition": asset.get("definition"), "findings": asset["findings"],
                }, indent=2))
            assert len(assets) == 1, "REVIEW_REQUIRED: expected one generated rule"
            asset = assets[0]
            assert not asset["findings"], "REVIEW_REQUIRED: policy generation findings"
            definition = asset.get("definition", {})
            assert set(definition) in ({"cedar"}, {"policy"}), (
                "REVIEW_REQUIRED: expected a single policy statement"
            )
            definition_type = next(iter(definition))
            GENERATED_CEDAR = definition[definition_type]["statement"]
            assert GENERATED_CEDAR.strip(), "EMPTY_GENERATED_POLICY"
            print({"response_definition_type": definition_type, "next_step": "PARSE_AND_TEST_AS_CEDAR"})
            """,
        ),
        *step(
            "Verificar a intenção com o avaliador Cedar",
            "Estes testes de linguagem não chamam a ferramenta nem substituem "
            "o teste AWS. Conferem exemplos permitidos e proibidos, incluindo "
            "claims ausentes, outra ferramenta e outro Gateway. Uma matriz "
            "finita não prova equivalência para todos os pedidos; por isso "
            "o rascunho continuará em observação.",
            """
            import cedarpy

            parsed = cedarpy.PolicySet.from_str(GENERATED_CEDAR)
            cases = [
                ("allowed", {}, True),
                ("other_person", {"person": auditor_entry["sub"]}, False),
                ("other_customer", {"customer": "cliente-002"}, False),
                ("other_issuer", {"iss": "https://untrusted.invalid"}, False),
                ("other_audience", {"aud": "other-app"}, False),
                ("wrong_token_use", {"token_use": "access"}, False),
                ("missing_issuer", {"iss": None}, False),
                ("missing_audience", {"aud": None}, False),
                ("missing_token_use", {"token_use": None}, False),
                ("other_tool", {"tool": "other___tool"}, False),
                ("other_gateway", {"gateway": gateway_entry["arn"] + "-other"}, False),
            ]
            for case, changes, expected in cases:
                person = changes.get("person", analyst_entry["sub"])
                principal = {"type": "AgentCore::OAuthUser", "id": person}
                tags = {"iss": ISSUER, "aud": CLIENT_ID, "token_use": "id"}
                tags.update({key: value for key, value in changes.items() if key in tags})
                request = {
                    "principal": principal,
                    "action": {"type": "AgentCore::Action", "id": changes.get("tool", TOOL_NAME)},
                    "resource": {
                        "type": "AgentCore::Gateway",
                        "id": changes.get("gateway", gateway_entry["arn"]),
                    },
                    "context": {"input": {"customer_id": changes.get("customer", "cliente-001")}},
                }
                decision = cedarpy.is_authorized(request, parsed, [{
                    "uid": principal, "attrs": {}, "parents": [],
                    "tags": {key: value for key, value in tags.items() if value is not None},
                }])
                assert not decision.diagnostics.errors, (
                    "GENERATED_POLICY_EVALUATION_ERRORS", case, decision.diagnostics.errors,
                )
                assert decision.allowed == expected, "GENERATED_POLICY_INTENT_MISMATCH: " + case
                print({"cedar_case": case, "allowed": decision.allowed, "execution": "LANGUAGE_VALIDATION"})
            """,
        ),
        *step(
            "Criar a política gerada em LOG_ONLY",
            "A validação estrita do serviço continua habilitada. LOG_ONLY "
            "permite observar esta política sem fazê-la conceder acesso. "
            "A política manual permanece ACTIVE e o Gateway ENFORCE. "
            "Promover o rascunho exige uma decisão posterior de revisão.",
            """
            draft_hash = hashlib.sha256(GENERATED_CEDAR.encode()).hexdigest()
            draft_entry = state.get("policy.draft")
            if draft_entry is None:
                created = control.create_policy(
                    policyEngineId=engine_entry["id"], name="ReviewAnalystCustomer001",
                    description="Rascunho gerado pela AWS; apenas observacao, sem aprovacao automatica",
                    definition={"cedar": {"statement": GENERATED_CEDAR}},
                    validationMode="FAIL_ON_ANY_FINDINGS", enforcementMode="LOG_ONLY",
                    clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + ":draft-policy")),
                )
                draft_entry = state.record("policy.draft", {
                    "id": created["policyId"], "arn": created["policyArn"],
                    "engine_id": engine_entry["id"], "statement_sha256": draft_hash,
                    "generation_id": generation_entry["id"],
                    "asset_id": asset["policyGenerationAssetId"],
                }, lesson="05")
            assert draft_entry["engine_id"] == engine_entry["id"]
            assert draft_entry["generation_id"] == generation_entry["id"]
            assert draft_entry["asset_id"] == asset["policyGenerationAssetId"]
            assert draft_entry["statement_sha256"] == draft_hash
            draft = wait_ready(
                lambda: control.get_policy(
                    policyEngineId=engine_entry["id"], policyId=draft_entry["id"],
                ), "ACTIVE",
            )
            assert draft["policyArn"] == draft_entry["arn"]
            assert draft["definition"] == {"cedar": {"statement": GENERATED_CEDAR}}
            assert draft["enforcementMode"] == "LOG_ONLY"
            current_gateway = control.get_gateway(gatewayIdentifier=gateway_entry["id"])
            assert current_gateway["policyEngineConfiguration"] == {
                "arn": engine_entry["arn"], "mode": "ENFORCE",
            }
            current_active = control.get_policy(
                policyEngineId=engine_entry["id"], policyId=active_entry["id"],
            )
            assert current_active["enforcementMode"] == "ACTIVE"
            assert current_active["definition"] == active["definition"]
            print({
                "draft_policy_id": draft_entry["id"], "enforcement_mode": draft["enforcementMode"],
                "automatically_approved": False,
            })
            """,
        ),
        md("""
        ### Repetir as chamadas reais após adicionar o rascunho

        Autenticamos novamente as duas pessoas e repetimos o ALLOW e os
        dois DENY da aula 04. Isso verifica que as chamadas continuam
        protegidas pela política ACTIVE. Esses resultados não comprovam
        decisões do rascunho LOG_ONLY; para estudá-las, configure e examine
        os logs de avaliação de Policy.
        """),
        authentication,
        verification,
        md("""
        ### Revisão antes de promover uma política

        Compare intenção e Cedar: principal, action, resource, claims e
        parâmetros. Examine findings e casos ausentes na matriz. Uma
        política gerada pode estar sintaticamente correta e ainda conceder
        mais acesso do que o necessário.

        Nesta aula criamos o rascunho na AWS em LOG_ONLY e mantivemos a
        proteção anterior. O aceite completo exige geração concluída,
        assets revisáveis, testes da linguagem e chamadas reais protegidas.
        Não há promoção automática a ACTIVE.

        Entra ID usa o mesmo processo de autoria e revisão, com issuer,
        audiência e claims do seu tenant/aplicação. Não substitua apenas
        o nome do provedor: revise o contrato de identidade da política.

        A aula 99 remove também a política em observação. Assets de geração
        são temporários no serviço e expiram após sete dias; não existe
        uma chamada DeletePolicyGeneration no SDK usado nesta jornada.
        """),
    ]
