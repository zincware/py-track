"""Base classes for 'zntrack.<field>' fields."""

import dataclasses
import json
import logging
import pathlib
import typing

import pandas as pd
import yaml
import znflow
import znflow.utils
import zninit
import znjson
from znflow import handler

from zntrack import exceptions
from zntrack.fields.field import (
    DataIsLazyError,
    Field,
    FieldGroup,
    LazyField,
    PlotsMixin,
)
from zntrack.utils import config, get_nwd, module_handler, update_key_val

if typing.TYPE_CHECKING:
    from zntrack import Node
log = logging.getLogger(__name__)


class ConnectionConverter(znjson.ConverterBase):
    """Convert a znflow.Connection object to dict and back."""

    level = 100
    representation = "znflow.Connection"
    instance = znflow.Connection

    def encode(self, obj: znflow.Connection) -> dict:
        """Convert the znflow.Connection object to dict."""
        if obj.item is not None:
            raise NotImplementedError("znflow.Connection getitem is not supported yet.")
        return dataclasses.asdict(obj)

    def decode(self, value: str) -> znflow.Connection:
        """Create znflow.Connection object from dict."""
        return znflow.Connection(**value)


class CombinedConnectionsConverter(znjson.ConverterBase):
    """Convert a znflow.Connection object to dict and back."""

    level = 100
    representation = "znflow.CombinedConnections"
    instance = znflow.CombinedConnections

    def encode(self, obj: znflow.CombinedConnections) -> dict:
        """Convert the znflow.Connection object to dict."""
        if obj.item is not None:
            raise NotImplementedError(
                "znflow.CombinedConnections getitem is not supported yet."
            )
        return dataclasses.asdict(obj)

    def decode(self, value: str) -> znflow.CombinedConnections:
        """Create znflow.Connection object from dict."""
        connections = []
        for item in value["connections"]:
            if isinstance(item, dict):
                # @nodify functions aren't support as 'zn.deps'
                # Nodes directly aren't supported because they aren't lists
                connections.append(znflow.Connection(**item))
            else:
                # For the case that item is already a znflow.Connection
                connections.append(item)
        value["connections"] = connections
        return znflow.CombinedConnections(**value)


class SliceConverter(znjson.ConverterBase):
    """Convert a znflow.Connection object to dict and back."""

    level = 100
    representation = "slice"
    instance = slice

    def encode(self, obj: slice) -> dict:
        """Convert the znflow.Connection object to dict."""
        return {"start": obj.start, "stop": obj.stop, "step": obj.step}

    def decode(self, value: dict) -> znflow.Connection:
        """Create znflow.Connection object from dict."""
        return slice(value["start"], value["stop"], value["step"])


znjson.config.register(SliceConverter)


class Params(Field):
    """A parameter field.

    Parameters
    ----------
    dvc_option: str
        The DVC option to use. Default is "params".

    """

    dvc_option: str = "params"
    group = FieldGroup.PARAMETER

    def get_params_data(self, instance: "Node") -> dict:
        """Get the parameters data."""
        return {self.name: getattr(instance, self.name)}

    def get_dvc_data(self, instance: "Node") -> dict:
        """Get the DVC data."""
        return {"params": [instance.name]}

    def get_files(self, instance: "Node") -> list:
        """Get the list of files affected by this field.

        Returns
        -------
        list
            A list of file paths.

        """
        return [config.files.params]

    def save(self, instance: "Node"):
        """Save the field to disk.

        Parameters
        ----------
        instance : Node
            The node instance associated with this field.

        """
        file = self.get_files(instance)[0]

        try:
            params_dict = yaml.safe_load(pathlib.Path(file).read_text())
        except FileNotFoundError:
            params_dict = {instance.name: {}}

        if instance.name not in params_dict:
            params_dict[instance.name] = {}

        params_dict[instance.name][self.name] = getattr(instance, self.name)
        params_dict = json.loads(json.dumps(params_dict, cls=znjson.ZnEncoder))

        with open(file, "w") as f:
            yaml.safe_dump(params_dict, f, indent=4)

    def get_data(self, instance: "Node") -> any:
        """Get the value of the field from the file."""
        file = self.get_files(instance)[0]
        params_dict = yaml.safe_load(instance.state.fs.read_text(file))
        value = params_dict[instance.name][self.name]
        return json.loads(json.dumps(value), cls=znjson.ZnDecoder)

    def get_stage_add_argument(self, instance: "Node") -> typing.List[tuple]:
        """Get the DVC stage add argument for this field.

        Parameters
        ----------
        instance : Node
            The node instance associated with this field.

        Returns
        -------
        list
            A list of tuples containing the DVC option and the file path.

        """
        file = self.get_files(instance)[0]
        return [(f"--{self.dvc_option}", f"{file}:{instance.name}")]


