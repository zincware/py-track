import contextlib
import json
import logging
import os
import subprocess
import uuid

import tqdm
import yaml
import znflow

from zntrack import utils
from zntrack.group import Group
from zntrack.state import PLUGIN_LIST
from zntrack.utils.finalize import make_commit
from zntrack.utils.import_handler import import_handler
from zntrack.utils.misc import load_env_vars

from . import config
from .deployment import ZnTrackDeployment

log = logging.getLogger(__name__)


class Project(znflow.DiGraph):
    def __init__(
        self,
        *args,
        disable=False,
        immutable_nodes=True,
        deployment=None,
        tags: dict[str, str] | None = None,
        **kwargs,
    ):
        if deployment is None:
            deployment = ZnTrackDeployment()
        self.tags = tags or {}
        load_env_vars()
        super().__init__(
            *args,
            disable=disable,
            immutable_nodes=immutable_nodes,
            deployment=deployment,
            **kwargs,
        )

    def compute_all_node_names(self) -> dict[uuid.UUID, str]:
        """Compute the Node name based on existing nodes on the graph."""
        all_nodes = [self.nodes[uuid]["value"] for uuid in self.nodes]
        node_names = {}
        for node in all_nodes:
            if "name" in node.__dict__ and node.__dict__["name"] is not None:
                if node.__dict__["name"] in node_names.values():
                    raise ValueError(
                        f"A node with the name '{node.__dict__['name']}' already exists."
                    )
                if node.state.group is None:
                    if self.active_group is not None:
                        node_names[node.uuid] = (
                            f"{'_'.join(self.active_group.names)}_{node.__dict__['name']}"
                        )
                    else:
                        node_names[node.uuid] = node.__dict__["name"]
                else:
                    node_names[node.uuid] = (
                        f"{'_'.join(node.state.group.name)}_{node.__dict__['name']}"
                    )
            else:
                if node.state.group is None:
                    if self.active_group is not None:
                        node_name = f"{'_'.join(self.active_group.names)}_{node.__class__.__name__}"
                    else:
                        node_name = node.__class__.__name__
                else:
                    node_name = (
                        f"{'_'.join(node.state.group.name)}_{node.__class__.__name__}"
                    )
                if node_name not in node_names.values():
                    node_names[node.uuid] = node_name
                else:
                    i = 0
                    while True:
                        i += 1
                        if f"{node_name}_{i}" not in node_names.values():
                            node_names[node.uuid] = f"{node_name}_{i}"
                            break
        return node_names

    def add_node(self, node_for_adding, **attr):
        from zntrack import Node

        if not isinstance(node_for_adding, Node):
            raise ValueError(
                f"Node must be an instance of 'zntrack.Node', not {type(node_for_adding)}"
            )

        return super().add_node(node_for_adding, **attr)

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            for group in self.groups.values():
                for node_uuid in group.uuids:
                    # we need to access the `state` attribute to initialize
                    # the property, so the `log.debug` is necessary!
                    log.debug(self.nodes[node_uuid]["value"].state)
                    self.nodes[node_uuid]["value"].__dict__["state"]["group"] = (
                        Group.from_znflow_group(group)
                    )

            all_node_names = self.compute_all_node_names()
            for node_uuid in self.nodes:
                self.nodes[node_uuid]["value"].__dict__["name"] = all_node_names[
                    node_uuid
                ]
        finally:
            super().__exit__(exc_type, exc_val, exc_tb)

    def build(self) -> None:
        log.info(f"Saving {config.PARAMS_FILE_PATH}")
        params_dict = {}
        dvc_dict = {"stages": {}, "plots": []}
        zntrack_dict = {}
        for node_uuid in tqdm.tqdm(self):
            node = self.nodes[node_uuid]["value"]
            if node._external_:
                continue
            for plugin in node.state.plugins.values():
                # TODO: combine all params into one dict
                if (
                    value := plugin.convert_to_params_yaml()
                ) is not config.PLUGIN_EMPTY_RETRUN_VALUE:
                    params_dict[node.name] = value
                if (
                    value := plugin.convert_to_dvc_yaml()
                ) is not config.PLUGIN_EMPTY_RETRUN_VALUE:
                    dvc_dict["stages"][node.name] = value["stages"]
                    # TODO: this won't work if multiple plugins want to modify the dvc.yaml
                    if len(value["plots"]) > 0:
                        dvc_dict["plots"].extend(value["plots"])
                if (
                    value := plugin.convert_to_zntrack_json(graph=self)
                ) is not config.PLUGIN_EMPTY_RETRUN_VALUE:
                    zntrack_dict[node.name] = value

        if len(dvc_dict["plots"]) == 0:
            del dvc_dict["plots"]

        config.PARAMS_FILE_PATH.write_text(yaml.safe_dump(params_dict))
        config.DVC_FILE_PATH.write_text(yaml.safe_dump(dvc_dict))
        config.ZNTRACK_FILE_PATH.write_text(json.dumps(zntrack_dict, indent=4))

        # TODO: update file or overwrite?

    def repro(self, build: bool = True, force: bool = False):
        if build:
            self.build()
        cmd = ["dvc", "repro"]
        if force:
            cmd.append("--force")
        subprocess.check_call(cmd)

    def finalize(
        self,
        msg: str | None = None,
        commit: bool = True,
        skip_cached: bool = True,
        update_run_names: bool = True,
        **kwargs,
    ):
        """Finalize the project by making a commit and loading environment variables.

        This method performs the following actions:
        1. Makes a commit with the provided message if `commit` is True.
        2. Loads environment variables.
        3. Loads and finalizes plugins specified in the `ZNTRACK_PLUGINS` environment variable.

        Parameters
        ----------
        msg : str, optional
            The commit message. If None, the message will be 'zntrack: auto commit'.
        commit : bool, optional
            Whether to make a commit or not. Default is True
        skip_cached : bool, optional
            Do not upload cached nodes.
        update_run_names: bool, optional
            Include part of the commit message in the run names.
        **kwargs
            Additional keyword arguments to pass to `make_commit`.

        """
        if msg is None:
            msg = "zntrack: auto commit"
        if commit:
            make_commit(msg, **kwargs)
        utils.misc.load_env_vars()
        plugins_paths = os.environ.get(
            "ZNTRACK_PLUGINS", "zntrack.plugins.dvc_plugin.DVCPlugin"
        )
        plugins: PLUGIN_LIST = [import_handler(p) for p in plugins_paths.split(",")]
        for plugin in plugins:
            plugin.finalize(skip_cached=skip_cached, update_run_names=update_run_names)

    @contextlib.contextmanager
    def group(self, *names: str):
        """Group nodes together.

        Parameters
        ----------
        names : list[str], optional
            The name of the group. If None, the group will be named 'GroupX' where X is
            the number of groups + 1. If more than one name is given, the groups will
            be nested to 'nwd = name[0]/name[1]/.../name[-1]'

        """
        # This context manager also open self.__enter__ in the `super`
        if not names:
            name = "Group1"
            while (name,) in self.groups:
                name = f"Group{int(name[5:]) + 1}"
            names = (name,)

        with super().group(*names) as znflow_grp:
            group = Group(name=znflow_grp.names)
            yield group
        group._nodes = znflow_grp.nodes
