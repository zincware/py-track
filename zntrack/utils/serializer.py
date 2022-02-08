"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description: List of functions that are used to serialize and deserialize Python Objects

Notes
-----
    These functions can be used for e.g., small numpy arrays.
    The content will be converted to json serializable data.
    Converting e.g., large numpy arrays can cause major slow downs and is not recommended!
    Please consider using DVC.outs() and save them in a binary file format.

"""
import dataclasses
import importlib
import inspect
import logging

import znipy
import znjson

from zntrack.core.base import Node

log = logging.getLogger(__name__)


@dataclasses.dataclass
class SerializedClass:
    """Store a serialized Class"""

    module: str
    cls: str

    def get_cls(self):
        """Import the serialized class from the given module"""
        try:
            module = importlib.import_module(self.module)
            cls = getattr(module, self.cls)
        except ModuleNotFoundError:
            # Try loading from jupyter notebook if otherwise not available
            module = znipy.NotebookLoader().load_module(self.module)
            cls = getattr(module, self.cls)
        return cls


@dataclasses.dataclass
class SerializedNode(SerializedClass):
    name: str


@dataclasses.dataclass
class SerializedMethod(SerializedClass):
    kwargs: dict = dataclasses.field(default_factory=dict)


class ZnTrackTypeConverter(znjson.ConverterBase):
    """Main Serializer for ZnTrack Nodes, e.g. as dependencies"""

    instance = Node
    representation = "ZnTrackType"

    def _encode(self, obj) -> dict:
        """Convert Node to serializable dict"""
        return dataclasses.asdict(
            SerializedNode(
                module=obj.module, cls=obj.__class__.__name__, name=obj.node_name
            )
        )

    def _decode(self, value: dict) -> Node:
        """return serialized Node"""

        serialized_node = SerializedNode(**value)
        return serialized_node.get_cls().load(name=serialized_node.name)

    def __eq__(self, other):
        """Overwrite check, because checking .zntrack equality"""
        return isinstance(other, Node)


class MethodConverter(znjson.ConverterBase):
    """ZnJSON Converter for zn.method attributes"""

    representation = "zn.method"

    def _encode(self, obj):
        """Serialize the object"""

        serialized_method = SerializedMethod(
            module=obj.__class__.__module__,
            cls=obj.__class__.__name__,
        )

        # If using Jupyter Notebooks
        # if the class is originally imported from main,
        #  it will be copied to the same module path as the
        #  ZnTrack Node source code.
        if serialized_method.module == "__main__":
            serialized_method.module = obj.znjson_module

        for key in inspect.signature(obj.__class__.__init__).parameters:
            if key == "self":
                continue
            if key in ["args", "kwargs"]:
                log.error(f"Can not convert {key}!")
                continue
            try:
                serialized_method.kwargs[key] = getattr(obj, key)
            except AttributeError as error:
                raise AttributeError(
                    f"Could not find {key} in passed method! Please use "
                    "@check_signature from ZnTrack to check that the method signature"
                    " fits the method attributes"
                ) from error

        return dataclasses.asdict(serialized_method)

    def _decode(self, value: dict):
        """Deserialize the object"""

        if "name" in value:
            # keep it backwards compatible
            value["cls"] = value.pop("name")

        serialized_method = SerializedMethod(**value)
        return serialized_method.get_cls()(**serialized_method.kwargs)

    def __eq__(self, other) -> bool:
        """Identify if this serializer should be applied"""
        try:
            return other.znjson_zn_method
        except AttributeError:
            return False