class Output(LazyField):
    """A field that is saved to disk."""

    group = FieldGroup.RESULT

    def get_dvc_data(self, instance: "Node") -> dict:
        """Get the DVC data."""
        return {"outs": [x.as_posix() for x in self.get_files(instance)]}

    def get_zntrack_data(self, instance: "Node") -> dict:
        """Get the zntrack data."""
        return {self.name: pathlib.Path(f"$nwd$/{self.name}.json")}

    def __init__(self, dvc_option: str, **kwargs):
        """Create a new Output field.

        Parameters
        ----------
        dvc_option : str
            The DVC option used to specify the output file.
        **kwargs
            Additional arguments to pass to the parent constructor.

        """
        self.dvc_option = dvc_option
        super().__init__(**kwargs)

    def get_files(self, instance) -> list:
        """Get the path of the file in the node directory.

        Parameters
        ----------
        instance : Node
            The node instance.

        Returns
        -------
        list
            A list containing the path of the file.

        """
        return [get_nwd(instance) / f"{self.name}.json"]

    def save(self, instance: "Node"):
        """Save the field to disk.

        Parameters
        ----------
        instance : Node
            The node instance.

        """
        try:
            value = self.get_value_except_lazy(instance)
        except DataIsLazyError:
            return

        instance.nwd.mkdir(exist_ok=True, parents=True)
        file = self.get_files(instance)[0]
        file.write_text(json.dumps(value, cls=znjson.ZnEncoder, indent=4))

    def get_data(self, instance: "Node") -> any:
        """Get the value of the field from the file."""
        file = self.get_files(instance)[0]
        return json.loads(
            instance.state.fs.read_text(file.as_posix()),
            cls=znjson.ZnDecoder,
        )

    def get_stage_add_argument(self, instance) -> typing.List[tuple]:
        """Get the DVC command for this field.

        Parameters
        ----------
        instance : Node
            The node instance.

        Returns
        -------
        list
            A list containing the DVC command for this field.

        """
        file = self.get_files(instance)[0]
        return [(f"--{self.dvc_option}", file.as_posix())]


class Plots(PlotsMixin, LazyField):
    """A field that is saved to disk."""

    dvc_option: str = "plots"
    group = FieldGroup.RESULT

    def get_dvc_data(self, instance: "Node") -> dict:
        """Get the DVC data."""
        return {"plots": [x.as_posix() for x in self.get_files(instance)]}

    def get_zntrack_data(self, instance: "Node") -> dict:
        """Get the zntrack data."""
        return {self.name: pathlib.Path(f"$nwd$/{self.name}.csv")}

    def get_files(self, instance) -> list:
        """Get the path of the file in the node directory."""
        return [get_nwd(instance) / f"{self.name}.csv"]

    def save(self, instance: "Node"):
        """Save the field to disk."""
        super().save(instance)
        try:
            value = self.get_value_except_lazy(instance)
        except DataIsLazyError:
            return
        if value is None:
            return

        instance.nwd.mkdir(exist_ok=True, parents=True)
        file = self.get_files(instance)[0]
        value.to_csv(file)

    def get_data(self, instance: "Node") -> any:
        """Get the value of the field from the file."""
        file = self.get_files(instance)[0]
        return pd.read_csv(instance.state.fs.open(file.as_posix()), index_col=0)

    def get_stage_add_argument(self, instance) -> typing.List[tuple]:
        """Get the dvc command for this field."""
        file = self.get_files(instance)[0]
        return [(f"--{self.dvc_option}", file.as_posix())]


_default = object()


def _get_all_connections_and_instances(value) -> list["Node"]:
    """Get Nodes from Connections and CombinedConnections."""
    connections = []
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, znflow.CombinedConnections):
            stack.extend(node.connections)
        elif isinstance(node, znflow.Connection):
            instance = node.instance
            while isinstance(instance, znflow.Connection):
                instance = instance.instance
            connections.append(instance)
    return connections


