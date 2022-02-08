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

import znipy
import znjson

from zntrack.core.base import Node
from zntrack.core.functions.decorator import NodeConfig, nodify
from zntrack.interface.base import DVCInterface
from zntrack.project.zntrack_project import ZnTrackProject
from zntrack.utils.config import config
from zntrack.utils.serializer import MethodConverter, ZnTrackTypeConverter

znipy.register()

# register converters
znjson.config.ACTIVE_CONVERTER = [
    ZnTrackTypeConverter,
    znjson.PathlibConverter,
    MethodConverter,
]
try:
    znjson.register([znjson.NumpyConverter, znjson.SmallNumpyConverter])
except AttributeError:
    pass

#
__all__ = [
    Node.__name__,
    ZnTrackProject.__name__,
    DVCInterface.__name__,
    "config",
    nodify.__name__,
    NodeConfig.__name__,
]

__version__ = "0.3.5"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Formatter for advanced logging
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
formatter = logging.Formatter("%(asctime)s %(module)s (%(levelname)s): %(message)s")

channel = logging.StreamHandler(sys.stdout)
channel.setLevel(logging.DEBUG)
channel.setFormatter(formatter)

logger.addHandler(channel)
