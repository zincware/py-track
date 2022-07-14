import os
import pathlib
import shutil
import subprocess
import typing

import pytest

from zntrack import dvc
from zntrack.core.base import Node


@pytest.fixture
def proj_path(tmp_path):
    shutil.copy(__file__, tmp_path)
    os.chdir(tmp_path)
    subprocess.check_call(["git", "init"])
    subprocess.check_call(["dvc", "init"])

    return tmp_path


class SingleNode(Node):
    path1: pathlib.Path = dvc.outs()

    def __init__(self, path_x=None, **kwargs):
        super().__init__(**kwargs)
        self.path1 = pathlib.Path(f"{path_x}.json")

    def run(self):
        self.path1.write_text("")


class SingleNodeListOut(Node):
    paths: typing.List[pathlib.Path] = dvc.outs()

    def __init__(self, paths=None, **kwargs):
        super().__init__(**kwargs)
        self.paths = paths

    def run(self):
        for path in self.paths:
            path.write_text("Lorem Ipsum")


def test_load_dvc_outs(proj_path):
    SingleNode(path_x="test", name="1500").write_graph(run=True)

    assert SingleNode.load(name="1500").path1 == pathlib.Path("test.json")


def test_multiple_outs(proj_path):
    SingleNodeListOut(
        paths=[pathlib.Path("test_1.txt"), pathlib.Path("test_2.txt")]
    ).write_graph(run=True)

    assert pathlib.Path("test_1.txt").read_text() == "Lorem Ipsum"
    assert pathlib.Path("test_2.txt").read_text() == "Lorem Ipsum"
    assert SingleNodeListOut.load().paths == [
        pathlib.Path("test_1.txt"),
        pathlib.Path("test_2.txt"),
    ]
