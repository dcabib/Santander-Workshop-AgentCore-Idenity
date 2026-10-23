"""Gera a trilha 09 a partir do código testável do laboratório Terraform."""

import base64
from pathlib import Path
from textwrap import dedent

import nbformat as nb

try:
    from .notebook_learning import learning_cell
except ImportError:
    from notebook_learning import learning_cell

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "notebooks/09_terraform_runtime_gateway_identity.ipynb"


def markdown(text):
    return nb.v4.new_markdown_cell(dedent(text).strip())


def code(text, *, tags=None):
    return nb.v4.new_code_cell(
        dedent(text).strip(), metadata={"tags": tags or []}
    )


def build_notebook():
    cells = [
        markdown("""
        # 09 · Deploy com Terraform: AgentCore Runtime, Gateway e Identity

        **Workshop prático em uma conta AWS · Python · dados bancários sintéticos**

        Ao concluir este laboratório, você terá entendido e poderá implantar um agente
        no **AgentCore Runtime**, conectá-lo a ferramentas pelo **AgentCore Gateway**
        e obter credenciais de saída com **AgentCore Identity**. O Terraform gerencia
        todos os recursos, inclusive o ZIP publicado no S3.

        A solução consulta os clientes fictícios C001 e C002. Primeiro validamos o
        caminho completo de forma determinística. Depois um modelo Bedrock usa a
        mesma ferramenta para responder em linguagem natural.

        **Duração sugerida:** 90–120 minutos. **Conhecimentos prévios:** Python básico,
        IAM e noções de Terraform. **Resultado de aprendizagem:** explicar cada salto
        de autenticação, revisar um plano, implantar, comprovar recusas de acesso e
        remover os recursos pelo mesmo IaC.

        O notebook vem com chamadas AWS desativadas. **Run All** executa a parte local;
        isso não comprova deploy. A seção de aceitação só produz `AWS_LIVE/PASS` depois
        das chamadas reais. Consulte também [o registro de validação](../docs/validacao.md#laboratório-09).

        **Solução validada na AWS em 23/10/2026, em `us-east-1`:** nove testes de
        aceitação passaram, incluindo recusas de acesso, consulta pelo Runtime e
        resposta do modelo Bedrock após usar a ferramenta. Um novo plano Terraform
        terminou sem mudanças. Os resultados são uma referência da implantação
        testada; execute os testes novamente para comprovar o seu ambiente.
        """),
        markdown("""
        ## 1. Arquitetura e percurso de uma chamada

        ![Arquitetura do workshop Terraform](attachment:arquitetura.svg)

        1. O notebook assina `InvokeAgentRuntime` com as credenciais temporárias do perfil AWS.
        2. O Runtime assume sua role e solicita ao Identity um **workload access token** (WAT).
        3. O Identity usa o cliente OAuth2 Cognito registrado no credential provider
           para obter um **access token M2M**.
        4. O Runtime usa esse JWT para iniciar uma sessão MCP com o Gateway.
        5. O Gateway verifica assinatura, emissor, cliente e scope; sua role invoca a Lambda.
        6. A Lambda retorna dados sintéticos e IDs de execução. O resultado volta ao notebook.

        O segredo Cognito não é entregue ao agente como variável de ambiente. O código
        pede um token ao Identity, e os tokens não são exibidos nas respostas ou evidências.
        """),
        markdown("""
        ### Três credenciais diferentes — três responsabilidades

        | Credencial | Quem usa | Destino | O que demonstra |
        |---|---|---|---|
        | IAM/SigV4 | Operador e role do Runtime | APIs AWS | Permissão para invocar Runtime e usar Identity |
        | WAT | Código do Runtime | AgentCore Identity | Qual workload está solicitando a credencial |
        | Access token OAuth2 | Runtime | Gateway | Qual aplicação Cognito pode usar as ferramentas |

        **M2M não é OBO.** `client_credentials` identifica a aplicação, não um usuário
        final. `customer_id="C001"` seleciona uma fixture; não autoriza acesso a dados
        reais por usuário. A trilha 14 do repositório trata de delegação OBO.

        O Runtime cria uma identidade interna gerenciada pelo serviço. Este laboratório
        declara adicionalmente um `aws_bedrockagentcore_workload_identity` para tornar
        a chamada manual `GetWorkloadAccessToken` visível e ensinável. Essa API não deve
        ser usada com uma identidade interna gerenciada pelo Runtime.

        **Discussão:** por que um JWT bem assinado ainda pode precisar ser rejeitado?
        Observe a aplicação `unauthorized` nos testes adiante.
        """),
        markdown("""
        ## 2. Preparar o ambiente

        No terminal, na raiz do repositório:

        ```bash
        uv sync --frozen --extra banking
        ```

        Abra este notebook no VS Code ou Jupyter e selecione `.venv/bin/python`.
        Precisamos de Python 3.12/3.13 e Terraform >=1.11 e <2. O provider AWS está
        fixado em 6.70.0. O kernel usa `uv.lock`; o pacote Linux ARM64 usa o lock com
        hashes em `infra/terraform_agentcore/requirements.lock`.

        A próxima célula encontra a raiz e verifica as bibliotecas. Ela não consulta a AWS.
        """),
        code("""
        import inspect
        import json
        import subprocess
        import sys
        from importlib.metadata import version
        from pathlib import Path
        from types import SimpleNamespace

        from IPython.display import Markdown, display

        ROOT = next(
            p for p in [Path.cwd().resolve(), *Path.cwd().resolve().parents]
            if (p / "infra/terraform_agentcore/versions.tf").is_file()
        )
        INFRA = ROOT / "infra/terraform_agentcore"
        BUILD = ROOT / "build/terraform-agentcore"
        assert (3, 12) <= sys.version_info[:2] < (3, 14)
        print({
            "python": sys.version.split()[0],
            "boto3": version("boto3"),
            "bedrock-agentcore": version("bedrock-agentcore"),
            "mcp": version("mcp"),
        })

        def show_source(relative_path, language="python"):
            source = (ROOT / relative_path).read_text()
            display(Markdown(f"```{language}\\n{source}\\n```"))

        def run_script(script, *arguments):
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / script), *map(str, arguments)],
                cwd=ROOT, check=True,
            )
        """),
        markdown("""
        ### Controles de execução

        Comece com todos os controles em `False`.

        | Controle | Quando ativar |
        |---|---|
        | `RUN_BUILD` | Para montar os ZIPs localmente; baixa dependências fixadas |
        | `RUN_AWS` | Depois de configurar e confirmar o perfil e a conta do laboratório |
        | `RUN_PIPELINE` | Para `init`, `validate` e geração do plano Terraform |
        | `APPLY_CHANGESET` | Depois de revisar o plano, para aplicá-lo |
        | `RUN_AGENT` | Para testar também o modelo Bedrock com tool use |

        O wrapper é o único caminho de deploy. Não usaremos `aws create-*`,
        `boto3.create_*`, uploads manuais ou ajustes no console.
        """),
        code("""
        RUN_BUILD = False
        RUN_AWS = False
        RUN_PIPELINE = False
        APPLY_CHANGESET = False
        RUN_AGENT = False
        CONFIG_PATH = ROOT / "config/local.terraform.json"

        assert not (RUN_PIPELINE or APPLY_CHANGESET or RUN_AGENT) or RUN_AWS
        assert not APPLY_CHANGESET or RUN_PIPELINE
        print({"mode": "AWS_ENABLED" if RUN_AWS else "LOCAL_ONLY",
               "cloud_mutations_enabled": RUN_PIPELINE and APPLY_CHANGESET})
        """),
        markdown("""
        ## 3. Conhecer e testar a ferramenta antes do deploy

        A Lambda recebe os argumentos diretamente no `event`. O Gateway informa o
        nome da ferramenta em `context.client_context.custom["bedrockAgentCoreToolName"]`.
        O nome público tem o prefixo do target: **`banking___get_customer_profile`**.

        Nossa função aceita somente `customer_id`, rejeita clientes inexistentes e
        não oferece operações de escrita. Valores monetários são strings decimais,
        evitando erros de arredondamento de ponto flutuante.
        """),
        code("""
        from santander_demo.terraform_lab.backend import TOOL_NAME, customer_profile, handler

        show_source("src/santander_demo/terraform_lab/backend.py")
        local_profiles = [customer_profile(customer) for customer in ("C001", "C002")]
        print(json.dumps({"mode": "LOCAL_FUNCTION_TEST", "profiles": local_profiles},
                         ensure_ascii=False, indent=2))
        assert local_profiles[0]["balance_brl"] == "1250.00"
        assert local_profiles[1]["balance_brl"] == "8700.00"
        """),
        markdown("""
        ### Exercitar o contrato Gateway → Lambda

        Vamos construir um contexto fictício com o mesmo formato da AWS. O objetivo
        é testar o handler, não afirmar que uma Lambda foi invocada na nuvem.
        Também comprovamos que C999 é rejeitado.
        """),
        code("""
        local_context = SimpleNamespace(
            aws_request_id="LOCAL_LAMBDA_REQUEST",
            client_context=SimpleNamespace(custom={
                "bedrockAgentCoreToolName": TOOL_NAME,
                "bedrockAgentCoreAwsRequestId": "LOCAL_GATEWAY_REQUEST",
            }),
        )
        local_result = handler({"customer_id": "C001"}, local_context)
        assert local_result["execution"]["tool"] == TOOL_NAME
        try:
            handler({"customer_id": "C999"}, local_context)
        except ValueError as error:
            print({"negative_test": "PASS", "reason": str(error)})
        else:
            raise AssertionError("Um cliente inexistente não pode produzir sucesso")
        """),
        markdown("""
        ## 4. Como o Runtime usa Identity e MCP

        A função abaixo faz duas chamadas de **data plane**, não cria recursos:
        primeiro obtém o WAT para o workload já provisionado; depois pede ao Identity
        um access token `M2M` com o scope `tools.read`.

        O agente não conhece o client secret. A role tem permissão para usar esse
        provider e seu segredo gerenciado. Um retorno sem token é erro: não há
        fallback para credenciais alternativas ou dados locais.
        """),
        code("""
        from santander_demo.terraform_lab import runtime as runtime_code

        display(Markdown("```python\\n" + inspect.getsource(runtime_code.gateway_access_token) + "\\n```"))
        display(Markdown("```python\\n" + inspect.getsource(runtime_code.connect_gateway) + "\\n```"))
        """),
        markdown("""
        ### Descoberta e chamada de ferramentas

        MCP começa por `initialize`, depois `tools/list` e `tools/call`.
        O cliente trata paginação, recusa catálogo inesperado e verifica o resultado.
        O endereço do Gateway vem do Terraform e é validado antes do envio do bearer.
        Redirecionamentos HTTP permanecem desativados.

        A modalidade determinística torna a aceitação reproduzível. Na modalidade
        `llm`, o modelo escolhe a ferramenta pelo contrato MCP e o código limita
        as chamadas ao cliente solicitado. Em ambos os casos, o resultado vem da AWS.
        """),
        code("""
        display(Markdown("```python\\n" + inspect.getsource(runtime_code.run) + "\\n```"))
        """),
        markdown("""
        ## 5. Ler o Terraform: provider e variáveis

        Em `versions.tf`, fixamos o provider e usamos `allowed_account_ids`.
        Isso evita um apply em outra conta mesmo que o perfil esteja incorreto.
        O wrapper também confere a conta com STS.

        Cada turma deve usar um prefixo e um state próprios. Neste workshop o state
        fica local para simplificar a execução; ele contém segredos Cognito.
        `sensitive` oculta a saída, mas **não criptografa o state**.
        Use o backend remoto aprovado da equipe para colaboração.
        """),
        code("""
        show_source("infra/terraform_agentcore/versions.tf", "hcl")
        show_source("infra/terraform_agentcore/variables.tf", "hcl")
        """),
        markdown("""
        ### Cognito e AgentCore Identity

        O Cognito é o servidor OAuth2. O resource server define `tools.read`.
        Criamos dois clientes confidenciais: `agent` e `unauthorized`. O segundo tem
        token legítimo do mesmo emissor, porém não entra na allowlist do Gateway.

        O credential provider do Identity referencia o cliente `agent`. O domínio
        Cognito é criado antes do provider para publicar os endpoints de OAuth2.
        O fluxo M2M não precisa de usuário, login interativo nem callback de navegador.
        """),
        code("""
        show_source("infra/terraform_agentcore/identity.tf", "hcl")
        """),
        markdown("""
        ### Artefatos e permissões

        O bucket tem bloqueio de acesso público, criptografia, versionamento e política
        de TLS. O recurso `aws_s3_object` publica o ZIP pelo Terraform.
        A chave inclui o SHA-256; o Runtime recebe também o `version_id`.

        As roles têm funções distintas:

        | Role | Permissão de trabalho |
        |---|---|
        | Runtime | Ler seu artefato, obter credencial pelo Identity, gravar logs e chamar o modelo configurado |
        | Gateway | Invocar somente a Lambda da ferramenta |
        | Lambda | Gravar seus logs |

        Nenhuma role da aplicação recebe `AdministratorAccess`.
        """),
        code("""
        show_source("infra/terraform_agentcore/storage.tf", "hcl")
        show_source("infra/terraform_agentcore/iam.tf", "hcl")
        """),
        markdown("""
        ### Runtime, Gateway, target e logs

        O Runtime usa **deploy direto de código**, Python 3.12 e dependências Linux ARM64,
        dispensando Docker/ECR/CodeBuild neste laboratório.

        A ausência de `authorizer_configuration` no Runtime mantém a entrada padrão
        **AWS_IAM**. `network_mode="PUBLIC"` é configuração de saída de rede, não
        autorização anônima. O Gateway usa `CUSTOM_JWT`, cliente permitido e scope.

        O target transforma a função Lambda em ferramenta MCP. `depends_on` também
        expressa dependências de permissões que nem sempre aparecem por referências
        entre atributos. Logs têm retenção e lifecycle de sessão limita o tempo ocioso.
        """),
        code("""
        show_source("infra/terraform_agentcore/main.tf", "hcl")
        show_source("infra/terraform_agentcore/outputs.tf", "hcl")
        """),
        markdown("""
        ## 6. Executar os testes locais

        A próxima célula executa testes reais de Python: contrato Lambda, uso do Identity,
        validação do destino do bearer, sessão MCP sobre HTTP em memória e loop de tool use.
        Nenhum recurso AWS é criado ou invocado por esses testes.

        Para rodar toda a suíte do repositório no terminal: `uv run --frozen --extra banking pytest -q`.
        """),
        code("""
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_terraform_lab.py"],
            cwd=ROOT, check=True,
        )
        print({"python_tests": "PASS", "validation_scope": "LOCAL_ONLY"})
        """),
        markdown("""
        ## 7. Construir o pacote Linux ARM64

        Na célula de controles, defina `RUN_BUILD=True`, execute-a e volte a esta etapa.
        O script instala wheels
        ARM64 usando um lock com hashes e gera ZIPs com timestamps fixos.
        Não copie a `.venv` do macOS/Windows: extensões nativas terão arquitetura incorreta.

        Saídas: `build/terraform-agentcore/runtime.zip`, `lambda.zip` e `manifest.json`.
        O build não faz upload. Na primeira execução há downloads de dependências.
        """),
        code("""
        if RUN_BUILD:
            run_script("terraform_build.py")
            build_manifest = json.loads((BUILD / "manifest.json").read_text())
            print(json.dumps(build_manifest, indent=2))
        else:
            print({"build": "NOT_RUN", "next": "Ative RUN_BUILD para gerar os ZIPs"})
        """),
        markdown("""
        ## 8. Selecionar o ambiente AWS

        Copie e edite a configuração, sem colocar access keys ou secrets nela:

        ```bash
        cp config/terraform.example.json config/local.terraform.json
        ```

        Preencha `profile`, `region`, `expected_account_id` e `project_name`.
        Use uma conta de laboratório. São criados Cognito M2M, Runtime, Gateway,
        Identity, Lambda, S3 e logs; esses serviços têm cobrança. A etapa LLM adiciona
        consumo Bedrock. As credenciais de deploy precisam de permissões para esses
        recursos e `iam:PassRole`.

        Depois de configurar, ative `RUN_AWS`. A próxima célula executa apenas STS.
        Não removemos a checagem de conta para resolver erros de credenciais.
        """),
        code("""
        if RUN_AWS:
            assert CONFIG_PATH.is_file(), "Copie e edite config/terraform.example.json"
            run_script("terraform_deploy.py", "preflight", "--config", CONFIG_PATH)
        else:
            print({"aws_preflight": "NOT_RUN"})
        """),
        markdown("""
        ## 9. Inicializar, validar e testar o Terraform sem criar recursos

        Ative `RUN_PIPELINE`, mantendo `APPLY_CHANGESET=False`.
        `init` instala o provider fixado; `validate` confere o schema.
        `terraform test` usa **mock_provider** para verificar o contrato de segurança.
        O `command=apply` dentro do teste aplica somente mocks, sem acesso à AWS.

        O mock não comprova permissões efetivas ou comportamento dos serviços.
        Ele detecta regressões como retirar a allowlist ou tornar artefatos públicos.
        """),
        code("""
        if RUN_PIPELINE:
            assert RUN_AWS
            assert (BUILD / "runtime.zip").is_file() and (BUILD / "lambda.zip").is_file()
            run_script("terraform_deploy.py", "init", "--config", CONFIG_PATH)
            run_script("terraform_deploy.py", "validate", "--config", CONFIG_PATH)
            subprocess.run([
                "terraform", f"-chdir={INFRA}", "test", "-no-color",
                "-var=expected_account_id=123456789012",
                f"-var=runtime_zip={BUILD / 'runtime.zip'}",
                f"-var=lambda_zip={BUILD / 'lambda.zip'}",
            ], cwd=ROOT, check=True)
        else:
            print({"terraform_validation": "NOT_RUN"})
        """),
        markdown("""
        ## 10. Planejar o deploy

        `plan` consulta a AWS, calcula as mudanças e salva `deploy.tfplan`.
        Revise conta, região, recursos a criar/alterar/remover e permissões IAM.
        O wrapper registra hashes dos arquivos e da configuração. Ele recusará aplicar
        esse plano se as entradas mudarem.

        O plano binário contém dados sensíveis, assim como o state. Não publique os
        arquivos de `build/`, `.tfstate`, backups ou a configuração local.
        Esta célula não aplica as mudanças.
        """),
        code("""
        if RUN_PIPELINE:
            run_script("terraform_deploy.py", "plan", "--config", CONFIG_PATH)
        else:
            print({"terraform_plan": "NOT_RUN"})
        """),
        markdown("""
        ## 11. Aplicar o plano revisado

        Ative `APPLY_CHANGESET` somente após revisar o plano da célula anterior.
        O wrapper executa `terraform apply` sobre o plano salvo. O Terraform cria
        os recursos, publica o ZIP e aguarda os serviços. Em um ambiente novo esta
        primeira fase cria 24 recursos; a próxima fase incorpora o grupo de logs
        criado automaticamente pelo Runtime.

        Se houver erro, preserve o state, leia o diagnóstico e corrija os arquivos
        Terraform. Não faça ajustes avulsos no console ou na CLI. Depois gere outro
        plano; o state registra os recursos que já foram criados.
        """),
        code("""
        if APPLY_CHANGESET:
            assert RUN_AWS and RUN_PIPELINE
            run_script("terraform_deploy.py", "apply", "--config", CONFIG_PATH)
        else:
            print({"terraform_apply": "NOT_RUN"})
        """),
        markdown("""
        ### Segunda fase: incorporar o grupo de logs criado pelo serviço

        O AgentCore cria seu log group durante o deploy. O nome inclui o ID gerado
        do Runtime, que ainda não existe no primeiro `plan`. Tentar criar o mesmo
        grupo produz `ResourceAlreadyExistsException`.

        Nosso IaC resolve isso com um bloco **`import` declarativo**, aplicado depois
        que o Runtime existe. O wrapper lê o state e habilita `manage_runtime_logs`
        nessa segunda fase. Revise o plano: ele deve importar o grupo e configurar
        retenção/tags, sem recriar o Runtime. Não há `terraform import` avulso nem
        alterações manuais no CloudWatch.
        """),
        code("""
        if RUN_PIPELINE:
            run_script("terraform_deploy.py", "plan", "--config", CONFIG_PATH)
        else:
            print({"runtime_logs_plan": "NOT_RUN"})
        """),
        markdown("""
        ### Aplicar a gestão de logs

        Execute depois de revisar o segundo plano. O mesmo controle `APPLY_CHANGESET`
        autoriza esta fase. Agora o grupo de logs pertence ao state e participa
        do `terraform destroy`. Em ambientes já completos, este plano não terá mudanças.
        """),
        code("""
        if APPLY_CHANGESET:
            assert RUN_AWS and RUN_PIPELINE
            run_script("terraform_deploy.py", "apply", "--config", CONFIG_PATH)
        else:
            print({"runtime_logs_apply": "NOT_RUN"})
        """),
        markdown("""
        ## 12. Inspecionar os outputs

        O output `workshop` é o contrato entre Terraform e os clientes Python.
        Ele contém ARNs, nomes, URLs e hashes, sem tokens ou client secrets.
        Confirme `runtime_logs_managed=true` após concluir as duas fases.
        Não use `terraform show -json` na tela do workshop: ele pode expor segredos do state.

        A execução pressupõe um deploy concluído. Se você já implantou pelo terminal,
        basta ativar `RUN_AWS`; não é necessário reaplicar o ambiente.
        """),
        code("""
        if RUN_AWS:
            command = [
                sys.executable, str(ROOT / "scripts/terraform_deploy.py"),
                "outputs", "--config", str(CONFIG_PATH),
            ]
            subprocess.run(command, cwd=ROOT, check=True)
        else:
            print({"terraform_outputs": "NOT_RUN"})
        """),
        markdown("""
        ## 13. Provar autenticação, autorização e funcionamento ponta a ponta

        O verificador executa a matriz abaixo. Uma única falha interrompe o teste;
        não transformamos erros em respostas simuladas.

        | Caso | Resultado obrigatório |
        |---|---|
        | Runtime sem assinatura IAM | HTTP 401/403 identificável como recusa do serviço |
        | Gateway sem token | HTTP 401/403 |
        | Gateway com token inválido | HTTP 401/403 |
        | Gateway com JWT válido de `unauthorized` | HTTP 401/403 |
        | Identity → Gateway | Inicialização MCP e catálogo esperado |
        | Ferramenta consultando C999 | Erro, sem perfil retornado; causa ainda não comprovada |
        | Runtime consultando C001 | Saldo sintético 1250.00 e IDs de execução |
        | Runtime consultando C002 | Saldo sintético 8700.00 e IDs de execução |

        O teste de outro cliente mostra a diferença entre autenticação e autorização.
        Para montar esse controle negativo, o verificador lê em memória o segredo
        daquele cliente Cognito. Essa leitura é exclusiva do teste; o Runtime usa Identity.

        **Limite do caso C999:** o Gateway pode devolver
        `An internal error occurred. Please retry later.`. `isError=True`
        comprova apenas uma resposta de erro; não distingue cliente inexistente,
        falha no backend ou recusa de acesso. O relatório registra
        `scope=ERROR_WITHOUT_PROFILE` e `cause=NOT_PROVEN`. Esse caso não entra
        como prova de bloqueio por permissão nem de uma mensagem de negócio específica.

        O relatório fica em `evidence/terraform-agentcore-live.json`. Depois do
        preflight e da leitura dos outputs, o verificador registra `RUNNING`;
        uma falha nos casos registra `FAIL`. Somente todos os casos aprovados
        produzem `PASS`, com o SHA-256 do pacote testado. Assim, uma falha durante
        os testes não deixa o sucesso anterior parecer o resultado desta execução.
        """),
        code("""
        if RUN_AWS:
            run_script("terraform_check.py", "--config", CONFIG_PATH)
            live_report = json.loads((ROOT / "evidence/terraform-agentcore-live.json").read_text())
            assert live_report["status"] == "PASS" and live_report["mode"] == "AWS_LIVE"
            print({name: result["status"] for name, result in live_report["checks"].items()})
        else:
            print({"acceptance": "NOT_RUN", "reason": "Modo local não comprova deploy AWS"})
        """),
        markdown("""
        ## 14. Executar o agente com LLM e tool use

        Depois de aprovar a integração, ative `RUN_AGENT`. O modelo usa Bedrock Converse
        e recebe o schema descoberto pelo MCP. A implementação admite até quatro rodadas,
        rejeita ferramentas desconhecidas e impede mudar o cliente da solicitação.
        Uma resposta sem consulta à ferramenta não é aceita como prova.

        O modelo padrão é regional (`amazon.nova-lite-v1:0`). Ele precisa estar disponível
        e autorizado na região selecionada. Se escolher outro modelo, altere a configuração
        e faça novo plan/apply para atualizar a role e a variável do Runtime.
        Não acrescente permissões genéricas para contornar um erro.
        """),
        code("""
        if RUN_AGENT:
            assert RUN_AWS
            run_script("terraform_check.py", "--config", CONFIG_PATH, "--llm")
            live_report = json.loads((ROOT / "evidence/terraform-agentcore-live.json").read_text())
            assert live_report["llm"] == "PASS"
            print(live_report["checks"]["runtime_llm"]["result"]["answer"])
        else:
            print({"llm_test": "NOT_RUN"})
        """),
        markdown("""
        ## 15. Verificar idempotência e observar a execução

        Após o apply e os testes, um novo plano deve terminar com **No changes**.
        O comando `drift` usa `-detailed-exitcode`: 0 significa nenhuma mudança,
        2 indica diferença que deve ser revisada.

        Para investigar uma falha, consulte no CloudWatch os grupos
        `runtime_log_group` e `lambda_log_group` do output. O backend registra o
        request ID do Gateway e o da Lambda. O Runtime registra o modo e a ferramenta.
        As evidências não constituem tracing distribuído completo, mas permitem
        correlacionar a execução da ferramenta.
        """),
        code("""
        if RUN_AWS:
            run_script("terraform_deploy.py", "drift", "--config", CONFIG_PATH)
        else:
            print({"drift_check": "NOT_RUN"})
        """),
        markdown("""
        ## 16. Exercícios para a turma

        1. **Explique a recusa:** por que o token de `unauthorized` é válido, mas a
           ferramenta não pode ser chamada? Localize o campo Terraform responsável.
        2. **Mudança reproduzível:** altere o saldo sintético de C002, ajuste a asserção,
           rode testes, build, plan e apply. Observe a chave S3 e a versão do Runtime.
        3. **Nova ferramenta:** adicione uma consulta sintética somente de leitura.
           Atualize schema, allowlist, handler e testes. Não basta alterar só o prompt.
        4. **Debate de produção:** o que muda para dados reais? Discuta autenticação
           de usuário, autorização por recurso, OBO, backend remoto e observabilidade.

        Antes de seguir, explique: **quem autentica o operador, quem obtém a credencial
        de saída e quem autoriza a aplicação a chamar a ferramenta?**
        """),
        markdown("""
        ## 17. Diagnóstico sem criar drift

        | Falha | Próximo passo |
        |---|---|
        | Conta errada ou sessão expirada | Renove o login do perfil e confira STS |
        | `AccessDenied` no Terraform | Identifique a operação/role e obtenha a permissão necessária |
        | Token Cognito recusado | Confira domínio, client ID e scope no Terraform |
        | Identity sem token | Confira workload explícito, provider e permissão do segredo |
        | Catálogo MCP inesperado | Confira target, schema e nome `banking___get_customer_profile` |
        | Erro de import no Runtime | Refaça o build Linux ARM64 com o lock correto |
        | Erro de modelo | Confira disponibilidade regional e ARN permitido |
        | Alteração não aparece | Refaça build e gere novo plano; não atualize Lambda/Runtime manualmente |

        As credenciais ficam somente em memória durante as chamadas. Não cole tokens
        em relatórios, notebooks executados ou tickets. Preserve o erro de status,
        horário e IDs necessários ao diagnóstico.
        """),
        markdown("""
        ## Limpeza — remover a infraestrutura pelo Terraform

        Os recursos desta trilha pertencem ao seu state Terraform, não aos stacks
        CloudFormation das outras trilhas. O Terraform calcula a ordem de destruição.

        Primeiro ative apenas `CLEANUP_PLAN` e revise o plano. Em seguida ative
        `CLEANUP_EXECUTE` para aplicar **o plano de destruição salvo**.
        O bucket é exclusivo de artefatos e usa `force_destroy=true`: suas versões
        também são removidas. Não guarde dados reais nele.

        Não apague o state antes do destroy. Se ocorrer erro, corrija pelo IaC;
        não desabilite proteções nem exclua recursos manualmente.
        """),
        code("""
        CLEANUP_PLAN = False
        CLEANUP_EXECUTE = False

        if CLEANUP_PLAN:
            assert RUN_AWS
            run_script("terraform_deploy.py", "plan-destroy", "--config", CONFIG_PATH)
        if CLEANUP_EXECUTE:
            assert RUN_AWS
            run_script("terraform_deploy.py", "destroy", "--config", CONFIG_PATH)
            print({"cloud_cleanup": "TERRAFORM_DESTROY_COMPLETE"})
        else:
            print({"cloud_cleanup": "NOT_RUN"})
        """, tags=["cleanup_cloud"]),
        markdown("""
        ### Limpeza — encerrar a sessão local

        A próxima célula remove referências às variáveis de dados e configuração
        deste exercício e preserva código, state e evidências. Os context managers
        já encerraram as conexões MCP/HTTP. Isso não revoga tokens nem apaga todas
        as cópias da memória: limpe as saídas e encerre o kernel após a apresentação.
        """),
        code("""
        _names = [
            "local_profiles", "local_context", "local_result", "live_report",
            "build_manifest", "command", "CONFIG_PATH", "RUN_BUILD", "RUN_AWS",
            "RUN_PIPELINE", "APPLY_CHANGESET", "RUN_AGENT", "CLEANUP_PLAN",
            "CLEANUP_EXECUTE",
        ]
        for _name in _names:
            globals().pop(_name, None)
        assert not any(name in globals() for name in _names)
        print({"cleanup_local": "PASS", "files": "PRESERVED"})
        del _name, _names
        """, tags=["cleanup_local"]),
        markdown("""
        ## Referências e próximos passos

        - [Runbook completo desta trilha](../docs/terraform/README.md)
        - [Registro dos testes efetivamente executados](../docs/validacao.md#laboratório-09)
        - [AWS: deploy Python direto e ARM64](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html)
        - [AWS: IAM do Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)
        - [AWS: workload access tokens](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/get-workload-access-token.html)
        - [AWS: Identity com Cognito](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-getting-started-cognito.html)
        - [AWS: contrato do target Lambda](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html)
        - [Terraform: Runtime](https://registry.terraform.io/providers/hashicorp/aws/6.70.0/docs/resources/bedrockagentcore_agent_runtime)
        - [Terraform: Gateway](https://registry.terraform.io/providers/hashicorp/aws/6.70.0/docs/resources/bedrockagentcore_gateway)
        - [Terraform: Identity provider](https://registry.terraform.io/providers/hashicorp/aws/6.70.0/docs/resources/bedrockagentcore_oauth2_credential_provider)
        - [Terraform: workload identity](https://registry.terraform.io/providers/hashicorp/aws/6.70.0/docs/resources/bedrockagentcore_workload_identity)

        Com a primeira implantação compreendida, avance para o
        [notebook 10](10_santander_multi_conta.ipynb). Ele introduz as fronteiras
        entre contas antes dos agentes distribuídos e da delegação até a fonte.
        """),
    ]
    diagram = (ROOT / "docs/terraform/arquitetura.svg").read_bytes()
    cells[1].attachments = {
        "arquitetura.svg": {"image/svg+xml": base64.b64encode(diagram).decode()}
    }
    cells.insert(2, learning_cell("09"))
    notebook = nb.v4.new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {
                "display_name": "Python 3 (workshop .venv)",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
            "santander": {
                "local_validation_mode": "LOCAL_CODE_AND_PROTOCOL_TESTS",
                "cloud_iac": "Terraform",
                "scenario": "terraform_agentcore",
            },
        },
    )
    # IDs estáveis tornam regeneração idempotente e o diff legível.
    for index, cell in enumerate(notebook.cells):
        cell.id = f"terraform-{index:03d}"
    nb.validate(notebook)
    return notebook


if __name__ == "__main__":
    nb.write(build_notebook(), OUTPUT)
    print(OUTPUT.relative_to(ROOT))
