"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description: Standard python init file for the main directory
"""

import logging
import sys

import znjson

import zntrack.dvc as dvc

from .core import Node
from .interface import DVCInterface
from .project import ZnTrackProject
from .utils import config
from .utils.serializer import MethodConverter, ZnTrackTypeConverter

# register converters
znjson.config.ACTIVE_CONVERTER = [
    ZnTrackTypeConverter,
    znjson.PathlibConverter,
    MethodConverter,
]
try:
    znjson.register(znjson.NumpyConverter)
except AttributeError:
    pass

#
__all__ = ["Node", "ZnTrackProject", "DVCInterface", "config", "dvc"]

__version__ = "0.3.0"

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Formatter for advanced logging
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
formatter = logging.Formatter("%(asctime)s (%(levelname)s): %(message)s")

channel = logging.StreamHandler(sys.stdout)
channel.setLevel(logging.DEBUG)
channel.setFormatter(formatter)

logger.addHandler(channel)