class Dependency(LazyField):
    """A dependency field."""

    dvc_option = "deps"
    group = FieldGroup.PARAMETER

    def __init__(self, default=_default):
        """Create a new dependency field.

        A `zn.deps` does not support default values.
        To build a dependency graph, the values must be passed at runtime.
        """
        if default is _default:
            super().__init__()
        elif default is None:
            super().__init__(default=default)
        else:
            raise ValueError(
                "A dependency field does not support default dependencies. You can only"
                " use 'None' to declare this an optional dependency"
                f"and not {default}."
            )

    def get_files(self, instance) -> list:
        """Get the affected files of the respective Nodes."""
        files = []

        value = getattr(instance, self.name)
        # TODO use IterableHandler?

        if isinstance(value, dict):
            value = list(value.values())
        if not isinstance(value, (list, tuple)):
            value = [value]
        if isinstance(value, tuple):
            value = list(value)

        others = []
        for node in value:
            if isinstance(node, (znflow.CombinedConnections, znflow.Connection)):
                others.extend(_get_all_connections_and_instances(node))
            else:
                others.append(node)

        value = others

        for node in value:
            node: Node
            if node is None:
                continue
            if node._external_:
                from zntrack.utils import run_dvc_cmd

                # TODO save these files in a specific directory called `external`
                # TODO the `dvc import cmd` should not run here but rather be a stage?

                deps_file = pathlib.Path("external", f"{node.uuid}.json")
                deps_file.parent.mkdir(exist_ok=True, parents=True)

                # zntrack run node.name --external \
                # --remote node.state.remote --rev node.state.rev

                # when combining with zn.nodes this should be used
                # dvc stage add <name> --params params.yaml:<name>
                # --outs nodes/<name>/node-meta.json zntrack run <name> --external

                cmd = [
                    "import",
                    node.state.remote if node.state.remote is not None else ".",
                    (get_nwd(node) / "node-meta.json").as_posix(),
                    "-o",
                    deps_file.as_posix(),
                ]
                if node.state.rev is not None:
                    cmd.extend(["--rev", node.state.rev])
                # TODO how can we test, that the loaded file truly is the correct one?
                if not deps_file.exists():
                    run_dvc_cmd(cmd)
                files.append(deps_file.as_posix())
                # dvc import node-meta.json + add as dependency file
                continue
            # if node.state.rev is not None or node.state.remote is not None:
            #     # TODO if the Node has a `rev` or `remote` attribute, we need to
            #     #  get the UUID file of the respective Node through node.state.fs.open
            #     # save that somewhere (can't use NWD, because we can now have multiple
            #     # nodes with the same name...)
            #     # and make the uuid a dependency of the node.
            #     continue
            files.append(get_nwd(node) / "node-meta.json")
            for field in zninit.get_descriptors(Field, self=node):
                if field.dvc_option in ["params", "deps"]:
                    # We do not want to depend on parameter files or
                    # recursively on dependencies.
                    continue
                files.extend(field.get_files(node))
                log.debug(f"Found field {field} and extended files to {files}")
        return files

    def save(self, instance: "Node"):
        """Save the field to disk."""
        try:
            value = self.get_value_except_lazy(instance)
        except DataIsLazyError:
            return

        self._write_value_to_config(
            value,
            instance,
            encoder=znjson.ZnEncoder.from_converters(
                [ConnectionConverter, CombinedConnectionsConverter], add_default=True
            ),
        )

    def get_data(self, instance: "Node") -> any:
        """Get the value of the field from the file."""
        zntrack_dict = json.loads(
            instance.state.fs.read_text(config.files.zntrack),
        )
        value = zntrack_dict[instance.name][self.name]

        value = update_key_val(value, instance=instance)

        value = json.loads(
            json.dumps(value),
            cls=znjson.ZnDecoder.from_converters(
                [ConnectionConverter, CombinedConnectionsConverter], add_default=True
            ),
        )

        # Up until here we have connection objects. Now we need
        # to resolve them to Nodes. The Nodes, as in 'connection.instance'
        #  are already loaded by the ZnDecoder.
        return handler.UpdateConnectors()(value)

    def get_stage_add_argument(self, instance) -> typing.List[tuple]:
        """Get the dvc command for this field."""
        return [
            (f"--{self.dvc_option}", pathlib.Path(file).as_posix())
            for file in self.get_files(instance)
        ]


