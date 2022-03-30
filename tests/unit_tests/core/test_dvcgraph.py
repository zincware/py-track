import pathlib

import pytest

from zntrack import dvc, utils, zn
from zntrack.core.dvcgraph import (
    DVCRunOptions,
    GraphWriter,
    filter_ZnTrackOption,
    handle_deps,
    handle_dvc,
    prepare_dvc_script,
)


class ExampleDVCOutsNode(GraphWriter):
    is_loaded = False
    outs = dvc.outs(pathlib.Path("example.dat"))


def test_get_dvc_arguments():
    dvc_options = DVCRunOptions(
        force=True,
        always_changed=False,
        no_exec=True,
        external=False,
        no_commit=False,
        no_run_cache=False,
    )

    assert dvc_options.dvc_args == ["--no-exec", "--force"]


def test_handle_deps():
    assert handle_deps(["a.dat", "b.dat"]) == ["a.dat", "b.dat"]


def test_handle_deps_posix():
    """Change the path to posix for e.g. Windows users"""
    # TODO this does not really test anything, but I don't know how to fix that,
    #  because converting windows path to posix under linux does not work natively
    assert handle_deps(r"src\file.txt") in [
        ["src/file.txt"],
        [r"src\file.txt"],
    ]


def test_handle_dvc():
    assert handle_dvc(r"src\file.txt", "outs") in [
        ["--outs", "src/file.txt"],
        ["--outs", r"src\file.txt"],
    ]
    assert handle_dvc(["src/file.txt", "outs.txt"], "outs") == [
        "--outs",
        "src/file.txt",
        "--outs",
        "outs.txt",
    ]
    assert handle_dvc(("src/file.txt", "outs.txt"), "outs") == [
        "--outs",
        "src/file.txt",
        "--outs",
        "outs.txt",
    ]


def test_handle_deps_unknown():
    with pytest.raises(ValueError):
        handle_deps(handle_deps)


def test_handle_deps_node():
    assert handle_deps(ExampleDVCOutsNode()) == ["example.dat"]


class ExampleAffectedFiles(GraphWriter):
    is_loaded = False
    param = zn.params()
    zn_outs = zn.outs()
    zn_metrics = zn.metrics()
    dvc_outs = dvc.outs(pathlib.Path("dvc_outs.dat"))
    dvc_metrics = dvc.outs(pathlib.Path("dvc_metrics.json"))
    dvc_empty = dvc.outs()
    dvc_outs_lst = dvc.outs(["a.dat", "b.dat"])


def test_affected_files():
    example = ExampleAffectedFiles()

    assert example.affected_files == {
        pathlib.Path("dvc_metrics.json"),
        pathlib.Path("dvc_outs.dat"),
        pathlib.Path("nodes/ExampleAffectedFiles/metrics_no_cache.json"),
        pathlib.Path("nodes/ExampleAffectedFiles/outs.json"),
        "a.dat",
        "b.dat",
    }


class ExampleClassWithParams(GraphWriter):
    is_loaded = False
    param1 = zn.params(default_value=1)
    param2 = zn.params(default_value=2)


def test__descriptor_list():
    example = ExampleClassWithParams()

    assert len(example._descriptor_list) == 2


def test_descriptor_list_filter():
    example = ExampleClassWithParams()

    assert filter_ZnTrackOption(
        data=example._descriptor_list, cls=example, zn_type=utils.ZnTypes.PARAMS
    ) == {
        "param1": 1,
        "param2": 2,
    }

    assert filter_ZnTrackOption(
        data=example._descriptor_list,
        cls=example,
        zn_type=utils.ZnTypes.PARAMS,
        return_with_type=True,
    ) == {"params": {"param1": 1, "param2": 2}}


def test_prepare_dvc_script():
    dvc_run_option = DVCRunOptions(
        no_commit=False,
        external=True,
        always_changed=True,
        no_run_cache=False,
        no_exec=True,
        force=True,
    )

    script = prepare_dvc_script(
        node_name="node01",
        dvc_run_option=dvc_run_option,
        custom_args=["--deps", "file.txt"],
        nb_name=None,
        module="src.file",
        func_or_cls="MyNode",
        call_args=".load().run_and_save()",
    )

    assert script == [
        "dvc",
        "run",
        "-n",
        "node01",
        "--external",
        "--always-changed",
        "--no-exec",
        "--force",
        "--deps",
        "file.txt",
        f'{utils.get_python_interpreter()} -c "from src.file import MyNode;'
        ' MyNode.load().run_and_save()" ',
    ]

    script = prepare_dvc_script(
        node_name="node01",
        dvc_run_option=dvc_run_option,
        custom_args=["--deps", "file.txt"],
        nb_name="notebook.ipynb",
        module="src.file",
        func_or_cls="MyNode",
        call_args=".load().run_and_save()",
    )

    assert script == [
        "dvc",
        "run",
        "-n",
        "node01",
        "--external",
        "--always-changed",
        "--no-exec",
        "--force",
        "--deps",
        "file.txt",
        "--deps",
        "src/file.py",
        f'{utils.get_python_interpreter()} -c "from src.file import MyNode;'
        ' MyNode.load().run_and_save()" ',
    ]
