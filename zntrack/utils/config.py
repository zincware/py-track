"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description: 
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Collection of Node configurations"""

    debug: bool = False  # not implemented yet
    nb_name: str = None
    nb_class_path: Path = Path("src")


config = Config()
