import json
import os
import pathlib
from unittest.mock import mock_open, patch

import pytest
import yaml

from zntrack.utils import file_io


def test_save_file_json():
    open_mock = mock_open(read_data=None)

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        file_io.write_file(pathlib.Path("example.json"), {"a": "b"})

        # use to check the calls
        # assert open_mock.mock_calls == {}

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("example.json")

        open_mock().write.assert_called_once_with(json.dumps({"a": "b"}, indent=4))


def test_save_file_yaml():
    open_mock = mock_open(read_data=None)

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        file_io.write_file(pathlib.Path("example.yaml"), {"a": "b"})

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("example.yaml")
        open_mock().write.assert_called_once_with(
            yaml.safe_dump({"a": "b"}, indent=4, default_style="|")
        )


def test_save_file_yaml_mkdir(tmp_path):
    os.chdir(tmp_path)
    file_io.write_file(pathlib.Path("src", "example.yaml"), {"a": "b"}, mkdir=True)
    assert pathlib.Path("src").is_dir()


def test_save_file_yml():
    open_mock = mock_open(read_data=None)

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        file_io.write_file(pathlib.Path("example.yml"), {"a": "b"})

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("example.yml")
        open_mock().write.assert_called_once_with(
            yaml.safe_dump({"a": "b"}, indent=4, default_style="|")
        )


def test_save_file_txt():
    with pytest.raises(ValueError):
        file_io.write_file(pathlib.Path("example.txt"), {"a": "b"})


def test_read_file_json():
    open_mock = mock_open(read_data=json.dumps({"a": "b"}))

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        assert file_io.read_file(pathlib.Path("example.json")) == {"a": "b"}

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("example.json")


def test_read_file_yaml():
    open_mock = mock_open(read_data=yaml.safe_dump({"a": "b"}))

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        assert file_io.read_file(pathlib.Path("example.yaml")) == {"a": "b"}

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("example.yaml")


def test_read_file_yml():
    open_mock = mock_open(read_data=yaml.safe_dump({"a": "b"}))

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        assert file_io.read_file(pathlib.Path("example.yml")) == {"a": "b"}

        args, kwargs = open_mock.call_args
        assert args[0] == pathlib.Path("example.yml")


def test_read_file_txt():
    with pytest.raises(ValueError):
        file_io.read_file(pathlib.Path("example.txt"))


def test_update_config_file_json():
    open_mock = mock_open(
        read_data=json.dumps(
            {"Node1": {"param1": 1, "param2": 2}, "Node2": {"param1": 3, "param2": 4}}
        )
    )

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        file_io.update_config_file(
            file=pathlib.Path("params.json"),
            node_name="Node1",
            value_name="param2",
            value=42,
        )
    open_mock().write.assert_called_once_with(
        json.dumps(
            {"Node1": {"param1": 1, "param2": 42}, "Node2": {"param1": 3, "param2": 4}},
            indent=4,
        )
    )


def test_update_config_file_new_param():
    open_mock = mock_open(
        read_data=json.dumps(
            {"Node1": {"param1": 1, "param2": 2}, "Node2": {"param1": 3, "param2": 4}}
        )
    )

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        file_io.update_config_file(
            file=pathlib.Path("params.json"),
            node_name="Node1",
            value_name="param3",
            value=3,
        )
    open_mock().write.assert_called_once_with(
        json.dumps(
            {
                "Node1": {"param1": 1, "param2": 2, "param3": 3},
                "Node2": {"param1": 3, "param2": 4},
            },
            indent=4,
        )
    )


def test_update_config_file_new_node():
    open_mock = mock_open(
        read_data=json.dumps(
            {"Node1": {"param1": 1, "param2": 2}, "Node2": {"param1": 3, "param2": 4}}
        )
    )

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        file_io.update_config_file(
            file=pathlib.Path("params.json"),
            node_name="Node3",
            value_name="param1",
            value=1,
        )
    open_mock().write.assert_called_once_with(
        json.dumps(
            {
                "Node1": {"param1": 1, "param2": 2},
                "Node2": {"param1": 3, "param2": 4},
                "Node3": {"param1": 1},
            },
            indent=4,
        )
    )


def test_update_config_file_yaml():
    open_mock = mock_open(
        read_data=yaml.safe_dump(
            {"Node1": {"param1": 1, "param2": 2}, "Node2": {"param1": 3, "param2": 4}}
        )
    )

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    with patch.object(pathlib.Path, "open", pathlib_open):
        file_io.update_config_file(
            file=pathlib.Path("params.yaml"),
            node_name="Node1",
            value_name="param2",
            value=42,
        )
    open_mock().write.assert_called_once_with(
        yaml.safe_dump(
            {"Node1": {"param1": 1, "param2": 42}, "Node2": {"param1": 3, "param2": 4}},
            indent=4,
            default_style="|",
        )
    )


def test_update_config_error():
    with pytest.raises(ValueError):
        file_io.update_config_file(
            file="file.txt", node_name=None, value_name=None, value={}
        )


@pytest.mark.parametrize("desc", ("Lorem Ipsum", None, ""))
def test_update_desc(desc):
    dvc_dict = {"stages": {"MyNode": {"cmd": "run"}}}

    open_mock = mock_open(read_data=yaml.safe_dump(dvc_dict))

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    file = pathlib.Path("dvc.yaml")

    with patch.object(pathlib.Path, "open", pathlib_open):
        file_io.update_desc(file, node_name="MyNode", desc=desc)

    if desc is not None:
        dvc_dict["stages"]["MyNode"]["desc"] = desc
        open_mock().write.assert_called_once_with(
            yaml.safe_dump(dvc_dict, indent=4, default_style="|")
        )
    else:
        assert not open_mock().called


@pytest.mark.parametrize("data", ({"author": "Fabian"}, None))
def test_update_meta(data):
    dvc_dict = {"stages": {"MyNode": {"cmd": "run", "meta": {"a": "b"}}}}

    open_mock = mock_open(read_data=yaml.safe_dump(dvc_dict))

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    file = pathlib.Path("dvc.yaml")

    with patch.object(pathlib.Path, "open", pathlib_open):
        file_io.update_meta(file=file, node_name="MyNode", data=data)

    if data is not None:
        dvc_dict["stages"]["MyNode"]["meta"].update(data)
        open_mock().write.assert_called_once_with(yaml.safe_dump(dvc_dict, indent=4))
    else:
        assert not open_mock().called


def test_update_meta_existing():
    dvc_dict = {"stages": {"MyNode": {"meta": "not a dict"}}}
    open_mock = mock_open(read_data=yaml.safe_dump(dvc_dict))

    def pathlib_open(*args, **kwargs):
        return open_mock(*args, **kwargs)

    file = pathlib.Path("dvc.yaml")

    with patch.object(pathlib.Path, "open", pathlib_open):
        with pytest.raises(ValueError):
            file_io.update_meta(file=file, node_name="MyNode", data={"a": "b"})
