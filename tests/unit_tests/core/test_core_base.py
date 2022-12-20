import json
import os
import pathlib
from unittest.mock import MagicMock, call, mock_open, patch

import pytest
import yaml

from zntrack import dvc, utils, zn
from zntrack.core.base import (
    LoadViaGetItem,
    Node,
    _handle_nodes_as_methods,
    update_dependency_options,
)


class ExampleDVCOutsNode(Node):
    outs = dvc.outs("example.dat")


def test_node_module():
    example = ExampleDVCOutsNode()
    assert example.module == "test_core_base"

    example._module = "src.base"
    assert example.module == "src.base"


class ExampleFullNode(Node):
    params = zn.params(10)
    zn_outs = zn.outs()
    dvc_outs = dvc.outs("file.txt")
    deps = dvc.deps("deps.inp")

    def run(self):
        self.zn_outs = "outs"


class ExampleHashNode(Node):
    hash = zn.Hash()
    # None of these are tested, they should be ignored
    params = zn.params(10)
    zn_outs = zn.outs()
    dvc_outs = dvc.outs("file.txt")
    deps = dvc.deps("deps.inp")


@pytest.mark.parametrize("run", (True, False))
def test_save(run):
    zntrack_mock = mock_open(read_data="{}")
    params_mock = mock_open(read_data="{}")
    zn_outs_mock = mock_open(read_data="{}")

    example = ExampleFullNode()

    def pathlib_open(*args, **kwargs):
        if args[0] == pathlib.Path("zntrack.json"):
            return zntrack_mock(*args, **kwargs)
        elif args[0] == pathlib.Path("params.yaml"):
            return params_mock(*args, **kwargs)
        elif args[0] == pathlib.Path("nodes/ExampleFullNode/outs.json"):
            return zn_outs_mock(*args, **kwargs)
        else:
            raise ValueError(args)

    with patch.object(pathlib.Path, "open", pathlib_open):
        if run:
            example.run()
            example.save(results=True)
            assert zn_outs_mock().write.mock_calls == [
                call(json.dumps({"zn_outs": "outs"}, indent=4))
            ]
            assert not zntrack_mock().write.called
            assert not params_mock().write.called
        else:
            example.save()
            assert not zn_outs_mock().write.called
            assert zntrack_mock().write.mock_calls == [
                call(json.dumps({})),  # clear everything first
                call(
                    json.dumps(
                        {"ExampleFullNode": {"deps": "deps.inp"}},
                        indent=4,
                    )
                ),
                call(
                    json.dumps(
                        {"ExampleFullNode": {"dvc_outs": "file.txt"}},
                        indent=4,
                    )
                ),
            ]
            assert params_mock().write.mock_calls == [
                call(yaml.safe_dump({})),  # clear everything first
                call(
                    yaml.safe_dump(
                        {"ExampleFullNode": {"params": 10}}, indent=4, default_style="|"
                    )
                ),
            ]


def test_save_only_hash():
    zntrack_mock = mock_open(read_data="{}")
    params_mock = mock_open(read_data="{}")
    zn_outs_mock = mock_open(read_data="{}")
    hash_mock = mock_open(read_data="{}")

    example = ExampleFullNode()

    with pytest.raises(utils.exceptions.DescriptorMissingError):
        example.save(hash_only=True)

    def pathlib_open(*args, **kwargs):
        if args[0] == pathlib.Path("zntrack.json"):
            return zntrack_mock(*args, **kwargs)
        elif args[0] == pathlib.Path("params.yaml"):
            return params_mock(*args, **kwargs)
        elif args[0] == pathlib.Path("nodes/ExampleFullNode/outs.json"):
            return zn_outs_mock(*args, **kwargs)
        elif args[0] == pathlib.Path("nodes/ExampleHashNode/hash.json"):
            return hash_mock(*args, **kwargs)
        else:
            raise ValueError(args)

    example = ExampleHashNode()
    with patch.object(pathlib.Path, "open", pathlib_open):
        example.save(hash_only=True)
        assert not params_mock().write.called
        assert not zntrack_mock().write.called
        assert not zn_outs_mock().write.called
        assert hash_mock().write.called


def test__load():
    zntrack_mock = mock_open(
        read_data=json.dumps(
            {"ExampleFullNode": {"dvc_outs": "file_.txt", "deps": "deps_.inp"}},
            indent=4,
        )
    )
    params_mock = mock_open(read_data=yaml.safe_dump({"ExampleFullNode": {"params": 42}}))
    zn_outs_mock = mock_open(read_data=json.dumps({"zn_outs": "outs_"}))
    dvc_mock = mock_open(read_data=yaml.safe_dump({"stages": {"ExampleFullNode": None}}))

    example = ExampleFullNode()

    def pathlib_open(*args, **kwargs):
        if args[0] == pathlib.Path("zntrack.json"):
            return zntrack_mock(*args, **kwargs)
        elif args[0] == pathlib.Path("params.yaml"):
            return params_mock(*args, **kwargs)
        elif args[0] == pathlib.Path("nodes/ExampleFullNode/outs.json"):
            return zn_outs_mock(*args, **kwargs)
        elif args[0] == pathlib.Path("dvc.yaml"):
            # required for logging with __repr__ which uses '_graph_entry_exists'
            return dvc_mock(*args, **kwargs)
        else:
            raise ValueError(args)

    with patch.object(pathlib.Path, "open", pathlib_open):
        example._update_options()
        assert example.dvc_outs == "file_.txt"
        assert example.deps == "deps_.inp"
        assert example.params == 42
        assert example.zn_outs == "outs_"
        assert example.is_loaded


