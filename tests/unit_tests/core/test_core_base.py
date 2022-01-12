import json
import pathlib
from unittest.mock import call, mock_open, patch

import pytest
import yaml

from zntrack import dvc, zn
from zntrack.core.base import Node


class ExampleDVCOutsNode(Node):
    outs = dvc.outs("example.dat")


def test_node_module():
    example = ExampleDVCOutsNode()
    assert example.module == "test_core_base"

    example._module = "src.base"
    assert example.module == "src.base"


def test_python_interpreter():
    example = ExampleDVCOutsNode()
    assert example.python_interpreter in ["python", "python3"]


class ExampleFullNode(Node):
    params = zn.params(10)
    zn_outs = zn.outs("outs")
    dvc_outs = dvc.outs("file.txt")
    deps = dvc.deps("deps.inp")


def test_save():
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
        example.save()

        # could not get it to work with assert_called_once_with
        assert zntrack_mock().write.mock_calls == [
            call(
                json.dumps(
                    {"ExampleFullNode": {"dvc_outs": "file.txt", "deps": "deps.inp"}},
                    indent=4,
                )
            )
        ]
        assert params_mock().write.mock_calls == [
            call(yaml.safe_dump({"ExampleFullNode": {"params": 10}}, indent=4))
        ]

        assert zn_outs_mock().write.mock_calls == [
            call(json.dumps({"zn_outs": "outs"}, indent=4))
        ]


def test__load():
    zntrack_mock = mock_open(
        read_data=json.dumps(
            {"ExampleFullNode": {"dvc_outs": "file_.txt", "deps": "deps_.inp"}},
            indent=4,
        )
    )
    params_mock = mock_open(read_data=yaml.safe_dump({"ExampleFullNode": {"params": 42}}))
    zn_outs_mock = mock_open(read_data=json.dumps({"zn_outs": "outs_"}))

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
        example._load()
        assert example.dvc_outs == "file_.txt"
        assert example.deps == "deps_.inp"
        assert example.params == 42
        assert example.zn_outs == "outs_"
        assert example.is_loaded


class CorrectNode(Node):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_name = self.node_name


class InCorrectNode(Node):
    def __init__(self):
        super().__init__()
        self.test_name = self.node_name


def test_load():
    default_correct_node = CorrectNode.load()
    assert default_correct_node.node_name == CorrectNode.__name__

    default_incorrect_node = InCorrectNode.load()
    assert default_incorrect_node.node_name == InCorrectNode.__name__

    correct_node = CorrectNode.load(name="Test")
    assert correct_node.node_name == "Test"
    assert correct_node.test_name == correct_node.node_name

    incorrect_node = InCorrectNode.load(name="Test")
    assert incorrect_node.node_name == "Test"
    with pytest.raises(AssertionError):
        assert incorrect_node.test_name == incorrect_node.node_name


class RunTestNode(Node):
    outs = zn.outs()

    def run(self):
        self.outs = 42


def test_run_and_save():
    open_mock = mock_open(read_data="{}")

    example = RunTestNode()

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        example.run_and_save()

        assert example.outs == 42

    assert open_mock().write.mock_calls == [
        call(json.dumps({"RunTestNode": {}}, indent=4)),
        call(yaml.safe_dump({"RunTestNode": {}})),
        call(json.dumps({"outs": 42}, indent=4)),
    ]
