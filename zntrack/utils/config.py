"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description: Configuration File for ZnTrack
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Collection of Node configurations

    Attributes
    ----------
    debug: bool
        TODO
    nb_name: str
        Name of the JupyterNotebook, if the Nodes are defined in a Notebook
    nb_class_path: Path
        The path where jupyter notebooks should write the *.py
    no_dvc: bool, default = False
        Do not write a dvc file when true.
    notebook: str, default = None
        Name of the Notebook to import the Node from. This uses direct notebook import
        and does not write a python file to src.
    """

    debug: bool = False  # not implemented yet
    nb_name: str = None
    notebook: str = None
    nb_class_path: Path = Path("src")
    no_dvc: bool = False


config = Config()
