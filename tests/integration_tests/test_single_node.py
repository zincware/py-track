import os
import shutil
import subprocess

from zntrack import dvc, zn
from zntrack.core.base import Node


class ExampleNode01(Node):
    inputs = dvc.params()
    outputs = zn.outs()

    def __init__(self, inputs=None):
        super().__init__()
        self.inputs = inputs

    def run(self):
        self.outputs = self.inputs


def test_run(tmp_path):
    shutil.copy(__file__, tmp_path)
    os.chdir(tmp_path)
    subprocess.check_call(["git", "init"])
    subprocess.check_call(["dvc", "init"])

    test_node_1 = ExampleNode01(inputs="Lorem Ipsum")
    test_node_1.write_graph()

    subprocess.check_call(["dvc", "repro"])

    load_test_node_1 = ExampleNode01.load()
    assert load_test_node_1.outputs == "Lorem Ipsum"
