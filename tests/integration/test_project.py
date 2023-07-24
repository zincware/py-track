import json
import pathlib

import pytest

import zntrack
from zntrack.project import Experiment


class WriteIO(zntrack.Node):
    inputs = zntrack.zn.params()
    outputs = zntrack.zn.outs()

    def run(self) -> None:
        self.outputs = self.inputs


class ZnNodesNode(zntrack.Node):
    """Used zn.nodes"""

    node = zntrack.zn.nodes()
    result = zntrack.zn.outs()

    def run(self) -> None:
        self.result = self.node.inputs


@pytest.mark.parametrize("assert_before_exp", [True, False])
def test_WriteIO(tmp_path_2, assert_before_exp):
    """Test the WriteIO node."""
    with zntrack.Project() as project:
        node = WriteIO(inputs="Hello World")

    project.run()
    node.load()
    if assert_before_exp:
        assert node.outputs == "Hello World"

    # write a non-tracked file using pathlib
    pathlib.Path("test.txt").write_text("Hello World")

    with project.create_experiment(name="exp1") as exp1:
        node.inputs = "Hello World"

    # check that the file is still there
    assert pathlib.Path("test.txt").read_text() == "Hello World"

    with project.create_experiment(name="exp2") as exp2:
        node.inputs = "Lorem Ipsum"

    assert exp1.name == "exp1"
    assert exp2.name == "exp2"

    assert project.experiments.keys() == {"exp1", "exp2"}

    assert isinstance(project.experiments["exp1"], Experiment)

    project.run_exp()
    assert node.from_rev(rev="exp1").inputs == "Hello World"
    assert node.from_rev(rev="exp1").outputs == "Hello World"

    assert node.from_rev(rev="exp2").inputs == "Lorem Ipsum"
    assert node.from_rev(rev="exp2").outputs == "Lorem Ipsum"

    exp2.apply()
    assert (
        zntrack.from_rev("WriteIO").inputs
        == zntrack.from_rev("WriteIO", rev=exp2.name).inputs
    )
    exp1.apply()
    assert (
        zntrack.from_rev("WriteIO").inputs
        == zntrack.from_rev("WriteIO", rev=exp1.name).inputs
    )


@pytest.mark.parametrize("assert_before_exp", [True, False])
def test_WriteIO_no_name(tmp_path_2, assert_before_exp):
    """Test the WriteIO node."""
    with zntrack.Project() as project:
        node = WriteIO(inputs="Hello World")

    project.run()
    node.load()
    if assert_before_exp:
        assert node.outputs == "Hello World"

    with project.create_experiment() as exp1:
        node.inputs = "Hello World"

    with project.create_experiment() as exp2:
        node.inputs = "Lorem Ipsum"

    project.run_exp()

    exp1.load()
    assert exp1.nodes["WriteIO"].inputs == "Hello World"
    assert exp1.nodes["WriteIO"].outputs == "Hello World"

    assert exp1["WriteIO"].inputs == "Hello World"
    assert exp1["WriteIO"].outputs == "Hello World"

    exp2.load()
    assert exp2.nodes["WriteIO"].inputs == "Lorem Ipsum"
    assert exp2.nodes["WriteIO"].outputs == "Lorem Ipsum"

    assert exp2["WriteIO"].inputs == "Lorem Ipsum"
    assert exp2["WriteIO"].outputs == "Lorem Ipsum"

    assert zntrack.from_rev("WriteIO", rev=exp1.name).inputs == "Hello World"
    assert zntrack.from_rev("WriteIO", rev=exp1.name).outputs == "Hello World"

    assert zntrack.from_rev("WriteIO", rev=exp2.name).inputs == "Lorem Ipsum"
    assert zntrack.from_rev("WriteIO", rev=exp2.name).outputs == "Lorem Ipsum"


def test_project_remove_graph(proj_path):
    with zntrack.Project() as project:
        node = WriteIO(inputs="Hello World")
    project.run()
    node.load()
    assert node.outputs == "Hello World"

    with zntrack.Project(remove_existing_graph=True) as project:
        node2 = WriteIO(inputs="Lorem Ipsum", name="node2")
    project.run()
    node2.load()
    assert node2.outputs == "Lorem Ipsum"
    with pytest.raises(zntrack.exceptions.NodeNotAvailableError):
        node.load()


