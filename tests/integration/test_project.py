import json
import pathlib

import git
import pytest

import zntrack.examples
from zntrack.project import Experiment
from zntrack.utils import config


class ZnNodesNode(zntrack.Node):
    """Used zn.nodes"""

    node = zntrack.deps()
    result = zntrack.zn.outs()

    def run(self) -> None:
        self.result = self.node.params


@pytest.mark.parametrize("assert_before_exp", [True, False])
def test_WriteIO(tmp_path_2, assert_before_exp):
    """Test the WriteIO node."""
    with zntrack.Project() as project:
        node = zntrack.examples.ParamsToOuts(params="Hello World")

    project.run()
    node.load()
    if assert_before_exp:
        assert node.outs == "Hello World"

    # write a non-tracked file using pathlib
    pathlib.Path("test.txt").write_text("Hello World")

    with project.create_experiment(name="exp1") as exp1:
        node.params = "Hello World"

    # check that the file is still there
    assert pathlib.Path("test.txt").read_text() == "Hello World"

    with project.create_experiment(name="exp2") as exp2:
        node.params = "Lorem Ipsum"

    assert exp1.name == "exp1"
    assert exp2.name == "exp2"

    assert project.experiments.keys() == {"exp1", "exp2"}

    assert isinstance(project.experiments["exp1"], Experiment)

    project.run_exp()
    assert node.from_rev(rev="exp1").params == "Hello World"
    assert node.from_rev(rev="exp1").outs == "Hello World"

    assert node.from_rev(rev="exp2").params == "Lorem Ipsum"
    assert node.from_rev(rev="exp2").outs == "Lorem Ipsum"

    exp2.apply()
    assert (
        zntrack.from_rev("ParamsToOuts").params
        == zntrack.from_rev("ParamsToOuts", rev=exp2.name).params
    )
    exp1.apply()
    assert (
        zntrack.from_rev("ParamsToOuts").params
        == zntrack.from_rev("ParamsToOuts", rev=exp1.name).params
    )


@pytest.mark.parametrize("assert_before_exp", [True, False])
def test_WriteIO_no_name(tmp_path_2, assert_before_exp):
    """Test the WriteIO node."""
    with zntrack.Project() as project:
        node = zntrack.examples.ParamsToOuts(params="Hello World")

    project.run()
    node.load()
    if assert_before_exp:
        assert node.outs == "Hello World"

    with project.create_experiment() as exp1:
        node.params = "Hello World"

    with project.create_experiment() as exp2:
        node.params = "Lorem Ipsum"

    project.run_exp()

    exp1.load()
    assert exp1.nodes["ParamsToOuts"].params == "Hello World"
    assert exp1.nodes["ParamsToOuts"].outs == "Hello World"

    assert exp1["ParamsToOuts"].params == "Hello World"
    assert exp1["ParamsToOuts"].outs == "Hello World"

    exp2.load()
    assert exp2.nodes["ParamsToOuts"].params == "Lorem Ipsum"
    assert exp2.nodes["ParamsToOuts"].outs == "Lorem Ipsum"

    assert exp2["ParamsToOuts"].params == "Lorem Ipsum"
    assert exp2["ParamsToOuts"].outs == "Lorem Ipsum"

    assert zntrack.from_rev("ParamsToOuts", rev=exp1.name).params == "Hello World"
    assert zntrack.from_rev("ParamsToOuts", rev=exp1.name).outs == "Hello World"

    assert zntrack.from_rev("ParamsToOuts", rev=exp2.name).params == "Lorem Ipsum"
    assert zntrack.from_rev("ParamsToOuts", rev=exp2.name).outs == "Lorem Ipsum"


def test_project_remove_graph(proj_path):
    with zntrack.Project() as project:
        node = zntrack.examples.ParamsToOuts(params="Hello World")
    project.run()
    node.load()
    assert node.outs == "Hello World"

    with zntrack.Project(remove_existing_graph=True) as project:
        node2 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum", name="node2")
    project.run()
    node2.load()
    assert node2.outs == "Lorem Ipsum"
    with pytest.raises(zntrack.exceptions.NodeNotAvailableError):
        node.load()


def test_project_repr_node(tmp_path_2):
    with zntrack.Project() as project:
        node = zntrack.examples.ParamsToOuts(params="Hello World")
        print(node)


