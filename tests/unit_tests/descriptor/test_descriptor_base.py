import json
import pathlib
from unittest.mock import mock_open, patch

import pytest
import yaml

from zntrack import zn
from zntrack.descriptor.base import DescriptorIO


class ExampleClass(DescriptorIO):
    pass


def test_node_name_set():
    example = ExampleClass()
    example.node_name = "NamedExample"
    assert example.node_name == "NamedExample"


def test_save_file_json():
    example = ExampleClass()

    open_mock = mock_open(read_data=None)

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        example._write_file(pathlib.Path("example.json"), {"a": "b"})

        # use to check the calls
        # assert open_mock.mock_calls == {}

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("example.json")

        open_mock().write.assert_called_once_with(json.dumps({"a": "b"}, indent=4))


def test_save_file_yaml():
    example = ExampleClass()

    open_mock = mock_open(read_data=None)

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        example._write_file(pathlib.Path("example.yaml"), {"a": "b"})

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("example.yaml")
        open_mock().write.assert_called_once_with(yaml.safe_dump({"a": "b"}, indent=4))


def test_save_file_yml():
    example = ExampleClass()

    open_mock = mock_open(read_data=None)

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        example._write_file(pathlib.Path("example.yml"), {"a": "b"})

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("example.yml")
        open_mock().write.assert_called_once_with(yaml.safe_dump({"a": "b"}, indent=4))


def test_read_file_json():
    example = ExampleClass()

    open_mock = mock_open(read_data=json.dumps({"a": "b"}))

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        assert example._read_file(pathlib.Path("example.json")) == {"a": "b"}

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("example.json")


def test_read_file_yaml():
    example = ExampleClass()

    open_mock = mock_open(read_data=yaml.safe_dump({"a": "b"}))

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        assert example._read_file(pathlib.Path("example.yaml")) == {"a": "b"}

        open_mock.assert_called_with(pathlib.Path("example.yaml"), "r")


def test_read_file_yml():
    example = ExampleClass()

    open_mock = mock_open(read_data=yaml.safe_dump({"a": "b"}))

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        assert example._read_file(pathlib.Path("example.yml")) == {"a": "b"}

        open_mock.assert_called_with(pathlib.Path("example.yml"), "r")


def test_load_from_file():
    example = ExampleClass()

    open_mock = mock_open(read_data=yaml.safe_dump({"a": "b"}))

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        example._load_from_file(file=pathlib.Path("params.yaml"))
        assert getattr(example, "a") == "b"

        open_mock.assert_called_with(pathlib.Path("params.yaml"), "r")


def test_load_from_file_w_key():
    example = ExampleClass()

    open_mock = mock_open(read_data=yaml.safe_dump({"node_name": {"a": "b"}}))

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        example._load_from_file(file=pathlib.Path("params.yaml"), key="node_name")
        assert getattr(example, "a") == "b"

        open_mock.assert_called_with(pathlib.Path("params.yaml"), "r")


def test_load_from_file_err():
    example = ExampleClass()

    with pytest.raises(FileNotFoundError):
        example._load_from_file(file=pathlib.Path("param.yaml"), raise_file_error=True)

    assert example._load_from_file(file=pathlib.Path("param.yaml")) is None


class ExampleClassWithParams(DescriptorIO):
    param1 = zn.params(default_value=1)
    param2 = zn.params(default_value=2)


def test_save_to_file():
    example = ExampleClassWithParams()

    open_mock = mock_open(read_data="{}")

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        example._save_to_file(file=pathlib.Path("params.json"), zntrack_type="params")
        # example._write_file(pathlib.Path("example.json"), {"a": "b"})

        # use to check the calls
        # assert open_mock.mock_calls == {}

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("params.json")

        open_mock().write.assert_called_once_with(
            json.dumps({"param1": 1, "param2": 2}, indent=4)
        )


def test_save_to_file_w_key():
    example = ExampleClassWithParams()

    open_mock = mock_open(read_data="{}")

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        example._save_to_file(
            file=pathlib.Path("params.json"), zntrack_type="params", key="node_name"
        )
        # example._write_file(pathlib.Path("example.json"), {"a": "b"})

        # use to check the calls
        # assert open_mock.mock_calls == {}

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("params.json")

        open_mock().write.assert_called_once_with(
            json.dumps({"node_name": {"param1": 1, "param2": 2}}, indent=4)
        )


def test__descriptor_list():
    example = ExampleClassWithParams()

    assert len(example._descriptor_list.data) == 2


def test_descriptor_list_filter():
    example = ExampleClassWithParams()

    assert example._descriptor_list.filter(zntrack_type="params") == {
        "param1": 1,
        "param2": 2,
    }

    assert example._descriptor_list.filter(
        zntrack_type="params", return_with_type=True
    ) == {"params": {"param1": 1, "param2": 2}}