class CorrectNode(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.test_name = self.node_name


class InCorrectNode(Node):
    def __init__(self):
        super().__init__()
        self.test_name = self.node_name


def test_load():
    default_correct_node = CorrectNode.load()
    assert default_correct_node.node_name == CorrectNode.__name__
    default_correct_node = CorrectNode.load(name=None)
    assert default_correct_node.node_name == CorrectNode.__name__

    with pytest.raises(TypeError):
        # can not load a Node that misses a correct super().__init__(**kwargs)
        _ = InCorrectNode.load()

    with pytest.raises(TypeError):
        _ = InCorrectNode["Test"]

    correct_node = CorrectNode.load(name="Test")
    assert correct_node.node_name == "Test"
    assert correct_node.test_name == correct_node.node_name

    with pytest.raises(ValueError):
        CorrectNode.load(name=25)


class RunTestNode(Node):
    outs = zn.outs()

    def run(self):
        self.outs = 42


@pytest.mark.parametrize("is_loaded", (True, False))
def test_run_and_save(is_loaded):
    open_mock = mock_open(read_data="{}")

    example = RunTestNode()
    example.is_loaded = is_loaded

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        example.run_and_save()

        assert example.outs == 42

    if example.is_loaded:
        assert open_mock().write.mock_calls == [
            call(json.dumps({"outs": 42}, indent=4)),
        ]
    else:
        assert open_mock().write.mock_calls == [
            call("{}\n"),  # clear_config_file(utils.Files.params) in save
            call("{}"),  # clear_config_file(utils.Files.zntrack) in save
            call(json.dumps({"outs": 42}, indent=4)),
        ]


class WrongInit(Node):
    def __init__(self, non_default, **kwargs):
        super().__init__(**kwargs)


def test_WrongInit():
    """Test that a TypeError occurs if any value it not set to default in __init__"""
    with pytest.raises(TypeError):
        WrongInit.load()


def test_update_dependency_options():
    """Test update_dependency_options calls

    I'm not sure if this is the supposed way to use patch / MagicMock but it works
    """

    with patch(f"{__name__}.MagicMock", spec=Node):
        magic_mock = MagicMock()
        update_dependency_options(magic_mock)
        assert magic_mock._update_options.called

    with patch(f"{__name__}.MagicMock", spec=Node):
        magic_mock = MagicMock()
        update_dependency_options([magic_mock])
        assert magic_mock._update_options.called


class ZnTrackOptionCollection:
    param1: dict = zn.params()
    param2: list = zn.params([1, 2])
    param3 = zn.params()

    out1: str = dvc.outs()
    out2: pathlib.Path = dvc.outs()
    out3 = dvc.outs()

    result: int = zn.outs()
    result2 = zn.outs()

    no_option: int = 5
    no_option2 = 42


class CollectionChild(ZnTrackOptionCollection):
    pass


class NodeMock(metaclass=LoadViaGetItem):
    def load(self):
        pass


@pytest.mark.parametrize(
    ("key", "called"),
    [
        ("node", {"name": "node"}),
        ({"name": "node"}, {"name": "node"}),
        ({"name": "node", "lazy": True}, {"name": "node", "lazy": True}),
    ],
)
def test_LoadViaGetItem(key, called):
    with patch.object(NodeMock, "load") as mock:
        NodeMock[key]

    mock.assert_called_with(**called)


def test_matmul_not_supported():
    with pytest.raises(ValueError):
        # must be str
        RunTestNode @ 25

    with pytest.raises(ValueError):
        RunTestNode() @ 25

    with patch("zntrack.core.base.getdeps") as mock:
        # must patch the correct namespace
        # https://stackoverflow.com/a/16134754/10504481
        NodeMock @ "string"
        RunTestNode @ "outs"
        RunTestNode() @ "outs"

    assert mock.call_count == 3


def test_write_graph():
    example = ExampleDVCOutsNode()
    script = example.write_graph(dry_run=True)

    expected_script = [
        "stage",
        "add",
        "-n",
        "ExampleDVCOutsNode",
        "--force",
        "--outs",
        "example.dat",
        "zntrack run test_core_base.ExampleDVCOutsNode --name=ExampleDVCOutsNode",
    ]

    assert script == expected_script


def test__handle_nodes_as_methods():
    example = ExampleDVCOutsNode()

    with patch.object(ExampleDVCOutsNode, "write_graph") as write_graph_mock:
        _handle_nodes_as_methods({"example": example})

    write_graph_mock.assert_called_with(
        run=True, call_args=f"--name={example.node_name} --hash-only"
    )

    with patch.object(ExampleDVCOutsNode, "write_graph") as write_graph_mock:
        _handle_nodes_as_methods({"example": None})
    assert not write_graph_mock.called


def test_node_name(tmp_path):
    os.chdir(tmp_path)
    node = ExampleDVCOutsNode()
    assert node.node_name == "ExampleDVCOutsNode"
    assert node.nwd == pathlib.Path("nodes") / "ExampleDVCOutsNode"

    # load
    node = ExampleDVCOutsNode.load(name="MyNode")
    assert node.node_name == "MyNode"
    assert node.nwd == pathlib.Path("nodes") / "MyNode"

    # set
    node = ExampleDVCOutsNode()
    node.node_name = "MyNode"
    assert node.node_name == "MyNode"
    assert node.nwd == pathlib.Path("nodes") / "MyNode"

    node.nwd = pathlib.Path("nodes") / "CustomNWD"
    assert node.nwd == pathlib.Path("nodes") / "CustomNWD"