def test_automatic_node_names_False(tmp_path_2):
    with pytest.raises(zntrack.exceptions.DuplicateNodeNameError):
        with zntrack.Project(automatic_node_names=False) as project:
            _ = zntrack.examples.ParamsToOuts(params="Hello World")
            _ = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
    with pytest.raises(zntrack.exceptions.DuplicateNodeNameError):
        with zntrack.Project(automatic_node_names=False) as project:
            _ = zntrack.examples.ParamsToOuts(params="Hello World", name="NodeA")
            _ = zntrack.examples.ParamsToOuts(params="Lorem Ipsum", name="NodeA")


def test_automatic_node_names_default(tmp_path_2):
    with zntrack.Project(automatic_node_names=False) as project:
        _ = zntrack.examples.ParamsToOuts(params="Hello World")
        _ = zntrack.examples.ParamsToOuts(params="Lorem Ipsum", name="WriteIO2")


def test_automatic_node_names_True(tmp_path_2):
    with zntrack.Project(automatic_node_names=True) as project:
        node = zntrack.examples.ParamsToOuts(params="Hello World")
        node2 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
        assert node.name == "ParamsToOuts"
        assert node2.name == "ParamsToOuts_1"
    project.run()

    with project:
        node3 = zntrack.examples.ParamsToOuts(params="Dolor Sit")
        assert node3.name == "ParamsToOuts_2"

    project.run()

    assert node.name == "ParamsToOuts"
    assert node2.name == "ParamsToOuts_1"
    assert node3.name == "ParamsToOuts_2"

    project.run()
    project.load()
    assert "ParamsToOuts" in project.nodes
    assert "ParamsToOuts_1" in project.nodes
    assert "ParamsToOuts_2" in project.nodes

    assert node.outs == "Hello World"
    assert node2.outs == "Lorem Ipsum"
    assert node3.outs == "Dolor Sit"


def test_group_nodes(tmp_path_2):
    with zntrack.Project(automatic_node_names=True) as project:
        with project.group() as group_1:
            node_1 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
            node_2 = zntrack.examples.ParamsToOuts(params="Dolor Sit")
        with project.group() as group_2:
            node_3 = zntrack.examples.ParamsToOuts(params="Amet Consectetur")
            node_4 = zntrack.examples.ParamsToOuts(params="Adipiscing Elit")
        with project.group("NamedGrp") as group_3:
            node_5 = zntrack.examples.ParamsToOuts(params="Sed Do", name="NodeA")
            node_6 = zntrack.examples.ParamsToOuts(params="Eiusmod Tempor", name="NodeB")

        node7 = zntrack.examples.ParamsToOuts(params="Hello World")
        node8 = zntrack.examples.ParamsToOuts(params="How are you?")
        node9 = zntrack.examples.ParamsToOuts(params="I'm fine, thanks!", name="NodeC")

    project.run()

    # test nodes in groups
    assert node_1 in group_1
    assert node_2 in group_1
    assert node_3 not in group_1
    assert node_4 not in group_1
    assert len(group_1) == 2
    assert group_1.nwd == pathlib.Path("nodes", "Group1")
    assert node_3 in group_2
    assert node_4 in group_2
    assert node_5 in group_3
    assert node_6 in group_3

    # test node_names in project
    assert "Group1_ParamsToOuts" in group_1
    assert "Group1_ParamsToOuts_1" in group_1
    assert "Group2_ParamsToOuts" in group_2
    assert "Group2_ParamsToOuts_1" in group_2
    assert "NamedGrp_NodeA" in group_3
    assert "NamedGrp_NodeB" in group_3
    assert "NamedGrp_NodeA" not in group_1
    assert "NamedGrp_NodeB" not in group_1
    assert "NamedGrp_NodeA" not in group_2
    assert "NamedGrp_NodeB" not in group_2

    # test without group prefix
    assert "ParamsToOuts" in group_1
    assert "ParamsToOuts_1" in group_1
    assert "ParamsToOuts" in group_2
    assert "ParamsToOuts_1" in group_2
    assert "NodeA" in group_3
    assert "NodeB" in group_3

    # test getitem with node name
    assert group_1["ParamsToOuts"] == node_1
    assert group_1["ParamsToOuts_1"] == node_2
    assert group_2["ParamsToOuts"] == node_3
    assert group_2["ParamsToOuts_1"] == node_4
    assert group_3["NodeA"] == node_5
    assert group_3["NodeB"] == node_6

    # test getitem with full name
    assert group_1["Group1_ParamsToOuts"] == node_1
    assert group_1["Group1_ParamsToOuts_1"] == node_2
    assert group_2["Group2_ParamsToOuts"] == node_3
    assert group_2["Group2_ParamsToOuts_1"] == node_4
    assert group_3["NamedGrp_NodeA"] == node_5
    assert group_3["NamedGrp_NodeB"] == node_6

    with pytest.raises(KeyError):
        group_1["NodeA"]

    # test iter group
    assert list(group_1) == [node_1, node_2]
    assert list(group_2) == [node_3, node_4]
    assert list(group_3) == [node_5, node_6]

    assert group_1.name == "Group1"
    assert group_2.name == "Group2"
    assert group_3.name == "NamedGrp"

    assert node_1.name == "Group1_ParamsToOuts"
    assert node_2.name == "Group1_ParamsToOuts_1"
    assert node_3.name == "Group2_ParamsToOuts"
    assert node_4.name == "Group2_ParamsToOuts_1"

    assert node_5.name == "NamedGrp_NodeA"
    assert node_6.name == "NamedGrp_NodeB"

    assert node7.name == "ParamsToOuts"
    assert node8.name == "ParamsToOuts_1"
    assert node9.name == "NodeC"

    assert (
        zntrack.examples.ParamsToOuts.from_rev(name="NamedGrp_NodeA").params == "Sed Do"
    )


