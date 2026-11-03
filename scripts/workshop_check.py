"""Aceite real do ambiente AWS; qualquer dependência ausente encerra com erro."""

import argparse
import asyncio
import json
import uuid
from pathlib import Path

from santander_demo.aws_workshop.client import AWSWorkshop


async def check(config, domain):
    lab = AWSWorkshop(config, domain)
    result = {"preflight": lab.preflight(), "anonymous": await lab.deny_anonymous()}
    result["direct_runtime"] = lab.deny_direct_runtime()
    token = lab.login()
    result["tools"] = [x["name"] for x in await lab.tools(token)]
    for name in ["riscos___consultar_risco", "especialista___consultar_fraude"]:
        if name not in result["tools"]:
            raise AssertionError("MISSING_GATEWAY_TOOL:" + name)
    risk = await lab.call(token, "riscos___consultar_risco", {
        "cliente_id": "C001", "max_registros": 1,
    })
    if risk["result"].get("customer_id") != "C001":
        raise AssertionError("RISK_RESPONSE_INVALID")
    result["risk"] = risk
    source = await lab.call(token, "especialista___identidade_fonte", {})
    if source["result"]["verified_subject"] != lab.claims(token)["sub"]:
        raise AssertionError("SOURCE_IDENTITY_CHANGED")
    result["source_identity"] = source
    result["fraud"] = await lab.call(token, "especialista___consultar_fraude", {
        "cliente_id": "C001", "max_registros": 1,
    })
    session = "workshop-" + uuid.uuid4().hex
    result["memory_write"] = await lab.call(token, "especialista___memorizar_referencia", {
        "tabela": "fraude", "session_id": session,
    })
    memory = await lab.call(token, "especialista___recuperar_memoria", {"session_id": session})
    if [x["table"] for x in memory["result"]["documents"]] != ["fraude"]:
        raise AssertionError("MEMORY_CONTENT_INVALID")
    result["memory_read"] = memory
    other = await lab.call(lab.login("a"), "especialista___recuperar_memoria", {
        "session_id": session,
    })
    if other["result"]["documents"]:
        raise AssertionError("MEMORY_ACTOR_LEAK")
    result["memory_isolation"] = other
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/aws.workshop.json")
    parser.add_argument("--domain", default="platform")
    parser.add_argument("--output", help="Arquivo de evidência; o padrão é separado por domínio")
    args = parser.parse_args()
    report = asyncio.run(check(args.config, args.domain))
    suffix = "core" if args.domain == "platform" else args.domain
    path = Path(args.output or f"evidence/workshop-{suffix}.json")
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"execution": "AWS", "domain": args.domain, "evidence": str(path)}))


if __name__ == "__main__":
    main()