class _SaveNodes(znflow.utils.IterableHandler):
    def default(self, value, **kwargs):
        name = kwargs["name"]
        if isinstance(value, znflow.Node):
            value.name = name
            value.save(results=False)
        return value


class NodeField(Dependency):
    """Add another Node as a field.

    The other Node will provide its parameters and methods to be used.
    From a graph standpoint, it will add these parameters and methods to the Node
    it is attached to.
    The Node will not execute its run method or save any results to disk.
    """

    def __set__(self, instance, value):
        """Disable the _graph_ in the value 'Node'."""
        if value is None:
            return super().__set__(instance, value)

        for entry in value if isinstance(value, (list, tuple)) else [value]:
            if hasattr(entry, "_graph_"):
                entry._graph_ = None
                if entry.uuid in instance._graph_:
                    raise exceptions.ZnNodesOnGraphError(
                        node=entry, field=self, instance=instance
                    )
            else:
                raise TypeError(f"The value must be a Node and not {entry}.")
        return super().__set__(instance, value)

    def get_node_names(self, instance) -> list:
        """Get the name of the other Node."""
        try:
            value = self.get_value_except_lazy(instance)
        except DataIsLazyError:
            return []

        if value is None:  # the zn.nodes(None) case
            return []
        if isinstance(value, (list, tuple)):
            return [f"{instance.name}_{self.name}_{idx}" for idx in range(len(value))]
        return [f"{instance.name}_{self.name}"]

    def save(self, instance: "Node"):
        """Save the Node parameters to disk."""
        try:
            value = self.get_value_except_lazy(instance)
        except DataIsLazyError:
            return

        if value is not None:
            if not isinstance(value, (list, tuple)):
                value = [value]

            for node, name in zip(value, self.get_node_names(instance)):
                _SaveNodes()(node, name=name)
        super().save(instance)

    def _get_nwd(self, instance: "Node", name: str) -> pathlib.Path:
        """Get the node working directory."""
        # get the name of the parent directory as string
        # e.g. we have nodes/AL_0/AL_0_ASEMD_checker_list_0
        # but want nodes/AL_0/ASEMD_checker_list_0
        if name.startswith(get_nwd(instance).parent.name):
            return (
                get_nwd(instance).parent / name[len(get_nwd(instance).parent.name) + 1 :]
            )
        else:
            return get_nwd(instance).parent / name

    def get_optional_dvc_cmd(
        self, instance: "Node", git_only_repo: bool
    ) -> typing.List[list]:
        """Get the dvc command for this field."""
        nodes = getattr(instance, self.name)
        if nodes is None:
            return []

        names = self.get_node_names(instance)
        if not isinstance(nodes, (list, tuple)):
            nodes = [nodes]

        cmd = []

        for node, name in zip(nodes, names):
            if not isinstance(node, znflow.Node):
                raise TypeError(f"The value must be a Node and not {node}.")
            node.name = name
            module = module_handler(node.__class__)

            nwd = self._get_nwd(instance, name)
            node.__dict__["nwd"] = nwd

            _cmd = [
                "stage",
                "add",
                "--name",
                name,
                "--force",
                "--metrics-no-cache" if git_only_repo else "--outs",
                (nwd / "node-meta.json").as_posix(),  # HOW DO I MOVE THIS TO GROUP ?
                "--params",
                f"{config.files.zntrack}:{instance.name}.{self.name}",
            ]
            field_cmds = []
            for attr in zninit.get_descriptors(Params, self=node):
                field_cmds += attr.get_stage_add_argument(node)

            for field_cmd in set(field_cmds):
                _cmd += list(field_cmd)

            _cmd += [
                f"zntrack run {module}.{node.__class__.__name__} --name"
                f" {name} --meta-only"
            ]

            cmd.append(_cmd)

        return cmd

    def get_files(self, instance: "Node") -> list:
        """Get the files affected by this field."""
        return [
            self._get_nwd(instance, name) / "node-meta.json"
            for name in self.get_node_names(instance)
        ]
