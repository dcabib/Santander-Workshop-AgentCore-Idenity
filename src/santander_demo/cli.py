"""Comandos de consulta e aceite dos serviços implantados na AWS."""

import argparse
import asyncio
import json
from pathlib import Path

from santander_demo.aws_workshop.client import AWSWorkshop
from santander_demo.aws_workshop.contracts import policies


async def execute(lab, command):
    if command == "preflight":
        return {**lab.preflight(), **await lab.deny_anonymous()}
    if command == "demo":
        return await lab.invoke_agent(
            lab.login(), "Consulte o risco do cliente C001 e explique o resultado sintético.",
        )
    result = []
    for user, app, tool, limit, allowed in [
        ("a", "supervisor", "riscos___consultar_risco", 1, True),
        ("b", "supervisor", "riscos___consultar_risco", 1, False),
        ("c", "supervisor", "especialista___consultar_fraude", 1, True),
        ("c", "riscos", "especialista___consultar_fraude", 1, False),
        ("d", "supervisor", "riscos___consultar_risco", 1, False),
        ("c", "supervisor", "riscos___consultar_risco", 11, False),
    ]:
        token = lab.login(user, app)
        arguments = {"cliente_id": "C001", "max_registros": limit}
        evidence = (
            await lab.call(token, tool, arguments) if allowed
            else await lab.expect_denial(token, tool, arguments)
        )
        result.append({"user": user, "application": app, "tool": tool, "evidence": evidence})
    return {"execution": "AWS", "tests": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["demo", "matrix", "cedar", "preflight"])
    parser.add_argument("--config", default="config/aws.workshop.json")
    parser.add_argument("--domain", default="platform")
    parser.add_argument("--output")
    args = parser.parse_args()
    lab = AWSWorkshop(args.config, args.domain)
    if args.command == "cedar":
        print("\n\n".join(policies(
            lab.gateway["GatewayArn"], lab.identity["Issuer"],
            lab.identity["SupervisorClientId"], lab.identity["RiscosClientId"],
            {x: lab.identity[f"User{x.upper()}Oid"] for x in "abc"},
        ).values()))
        return
    result = asyncio.run(execute(lab, args.command))
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n")
    else:
        print(text)
