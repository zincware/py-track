"""The ZnTrack Node class."""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import json
import logging
import os
import pathlib
import time
import typing
import unittest.mock
import uuid

import dvc.api
import dvc.cli
import dvc.utils.strictyaml
import znflow
import zninit
import znjson

from zntrack import exceptions
from zntrack.notebooks.jupyter import jupyter_class_to_file
from zntrack.utils import (
    NodeName,
    NodeStatusResults,
    config,
    file_io,
    get_nwd,
    module_handler,
)

log = logging.getLogger(__name__)


@dataclasses.dataclass
class NodeStatus:
    """The status of a node.

    Attributes
    ----------
    loaded : bool
        Whether the attributes of the Node are loaded from disk.
        If a new Node is created, this will be False.
        If some attributes could not be loaded, this will be False.
    results : NodeStatusResults
        The status of the node results. E.g. was the computation successful.
    remote : str, default = None
        Where the Node has its data from. This could be the current "workspace" or
        a "remote" location, such as a git repository.
    rev : str, default = None
        The revision of the Node. This could be the current "HEAD" or a specific revision.
    """

    loaded: bool
    results: "NodeStatusResults"
    remote: str = None
    rev: str = None

    @functools.cached_property
    def fs(self) -> dvc.api.DVCFileSystem:
        """Get the file system of the Node."""
        for _ in range(10):
            try:
                return dvc.api.DVCFileSystem(
                    url=self.remote,
                    rev=self.rev,
                )
            except dvc.utils.strictyaml.YAMLValidationError as err:
                log.debug(err)
                time.sleep(0.1)
        raise dvc.utils.strictyaml.YAMLValidationError

    @contextlib.contextmanager
    def magic_patch(self) -> typing.ContextManager:
        """Patch the open function to use the Node's file system.

        Opening a relative path will use the Node's file system.
        Opening an absolute path will use the local file system.
        """
        import builtins

        original_open = builtins.open
        original_listdir = os.listdir

        def _open(file, *args, **kwargs):
            if file == config.files.params:
                return original_open(file, *args, **kwargs)

            if not pathlib.Path(file).is_absolute():
                return self.fs.open(file, *args, **kwargs)

            return original_open(file, *args, **kwargs)

        def _read_text(file, *args, **kwargs):
            if file == "params.yaml":
                with original_open(file, *args, **kwargs) as f:
                    return f.read()

            if not pathlib.Path(file).is_absolute():
                return self.fs.read_text(file, *args, **kwargs)

            with original_open(file, *args, **kwargs) as f:
                return f.read()

        def _listdir(path, *args, **kwargs):
            if not pathlib.Path(path).is_absolute():
                return self.fs.listdir(path, detail=False)

            return original_listdir(path, *args, **kwargs)

        with unittest.mock.patch("builtins.open", _open):
            with unittest.mock.patch("__main__.open", _open):
                with unittest.mock.patch("os.listdir", _listdir):
                    with unittest.mock.patch("pathlib.Path.read_text", _read_text):
                        with unittest.mock.patch("pathlib.Path.open", _open):
                            yield


