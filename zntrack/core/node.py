"""The Node class."""
from __future__ import annotations

import dataclasses
import enum
import importlib
import logging
import pathlib
import typing

import dvc.api
import dvc.cli
import znflow
import zninit

from zntrack.utils import deprecated, module_handler

log = logging.getLogger(__name__)


class NodeStatusResults(enum.Enum):
    """The status of a node.

    Attributes
    ----------
    UNKNOWN : int
        No information is available.
    PENDING : int
        the Node instance is written to disk, but not yet run.
        `dvc stage add ` with the given parameters was run.
    RUNNING : int
        the Node instance is currently running.
        This state will be set when the run method is called.
    FINISHED : int
        the Node instance has finished running.
    FAILED : int
        the Node instance has failed to run.
    """

    UNKNOWN = 0
    PENDING = 1
    RUNNING = 2
    FINISHED = 3
    FAILED = 4


@dataclasses.dataclass
class NodeStatus:
    """The status of a node.

    Attributes
    ----------
    loaded : bool
        Whether the attributes of the Node are loaded from disk.
        If a new Node is created, this will be False.
    results : NodeStatusResults
        The status of the node results. E.g. was the computation successful.
    origin : str, default = "workspace"
        Where the Node has its data from. This could be the current "workspace" or
        a "remote" location, such as a git repository.
    rev : str, default = "HEAD"
        The revision of the Node. This could be the current "HEAD" or a specific revision.
    """

    loaded: bool
    results: "NodeStatusResults"
    origin: str = "workspace"
    rev: str = "HEAD"

    def get_file_system(self) -> dvc.api.DVCFileSystem:
        """Get the file system of the Node."""
        return dvc.api.DVCFileSystem(
            url=self.origin if self.origin != "workspace" else None,
            rev=self.rev if self.rev != "HEAD" else None,
        )


class Node(zninit.ZnInit, znflow.Node):
    """A node in a ZnTrack workflow.

    Attributes
    ----------
    name : str, default = cls.__name__
        the Name of the Node
    state : NodeStatus
        information about the state of the Node.
    nwd : pathlib.Path
        the node working directory.
    """

    _state: NodeStatus = None

    name: str = zninit.Descriptor(None)

    def _post_init_(self):
        if znflow.get_attribute(self, "name") is None:
            self.name = self.__class__.__name__

    @property
    def state(self) -> NodeStatus:
        """Get the state of the node."""
        if self._state is None:
            self._state = NodeStatus(False, NodeStatusResults.UNKNOWN)
        return self._state

    @property
    def nwd(self) -> pathlib.Path:
        """Get the node working directory."""
        return pathlib.Path("nodes", znflow.get_attribute(self, "name"))

    def save(self) -> None:
        """Save the node's output to disk."""
        # TODO have an option to save and run dvc commit afterwards.
        from zntrack.fields.field import Field

        for attr in zninit.get_descriptors(Field, self=self):
            attr.save(self)

    def run(self) -> None:
        """Run the node's code."""

    def load(self) -> None:
        """Load the node's output from disk."""
        from zntrack.fields.field import Field

        for attr in zninit.get_descriptors(Field, self=self):
            attr.load(self)

        self.state.loaded = True

    @classmethod
    def from_rev(cls, name=None, origin="workspace", rev="HEAD") -> Node:
        """Create a Node instance from an experiment."""
        node = cls.__new__(cls)
        node.name = name if name is not None else cls.__name__
        node._state = NodeStatus(False, NodeStatusResults.UNKNOWN, origin, rev)
        node_identifier = NodeIdentifier(
            module_handler(cls), cls.__name__, node.name, origin, rev
        )
        log.error(f"Creating node {node_identifier}")
        node.load()
        return node

    @deprecated(
        "Building a graph is now done using 'with zntrack.Project() as project: ...'",
        version="0.6.0",
    )
    def write_graph(self, run: bool = False, **kwargs):
        """Write the graph to dvc.yaml."""
        cmd = get_dvc_cmd(self, **kwargs)
        dvc.cli.main(cmd)
        self.save()

        if run:
            dvc.cli.main(["repro", self.name])


def get_dvc_cmd(
    node: Node,
    quiet: bool = False,
    verbose: bool = False,
    force: bool = True,
    external: bool = False,
    always_changed: bool = False,
    desc: str = None,
) -> typing.List[str]:
    """Get the 'dvc stage add' command to run the node."""
    from zntrack.fields.field import Field

    cmd = ["stage", "add"]
    cmd += ["--name", node.name]
    if quiet:
        cmd += ["--quiet"]
    if verbose:
        cmd += ["--verbose"]
    if force:
        cmd += ["--force"]
    if external:
        cmd += ["--external"]
    if always_changed:
        cmd += ["--always-changed"]
    if desc is not None:
        cmd += ["--desc", desc]
    field_cmds = []
    for attr in zninit.get_descriptors(Field, self=node):
        field_cmds += attr.get_stage_add_argument(node)
    for field_cmd in set(field_cmds):
        cmd += list(field_cmd)

    module = module_handler(node.__class__)
    cmd += [f"zntrack run {module}.{node.__class__.__name__} --name {node.name}"]
    return cmd


@dataclasses.dataclass
class NodeIdentifier:
    """All information that uniquly identifies a node."""

    module: str
    cls: str
    name: str
    origin: str
    rev: str

    @classmethod
    def from_node(cls, node: Node):
        """Create a _NodeIdentifier from a Node object."""
        return cls(
            module=module_handler(node),
            cls=node.__class__.__name__,
            name=node.name,
            origin=node.state.origin,
            rev=node.state.rev,
        )

    def get_node(self) -> Node:
        """Get the node from the identifier."""
        module = importlib.import_module(self.module)
        cls = getattr(module, self.cls)
        return cls.from_rev(name=self.name, origin=self.origin, rev=self.rev)