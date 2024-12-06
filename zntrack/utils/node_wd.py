"""Helpers for the Node Working Directory (NWD)."""

import json
import logging
import os
import pathlib
import shutil
import typing as t

import znflow.utils
import znjson

from zntrack.add import DVCImportPath
from zntrack.config import NWD_PATH, ZNTRACK_FILE_PATH, NodeStatusEnum

if t.TYPE_CHECKING:
    from zntrack import Node


log = logging.getLogger(__name__)


class _NWD(str):
    """String that allows for pathlib like truediv operation."""

    def __truediv__(self, other) -> pathlib.Path:
        return pathlib.Path(self, other)


nwd = _NWD("$nwd$")


def move_nwd(target: pathlib.Path, destination: pathlib.Path) -> None:
    """Move files from 'target' to 'destination'."""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(target, destination, copy_function=os.link)
    shutil.rmtree(target)


def get_nwd(node: "Node") -> pathlib.Path:
    """Get the node working directory.

    This is used instead of `node.nwd` because it allows
    for parameters to define if the nwd should be created.

    Arguments:
    ---------
    node: Node
        The node instance for which the nwd should be returned.

    """
    try:
        nwd = node.__dict__["nwd"]
    except KeyError:
        if node.name is None:
            raise ValueError("Unable to determine node name.")
        if (
            node.state.remote is None
            and node.state.rev is None
            and node.state.state != NodeStatusEnum.FINISHED
        ):
            nwd = pathlib.Path(NWD_PATH, node.name)
        else:
            try:
                with node.state.fs.open(ZNTRACK_FILE_PATH) as f:
                    zntrack_config = json.load(f)
                nwd = zntrack_config[node.name]["nwd"]
                nwd = json.loads(json.dumps(nwd), cls=znjson.ZnDecoder)
            except (FileNotFoundError, KeyError):
                nwd = pathlib.Path(NWD_PATH, node.name)

        if node.state.group is not None:
            # strip the groups from node_name
            to_replace = "_".join(node.state.group.name) + "_"
            replacement = "/".join(node.state.group.name) + "/"
            nwd = pathlib.Path(str(nwd).replace(to_replace, replacement))

    return nwd


class NWDReplaceHandler(znflow.utils.IterableHandler):
    """Replace the nwd placeholder with the actual nwd."""

    def default(self, value, **kwargs):
        """Replace the nwd placeholder with the actual nwd."""
        if isinstance(value, str):
            if value == nwd:
                # nwd is of type str but will be converted to pathlib.Path
                return pathlib.Path(kwargs["nwd"])
            return value.replace(nwd, pathlib.Path(kwargs["nwd"]).as_posix())
        elif isinstance(value, pathlib.Path):
            return pathlib.Path(
                value.as_posix().replace(nwd, pathlib.Path(kwargs["nwd"]).as_posix())
            )
        elif value is None:
            return value
        elif isinstance(value, DVCImportPath):
            # with DVCImportPath, we do not expect the nwd placeholder
            return value.path
        else:
            raise ValueError(
                f"replace_nwd_placeholder is not implemented for {type(value)}"
            )
