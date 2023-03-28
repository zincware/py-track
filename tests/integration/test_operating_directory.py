import pathlib
import subprocess
import time

import pytest

from zntrack import Node, dvc, exceptions, utils, zn


class ListOfDataNode(Node):
    data: list = zn.outs()

    def run(self):
        with self.operating_directory(move_on=None) as new:
            if new:
                self.data = list(range(5))
                raise ValueError("Execution was interrupted")
            else:
                self.data += list(range(5, 10))


class RestartFromCheckpoint(Node):
    file: pathlib.Path = dvc.outs(utils.nwd / "out.txt")

    def run(self):
        with self.operating_directory(move_on=None) as new:
            if new:
                self.file.write_text("Hello")
                raise ValueError("Execution was interrupted")
            else:
                text = self.file.read_text()
                self.file.write_text(f"{text} there")


class RemoveOnError(Node):
    data: list = zn.outs()

    def run(self):
        with self.operating_directory(remove_on=(TypeError, ValueError)):
            raise ValueError("Execution was interrupted")


class MoveOnError(Node):
    data: list = zn.outs()

    def run(self):
        with self.operating_directory(move_on=(TypeError, ValueError)):
            self.data = list(range(5))
            raise ValueError("Execution was interrupted")


def test_remove_on_error(proj_path):
    node = RemoveOnError()
    node.write_graph()

    node = RemoveOnError.load()
    with pytest.raises(ValueError):
        node.run()
        node.save()

    nwd_new = node.nwd.with_name(f"ckpt_{node.nwd.name}")
    assert not nwd_new.exists()

    node = node.load()
    with pytest.raises(exceptions.DataNotAvailableError):
        _ = node.data


def test_move_on_error(proj_path):
    node = MoveOnError()
    node.write_graph()

    node = MoveOnError.load()
    with pytest.raises(ValueError):
        node.run()
        node.save()

    nwd_new = node.nwd.with_name(f"ckpt_{node.nwd.name}")
    assert not nwd_new.exists()
    #  the file exists but even if 'run_and_save' fails so the output can be investigated.
    node = node.load()
    assert node.data == list(range(5))


def test_ListOfDataNode(proj_path):
    ListOfDataNode().write_graph()

    node = ListOfDataNode.load()

    with pytest.raises(exceptions.DVCProcessError):
        utils.run_dvc_cmd(["repro"])
    nwd_new = node.nwd.with_name(f"ckpt_{node.nwd.name}")
    assert nwd_new.exists()
    utils.run_dvc_cmd(["repro"])
    assert not nwd_new.exists()

    assert ListOfDataNode.load().data == list(range(10))


def test_ListOfDataNode2(proj_path):
    node = ListOfDataNode()
    node.write_graph()

    with pytest.raises(ValueError):
        node.run()
        node.save()
    node.run()
    node.save()

    assert node.load().data == list(range(10))


def test_RestartFromCheckpoint(proj_path):
    RestartFromCheckpoint().write_graph()

    with pytest.raises(exceptions.DVCProcessError):
        utils.run_dvc_cmd(["repro"])

    assert not RestartFromCheckpoint.load().file.exists()
    utils.run_dvc_cmd(["repro"])

    assert RestartFromCheckpoint.load().file.read_text() == "Hello there"


def test_RestartFromCheckpoint2(proj_path):
    node = RestartFromCheckpoint()
    node.write_graph()

    with pytest.raises(ValueError):
        node.run()
        node.save()

    node.run()
    node.save()

    assert node.load().file.read_text() == "Hello there"


class WriteNumbersSlow(Node):
    outs = zn.outs()
    maximum = zn.params()

    def run(self):
        with self.operating_directory() as new:
            if new:
                self.outs = []
            for x in range(len(self.outs), self.maximum):
                print(x)
                self.outs.append(x)
                self.save(results=True)
                time.sleep(0.1)


def test_kill_process(proj_path):
    node = WriteNumbersSlow(maximum=15)
    node.write_graph()
    nwd_new = node.nwd.with_name(f"ckpt_{node.nwd.name}")
    # killing the DVC process will not kill the python process as it would on
    #  a cluster
    proc = subprocess.Popen(
        ["zntrack", "run", "test_operating_directory.WriteNumbersSlow"]
    )
    time.sleep(2.0)
    proc.kill()
    assert nwd_new.exists()

    # zntrack.utils.run_dvc_cmd(["repro"])
    proc = subprocess.Popen(
        ["zntrack", "run", "test_operating_directory.WriteNumbersSlow"]
    )
    proc.wait()
    assert not nwd_new.exists()
    assert node.load().outs == list(range(15))

    # and now check again without killing
    node = WriteNumbersSlow(maximum=10)
    node.write_graph()
    zntrack.utils.run_dvc_cmd(["repro"])
    assert not nwd_new.exists()
    assert node.load().outs == list(range(10))


def test_disable_operating_directory(proj_path):
    ListOfDataNode().write_graph()
    with utils.config.updated_config(disable_operating_directory=True):
        node = ListOfDataNode.load()

        with pytest.raises(ValueError):
            ListOfDataNode.load().run_and_save()
        with pytest.raises(ValueError):  # running it twice does not change the outcome
            ListOfDataNode.load().run_and_save()
        assert node.nwd.exists()
        assert not node.nwd.with_name(f"ckpt_{node.nwd.name}").exists()

        with pytest.raises(exceptions.DataNotAvailableError):
            _ = ListOfDataNode.load().data
