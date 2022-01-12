import os
import shutil
import subprocess
from pathlib import Path

import pytest

from zntrack import dvc, zn
from zntrack.core.base import Node


class DVCOuts(Node):
    data_file: Path = dvc.outs()

    def __init__(self):
        super().__init__()
        self.data_file = Path("data")

    def run(self):
        self.data_file.write_text("Lorem Ipsum")


class ZnOuts(Node):
    data: str = zn.outs()

    def run(self):
        self.data = "Lorem Ipsum"


class DVCZnOuts(Node):
    data_file: Path = dvc.outs()
    data: str = zn.outs()

    def __init__(self):
        super().__init__()
        self.data_file = Path("data")

    def run(self):
        self.data_file.write_text("Lorem Ipsum")
        self.data = "Lorem Ipsum"


class DependenciesCollector(Node):
    dependencies = dvc.deps()

    def __init__(self, dependencies=None, name=None):
        super().__init__(name=name)
        self.dependencies = dependencies

    def run(self):
        pass


class DepsCollwOuts(Node):
    dependencies = dvc.deps()
    outs: Path = dvc.outs()

    def __init__(self, dependencies=None, name=None):
        super().__init__(name=name)
        # must add a name, if the Node is used with two different names to avoid
        # writing to the same file!
        self.outs = Path(f"{self.node_name}_lorem.txt")
        self.dependencies = dependencies

    def run(self):
        self.outs.write_text("Lorem Ipsum")


@pytest.fixture()
def dvc_repo_path(tmp_path):
    shutil.copy(__file__, tmp_path)
    os.chdir(tmp_path)
    subprocess.check_call(["git", "init"])
    subprocess.check_call(["dvc", "init"])

    return tmp_path


def test_dvc_outs(dvc_repo_path):
    os.chdir(dvc_repo_path)

    DVCOuts().write_graph()

    DependenciesCollector(dependencies=DVCOuts.load()).write_graph()

    subprocess.check_call(["dvc", "repro"])

    assert (
        DependenciesCollector.load().dependencies.data_file.read_text() == "Lorem Ipsum"
    )


def test_zn_outs(dvc_repo_path):
    os.chdir(dvc_repo_path)

    ZnOuts().write_graph()

    DependenciesCollector(dependencies=ZnOuts.load()).write_graph()

    subprocess.check_call(["dvc", "repro"])

    assert DependenciesCollector.load().dependencies.data == "Lorem Ipsum"


def test_dvc_zn_outs(dvc_repo_path):
    os.chdir(dvc_repo_path)

    DVCZnOuts().write_graph()

    DependenciesCollector(dependencies=DVCZnOuts.load()).write_graph()

    subprocess.check_call(["dvc", "repro"])

    assert (
        DependenciesCollector.load().dependencies.data_file.read_text() == "Lorem Ipsum"
    )

    assert DependenciesCollector.load().dependencies.data == "Lorem Ipsum"


def test_expand_dependencies(dvc_repo_path):
    os.chdir(dvc_repo_path)

    DVCZnOuts().write_graph()

    DependenciesCollector(name="Collector01", dependencies=DVCZnOuts.load()).write_graph()
    DependenciesCollector(name="Collector02", dependencies=DVCZnOuts.load()).write_graph()

    subprocess.check_call(["dvc", "repro"])

    assert (
        DependenciesCollector.load(name="Collector01").dependencies.data == "Lorem Ipsum"
    )
    assert (
        DependenciesCollector.load(name="Collector02").dependencies.data == "Lorem Ipsum"
    )


def test_exp_deps_w_outs(dvc_repo_path):
    """test_expand_dependencies_with_outs"""
    os.chdir(dvc_repo_path)

    DVCZnOuts().write_graph()

    DepsCollwOuts(name="Collector01", dependencies=DVCZnOuts.load()).write_graph()
    DepsCollwOuts(
        name="Collector02", dependencies=DepsCollwOuts.load(name="Collector01")
    ).write_graph()

    subprocess.check_call(["dvc", "repro"])

    assert DepsCollwOuts.load("Collector01").dependencies.data == "Lorem Ipsum"
    assert (
        DepsCollwOuts.load("Collector02").dependencies.dependencies.data == "Lorem Ipsum"
    )
