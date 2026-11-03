"""Regiões implementadas e validação estrita dos endpoints que recebem tokens."""

import re

REGIONS = ("us-east-1", "us-west-2")


def gateway_region(url):
    match = re.fullmatch(
        rf"https://[a-z0-9-]+\.gateway\.bedrock-agentcore\.({'|'.join(REGIONS)})\.amazonaws\.com/mcp",
        url,
    )
    if not match:
        raise ValueError("GATEWAY_INVALID")
    return match[1]
