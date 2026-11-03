from infra.workshop.generate import policy_draft, runner


def statements(document, role):
    return document["Resources"][role]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]


def test_draft_provider_may_validate_only_its_gateway_and_cannot_publish():
    policy = statements(policy_draft(), "DraftRole")
    invocation, = [s for s in policy if "bedrock-agentcore:InvokeGateway" in s["Action"]]
    assert invocation["Resource"] == {"Ref": "GatewayArn"}
    assert not any(
        action in {"bedrock-agentcore:CreatePolicy", "bedrock-agentcore:UpdatePolicy"}
        for s in policy for action in s["Action"]
    )


def test_runner_can_read_identity_directory_without_directory_administration():
    policy = statements(runner(), "Role")
    directory, = [
        s for s in policy if "workload-identity-directory/default" in str(s["Resource"])
    ]
    assert set(directory["Action"]) == {
        "bedrock-agentcore:GetWorkloadIdentity", "bedrock-agentcore:GetWorkloadAccessToken",
    }
    assert directory["Resource"] == {
        "Fn::Sub": "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:"
        "workload-identity-directory/default",
    }
    assert all(not action.startswith(("iam:Put", "iam:Create")) for s in policy for action in s["Action"])
