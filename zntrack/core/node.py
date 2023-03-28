"""The Node class."""
from __future__ import annotations

import contextlib
import dataclasses
import importlib
import logging
import os
import pathlib
import shutil
import typing

import dvc.api
import dvc.cli
import znflow
import zninit
import znjson

from zntrack import exceptions
from zntrack.notebooks.jupyter import jupyter_class_to_file
from zntrack.utils import (
    NodeStatusResults,
    convert_to_list,
    deprecated,
    module_handler,
    run_dvc_cmd,
    update_gitignore,
)
from zntrack.utils.config import config
from zntrack.utils.node_wd import move_nwd

log = logging.getLogger(__name__)

EXCEPTION_OR_LST_EXCEPTIONS = typing.Union[
    typing.Type[Exception], typing.Collection[typing.Type[Exception]], None
]


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

    def get_file_system(self) -> dvc.api.DVCFileSystem:
        """Get the file system of the Node."""
        return dvc.api.DVCFileSystem(
            url=self.remote,
            rev=self.rev,
        )


class _NameDescriptor(zninit.Descriptor):
    """A descriptor for the name attribute."""

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        if getattr(instance, "_name_") is None:
            instance._name_ = instance.__class__.__name__
        return getattr(instance, "_name_")

    def __set__(self, instance, value):
        if value is None:
            return
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

        return [
            fields.zn.Params,
            fields.zn.Dependency,
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
        nwd = pathlib.Path("nodes", znflow.get_attribute(self, "name"))
        if not nwd.exists():
            nwd.mkdir(parents=True)
        return nwd

    def save(self, parameter: bool = True, results: bool = True) -> None:
        """Save the node's output to disk."""
        # TODO have an option to save and run dvc commit afterwards.
        from zntrack.fields import Field, FieldGroup

        # Jupyter Notebook
        if config.nb_name:
            self.convert_notebook(config.nb_name)

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

    def run(self) -> None:
        """Run the node's code."""

    def load(self, lazy: bool = None) -> None:
        """Load the node's output from disk."""
        from zntrack.fields.field import Field

        kwargs = {} if lazy is None else {"lazy": lazy}
        self.state.loaded = True  # we assume loading will be successful.
        try:
            with config.updated_config(**kwargs):
                # TODO: it would be much nicer not to use a global config object here.
                for attr in zninit.get_descriptors(Field, self=self):
                    attr.load(self)
        except KeyError as err:
            raise exceptions.NodeNotAvailableError(self) from err

        # TODO: documentation about _post_init and _post_load_ and when they are called
        self._post_load_()

    @classmethod
    def from_rev(cls, name=None, remote=None, rev=None, lazy: bool = None) -> Node:
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

        kwargs = {} if lazy is None else {"lazy": lazy}
        with config.updated_config(**kwargs):
            node.load()

        return node

    @deprecated(
        "Building a graph is now done using 'with zntrack.Project() as project: ...'",
        version="0.6.0",
    )
    def write_graph(self, run: bool = False, **kwargs):
        """Write the graph to dvc.yaml."""
        cmd = get_dvc_cmd(self, **kwargs)
        for x in cmd:
            run_dvc_cmd(x)
        self.save()

        if run:
            run_dvc_cmd(["repro", self.name])

    @contextlib.contextmanager
    def operating_directory(
        self,
        prefix="ckpt",
        remove_on: EXCEPTION_OR_LST_EXCEPTIONS = None,
        move_on: EXCEPTION_OR_LST_EXCEPTIONS = Exception,
        disable: bool = None,
    ) -> bool:
        """Work in a temporary operating directory until successfully finished.

        This context manager will replace the path of the node working
        directory $nwd$ with a temporary operating directory 'prefix_$nwd$'
        and move the files to $nwd$, when successfully finished.
        This can be useful, when you are running, e.g., on hardware
        with limited execution time and can't use 'dvc checkpoints'.
        When successfully finished, all files will be moved from 'prefix_$nwd$' to $nwd$.
        You can call 'dvc repro' multiple times to continue from 'prefix_$nwd$'.
        If used properly this will result in reproducible data, but:
        - checkpoints will not be removed if parameters change. Always remove a
            checkpoint, when running with new parameters!
        - checkpoints are not versioned. If you want to checkpoint, e.g., model training,
            use 'dvc checkpoints'.

        Parameters
        ----------
        prefix: str, default = 'ckpt'
            Prefix for the temporary directory
        remove_on: Exception or list of Exceptions, default = None
            If one of the exceptions in 'remove_on' is raised, the temporary
            operating directory will be removed. Otherwise, it will remain
            and reused upon the next run.
        move_on: Exception, default = Exception
            If one of the exceptions in 'move_on' is raised, the temporary
            operating directories content is moved to $nwd$ and the temporary
            directory will be removed. This helps, in the case of an error,
            to not restart from an already failed data point.
            The default is set to move the files if any Exception occurs.
        disable: bool, default = False
            Disable the temporary operating directory. Yields True.


        Yields
        ------
        new_ckpt: bool
            True if creating a new checkpoint. False if the checkpoint already existed.
        """
        if disable is None:
            disable = config.disable_operating_directory
        if disable:
            yield True
            return

        nwd = self.nwd
        nwd_new = self.nwd.with_name(f"{prefix}_{self.nwd.name}")
        nwd_is_new = not nwd_new.exists()

        remove = False
        move = False
        remove_on = convert_to_list(remove_on)
        move_on = convert_to_list(move_on)

        update_gitignore(prefix=prefix)

        if nwd_is_new:
            log.info(f"Creating new operating directory: {nwd_new}")
            log.warning(
                "Experimental Feature: operating directory is currently not"
                " compatible with 'dvc exp --temp' or 'dvc exp --queue'"
            )
            # TODO add a unique path per node.
            # TODO check on windows!
            shutil.copytree(nwd, nwd_new, copy_function=os.link)
        else:
            log.info(f"Continuing inside operating directory: {nwd_new}.")

        self.nwd = nwd_new
        try:
            yield nwd_is_new
        except Exception as err:
            log.warning("Node execution was interrupted.")
            remove = any(isinstance(err, e) for e in remove_on)
            move = any(isinstance(err, e) for e in move_on)
            # finally -> ...
            raise err
        finally:
            # Save e.g. `zn.outs` before stopping.
            self.save(results=True)
            self.nwd = nwd
            if remove:
                log.info(f"Removing operating directory: {nwd_new}")
                shutil.rmtree(nwd_new)
            elif move:
                log.info(f"Moving files from '{nwd_new}' to {nwd}")
                move_nwd(nwd_new, nwd)

        log.info(f"Finished successfully. Moving files from {nwd_new} to {nwd}")
        move_nwd(nwd_new, nwd)


def get_dvc_cmd(
    node: Node,
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
        optionals += attr.get_optional_dvc_cmd(node)
    for field_cmd in set(field_cmds):
        cmd += list(field_cmd)

    module = module_handler(node.__class__)
    cmd += [f"zntrack run {module}.{node.__class__.__name__} --name {node.name}"]
    optionals = [x for x in optionals if x]  # remove empty entries []
    return [cmd] + optionals


@dataclasses.dataclass
class NodeIdentifier:
    """All information that uniquly identifies a node."""

    module: str
    cls: str
    name: str
    remote: str
    rev: str

    @classmethod
    def from_node(cls, node: Node):
        """Create a _NodeIdentifier from a Node object."""
        return cls(
            module=module_handler(node),
            cls=node.__class__.__name__,
            name=node.name,
            remote=node.state.remote,
            rev=node.state.rev,
        )

    def get_node(self) -> Node:
        """Get the node from the identifier."""
        module = importlib.import_module(self.module)
        cls = getattr(module, self.cls)
        return cls.from_rev(name=self.name, remote=self.remote, rev=self.rev)


class NodeConverter(znjson.ConverterBase):
    """A converter for the Node class."""

    level = 100
    representation = "zntrack.Node"
    instance = Node

    def encode(self, obj: Node) -> dict:
        """Convert the Node object to dict."""
        node_identifier = NodeIdentifier.from_node(obj)
        if node_identifier.rev is not None:
            raise NotImplementedError(
                "Dependencies to other revisions are not supported yet"
            )

        return dataclasses.asdict(node_identifier)

    def decode(self, value: dict) -> Node:
        """Create Node object from dict."""
        # TODO if rev = HEAD, replace with the rev from the 'Node.from_rev'
        return NodeIdentifier(**value).get_node()


znjson.config.register(NodeConverter)
