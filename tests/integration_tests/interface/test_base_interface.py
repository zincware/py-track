"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description:
"""
import os
import pathlib
import shutil
import subprocess

import pytest

from zntrack import Node, dvc, zn
from zntrack.interface import DVCInterface


class HelloWorld(Node):
    outputs = zn.outs()
    inputs = dvc.params()

    def __init__(self, inputs=None, name=None):
        super(HelloWorld, self).__init__(name=name)
        self.inputs = inputs

    def run(self):
        self.outputs = self.inputs


@pytest.fixture()
def single_experiment_path(tmp_path):
    shutil.copy(__file__, tmp_path)
    os.chdir(tmp_path)
    subprocess.run(["git", "init"])
    subprocess.run(["dvc", "init"])

    HelloWorld(inputs=1).write_graph()
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", "Init"])

    subprocess.run(["dvc", "repro"])

    return tmp_path


@pytest.fixture()
def multi_experiment_path(tmp_path):
    shutil.copy(__file__, tmp_path)
    os.chdir(tmp_path)
    subprocess.run(["git", "init"])
    subprocess.run(["dvc", "init"])

    HelloWorld(inputs=1).write_graph()
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", "Init"])

    subprocess.run(["dvc", "repro"])

    HelloWorld(inputs=2).write_graph()
    subprocess.run(["dvc", "exp", "run", "-n", "Test02"])
    HelloWorld(inputs=3).write_graph()
    subprocess.run(["dvc", "exp", "run", "-n", "Test03"])

    return tmp_path


@pytest.fixture()
def loaded_dvc_interface(single_experiment_path) -> DVCInterface:
    os.chdir(single_experiment_path)
    return DVCInterface()


def test_experiments(loaded_dvc_interface):
    """Check that loading works and look for the default workspace environment"""
    assert "workspace" in loaded_dvc_interface.experiments


def test_exp_list(loaded_dvc_interface):
    assert (
        loaded_dvc_interface.exp_list[0].name == "master"
        or loaded_dvc_interface.exp_list[0].name == "main"
    )
    assert len(loaded_dvc_interface.exp_list) == 1


def test__reset(loaded_dvc_interface):
    loaded_dvc_interface._reset()
    assert (
        loaded_dvc_interface.exp_list[0].name == "master"
        or loaded_dvc_interface.exp_list[0].name == "main"
    )


def test_load_files_into_directory(multi_experiment_path):
    """Test for specific experiments"""
    os.chdir(multi_experiment_path)
    interface = DVCInterface()
    interface.load_files_into_directory(
        files=["nodes/HelloWorld/outs.json"], experiments=["Test02", "Test03"]
    )
    assert pathlib.Path("experiments/Test02/outs.json").exists()
    assert pathlib.Path("experiments/Test03/outs.json").exists()


def test_load_files_into_directory_all_exp(multi_experiment_path):
    """Test for all experiments"""
    os.chdir(multi_experiment_path)
    interface = DVCInterface()
    interface.load_files_into_directory(files=["nodes/HelloWorld/outs.json"])
    assert pathlib.Path("experiments/Test02/outs.json").exists()
    assert pathlib.Path("experiments/Test03/outs.json").exists()
