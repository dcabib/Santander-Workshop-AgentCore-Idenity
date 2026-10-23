"""User pool, quatro usuários e credenciais sintéticas, todos pertencentes ao IaC."""

from infra.banking.generate import artifact_params
from infra.generate import att, output, param, ref, resource, role, statement, sub, template
from santander_demo.rag.cognito import policies


def identity():
    t = template(
        "Santander RAG - isolated Cognito test identities",
        {"Project": param(), **artifact_params()},
    )
    r = t["Resources"]
    r["Pool"] = resource(
        "AWS::Cognito::UserPool",
        {
            "UserPoolName": ref("Project"),
            "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
            "Policies": {
                "PasswordPolicy": {
                    "MinimumLength": 24,
                    "RequireLowercase": True,
                    "RequireUppercase": True,
                    "RequireNumbers": True,
                    "RequireSymbols": True,
                }
            },
            "Schema": [
                {
                    "Name": "email",
                    "AttributeDataType": "String",
                    "Required": True,
                    "Mutable": False,
                },
            ],
        },
    )
    r["Client"] = resource(
        "AWS::Cognito::UserPoolClient",
        {
            "ClientName": "workshop-notebook",
            "UserPoolId": ref("Pool"),
            "GenerateSecret": False,
            "ExplicitAuthFlows": ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
            "PreventUserExistenceErrors": "ENABLED",
            "ReadAttributes": ["email", "email_verified"],
            "IdTokenValidity": 15,
            "AccessTokenValidity": 15,
            "TokenValidityUnits": {"IdToken": "minutes", "AccessToken": "minutes"},
        },
    )
    for label in "ABCD":
        r[f"User{label}"] = resource(
            "AWS::Cognito::UserPoolUser",
            {
                "UserPoolId": ref("Pool"),
                "Username": "usuario-" + label.lower(),
                "MessageAction": "SUPPRESS",
                "UserAttributes": [
                    {"Name": "email", "Value": f"{label.lower()}@santander-rag.example.invalid"},
                    {"Name": "email_verified", "Value": "true"},
                ],
            },
        )
        r[f"Secret{label}"] = resource(
            "AWS::SecretsManager::Secret",
            {
                "Description": "Synthetic workshop credential; not a real person",
                "GenerateSecretString": {
                    "SecretStringTemplate": '{"username":"usuario-' + label.lower() + '"}',
                    "GenerateStringKey": "password",
                    "PasswordLength": 32,
                    "RequireEachIncludedType": True,
                },
            },
        )
        output(t, f"User{label}SecretArn", ref(f"Secret{label}"))
        output(t, f"User{label}Email", f"{label.lower()}@santander-rag.example.invalid")
    r["Log"] = resource("AWS::Logs::LogGroup", {"RetentionInDays": 7})
    r["Role"] = role(
        "lambda.amazonaws.com",
        [
            statement(["logs:CreateLogStream", "logs:PutLogEvents"], sub("${Log.Arn}:*")),
            statement(
                ["cognito-idp:AdminSetUserPassword", "cognito-idp:AdminGetUser"], att("Pool", "Arn")
            ),
            statement(["secretsmanager:GetSecretValue"], [ref(f"Secret{x}") for x in "ABCD"]),
        ],
    )
    r["Function"] = resource(
        "AWS::Lambda::Function",
        {
            "Runtime": "python3.12",
            "Architectures": ["arm64"],
            "Handler": "santander_demo.rag.cognito_seed.handler",
            "Role": att("Role", "Arn"),
            "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ArtifactKey")},
            "Timeout": 120,
            "LoggingConfig": {"LogGroup": ref("Log")},
        },
    )
    r["UsersReady"] = resource(
        "Custom::RagTestCredentials",
        {
            "ServiceToken": att("Function", "Arn"),
            "UserPoolId": ref("Pool"),
            **{f"User{x}SecretArn": ref(f"Secret{x}") for x in "ABCD"},
        },
        DependsOn=[f"User{x}" for x in "ABCD"],
    )
    for label in "ABCD":
        output(t, f"User{label}Oid", att("UsersReady", f"User{label}Oid"))
    output(t, "UserPoolId", ref("Pool"))
    output(t, "LoginClientId", ref("Client"))
    return t


def access(base):
    """Reutiliza o conector e IAM do cenário; troca apenas o contrato de identidade."""
    t = base
    t["Description"] = "Santander RAG - Cognito, AgentCore Identity and Policy, native managed KB"
    for key in ["TenantId", "BrokerClientId", "GatewayClientId", "BrokerSecretArn"]:
        del t["Parameters"][key]
    t["Parameters"].update(UserPoolId=param(), LoginClientId=param())
    r = t["Resources"]
    del r["OAuth"]
    auth = {
        "DiscoveryUrl": sub(
            "https://cognito-idp.${AWS::Region}.amazonaws.com/${UserPoolId}/.well-known/openid-configuration"
        ),
        "AllowedAudience": [ref("LoginClientId")],
        "CustomClaims": [
            {
                "InboundTokenClaimName": "token_use",
                "InboundTokenClaimValueType": "STRING",
                "AuthorizingClaimMatchValue": {
                    "ClaimMatchOperator": "EQUALS",
                    "ClaimMatchValue": {"MatchValueString": "id"},
                },
            }
        ],
    }
    r["Gateway"]["Properties"]["AuthorizerConfiguration"]["CustomJWTAuthorizer"] = auth
    users = {
        x.lower(): {"oid": "${User" + x + "Oid}", "email": "${User" + x + "Email}"} for x in "ABCD"
    }
    for name, policy in policies(
        "${Gateway.GatewayArn}",
        "https://cognito-idp.${AWS::Region}.amazonaws.com/${UserPoolId}",
        "${LoginClientId}",
        users,
    ).items():
        r[name]["Properties"]["Definition"]["Cedar"]["Statement"] = sub(policy)
    statements = r["CallerRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    statements[:] = [
        s for s in statements if "bedrock-agentcore:GetResourceOauth2Token" not in s["Action"]
    ]
    for key in ["OAuthProviderName", "OAuthProviderArn"]:
        del t["Outputs"][key]
    return t
