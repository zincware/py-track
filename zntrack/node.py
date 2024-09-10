import dataclasses
import json
import pathlib
import typing as t

import typing_extensions as te
import znfields
import znflow

from zntrack.state import NodeStatus

from .config import NOT_AVAILABLE, ZNTRACK_LAZY_VALUE, NodeStatusEnum
from .utils.node_wd import get_nwd

try:
    from typing import dataclass_transform
except ImportError:
    from typing_extensions import dataclass_transform

T = t.TypeVar("T", bound="Node")


@dataclass_transform()
@dataclasses.dataclass(kw_only=True)
class Node(znflow.Node, znfields.Base):
    """A Node."""

    name: str | None = None

    _unique_output_ = False
    _protected_ = znflow.Node._protected_ + ["nwd", "name", "state"]

    def __post_init__(self):
        if self.name is None:
            # automatic node names expectes the name to be None when
            # exiting the graph context.
            if not znflow.get_graph() is not znflow.empty_graph:
                self.name = self.__class__.__name__

    def run(self):
        raise NotImplementedError

    def save(self):
        for plugin in self.state.plugins.values():
            for field in dataclasses.fields(self):
                value = getattr(self, field.name)
                if any(value is x for x in [ZNTRACK_LAZY_VALUE, NOT_AVAILABLE]):
                    raise ValueError(
                        f"Field '{field.name}' is not set. Please set it before saving."
                    )
                plugin.save(field)
        _ = self.state
        self.__dict__["state"]["state"] = NodeStatusEnum.FINISHED

    def __init_subclass__(cls):
        return dataclasses.dataclass(cls)

    @property
    def nwd(self) -> pathlib.Path:
        return get_nwd(self, mkdir=True)

    @classmethod
    def from_rev(
        cls: t.Type[T],
        name: str | None = None,
        remote: str | None = ".",
        rev: str | None = None,
        running: bool = False,
        lazy_evaluation: bool = True,
        **kwargs,
    ) -> T:
        if name is None:
            name = cls.__name__
        lazy_values = {}
        for field in dataclasses.fields(cls):
            lazy_values[field.name] = ZNTRACK_LAZY_VALUE

        lazy_values["name"] = name
        instance = cls(**lazy_values)

        try:
            with instance.state.fs.open(instance.nwd / "node-meta.json") as f:
                content = json.load(f)
                run_count = content["run_count"]
        except FileNotFoundError:
            run_count = 0

        # TODO: check if the node is finished or not.
        instance.__dict__["state"] = NodeStatus(
            name=name,
            remote=remote,
            rev=rev,
            run_count=run_count,
            state=NodeStatusEnum.RUNNING if running else NodeStatusEnum.FINISHED,
            lazy_evaluation=lazy_evaluation,
            node=None,
        ).to_dict()

        if not instance.state.lazy_evaluation:
            for field in dataclasses.fields(cls):
                _ = getattr(instance, field.name)

        return instance

    @property
    def state(self) -> NodeStatus:
        if "state" not in self.__dict__:
            self.__dict__["state"] = NodeStatus(
                name=self.name,
                remote=".",
                rev=None,
                run_count=0,
                state=NodeStatusEnum.CREATED,
                lazy_evaluation=True,
                node=None,
            ).to_dict()

        return NodeStatus(**self.__dict__["state"], node=self)

    def update_run_count(self):
        try:
            self.__dict__["state"]["run_count"] += 1
        except KeyError:
            self.__dict__["state"] = NodeStatus(
                name=self.name,
                remote=".",
                rev=None,
                run_count=1,
                state=NodeStatusEnum.RUNNING,
                lazy_evaluation=True,
                node=None,
            ).to_dict()
        (self.nwd / "node-meta.json").write_text(
            json.dumps({"uuid": str(self.uuid), "run_count": self.state.run_count})
        )

    @te.deprecated("loading is handled automatically via lazy evaluation")
    def load(self):
        pass
