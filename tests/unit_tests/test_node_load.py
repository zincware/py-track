import pathlib

import subprocess
import pytest

import zntrack.config
import zntrack.examples
import zntrack.exceptions


def test_load_WriteDVCOuts(proj_path):
    with zntrack.Project() as project:
        node = zntrack.examples.WriteDVCOuts(params=42)

    assert node.__dict__["params"] == 42
    assert node.__dict__["outs"] == pathlib.Path("$nwd$/output.txt")

    assert node.params == 42
    assert node.outs == pathlib.Path("nodes/WriteDVCOuts/output.txt")

    assert node.__dict__["params"] == 42
    assert node.__dict__["outs"] == pathlib.Path("$nwd$/output.txt")


def test_load_ParamsToOuts(proj_path):
    with zntrack.Project() as project:
        node = zntrack.examples.ParamsToOuts(params=42)

    assert node.__dict__["params"] == 42
    assert node.__dict__["outs"] == zntrack.config.NOT_AVAILABLE

    assert node.params == 42
    assert node.outs == zntrack.config.NOT_AVAILABLE

    project.build()
    project.run()

    assert node.__dict__["params"] == 42
    assert node.__dict__["outs"] == 42

    assert node.params == 42
    assert node.outs == 42


def test_load_ParamsToOuts_from_rev(proj_path):
    with zntrack.Project() as project:
        zntrack.examples.ParamsToOuts(params=42)

    node = zntrack.examples.ParamsToOuts.from_rev()

    assert node.__dict__["params"] == zntrack.config.ZNTRACK_LAZY_VALUE
    assert node.__dict__["outs"] == zntrack.config.ZNTRACK_LAZY_VALUE

    with pytest.raises(zntrack.exceptions.NodeNotAvailableError):
        _ = node.params

    with pytest.raises(zntrack.exceptions.NodeNotAvailableError):
        _ = node.outs

    project.build()
    subprocess.run(["dvc", "repro"], cwd=proj_path, check=True)

    assert node.params == 42
    assert node.outs == 42


def test_load_WriteDVCOuts_from_rev(proj_path):
    with zntrack.Project() as project:
        zntrack.examples.WriteDVCOuts(params=42)

    node = zntrack.examples.WriteDVCOuts.from_rev()

    assert node.__dict__["params"] == zntrack.config.ZNTRACK_LAZY_VALUE
    assert node.__dict__["outs"] == zntrack.config.ZNTRACK_LAZY_VALUE

    with pytest.raises(zntrack.exceptions.NodeNotAvailableError):
        _ = node.params

    with pytest.raises(zntrack.exceptions.NodeNotAvailableError):
        _ = node.outs

    project.build()
    subprocess.run(["dvc", "repro"], cwd=proj_path, check=True)

    assert node.params == 42
    assert node.outs == pathlib.Path("nodes/WriteDVCOuts/output.txt")
