"""Entrypoint do ZIP de Runtime (CloudFormation aceita até dois itens)."""

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from santander_demo.registry_workflow.runtime import run

app = BedrockAgentCoreApp()
app.entrypoint(run)

if __name__ == "__main__":
    app.run()