def test_build_certain_nodes(tmp_path_2):
    # TODO support passing groups to project.build
    with zntrack.Project(automatic_node_names=True) as project:
        node_1 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
        node_2 = zntrack.examples.ParamsToOuts(params="Dolor Sit")
    project.build(nodes=[node_1, node_2])
    project.repro()

    assert zntrack.from_rev(node_1).outs == "Lorem Ipsum"
    assert zntrack.from_rev(node_2).outs == "Dolor Sit"

    node_1.params = "ABC"
    node_2.params = "DEF"

    project.build(nodes=[node_1])
    project.repro()

    assert zntrack.from_rev(node_1).outs == "ABC"
    assert zntrack.from_rev(node_2).outs == "Dolor Sit"

    project.run(nodes=[node_2])

    assert zntrack.from_rev(node_1).outs == "ABC"
    assert zntrack.from_rev(node_2).outs == "DEF"


def test_build_groups(tmp_path_2):
    with zntrack.Project(automatic_node_names=True) as project:
        with project.group() as group_1:
            node_1 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
            node_2 = zntrack.examples.ParamsToOuts(params="Dolor Sit")
        with project.group() as group_2:
            node_3 = zntrack.examples.ParamsToOuts(params="Amet Consectetur")
            node_4 = zntrack.examples.ParamsToOuts(params="Adipiscing Elit")

    project.run(nodes=[group_1])

    assert zntrack.from_rev(node_1).outs == "Lorem Ipsum"
    assert zntrack.from_rev(node_2).outs == "Dolor Sit"

    with pytest.raises(ValueError):
        zntrack.from_rev(node_3)
    with pytest.raises(ValueError):
        zntrack.from_rev(node_4)

    node_2.params = "DEF"

    project.run(nodes=[group_2, node_2])

    assert zntrack.from_rev(node_1).outs == "Lorem Ipsum"

    assert zntrack.from_rev(node_2).outs == "DEF"
    assert zntrack.from_rev(node_3).outs == "Amet Consectetur"
    assert zntrack.from_rev(node_4).outs == "Adipiscing Elit"

    with pytest.raises(TypeError):
        project.run(nodes=42)

    with pytest.raises(ValueError):
        project.run(nodes=[42])

    # assert that the only directories in "nodes/" are "Group1" and "Group2"
    assert set(path.name for path in (tmp_path_2 / "nodes").iterdir()) == {
        "Group1",
        "Group2",
    }


def test_groups_nwd(tmp_path_2):
    with zntrack.Project(automatic_node_names=True) as project:
        node_1 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
        with project.group() as group_1:
            node_2 = zntrack.examples.ParamsToOuts(params="Dolor Sit")
        with project.group("CustomGroup") as group_2:
            node_3 = zntrack.examples.ParamsToOuts(params="Adipiscing Elit")

    project.build()

    assert node_1.nwd == pathlib.Path("nodes", node_1.name)
    assert node_2.nwd == pathlib.Path(
        "nodes", "Group1", node_2.name.replace(f"Group1_", "")
    )
    assert node_3.nwd == pathlib.Path(
        "nodes", "CustomGroup", node_3.name.replace(f"CustomGroup_", "")
    )
    # now load the Nodes and assert as well

    assert zntrack.from_rev(node_1).nwd == pathlib.Path("nodes", node_1.name)
    assert zntrack.from_rev(node_2).nwd == pathlib.Path(
        "nodes", "Group1", node_2.name.replace(f"Group1_", "")
    )
    assert zntrack.from_rev(node_3).nwd == pathlib.Path(
        "nodes", "CustomGroup", node_3.name.replace(f"CustomGroup_", "")
    )

    with open(config.files.zntrack) as f:
        data = json.load(f)
        data[node_1.name]["nwd"]["value"] = "test"
        data[node_2.name].pop("nwd")

    with open(config.files.zntrack, "w") as f:
        json.dump(data, f)

    assert zntrack.from_rev(node_1).nwd == pathlib.Path("test")
    assert zntrack.from_rev(node_2).nwd == pathlib.Path("nodes", node_2.name)
    assert zntrack.from_rev(node_3).nwd == pathlib.Path(
        "nodes", "CustomGroup", node_3.name.replace(f"CustomGroup_", "")
    )


