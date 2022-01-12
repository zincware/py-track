"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description: zn.<option>

The following can be used to store e.g. metrics directly without
defining and writing to a file
"""
import logging

from zntrack.core.parameter import ZnTrackOption
from zntrack.descriptor import Metadata

log = logging.getLogger(__name__)


# module class definitions to be used via zn.<option>
# detailed explanations on https://dvc.org/doc/command-reference/run#options
# with the exception that these will be loaded to memory when.
# for direct file references use dvc.<option> instead.


class outs(ZnTrackOption):
    metadata = Metadata(dvc_option="outs", zntrack_type="zn")


class deps(ZnTrackOption):
    metadata = Metadata(dvc_option="deps", zntrack_type="deps")


class metrics(ZnTrackOption):
    metadata = Metadata(dvc_option="metrics_no_cache", zntrack_type="zn")


class params(ZnTrackOption):
    metadata = Metadata(dvc_option="params", zntrack_type="params")


class iterable(ZnTrackOption):
    metadata = Metadata(dvc_option="params", zntrack_type="iterable")


class Method(ZnTrackOption):
    """ZnTrack methods passing descriptor

    This descriptor allows to pass a class instance that is not a ZnTrack Node as a
    method that can be used later. It requires that all passed class attributes have
    the same name in the __init__ and via getattr an that they are serializable.

    Example
    --------
    >>> class HelloWorld:
    >>>     def __init__(self, name):
    >>>         self.name = name
    >>>
    >>> class MyNode(zntrack.Node)
    >>>     my_method = Method()
    >>> MyNode().my_method = HelloWorld(name="Max")

    """

    metadata = Metadata(dvc_option="params", zntrack_type="method")

    def __get__(self, instance, owner):
        if instance is None:
            return self
        log.debug(f"Get {self} from {instance}")
        value = instance.__dict__.get(self.name, self.default_value)
        # Set some attribute for the serializer
        value.znjson_zn_method = True
        return value