class _NameDescriptor(zninit.Descriptor):
    """A descriptor for the name attribute."""

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        if getattr(instance, "_name_") is None:
            return instance.__class__.__name__
        return str(getattr(instance, "_name_"))

    def __set__(self, instance, value):
        if value is None:
            return
        if isinstance(value, NodeName):
            if not instance._external_:
                value.update_suffix(instance._graph_.project, instance)
            instance._name_ = value
        elif isinstance(getattr(instance, "_name_"), NodeName):
            instance._name_.name = value
            instance._name_.suffix = 0
            instance._name_.update_suffix(instance._graph_.project, instance)
        else:
            # This should only happen if an instance is loaded.
            instance._name_ = value


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

    name: str = _NameDescriptor(None)
    _name_ = None

    _protected_ = znflow.Node._protected_ + ["name"]
    _priority_kwargs_ = ["name"]

    @property
    def _use_repr_(self) -> bool:
        """Only use dataclass like __repr__ if outside the _graph_ to avoid recursion.

        Due to modified behavior of '__getattribute__' inside the graph context,
        a fallback to the python default '__repr__' is needed to avoid recursion.
        """
        return self._graph_ is None

    def _post_load_(self) -> None:
        """Post load hook.

        This is called after the 'self.load()' is called.
        """

    @classmethod
    def convert_notebook(cls, nb_name: str = None):
        """Use jupyter_class_to_file to convert ipynb to py.

        Parameters
        ----------
        nb_name: str
            Notebook name when not using config.nb_name (this is not recommended)
        """
        # TODO this should not be a class method, but a function.
        jupyter_class_to_file(nb_name=nb_name, module_name=cls.__name__)

    @property
    def _init_descriptors_(self):
        from zntrack import fields
        from zntrack.fields.dependency import Dependency
        from zntrack.fields.zn import options as zn_options

        return [
            zn_options.Params,
            zn_options.Dependency,
            Dependency,
            fields.meta.Text,
            fields.meta.Environment,
            fields.dvc.DVCOption,
            _NameDescriptor,
        ]

    @property
    def state(self) -> NodeStatus:
        """Get the state of the node."""
        if self._state is None:
            self._state = NodeStatus(False, NodeStatusResults.UNKNOWN)
        return self._state

    @property
    def nwd(self) -> pathlib.Path:
        """Get the node working directory."""
        return get_nwd(self, mkdir=True)

    def save(
        self, parameter: bool = True, results: bool = True, meta_only: bool = False
    ) -> None:
        """Save the node's output to disk."""
        if meta_only:
            # the meta data will only be written here.
            import json

            (self.nwd / "node-meta.json").write_text(json.dumps({"uuid": str(self.uuid)}))
            return

        # TODO have an option to save and run dvc commit afterwards.

        # TODO: check if there is a difference in saving
        # a loaded node vs a new node and why
        from zntrack.fields import Field, FieldGroup

        # Jupyter Notebook
        if config.nb_name:
            self.convert_notebook(config.nb_name)

        if parameter:
            file_io.clear_config_file(file=config.files.params, node_name=self.name)
            file_io.clear_config_file(file=config.files.zntrack, node_name=self.name)

        for attr in zninit.get_descriptors(Field, self=self):
            if attr.group == FieldGroup.PARAMETER and parameter:
                attr.save(self)
            if attr.group == FieldGroup.RESULT and results:
                attr.save(self)
            if attr.group is None:
                raise ValueError(
                    f"Field {attr} has no group. Please assign a group from"
                    f" '{FieldGroup.__module__}.{FieldGroup.__name__}'."
                )
        # save the nwd to zntrack.json
        file_io.update_config_file(
            file=config.files.zntrack,
            node_name=self.name,
            value_name="nwd",
            value=get_nwd(self),
        )

    def run(self) -> None:
        """Run the node's code."""

    def load(self, lazy: bool = None, results: bool = True) -> None:
        """Load the node's output from disk.

        Attributes
        ----------
        lazy : bool, default = None
            Whether to load the node lazily. If None, the value from the config is used.
        results : bool, default = True
            Whether to load the results. If False, only the parameters are loaded.
        """
        from zntrack.fields.field import Field, FieldGroup

        kwargs = {} if lazy is None else {"lazy": lazy}
        self.state.loaded = True  # we assume loading will be successful.
        try:
            with config.updated_config(**kwargs):
                # TODO: it would be much nicer not to use a global config object here.
                for attr in zninit.get_descriptors(Field, self=self):
                    if attr.group == FieldGroup.RESULT and not results:
                        continue
                    attr.load(self)
        except KeyError as err:
            raise exceptions.NodeNotAvailableError(self) from err

        if results:
            with contextlib.suppress(FileNotFoundError):
                # If the uuid is available, we can assume that all data for
                #  this Node is available.
                with self.state.fs.open(get_nwd(self) / "node-meta.json") as f:
                    node_meta = json.load(f)
                    self._uuid = uuid.UUID(node_meta["uuid"])
                    self.state.results = NodeStatusResults.AVAILABLE
        # TODO: documentation about _post_init and _post_load_ and when they are called
        self._post_load_()

    @classmethod
    def from_rev(
        cls, name=None, remote=None, rev=None, lazy: bool = None, results: bool = True
    ) -> Node:
        """Create a Node instance from an experiment."""
        node = cls.__new__(cls)
        node.name = name
        node._state = NodeStatus(False, NodeStatusResults.UNKNOWN, remote, rev)
        node_identifier = NodeIdentifier(
            module_handler(cls), cls.__name__, node.name, remote, rev
        )
        log.debug(f"Creating {node_identifier}")

        with contextlib.suppress(TypeError):
            # This happens if the __init__ method has non-default parameter.
            # In this case, we just ignore it. This can e.g. happen
            #  if the init is auto-generated.
            # We call '__init__' before loading, because
            #  the `__init__` might do something like self.param = kwargs["param"]
            #  and this would overwrite the loaded value.
            node.__init__()

        node._in_construction = False
        node._external_ = True

        kwargs = {} if lazy is None else {"lazy": lazy}
        with config.updated_config(**kwargs):
            node.load(results=results)

        return node


