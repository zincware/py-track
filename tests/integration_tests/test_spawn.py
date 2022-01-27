import itertools
import os
import shutil
import subprocess

import pytest

from zntrack import SpawnNode, zn


@pytest.fixture
def proj_path(tmp_path):
    shutil.copy(__file__, tmp_path)
    os.chdir(tmp_path)
    subprocess.check_call(["git", "init"])
    subprocess.check_call(["dvc", "init"])

    return tmp_path


class SimpleSpawn(SpawnNode):
    param1 = zn.iterable([1, 2, 3])
    result = zn.outs()

    def run(self):
        self.result = self.param1


def test_simple_spawn(proj_path):
    SimpleSpawn().write_graph(no_exec=False)

    for node, value in zip(SimpleSpawn.load(), [1, 2, 3]):
        assert node.param1 == value
        assert node.result == value


def test_simple_spawn_w_name(proj_path):
    SimpleSpawn(name="TestNode").write_graph(no_exec=False)

    for node, value in zip(SimpleSpawn.load(name="TestNode"), [1, 2, 3]):
        assert node.param1 == value
        assert node.result == value


class GridSpawn(SpawnNode):
    param1 = zn.iterable([1, 2, 3])
    param2 = zn.iterable([1, 2, 3])

    result = zn.outs()

    def run(self):
        self.result = [self.param1, self.param2]


def test_grid_spawn(proj_path):
    GridSpawn().write_graph(no_exec=False)

    for node, (value1, value2) in zip(
        GridSpawn.load(), itertools.product([1, 2, 3], [1, 2, 3])
    ):
        assert node.param1 == value1
        assert node.param2 == value2
        assert node.result == [value1, value2]


def test_grid_spawn_w_name(proj_path):
    GridSpawn(name="test_node").write_graph(no_exec=False)

    for node, (value1, value2) in zip(
        GridSpawn.load(name="test_node"), itertools.product([1, 2, 3], [1, 2, 3])
    ):
        assert node.param1 == value1
        assert node.param2 == value2
        assert node.result == [value1, value2]


class GridSpawnFiltered(SpawnNode):
    param1 = zn.iterable([1, 2, 3])
    param2 = zn.iterable([1, 2, 3])

    result = zn.outs()

    def run(self):
        self.result = [self.param1, self.param2]

    def spawn_filter(self, param1, param2) -> bool:
        return param1 == param2


def test_grid_spawn_filtered(proj_path):
    GridSpawnFiltered().write_graph(no_exec=False)

    for node, value in zip(GridSpawnFiltered.load(), [1, 2, 3]):
        assert node.param1 == value
        assert node.param2 == value
        assert node.result == [value, value]


def test_grid_spawn_filtered_w_name(proj_path):
    GridSpawnFiltered(name="test_node").write_graph(no_exec=False)

    for node, value in zip(GridSpawnFiltered.load(name="test_node"), [1, 2, 3]):
        assert node.param1 == value
        assert node.param2 == value
        assert node.result == [value, value]


class SimpleSpawnWithInit(SpawnNode):
    param1 = zn.iterable()
    result = zn.outs()

    def __init__(self, param1=None, **kwargs):
        super().__init__(**kwargs)
        self.param1 = param1

    def run(self):
        self.result = self.param1


def test_simple_spawn_with_init(proj_path):
    SimpleSpawnWithInit(param1=[1, 2, 3]).write_graph(no_exec=False)

    for node, value in zip(SimpleSpawnWithInit.load(), [1, 2, 3]):
        assert node.param1 == value
        assert node.result == value


def test_simple_spawn_with_init_w_name(proj_path):
    SimpleSpawnWithInit(param1=[1, 2, 3], name="test_node").write_graph(no_exec=False)

    for node, value in zip(SimpleSpawnWithInit.load(name="test_node"), [1, 2, 3]):
        assert node.param1 == value
        assert node.result == value
