import os
import pathlib
import uuid

import git
import mlflow
import pandas as pd
import pytest
import yaml

import zntrack.examples


class RangePlotter(zntrack.Node):
    start: int = zntrack.params()
    stop: int = zntrack.params()

    plots: pd.DataFrame = zntrack.plots(y="range")

    def run(self):
        for idx in range(self.start, self.stop):
            self.state.extend_plots("plots", {"idx": idx})


@pytest.fixture
def mlflow_proj_path(proj_path):
    os.environ["ZNTRACK_PLUGINS"] = (
        "zntrack.plugins.dvc_plugin.DVCPlugin,zntrack.plugins.mlflow_plugin.MLFlowPlugin"
    )
    os.environ["MLFLOW_TRACKING_URI"] = "http://127.0.0.1:5000"
    os.environ["MLFLOW_EXPERIMENT_NAME"] = f"test-{uuid.uuid4()}"

    config = {
        "global": {
            "ZNTRACK_PLUGINS": os.environ["ZNTRACK_PLUGINS"],
            "MLFLOW_TRACKING_URI": os.environ["MLFLOW_TRACKING_URI"],
            "MLFLOW_EXPERIMENT_NAME": os.environ["MLFLOW_EXPERIMENT_NAME"],
        }
    }
    pathlib.Path("env.yaml").write_text(yaml.dump(config))

    yield proj_path

    del os.environ["ZNTRACK_PLUGINS"]
    del os.environ["MLFLOW_TRACKING_URI"]
    del os.environ["MLFLOW_EXPERIMENT_NAME"]


def test_mlflow_metrics(mlflow_proj_path):
    proj = zntrack.Project()

    with proj:
        node = zntrack.examples.ParamsToMetrics(params={"loss": 0})

    proj.build()
    # there should be no entry in the mlflow server

    proj.repro(build=False)
    # # the run should be there

    with node.state.plugins["MLFlowPlugin"]:
        pass  # load run_id states

    child_run_id = node.state.plugins["MLFlowPlugin"].child_run_id
    parent_run_id = node.state.plugins["MLFlowPlugin"].parent_run_id

    assert child_run_id is not None
    assert parent_run_id is not None

    run = mlflow.get_run(child_run_id)
    # assert params are logged
    assert run.data.params == {"params": "{'loss': 0}"}  # this is strange!
    # assert tags
    assert run.data.tags["dvc_stage_name"] == "ParamsToMetrics"
    assert run.data.tags["dvc_stage_hash"] == node.state.get_stage_hash()
    assert run.data.tags["zntrack_node"] == "zntrack.examples.ParamsToMetrics"

    # assert metrics
    assert run.data.metrics == {"metrics.loss": 0.0}

    # make a git commit with all the changes
    repo = git.Repo()
    repo.git.add(".")
    repo.git.commit("-m", "test")
    node.state.plugins["MLFlowPlugin"].finalize()

    run = mlflow.get_run(child_run_id)  # need to query the run again

    assert run.data.tags["git_commit_message"] == "test"
    assert run.data.tags["git_commit_hash"] == repo.head.commit.hexsha


def test_mlflow_plotting(mlflow_proj_path):
    proj = zntrack.Project()

    with proj:
        node = RangePlotter(start=0, stop=10)

    proj.build()
    proj.repro(build=False)

    with node.state.plugins["MLFlowPlugin"]:
        pass  # load run_id states

    child_run_id = node.state.plugins["MLFlowPlugin"].child_run_id
    parent_run_id = node.state.plugins["MLFlowPlugin"].parent_run_id

    assert child_run_id is not None
    assert parent_run_id is not None

    run = mlflow.get_run(child_run_id)
    # assert params are logged
    assert run.data.params == {"start": "0", "stop": "10"}
    # assert tags
    assert run.data.tags["dvc_stage_name"] == "RangePlotter"
    assert run.data.tags["dvc_stage_hash"] == node.state.get_stage_hash()
    assert run.data.tags["zntrack_node"] == "test_plugins_mlflow.RangePlotter"

    # assert metrics (last)
    assert run.data.metrics == {"plots.idx": 9.0}

    client = mlflow.MlflowClient()
    history = client.get_metric_history(child_run_id, "plots.idx")
    assert len(history) == 10
    assert [entry.value for entry in history] == list(range(10))

    # make a git commit with all the changes
    repo = git.Repo()
    repo.git.add(".")
    repo.git.commit("-m", "test")
    node.state.plugins["MLFlowPlugin"].finalize()

    run = mlflow.get_run(child_run_id)  # need to query the run again

    assert run.data.tags["git_commit_message"] == "test"
    assert run.data.tags["git_commit_hash"] == repo.head.commit.hexsha


