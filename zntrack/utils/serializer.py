"""List of functions that are used to serialize and deserialize Python Objects

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
import typing

import znjson

from zntrack.core.base import Node
from zntrack.zn.dependencies import NodeAttribute

log = logging.getLogger(__name__)


@dataclasses.dataclass
class SerializedClass:
    """Store a serialized Class"""

    module: str
    cls: str

    def get_cls(self) -> typing.Type[Node]:
        """Import the serialized class from the given module"""
        module = importlib.import_module(self.module)
        cls = getattr(module, self.cls)
        return cls


@dataclasses.dataclass
class SerializedNode(SerializedClass):
    """
    Attributes
    ----------
    name: str
        The name in Node.load(name=<name>)
    """

    name: str


@dataclasses.dataclass
class SerializedMethod(SerializedClass):
    """
    Attributes
    ----------
    kwargs: dict
        The arguments to encode the method again, as in method = Method(**kwargs)
    """

    kwargs: dict = dataclasses.field(default_factory=dict)


class ZnTrackTypeConverter(znjson.ConverterBase):
    """Main Serializer for ZnTrack Nodes, e.g. as dependencies"""

    instance = Node
    representation = "ZnTrackType"
    level = 10

    def _encode(self, obj: Node) -> dict:
        """Convert Node to serializable dict"""
        return dataclasses.asdict(
            SerializedNode(
                module=obj.module,
                cls=obj.__class__.__name__,
                name=obj.node_name,
            )
        )

    def _decode(self, value: dict) -> Node:
        """return serialized Node"""

        serialized_node = SerializedNode(**value)
        return serialized_node.get_cls().load(name=serialized_node.name)


class NodeAttributeConverter(znjson.ConverterBase):
    """Serializer for Node Attributes

    This allows to use getdeps(Node, "attr") as dvc/zn.deps() directly.
    """

    instance = NodeAttribute
    representation = "NodeAttribute"
    level = 10

    def _encode(self, obj: NodeAttribute) -> dict:
        """Convert NodeAttribute to serializable dict"""
        return dataclasses.asdict(obj)

    def _decode(self, value: dict):
        """return serialized Node attribute"""

        node_attribute = NodeAttribute(**value)
        serialized_node = SerializedNode(
            module=node_attribute.module, cls=node_attribute.cls, name=node_attribute.name
        )
        node = serialized_node.get_cls().load(name=node_attribute.name)
        log.debug(f"--> Resolving NodeAttribute {node_attribute}.")
        return getattr(node, node_attribute.attribute)


class MethodConverter(znjson.ConverterBase):
    """ZnJSON Converter for zn.method attributes"""

    representation = "zn.method"
    level = 10

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
