import os
import pathlib

import git

import zntrack.examples


def test_patch_open(proj_path):
    with zntrack.Project() as proj:
        node = zntrack.examples.WriteDVCOuts(params="Hello World")

    proj.run()

    repo = git.Repo()

    repo.git.add(A=True)
    commit = repo.index.commit("initial commit")

    node.params = "Lorem Ipsum"
    proj.run()

    node = zntrack.examples.WriteDVCOuts.from_rev(rev=commit.hexsha)

    with node.state.magic_patch():
        with open(node.outs, "r") as f:
            assert f.read() == "Hello World"
        assert pathlib.Path(node.outs).read_text() == "Hello World"
        with pathlib.Path(node.outs).open("r") as f:
            assert f.read() == "Hello World"

    with open(node.outs, "r") as f:
        assert f.read() == "Lorem Ipsum"
    assert pathlib.Path(node.outs).read_text() == "Lorem Ipsum"
    with pathlib.Path(node.outs).open("r") as f:
        assert f.read() == "Lorem Ipsum"

    listdir = os.listdir(node.nwd)

    with node.state.magic_patch():
        os.listdir(node.nwd) == listdir


def test_patch_list(proj_path):
    node = zntrack.from_rev(
        "HelloWorld",
        remote="https://github.com/PythonFZ/ZnTrackExamples.git",
        rev="fbb6ada",
    )

    def func(self, path):
        return os.listdir(path)

    type(node).list = func

    with node.state.magic_patch():
        assert "nodes/HelloWorld/random_number.json" in node.list(node.nwd)
        assert "nodes/HelloWorld/node-meta.json" in node.list(node.nwd)

    assert node.list(node.nwd) == []
