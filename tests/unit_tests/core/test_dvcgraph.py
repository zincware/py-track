import pathlib

from zntrack import dvc, zn
from zntrack.core.dvcgraph import GraphWriter, get_dvc_arguments, handle_deps


class ExampleDVCOutsNode(GraphWriter):
    outs = dvc.outs("example.dat")


def test_node_name_get():
    example = ExampleDVCOutsNode()
    assert example.node_name == "ExampleDVCOutsNode"
    example._node_name = "NamedExample"
    assert example.node_name == "NamedExample"


def test_get_dvc_arguments():
    assert get_dvc_arguments(
        {"force": True, "always_changed": False, "no_exec": True}
    ) == ["--force", "--no-exec"]


def test_handle_deps():
    assert handle_deps(["a.dat", "b.dat"]) == ["--deps", "a.dat", "--deps", "b.dat"]


def test_handle_deps_node():
    assert handle_deps(ExampleDVCOutsNode()) == ["--deps", pathlib.Path("example.dat")]


class ExampleAffectedFiles(GraphWriter):
    param = zn.params()
    zn_outs = zn.outs()
    zn_metrics = zn.metrics()
    dvc_outs = dvc.outs("dvc_outs.dat")
    dvc_metrics = dvc.outs("dvc_metrics.json")
    dvc_empty = dvc.outs()
    dvc_outs_lst = dvc.outs(["a.dat", "b.dat"])


def test_affected_files():
    example = ExampleAffectedFiles()

    assert example.affected_files == {
        pathlib.Path("dvc_metrics.json"),
        pathlib.Path("dvc_outs.dat"),
        pathlib.Path("nodes/ExampleAffectedFiles/metrics_no_cache.json"),
        pathlib.Path("nodes/ExampleAffectedFiles/outs.json"),
        pathlib.Path("a.dat"),
        pathlib.Path("b.dat"),
    }