def test_groups_nwd_zn_nodes_a(tmp_path_2):
    node = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
    with zntrack.Project(automatic_node_names=True) as project:
        node_1 = ZnNodesNode(node=node)
        with project.group() as group_1:
            node_2 = ZnNodesNode(node=node)
        with project.group("CustomGroup") as group_2:
            node_3 = ZnNodesNode(node=node)

    assert node_1.name == "ZnNodesNode"
    assert node_1.node.name == "ZnNodesNode+node"

    assert node_2.name == "Group1_ZnNodesNode"
    assert node_2.node.name == "Group1_ZnNodesNode+node"

    assert node_3.name == "CustomGroup_ZnNodesNode"
    assert node_3.node.name == "CustomGroup_ZnNodesNode+node"

    project.run()

    assert zntrack.from_rev(node_1).nwd == pathlib.Path("nodes/ZnNodesNode")
    assert zntrack.from_rev(node_2).nwd == pathlib.Path("nodes", "Group1", "ZnNodesNode")
    assert zntrack.from_rev(node_3).nwd == pathlib.Path(
        "nodes", "CustomGroup", "ZnNodesNode"
    )

    project.load()
    assert node_1.result == "Lorem Ipsum"
    assert node_2.result == "Lorem Ipsum"
    assert node_3.result == "Lorem Ipsum"


def test_groups_nwd_zn_nodes_b(tmp_path_2):
    node = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
    with zntrack.Project(automatic_node_names=True) as project:
        with project.group() as group_1:
            node_2 = ZnNodesNode(node=node)
        with project.group("CustomGroup") as group_2:
            node_3 = ZnNodesNode(node=node)

    project.run()

    assert zntrack.from_rev(node_2).nwd == pathlib.Path("nodes", "Group1", "ZnNodesNode")
    assert zntrack.from_rev(node_3).nwd == pathlib.Path(
        "nodes", "CustomGroup", "ZnNodesNode"
    )

    project.load()
    assert node_2.result == "Lorem Ipsum"
    assert node_3.result == "Lorem Ipsum"


def test_reopening_groups(proj_path):
    with zntrack.Project(automatic_node_names=True) as project:
        with project.group("AL0") as al_0:
            node_1 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
            node_2 = zntrack.examples.ParamsToOuts(params="Dolor Sit")
            node_3 = zntrack.examples.ParamsToOuts(params="Amet Consectetur")
        with project.group("AL0") as al_0:
            node_4 = zntrack.examples.ParamsToOuts(params="Adipiscing Elit")

    project.run()

    assert node_1.nwd == pathlib.Path("nodes", "AL0", "ParamsToOuts")
    assert node_2.nwd == pathlib.Path("nodes", "AL0", "ParamsToOuts_1")
    assert node_3.nwd == pathlib.Path("nodes", "AL0", "ParamsToOuts_2")

    assert node_4.nwd == pathlib.Path("nodes", "AL0", "ParamsToOuts_3")


def test_nested_groups(proj_path):
    with zntrack.Project(automatic_node_names=True) as project:
        with project.group("AL0") as al_0:
            node_1 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
        with project.group("AL0", "CPU") as al_0_cpu:
            node_2 = zntrack.examples.ParamsToOuts(params="Dolor Sit")
        with project.group("AL0", "GPU") as al_0_gpu:
            node_3 = zntrack.examples.ParamsToOuts(params="Amet Consectetur")

    project.run()
    project.load()

    assert node_1.nwd == pathlib.Path("nodes", "AL0", "ParamsToOuts")
    assert node_2.nwd == pathlib.Path("nodes", "AL0", "CPU", "ParamsToOuts")
    assert node_3.nwd == pathlib.Path("nodes", "AL0", "GPU", "ParamsToOuts")

    assert node_1.outs == "Lorem Ipsum"
    assert node_2.outs == "Dolor Sit"
    assert node_3.outs == "Amet Consectetur"


