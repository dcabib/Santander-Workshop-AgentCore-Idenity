import copy
import json
from unittest.mock import Mock

import pytest

from scripts import cleanup
from scripts.notebook_cleanup import LOCAL_NAMES, cleanup_cells
from scripts.verify_notebooks import check_offline_defaults

ACCOUNT = "123456789012"
REGION = "us-east-1"
STACK = "test-workshop"
ARN = f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{STACK}/test-id"


@pytest.fixture
def environment():
    template = cleanup.load_template("workshop", "bootstrap")
    cfn = Mock()
    cfn.describe_stacks.return_value = {
        "Stacks": [
            {
                "StackId": ARN,
                "StackName": STACK,
                "StackStatus": "CREATE_COMPLETE",
                "EnableTerminationProtection": False,
            }
        ]
    }
    cfn.get_template.return_value = {"TemplateBody": copy.deepcopy(template)}
    sts = Mock()
    sts.get_caller_identity.return_value = {"Account": ACCOUNT}
    session = Mock()
    session.client.side_effect = {"sts": sts, "cloudformation": cfn}.__getitem__
    return session, cfn, template


def prepare(environment):
    session, _, template = environment
    return cleanup.plan_cleanup(
        session, account=ACCOUNT, region=REGION, stack_name=STACK, template=template
    )


def test_plan_is_read_only_and_identifies_retained_resources(environment):
    session, cfn, _ = environment
    plan = prepare(environment)
    assert plan["mode"] == "READ_ONLY_PLAN"
    assert plan["retention_declared_in_template"]["Artifacts"]["policy"] == "Retain"
    assert plan["blockers"] == []
    cfn.delete_stack.assert_not_called()
    assert {args.args[0] for args in session.client.call_args_list} == {"sts", "cloudformation"}
    cfn.get_template.assert_called_once_with(StackName=ARN, TemplateStage="Original")


@pytest.mark.parametrize("mismatch", ["account", "region", "stack", "template"])
def test_wrong_target_never_reaches_deletion(environment, mismatch):
    session, cfn, _ = environment
    if mismatch == "account":
        session.client("sts").get_caller_identity.return_value["Account"] = "000000000000"
    elif mismatch == "region":
        cfn.describe_stacks.return_value["Stacks"][0]["StackId"] = ARN.replace(REGION, "us-west-2")
    elif mismatch == "stack":
        cfn.describe_stacks.return_value["Stacks"][0]["StackName"] = "another-stack"
    else:
        cfn.get_template.return_value["TemplateBody"]["Description"] = "unrelated"
    with pytest.raises(ValueError):
        prepare(environment)
    cfn.delete_stack.assert_not_called()


@pytest.mark.parametrize("blocked", ["protection", "updating", "confirmation"])
def test_deletion_requires_eligible_stack_and_exact_confirmation(environment, blocked):
    session, cfn, _ = environment
    stack = cfn.describe_stacks.return_value["Stacks"][0]
    if blocked == "protection":
        stack["EnableTerminationProtection"] = True
    elif blocked == "updating":
        stack["StackStatus"] = "UPDATE_IN_PROGRESS"
    plan = prepare(environment)
    with pytest.raises(ValueError):
        cleanup.execute_cleanup(session, plan, "wrong-arn" if blocked == "confirmation" else ARN)
    cfn.delete_stack.assert_not_called()
    cfn.update_termination_protection.assert_not_called()


def test_deletion_uses_reviewed_arn_and_waits_without_deleting_retained_items(environment):
    session, cfn, _ = environment
    result = cleanup.execute_cleanup(session, prepare(environment), ARN)
    cfn.delete_stack.assert_called_once_with(StackName=ARN)
    cfn.get_waiter.assert_called_once_with("stack_delete_complete")
    cfn.get_waiter.return_value.wait.assert_called_once_with(
        StackName=ARN, WaiterConfig={"Delay": 5, "MaxAttempts": 120}
    )
    assert result["cloud_cleanup"] == "STACK_DELETE_COMPLETE"
    assert result["retained_resources"]["Artifacts"]["policy"] == "Retain"
    assert {args.args[0] for args in session.client.call_args_list} == {"sts", "cloudformation"}


@pytest.mark.parametrize("notebook_id", sorted(LOCAL_NAMES))
def test_local_cleanup_is_repeatable_preserves_files_and_unrelated_state(
    notebook_id, tmp_path, capsys
):
    scenario = {"10": "banking", "11": "federation"}.get(notebook_id, "workshop")
    cells = cleanup_cells(notebook_id, scenario)
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"keep": true}')
    namespace = {
        "lab": object(),
        "token": "synthetic",
        "config": object(),
        "user_own_variable": "preserve",
        **{name: object() for name in LOCAL_NAMES[notebook_id]},
    }
    code = cells[-1].source
    exec(compile(code, "<cleanup>", "exec"), namespace)
    result = json.loads(capsys.readouterr().out)
    assert result["cleanup_local"] == "PASS"
    assert result["removed_variables"] >= 3
    assert "token" not in namespace and "config" not in namespace and "lab" not in namespace
    assert namespace["user_own_variable"] == "preserve"
    assert evidence.read_text() == '{"keep": true}'
    exec(compile(code, "<cleanup>", "exec"), namespace)
    assert json.loads(capsys.readouterr().out)["removed_variables"] == 0


def test_runner_rejects_enabled_cloud_cleanup_before_starting_kernel():
    import nbformat as nb

    notebook = nb.v4.new_notebook(cells=cleanup_cells("10", "banking"))
    check_offline_defaults(notebook)
    notebook.cells[1].source = notebook.cells[1].source.replace(
        "CLEANUP_EXECUTE = False", "CLEANUP_EXECUTE = True"
    )
    with pytest.raises(ValueError, match="CLEANUP_EXECUTE"):
        check_offline_defaults(notebook)


def test_template_lookup_rejects_unowned_paths():
    with pytest.raises(ValueError, match="não pertence"):
        cleanup.load_template("banking", "../../other-stack")
