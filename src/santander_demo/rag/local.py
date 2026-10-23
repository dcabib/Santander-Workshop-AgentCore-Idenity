"""Bancada explícita: JWT RSA e Cedar reais, Managed KB/LLM substituídos localmente."""

import json
import time
from functools import partial
from types import SimpleNamespace

import cedarpy
import jwt

from santander_demo.identity import JwtVerifier, LocalIssuer
from santander_demo.rag import cognito
from santander_demo.rag.client import checked_results, generate_answer, retrieval_arguments
from santander_demo.rag.contract import DOMAINS, QUESTION, SCOPE, TOOL, evaluate
from santander_demo.rag.corpus import DOCUMENTS, acl_entries, allowed_documents

LOCAL_USERS = {
    label: {"oid": f"00000000-0000-4000-8000-{i:012d}", "email": f"{label}@example.invalid"}
    for i, label in enumerate(DOMAINS, 1)
}
LOCAL_GATEWAY = "arn:aws:bedrock-agentcore:us-east-1:111111111111:gateway/local-rag"


class LocalKnowledgeBase:
    """Double de contrato; não simula relevância semântica nem comprova o serviço AWS."""

    def __init__(self, users=LOCAL_USERS, bucket="local-rag-corpus"):
        self.users, self.bucket, self.calls = users, bucket, []

    def retrieve(self, **request):
        self.calls.append(request)
        email = request.get("userContext", {}).get("userId")
        results = []
        for doc in DOCUMENTS:
            entries = [e for e in acl_entries(doc["domain"], self.users) if e["Name"] == email]
            if not any(e["Access"] == "ALLOW" for e in entries) or any(
                e["Access"] == "DENY" for e in entries
            ):
                continue
            results.append(
                {
                    "content": {"type": "TEXT", "text": doc["text"]},
                    "metadata": {"document_id": doc["id"], "domain": doc["domain"]},
                    "location": {
                        "type": "S3",
                        "s3Location": {
                            "uri": f"s3://{self.bucket}/documents/{doc['domain']}/{doc['id']}.txt"
                        },
                    },
                }
            )
        return {"retrievalResults": results}


class LocalModel:
    def __init__(self):
        self.calls = []

    def converse(self, **request):
        self.calls.append(request)
        chunks = json.loads(request["messages"][0]["content"][0]["text"])["trechos_autorizados"]
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "\n".join(f"[{c['id']}] {c['text']}" for c in chunks)}],
                }
            }
        }


class LocalRagLab:
    def __init__(self):
        self.issuer = LocalIssuer()
        self.verifier = JwtVerifier(
            key=self.issuer._key.public_key(),
            issuer=self.issuer.issuer,
            audience="api://local-rag",
            tenant=self.issuer.tenant,
        )
        self.kb = LocalKnowledgeBase()
        self.model = LocalModel()

    def token(self, label, **changes):
        now = int(time.time())
        claims = {
            "iss": self.issuer.issuer,
            "tid": self.issuer.tenant,
            "aud": "api://local-rag",
            "sub": "local-" + label,
            "oid": LOCAL_USERS[label]["oid"],
            "email": LOCAL_USERS[label]["email"],
            "azp": "local-broker",
            "ver": "2.0",
            "scp": SCOPE,
            "iat": now,
            "exp": now + 600,
        }
        claims.update(changes)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self.issuer._key, algorithm="RS256")

    def authorize(self, claims, arguments):
        return evaluate(
            claims,
            arguments,
            gateway_arn=LOCAL_GATEWAY,
            tenant=self.issuer.tenant,
            broker="local-broker",
            users=LOCAL_USERS,
        )

    def call(self, label, question=QUESTION, *, forged_email=None):
        identity = self.verifier.verify(self.token(label))
        arguments = retrieval_arguments(identity, question)
        if forged_email is not None:
            arguments["userContext"]["userId"] = forged_email
        before_retrieval, before_generation = len(self.kb.calls), len(self.model.calls)
        allowed = self.authorize(identity.claims, arguments)
        result = {
            "mode": "LOCAL_CONTRACT",
            "aws_identity_kb_model": "NOT_RUN",
            "case": label,
            "policy": "ALLOW" if allowed else "DENY",
            "document_ids": [],
        }
        if allowed:
            response = self.kb.retrieve(
                knowledgeBaseId="LOCALKB001",
                retrievalConfiguration={"managedSearchConfiguration": {"numberOfResults": 10}},
                **arguments,
            )
            chunks = checked_results(response, label, self.kb.bucket)
            result["document_ids"] = sorted({c["id"] for c in chunks})
            result.update(generate_answer(self.model, "LOCAL_MODEL", question, chunks))
        result["retrieval_calls"] = len(self.kb.calls) - before_retrieval
        result["generation_calls"] = len(self.model.calls) - before_generation
        return result


class LocalCognitoRagLab(LocalRagLab):
    """Mesmo JWT/Cedar do caminho Cognito, com chave efêmera local e serviços substituídos."""

    def __init__(self):
        super().__init__()
        self.config = {
            "region": "us-east-1",
            "user_pool_id": "us-east-1_LocalTest",
            "login_client_id": "localtestclient",
            "users": LOCAL_USERS,
        }
        self.verifier = SimpleNamespace(
            verify=partial(cognito.verify, config=self.config, key=self.issuer._key.public_key())
        )

    def token(self, label, **changes):
        now = int(time.time())
        claims = {
            "iss": cognito.issuer(self.config),
            "aud": self.config["login_client_id"],
            "sub": LOCAL_USERS[label]["oid"],
            "email": LOCAL_USERS[label]["email"],
            "email_verified": True,
            "token_use": "id",
            "iat": now,
            "exp": now + 600,
        }
        claims.update(changes)
        return jwt.encode(
            {k: v for k, v in claims.items() if v is not None}, self.issuer._key, algorithm="RS256"
        )

    def authorize(self, claims, arguments):
        principal = {"type": "AgentCore::OAuthUser", "id": claims["sub"]}
        tags = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in claims.items()}
        return cedarpy.is_authorized(
            {
                "principal": principal,
                "action": {"type": "AgentCore::Action", "id": TOOL},
                "resource": {"type": "AgentCore::Gateway", "id": LOCAL_GATEWAY},
                "context": {"input": arguments},
            },
            "\n".join(
                cognito.policies(
                    LOCAL_GATEWAY,
                    cognito.issuer(self.config),
                    self.config["login_client_id"],
                    LOCAL_USERS,
                ).values()
            ),
            [{"uid": principal, "attrs": {}, "parents": [], "tags": tags}],
        ).allowed


def demo():
    lab = LocalRagLab()
    rows = [lab.call(label) for label in DOMAINS]
    for row in rows:
        assert set(row["document_ids"]) == allowed_documents(row["case"])
        assert row["retrieval_calls"] == row["generation_calls"] == (row["case"] != "d")
    spoof = lab.call("a", forged_email=LOCAL_USERS["c"]["email"])
    assert spoof["policy"] == "DENY" and spoof["retrieval_calls"] == 0
    return {"mode": "LOCAL_CONTRACT", "users": rows, "spoof_a_as_c": spoof}


if __name__ == "__main__":
    print(json.dumps(demo(), indent=2, ensure_ascii=False))