def get_dvc_cmd(
    node: Node,
    git_only_repo: bool,
    quiet: bool = False,
    verbose: bool = False,
    force: bool = True,
    external: bool = False,
    always_changed: bool = False,
    desc: str = None,
) -> typing.List[typing.List[str]]:
    """Get the 'dvc stage add' command to run the node."""
    from zntrack.fields.field import Field

    optionals = []

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
    if desc:
        cmd += ["--desc", desc]
    field_cmds = []
    for attr in zninit.get_descriptors(Field, self=node):
        field_cmds += attr.get_stage_add_argument(node)
        optionals += attr.get_optional_dvc_cmd(node, git_only_repo=git_only_repo)

    for field_cmd in set(field_cmds):
        cmd += list(field_cmd)

    if git_only_repo:
        cmd += ["--metrics-no-cache", f"{(get_nwd(node) /'node-meta.json').as_posix()}"]
    else:
        cmd += ["--outs", f"{(get_nwd(node) /'node-meta.json').as_posix()}"]

    module = module_handler(node.__class__)
    cmd += [f"zntrack run {module}.{node.__class__.__name__} --name {node.name}"]
    optionals = [x for x in optionals if x]  # remove empty entries []
    return [cmd] + optionals


@dataclasses.dataclass
class NodeIdentifier:
    """All information that uniquely identifies a node."""

    module: str
    cls: str
    name: str
    remote: str
    rev: str

    @classmethod
    def from_node(cls, node: Node):
        """Create a _NodeIdentifier from a Node object."""
        # TODO module and cls are only required for `zn.nodes`
        return cls(
            module=module_handler(node),
            cls=node.__class__.__name__,
            name=node.name,
            remote=node.state.remote,
            rev=node.state.rev,
        )

    def get_node(self) -> Node:
        """Get the node from the identifier."""
        from zntrack import from_rev

        return from_rev(name=self.name, remote=self.remote, rev=self.rev)


class NodeConverter(znjson.ConverterBase):
    """A converter for the Node class."""

    level = 100
    representation = "zntrack.Node"
    instance = Node

    def encode(self, obj: Node) -> dict:
        """Convert the Node object to dict."""
        return dataclasses.asdict(NodeIdentifier.from_node(obj))

    def decode(self, value: dict) -> Node:
        """Create Node object from dict."""
        # TODO if rev = HEAD, replace with the rev from the 'Node.from_rev'
        return NodeIdentifier(**value).get_node()


znjson.config.register(NodeConverter)