def test_nested_groups_direct_enter(proj_path):
    project = zntrack.Project(automatic_node_names=True)

    with project.group("AL0") as al_0:
        node_1 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
    with project.group("AL0", "CPU") as al_0_cpu:
        node_2 = zntrack.examples.ParamsToOuts(params="Dolor Sit")
    with project.group("AL0", "GPU") as al_0_gpu:
        node_3 = zntrack.examples.ParamsToOuts(params="Amet Consectetur")

    project.run()
    project.load()

    assert node_1.nwd == pathlib.Path("nodes", "AL0", "ParamsToOuts")
    assert node_2.nwd == pathlib.Path("nodes", "AL0", "CPU", "ParamsToOuts")
    assert node_3.nwd == pathlib.Path("nodes", "AL0", "GPU", "ParamsToOuts")

    assert node_1.outs == "Lorem Ipsum"
    assert node_2.outs == "Dolor Sit"
    assert node_3.outs == "Amet Consectetur"


def test_group_dvc_outs(proj_path):
    project = zntrack.Project(automatic_node_names=True)

    with project.group("GRP1") as grp1:
        node = zntrack.examples.WriteDVCOuts(params="Hello World")

    project.run()

    assert node.outs == pathlib.Path("nodes", "GRP1", "WriteDVCOuts", "output.txt")
    assert zntrack.examples.WriteDVCOuts.from_rev(node.name).outs == pathlib.Path(
        "nodes", "GRP1", "WriteDVCOuts", "output.txt"
    )


@pytest.mark.parametrize("git_only_repo", [True, False])
def test_git_only_repo(proj_path, git_only_repo):
    with zntrack.Project(git_only_repo=git_only_repo) as project:
        zntrack.examples.ParamsToOuts(params="Lorem Ipsum")

    project.run()

    # commit everything
    repo = git.Repo()
    repo.git.add(".")
    repo.index.commit("initial commit")

    if git_only_repo:
        # check if node-meta.json is in the repo index
        assert ("nodes/ParamsToOuts/node-meta.json", 0) in repo.index.entries.keys()
    else:
        # check if node-meta.json is not in the repo index
        assert ("nodes/ParamsToOuts/node-meta.json", 0) not in repo.index.entries.keys()


def test_auto_remove(proj_path):
    with zntrack.Project(automatic_node_names=True) as project:
        n1 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
        n2 = zntrack.examples.ParamsToOuts(params="Dolor Sit")

    project.run()

    n1 = zntrack.examples.ParamsToOuts.from_rev(n1.name)
    n2 = zntrack.examples.ParamsToOuts.from_rev(n2.name)
    assert n1.outs == "Lorem Ipsum"
    assert n2.outs == "Dolor Sit"

    repo = git.Repo()
    repo.git.add(".")
    repo.index.commit("initial commit")

    with zntrack.Project(automatic_node_names=True) as project:
        n1 = zntrack.examples.ParamsToOuts(params="Hello World")

    project.run(auto_remove=True)

    n1 = zntrack.examples.ParamsToOuts.from_rev(n1.name)
    with pytest.raises(zntrack.exceptions.NodeNotAvailableError):
        n2 = zntrack.examples.ParamsToOuts.from_rev(n2.name)


def test_magic_names(proj_path):
    node = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
    assert node.name == "ParamsToOuts"
    with pytest.raises(ValueError):
        project = zntrack.Project(magic_names=True, automatic_node_names=True)

    project = zntrack.Project(magic_names=True, automatic_node_names=False)
    with project:
        node01 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
        node02 = zntrack.examples.ParamsToOuts(params="Dolor Sit")
        node03 = zntrack.examples.ParamsToOuts(params="Test01")
    assert node01.name == "node01"
    assert node02.name == "node02"
    assert node03.name == "node03"

    with project.group("Grp01"):
        node01 = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")
        node02 = zntrack.examples.ParamsToOuts(params="Dolor Sit")
        grp_node03 = zntrack.examples.ParamsToOuts(params="Test02")

    assert node01.name == "Grp01_node01"
    assert node02.name == "Grp01_node02"
    assert grp_node03.name == "Grp01_grp_node03"

    project.run()

    zntrack.from_rev(node01.name).outs == "Lorem Ipsum"
    zntrack.from_rev(node02.name).outs == "Dolor Sit"
    zntrack.from_rev(node03.name).outs == "Test01"
    zntrack.from_rev(grp_node03.name).outs == "Test02"


def test_project_run_load(proj_path):
    """Ensure Nodes are loaded after project is run from the same script."""

    project = zntrack.Project()

    with project:
        node = zntrack.examples.ParamsToOuts(params="Lorem Ipsum")

    project.run()

    assert node.outs == "Lorem Ipsum"