def test_project_repr_node(tmp_path_2):
    with zntrack.Project() as project:
        node = WriteIO(inputs="Hello World")
        print(node)


def test_automatic_node_names_False(tmp_path_2):
    with pytest.raises(zntrack.exceptions.DuplicateNodeNameError):
        with zntrack.Project(automatic_node_names=False) as project:
            _ = WriteIO(inputs="Hello World")
            _ = WriteIO(inputs="Lorem Ipsum")
    with pytest.raises(zntrack.exceptions.DuplicateNodeNameError):
        with zntrack.Project(automatic_node_names=False) as project:
            _ = WriteIO(inputs="Hello World", name="NodeA")
            _ = WriteIO(inputs="Lorem Ipsum", name="NodeA")


def test_automatic_node_names_default(tmp_path_2):
    with zntrack.Project(automatic_node_names=False) as project:
        _ = WriteIO(inputs="Hello World")
        _ = WriteIO(inputs="Lorem Ipsum", name="WriteIO2")


def test_automatic_node_names_True(tmp_path_2):
    with zntrack.Project(automatic_node_names=True) as project:
        node = WriteIO(inputs="Hello World")
        node2 = WriteIO(inputs="Lorem Ipsum")
        assert node.name == "WriteIO"
        assert node2.name == "WriteIO_1"
    project.run()

    with project:
        node3 = WriteIO(inputs="Dolor Sit")
        assert node3.name == "WriteIO_2"

    project.run()

    assert node.name == "WriteIO"
    assert node2.name == "WriteIO_1"
    assert node3.name == "WriteIO_2"

    project.run()
    project.load()
    assert "WriteIO" in project.nodes
    assert "WriteIO_1" in project.nodes
    assert "WriteIO_2" in project.nodes

    assert node.outputs == "Hello World"
    assert node2.outputs == "Lorem Ipsum"
    assert node3.outputs == "Dolor Sit"


def test_group_nodes(tmp_path_2):
    with zntrack.Project(automatic_node_names=True) as project:
        with project.group() as group_1:
            node_1 = WriteIO(inputs="Lorem Ipsum")
            node_2 = WriteIO(inputs="Dolor Sit")
        with project.group() as group_2:
            node_3 = WriteIO(inputs="Amet Consectetur")
            node_4 = WriteIO(inputs="Adipiscing Elit")
        with project.group(name="NamedGrp") as group_3:
            node_5 = WriteIO(inputs="Sed Do", name="NodeA")
            node_6 = WriteIO(inputs="Eiusmod Tempor", name="NodeB")

        node7 = WriteIO(inputs="Hello World")
        node8 = WriteIO(inputs="How are you?")
        node9 = WriteIO(inputs="I'm fine, thanks!", name="NodeC")

    project.run()

    assert node_1 in group_1
    assert node_2 in group_1
    assert node_3 not in group_1
    assert node_4 not in group_1
    assert len(group_1) == 2
    assert group_1.name == "Group1"

    assert node_3 in group_2
    assert node_4 in group_2
    assert node_5 in group_3
    assert node_6 in group_3

    assert node_1.name == "Group1_WriteIO"
    assert node_2.name == "Group1_WriteIO_1"
    assert node_3.name == "Group2_WriteIO"
    assert node_4.name == "Group2_WriteIO_1"

    assert node_5.name == "NamedGrp_NodeA"
    assert node_6.name == "NamedGrp_NodeB"

    assert node7.name == "WriteIO"
    assert node8.name == "WriteIO_1"
    assert node9.name == "NodeC"

    assert WriteIO.from_rev(name="NamedGrp_NodeA").inputs == "Sed Do"


def test_build_certain_nodes(tmp_path_2):
    # TODO support passing groups to project.build
    with zntrack.Project(automatic_node_names=True) as project:
        node_1 = WriteIO(inputs="Lorem Ipsum")
        node_2 = WriteIO(inputs="Dolor Sit")
    project.build(nodes=[node_1, node_2])
    project.repro()

    assert zntrack.from_rev(node_1).outputs == "Lorem Ipsum"
    assert zntrack.from_rev(node_2).outputs == "Dolor Sit"

    node_1.inputs = "ABC"
    node_2.inputs = "DEF"

    project.build(nodes=[node_1])
    project.repro()

    assert zntrack.from_rev(node_1).outputs == "ABC"
    assert zntrack.from_rev(node_2).outputs == "Dolor Sit"

    project.run(nodes=[node_2])

    assert zntrack.from_rev(node_1).outputs == "ABC"
    assert zntrack.from_rev(node_2).outputs == "DEF"


