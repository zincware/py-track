import contextlib
import dataclasses
import os
import pathlib
import tempfile
import typing as t

import dvc.api
import dvc.repo
import dvc.stage.serialize

# import dvc.stage.serialize
from dvc.utils import dict_sha256

from zntrack.config import NodeStatusEnum, ZNTRACK_LAZY_VALUE, NOT_AVAILABLE, ZNTRACK_OPTION, ZnTrackOptionEnum
from zntrack.exceptions import NodeNotAvailableError, InvalidOptionError
from zntrack.utils.import_handler import import_handler
from zntrack.plugins import ZnTrackPlugin

if t.TYPE_CHECKING:
    from zntrack import Node

PLUGIN_LIST = list[t.Type[ZnTrackPlugin]]


@dataclasses.dataclass(frozen=True)
class NodeStatus:
    name: str | None
    remote: str | None
    rev: str | None
    run_count: int = 0
    state: NodeStatusEnum = NodeStatusEnum.CREATED
    lazy_evaluation: bool = True
    tmp_path: pathlib.Path | None = None
    node: "Node|None" = dataclasses.field(
        default=None, repr=False, compare=False, hash=False
    )
    group: tuple[str] | None = None
    # TODO: move node name and nwd to here as well

    @property
    def fs(self) -> dvc.api.DVCFileSystem:
        """Get the file system of the Node."""
        return dvc.api.DVCFileSystem(
            url=self.remote,
            rev=self.rev,
        )

    @property
    def restarted(self) -> bool:
        """Whether the node was restarted."""
        return self.run_count > 1

    @contextlib.contextmanager
    def use_tmp_path(self, path: pathlib.Path | None = None) -> t.Iterator[None]:
        """Load the data for '*_path' into a temporary directory.

        If you can not use 'node.state.fs.open' you can use
        this as an alternative. This will load the data into
        a temporary directory and then delete it afterwards.
        The respective paths 'node.*_path' will be replaced
        automatically inside the context manager.

        This is only set, if either 'remote' or 'rev' are set.
        Otherwise, the data will be loaded from the current directory.
        """
        if path is not None:
            raise NotImplementedError("Custom paths are not implemented yet.")

        with tempfile.TemporaryDirectory() as tmpdir:
            self.node.__dict__["state"]["tmp_path"] = pathlib.Path(tmpdir)
            try:
                yield
            finally:
                self.node.__dict__["state"].pop("tmp_path")

    def get_stage(self) -> dvc.stage.PipelineStage:
        """Access to the internal dvc.repo api."""
        remote = self.remote if self.remote != "." else None
        with dvc.repo.Repo(remote=remote, rev=self.rev) as repo:
            stage = repo.stage.collect(self.name)[0]
            if self.rev is None:
                # If the rev is not None, we don't need this but get:
                # AttributeError: 'Repo' object has no attribute 'stage_cache'
                stage.save(allow_missing=True, run_cache=False)
            return stage

    def get_stage_lock(self) -> dict:
        """Access to the internal dvc.repo api."""
        stage = self.get_stage()
        return dvc.stage.serialize.to_single_stage_lockfile(stage)

    def get_stage_hash(self, include_outs: bool = False) -> str:
        """Get the hash of the stage."""
        if include_outs:
            raise NotImplementedError("Include outs is not implemented yet.")
        try:
            # I do not understand what is goind on here?
            (
                self.node.nwd / "node-meta.json"
            ).touch()  # REMOVE!!!! node-meta might exist, do not remove!!
            stage_lock = self.get_stage_lock()
        finally:
            content = (self.node.nwd / "node-meta.json").read_text()
            if content == "":
                (self.node.nwd / "node-meta.json").unlink()

        filtered_lock = {
            k: v for k, v in stage_lock.items() if k in ["cmd", "deps", "params"]
        }
        return dict_sha256(filtered_lock)

    @property
    def plugins(self) -> dict:
        """Get the plugins of the node."""
        plugins_paths = os.environ.get(
            "ZNTRACK_PLUGINS", "zntrack.plugins.dvc_plugin.DVCPlugin"
        )
        plugins: PLUGIN_LIST = [import_handler(p) for p in plugins_paths.split(",")]

        return {plugin.__name__: plugin(self.node) for plugin in plugins}

    def to_dict(self) -> dict:
        """Convert the NodeStatus to a dictionary."""
        content = dataclasses.asdict(self)
        content.pop("node")
        return content

    def extend_plots(self, attribute: str, data: dict):
        # if isintance(target, str): ...
        # TODO: how to check if something has already been written when using extend_plot on
        # some plots but not on others in the final saving step?

        # TODO: check that the stage hash is the same if metrics are set or not
        # TODO: test get_stage_hash with params / metrics / plots / outs / out_path / ...
        import pandas as pd

        fields = dataclasses.fields(self.node)
        for field in fields:
            if field.name == attribute:
                option_type = field.metadata.get(ZNTRACK_OPTION)
                if option_type == ZnTrackOptionEnum.PLOTS:
                    break
                else:
                    raise InvalidOptionError(f"Can not use self.{attribute} with type {option_type} for 'plots'.")
        else:
            raise InvalidOptionError(f"Unable to find 'self.{attribute}' in {self.node}.")

        try:
            target = getattr(self.node, attribute)
        except NodeNotAvailableError:
            target = pd.DataFrame()
        if target is ZNTRACK_LAZY_VALUE or target is NOT_AVAILABLE:
            # TODO: accessing data in a node that is not loaded will not raise NodeNotAvailableErrors!
            target = pd.DataFrame()
        print(target)
        df = pd.concat([target, pd.DataFrame([data])], ignore_index=True)
        setattr(self.node, attribute, df)
        for plugin in self.plugins.values():
            plugin.extend_plots(attribute, data, reference=df)