def test_multiple_nodes(mlflow_proj_path):
    with zntrack.Project() as proj:
        a = zntrack.examples.ParamsToOuts(params=3)
        b = zntrack.examples.ParamsToOuts(params=7)
        c = zntrack.examples.SumNodeAttributesToMetrics(inputs=[a.outs, b.outs], shift=0)

    proj.repro()

    assert c.metrics == {"value": 10.0}

    with a.state.plugins["MLFlowPlugin"]:
        a_run = mlflow.get_run(a.state.plugins["MLFlowPlugin"].child_run_id)

    with b.state.plugins["MLFlowPlugin"]:
        b_run = mlflow.get_run(b.state.plugins["MLFlowPlugin"].child_run_id)

    with c.state.plugins["MLFlowPlugin"]:
        c_run = mlflow.get_run(c.state.plugins["MLFlowPlugin"].child_run_id)

    assert c_run.data.metrics == {"metrics.value": 10.0}

    repo = git.Repo()
    repo.git.add(".")
    repo.git.commit("-m", "exp1")
    proj.finalize()

    a.params = 5
    proj.repro()

    repo = git.Repo()
    repo.git.add(".")
    repo.git.commit("-m", "exp2")
    proj.finalize()

    # find all runs with `git_commit_hash` == repo.head.commit.hexsha
    runs = mlflow.search_runs(
        filter_string=f"tags.git_commit_hash = '{repo.head.commit.hexsha}'"
    )
    assert len(runs) == 4

    a_run_2 = mlflow.search_runs(
        filter_string=f"tags.git_commit_hash = '{repo.head.commit.hexsha}' and tags.dvc_stage_name = '{a.name}'",
        output_format="list",
    )
    assert len(a_run_2) == 1
    a_run_2 = a_run_2[0]

    b_run_2 = mlflow.search_runs(
        filter_string=f"tags.git_commit_hash = '{repo.head.commit.hexsha}' and tags.dvc_stage_name = '{b.name}'",
        output_format="list",
    )
    assert len(b_run_2) == 1
    b_run_2 = b_run_2[0]

    c_run_2 = mlflow.search_runs(
        filter_string=f"tags.git_commit_hash = '{repo.head.commit.hexsha}' and tags.dvc_stage_name = '{c.name}'",
        output_format="list",
    )
    assert len(c_run_2) == 1
    c_run_2 = c_run_2[0]

    assert "original_run_id" not in a_run_2.data.tags
    assert b_run_2.data.tags["original_run_id"] == b_run.info.run_id
    assert "original_run_id" not in c_run_2.data.tags

    assert c_run_2.data.metrics == {"metrics.value": 12.0}


def test_project_tags(mlflow_proj_path):
    with zntrack.Project(tags={"lorem": "ipsum", "hello": "world"}) as proj:
        a = zntrack.examples.ParamsToOuts(params=3)
        b = zntrack.examples.ParamsToOuts(params=7)
        c = zntrack.examples.SumNodeAttributesToMetrics(inputs=[a.outs, b.outs], shift=0)

    proj.repro()

    with a.state.plugins["MLFlowPlugin"]:
        a_run = mlflow.get_run(a.state.plugins["MLFlowPlugin"].child_run_id)
        parent_run = mlflow.get_run(a.state.plugins["MLFlowPlugin"].parent_run_id)

    with b.state.plugins["MLFlowPlugin"]:
        b_run = mlflow.get_run(b.state.plugins["MLFlowPlugin"].child_run_id)

    with c.state.plugins["MLFlowPlugin"]:
        c_run = mlflow.get_run(c.state.plugins["MLFlowPlugin"].child_run_id)

    assert a_run.data.tags["lorem"] == "ipsum"
    assert a_run.data.tags["hello"] == "world"

    assert b_run.data.tags["lorem"] == "ipsum"
    assert b_run.data.tags["hello"] == "world"

    assert c_run.data.tags["lorem"] == "ipsum"
    assert c_run.data.tags["hello"] == "world"

    assert parent_run.data.tags["lorem"] == "ipsum"
    assert parent_run.data.tags["hello"] == "world"


# TODO: test plots via extend_plots and via setting them at the end
# each plugin must keep track of plots which are extended
#  -> code duplication. This should be done in the node.state?