def test_build_groups(tmp_path_2):
    with zntrack.Project(automatic_node_names=True) as project:
        with project.group() as group_1:
            node_1 = WriteIO(inputs="Lorem Ipsum")
            node_2 = WriteIO(inputs="Dolor Sit")
        with project.group() as group_2:
            node_3 = WriteIO(inputs="Amet Consectetur")
            node_4 = WriteIO(inputs="Adipiscing Elit")

    project.run(nodes=[group_1])

    assert zntrack.from_rev(node_1).outputs == "Lorem Ipsum"
    assert zntrack.from_rev(node_2).outputs == "Dolor Sit"

    with pytest.raises(ValueError):
        zntrack.from_rev(node_3)
    with pytest.raises(ValueError):
        zntrack.from_rev(node_4)

    node_2.inputs = "DEF"

    project.run(nodes=[group_2, node_2])

    assert zntrack.from_rev(node_1).outputs == "Lorem Ipsum"

    assert zntrack.from_rev(node_2).outputs == "DEF"
    assert zntrack.from_rev(node_3).outputs == "Amet Consectetur"
    assert zntrack.from_rev(node_4).outputs == "Adipiscing Elit"

    with pytest.raises(TypeError):
        project.run(nodes=42)

    with pytest.raises(ValueError):
        project.run(nodes=[42])


def test_groups_nwd(tmp_path_2):
    with zntrack.Project(automatic_node_names=True) as project:
        node_1 = WriteIO(inputs="Lorem Ipsum")
        with project.group() as group_1:
            node_2 = WriteIO(inputs="Dolor Sit")
        with project.group(name="CustomGroup") as group_2:
            node_3 = WriteIO(inputs="Adipiscing Elit")

    project.build()

    assert node_1.nwd == pathlib.Path("nodes", node_1.name)
    assert node_2.nwd == pathlib.Path(
        "nodes", group_1.name, node_2.name.replace(f"{group_1.name}_", "")
    )
    assert node_3.nwd == pathlib.Path(
        "nodes", group_2.name, node_3.name.replace(f"{group_2.name}_", "")
    )
    # now load the Nodes and assert as well

    assert zntrack.from_rev(node_1).nwd == pathlib.Path("nodes", node_1.name)
    assert zntrack.from_rev(node_2).nwd == pathlib.Path(
        "nodes", group_1.name, node_2.name.replace(f"{group_1.name}_", "")
    )
    assert zntrack.from_rev(node_3).nwd == pathlib.Path(
        "nodes", group_2.name, node_3.name.replace(f"{group_2.name}_", "")
    )

    with open("zntrack.json") as f:
        data = json.load(f)
        data[node_1.name]["nwd"]["value"] = "test"
        data[node_2.name].pop("nwd")

    with open("zntrack.json", "w") as f:
        json.dump(data, f)

    assert zntrack.from_rev(node_1).nwd == pathlib.Path("test")
    assert zntrack.from_rev(node_2).nwd == pathlib.Path("nodes", node_2.name)
    assert zntrack.from_rev(node_3).nwd == pathlib.Path(
        "nodes", group_2.name, node_3.name.replace(f"{group_2.name}_", "")
    )


def test_groups_nwd_zn_nodes(tmp_path_2):
    node = WriteIO(inputs="Lorem Ipsum")
    with zntrack.Project(automatic_node_names=True) as project:
        node_1 = ZnNodesNode(node=node)
        with project.group() as group_1:
            node_2 = ZnNodesNode(node=node)
        with project.group(name="CustomGroup") as group_2:
            node_3 = ZnNodesNode(node=node)

    project.run()

    assert zntrack.from_rev(node_1).node.nwd == pathlib.Path("nodes/ZnNodesNode_node")
    assert zntrack.from_rev(node_2).node.nwd == pathlib.Path(
        "nodes", group_1.name, "ZnNodesNode_1_node"
    )
    assert zntrack.from_rev(node_3).node.nwd == pathlib.Path(
        "nodes", group_2.name, "ZnNodesNode_1_node"
    )

    project.load()
    assert node_1.result == "Lorem Ipsum"
    assert node_2.result == "Lorem Ipsum"
    assert node_3.result == "Lorem Ipsum"
