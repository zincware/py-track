"""The class for the ZnTrackProject."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
import pathlib
import shutil
import subprocess
import typing

import dvc.api
import git
import tqdm
import yaml
import znflow
from znflow.handler import UpdateConnectors

from zntrack import exceptions
from zntrack.core.node import Node, get_dvc_cmd
from zntrack.utils import NodeName, config, run_dvc_cmd
from zntrack.utils.cli import get_groups

log = logging.getLogger(__name__)


def _initalize():
    """Initialize the project."""
    try:
        _ = git.Repo()
    except git.exc.InvalidGitRepositoryError:
        # TODO ASSERT IS EMPTY!
        repo = git.Repo.init()
        repo.init()
        run_dvc_cmd(["init", "--quiet"])
        # Create required files:
        config.files.zntrack.write_text(json.dumps({}))
        config.files.dvc.write_text(yaml.safe_dump({}))
        config.files.params.write_text(yaml.safe_dump({}))
        repo.git.add(A=True)
        repo.index.commit("Project initialized.")


class ZnTrackGraph(znflow.DiGraph):
    """Subclass of the znflow.DiGraph."""

    project: Project = None

    def add_node(self, node_for_adding: Node, **attr):
        """Rename Nodes if required."""
        if node_for_adding._external_:
            node_for_adding.name = NodeName(None, node_for_adding.name)
        else:
            node_for_adding.name = NodeName(self.active_group, node_for_adding.name)

        super().add_node(node_for_adding, **attr)


@dataclasses.dataclass
class Project:
    """The ZnTrack Project class.

    Attributes
    ----------
    graph : znflow.DiGraph
        the znflow graph of the project.
    initialize : bool, default = True
        If True, initialize a git repository and a dvc repository.
    remove_existing_graph : bool, default = False
        If True, remove 'dvc.yaml', 'zntrack.json' and 'params.yaml'
            before writing new nodes.
    automatic_node_names : bool, default = True
        If True, automatically add a number to the node name if the name is already
            used in the graph.
    git_only_repo : bool, default = True
        The DVC graph relies on file outputs for connecting stages.
        ZnTrack will use a '--metrics-no-cache' file output for each stage by default.
        Contrary to '--outs-no-cache', this will keep the DVC run cache available.
        If a project has a DVC remote available, '--outs' can be used instead.
        This will require a DVC remote to be setup.
    force : bool, default = False
        overwrite existing nodes.
    magic_names : bool, default = False
        If True, use magic names for the nodes. This will use the variable name of the
        node as the node name. E.g. `node = Node()` will result in a node name of 'node'.
        If used within a group, the group name will be added to the node name. E.g.
        `group.name = Grp1` and `model = Node()` will result in a name of 'Grp1_model'.
    """

    graph: ZnTrackGraph = dataclasses.field(default_factory=ZnTrackGraph, init=False)
    initialize: bool = True
    remove_existing_graph: bool = False
    automatic_node_names: bool = True
    git_only_repo: bool = True
    force: bool = False
    magic_names: bool = False

    _groups: dict[str, NodeGroup] = dataclasses.field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self):
        """Initialize the Project.

        Attributes
        ----------
        initialize : bool, default = True
            If True, initialize a git repository and a dvc repository.
        remove_existing_graph : bool, default = False
            If True, remove 'dvc.yaml', 'zntrack.json' and 'params.yaml'
              before writing new nodes.
        """
        self.graph.project = self
        if self.initialize:
            _initalize()
        if self.remove_existing_graph:
            # we remove the files that typically contain the graph definition
            config.files.zntrack.unlink(missing_ok=True)
            config.files.dvc.unlink(missing_ok=True)
            config.files.params.unlink(missing_ok=True)
            shutil.rmtree("nodes", ignore_errors=True)

        if self.automatic_node_names and self.magic_names:
            raise ValueError(
                "automatic_node_names and magic_names can not be True at the same time"
            )

    def __enter__(self, *args, **kwargs):
        """Enter the graph context."""
        self.graph.__enter__(*args, **kwargs)
        return self

    def __exit__(self, *args, **kwargs):
        """Exit the graph context."""
        self.graph.__exit__(*args, **kwargs)

        node_names = []
        for node_uuid in self.graph.nodes:
            node = self.graph.nodes[node_uuid]["value"]
            if node._external_:
                continue

            if node.name in node_names and not self.force:
                raise exceptions.DuplicateNodeNameError(node)

            node_names.append(node.name)

    @contextlib.contextmanager
    def group(self, *names: typing.List[str]):
        """Group nodes together.

        Parameters
        ----------
        names : list[str], optional
            The name of the group. If None, the group will be named 'GroupX' where X is
            the number of groups + 1. If more than one name is given, the groups will
            be nested to 'nwd = name[0]/name[1]/.../name[-1]'
        """
        if not names:
            name = "Group1"
            while pathlib.Path("nodes", name).exists():
                name = f"Group{int(name[5:]) + 1}"
            names = (name,)

        try:
            grp = self._groups[names]
        except KeyError:
            nwd = pathlib.Path("nodes", *names)
            nwd.mkdir(parents=True, exist_ok=True)
            grp = NodeGroup(name="_".join(names), nwd=nwd, nodes=[])
            self._groups[names] = grp

        with self.graph.group(names):
            yield grp
        # TODO: do we even need the group object?
        grp.nodes = [self.graph.nodes[x]["value"] for x in self.graph.get_group(names)]

        # we update the nwd when closing the context manager
        # changing the name is no longer possible after this
        for node in grp.nodes:
            if not node._external_:
                node.__dict__["nwd"] = grp.nwd / node._name_.get_name_without_groups()

    def auto_remove(self, remove_empty_dirs=True):
        """Remove all nodes from 'dvc.yaml' that are not in the graph."""
        _, dvc_node_names = get_groups(None, None)
        graph_node_names = [self.graph.nodes[x]["value"].name for x in self.graph.nodes]

        nodes_to_remove = []

        for node_name in dvc_node_names:
            if node_name not in graph_node_names:
                if "+" in node_name:
                    # currently there is no way to remove the zntrack.deps Nodes correctly
                    # so we check for the parent node, if that is not available, we remove
                    # the node
                    continue
                else:
                    nodes_to_remove.append(node_name)

        if len(nodes_to_remove):
            zntrack_config = json.loads(config.files.zntrack.read_text())

            for node_name in tqdm.tqdm(nodes_to_remove):
                run_dvc_cmd(["remove", node_name, "--outs"])
                _ = zntrack_config.pop(node_name, None)

            config.files.zntrack.write_text(json.dumps(zntrack_config, indent=4))

        if remove_empty_dirs:
            # remove all empty directories inside "nodes"
            for path in pathlib.Path("nodes").glob("**/*"):
                if path.is_dir() and not any(path.iterdir()):
                    path.rmdir()

    def run(
        self,
        eager=False,
        repro: bool = True,
        optional: dict = None,
        save: bool = True,
        environment: dict = None,
        nodes: list = None,
        auto_remove: bool = False,
    ):
        """Run the Project Graph.

        Parameters
        ----------
        eager : bool, default = False
            if True, run the nodes in eager mode.
            if False, run the nodes using dvc.
        save : bool, default = True
            if using 'eager=True' this will save the results to disk.
            Otherwise, the results will only be in memory.
        repro : bool, default = True
            if True, run dvc repro after running the nodes.
        optional : dict, default = None
            A dictionary of optional arguments for each node.
            Use {node_name: {arg_name: arg_value}} to pass arguments to nodes.
            Possible arg_names are e.g. 'always_changed: True'
        environment : dict, default = None
            A dictionary of environment variables for all nodes.
        nodes : list, default = None
            A list of node names to run. If None, run all nodes.
        auto_remove : bool, default = False
            If True, remove all nodes from 'dvc.yaml' that are not in the graph.
            This is the same as calling 'project.auto_remove()'
        """
        if not save and not eager:
            raise ValueError("Save can only be false if eager is True")

        self._handle_environment(environment)

        if optional is None:
            optional = {}

        node_names = None
        if nodes is not None:
            node_names = []
            for node in nodes:
                if isinstance(node, str):
                    node_names.append(node)
                elif isinstance(node, Node):
                    node_names.append(node.name)
                elif isinstance(node, NodeGroup):
                    node_names.extend([x.name for x in node.nodes])
                else:
                    raise ValueError(f"Unknown node type {type(node)}")

        sorted_nodes = self.graph.get_sorted_nodes()

        _tqdm_disabled = True if eager or len(sorted_nodes) <= 5 else False

        tbar = tqdm.tqdm(self.graph.get_sorted_nodes(), ncols=140, disable=_tqdm_disabled)

        for node_uuid in tbar:
            node: Node = self.graph.nodes[node_uuid]["value"]
            if node_names is not None and node.name not in node_names:
                continue
            node.nwd  # create the node working directory (property-access will create it)
            if node._external_:
                continue
            if eager:
                # update connectors
                log.info(f"Running node {node}")
                self.graph._update_node_attributes(node, UpdateConnectors())
                node.run()
                if save:
                    node.save()
                node.state.loaded = True
            else:
                log.info(f"Adding node {node}")
                cmd = get_dvc_cmd(
                    node, git_only_repo=self.git_only_repo, **optional.get(node.name, {})
                )
                for x in cmd:
                    stdout = None
                    if not _tqdm_disabled:
                        stdout = tbar.set_description
                    run_dvc_cmd(x, stdout=stdout)
                node.save(results=False)
        if not eager and repro:
            self.repro()
            # load the nodes
            for node_uuid in self.graph.get_sorted_nodes():
                node = self.graph.nodes[node_uuid]["value"]
                if node_names is not None and node.name not in node_names:
                    continue
                node.load()

        if auto_remove:
            self.auto_remove()

    def build(self, **kwargs) -> None:
        """Build the project graph without running it."""
        self.run(repro=False, **kwargs)

    def repro(self) -> None:
        """Run dvc repro."""
        run_dvc_cmd(["repro"])
        # TODO load nodes afterwards!

    def _handle_environment(self, environment: dict):
        """Write global environment variables to the env.yaml file."""
        if environment is not None:
            file = pathlib.Path("env.yaml")
            try:
                context = yaml.safe_load(file.read_text())
            except FileNotFoundError:
                context = {}

            context["global"] = environment
            file.write_text(yaml.safe_dump(context))

    def load(self):
        """Load all nodes in the project."""
        for node_uuid in self.graph.get_sorted_nodes():
            node = self.graph.nodes[node_uuid]["value"]
            node.load()

    def get_nodes(self) -> dict[str, znflow.Node]:
        """Get the nodes in the project."""
        nodes = {}
        for node_uuid in self.graph.get_sorted_nodes():
            node = self.graph.nodes[node_uuid]["value"]
            nodes[node.name] = node
        return nodes

    def remove(self, name):
        """Remove all nodes with the given name from the project."""
        # TODO there should never be multiple nodes with the same name
        for node_uuid in self.graph.get_sorted_nodes():
            node = self.graph.nodes[node_uuid]["value"]
            if node.name == name:
                self.graph.remove_node(node_uuid)

    @property
    def nodes(self) -> dict[str, znflow.Node]:
        """Get the nodes in the project."""
        return self.get_nodes()

    def create_branch(self, name: str) -> "Branch":
        """Create a branch in the project."""
        branch = Branch(self, name)
        branch.create()
        return branch

    @contextlib.contextmanager
    def create_experiment(self, name: str = None, queue: bool = True) -> Experiment:
        """Create a new experiment."""
        # TODO: return an experiment object that allows you to load the results
        # TODO this context manager WILL NOT ADD new nodes to the graph.

        exp = Experiment(name, project=self)

        repo = git.Repo()
        dirty = repo.is_dirty()
        if dirty:
            repo.git.stash("save", "--include-untracked")

        force = self.force
        self.force = True
        with self:
            yield exp
        self.run(repro=False)  # save nodes and update dvc.yaml
        self.force = force

        cmd = ["dvc", "exp", "run"]
        if queue:
            cmd.append("--queue")
        if name is not None:
            cmd.extend(["--name", name])
        try:
            proc = subprocess.run(cmd, capture_output=True, check=True)
            # "Reproducing", "Experiment", "'exp-name'"
            exp.name = proc.stdout.decode("utf-8").split()[2].replace("'", "")
        finally:
            repo.git.reset("--hard")
            repo.git.clean("-fd")
            if dirty:
                repo.git.stash("pop")
        if not queue:
            exp.apply()

    @property
    def experiments(self, *args, **kwargs) -> dict[str, Experiment]:
        """List all experiments."""
        experiments = dvc.api.exp_show(*args, **kwargs)
        return {
            experiment["Experiment"]: Experiment(experiment["rev"], project=self)
            for experiment in experiments
            if experiment["Experiment"] is not None
        }

    def run_exp(self, jobs: int = 1) -> None:
        """Run all queued experiments."""
        run_dvc_cmd(["exp", "run", "--run-all", "--jobs", str(jobs)])

    @property
    def branches(self):
        """Get the branches in the project."""
        repo = git.Repo()  # todo should be self.repo
        return [Branch(project=self, name=branch.name) for branch in repo.branches]


@dataclasses.dataclass
class Experiment:
    """A DVC Experiment."""

    name: str
    project: Project
    # TODO the project can not be used. The graph could be different.
    #  Project must be loaded from rev.
    # TODO name / rev / remote ...

    nodes: dict = dataclasses.field(default_factory=dict, init=False, repr=False)

    def apply(self) -> None:
        """Apply the experiment."""
        run_dvc_cmd(["exp", "apply", self.name])

    def load(self) -> None:
        """Load the nodes from this experiment."""
        self.nodes = {
            name: node.from_rev(name=name, rev=self.name)
            for name, node in self.project.get_nodes().items()
        }

    def __getitem__(self, key: typing.Union[str, Node]) -> Node:
        """Get the Node from the experiment."""
        if len(self.nodes) == 0:
            self.load()
        if isinstance(key, Node):
            key = key.name
        return self.nodes[key]


@dataclasses.dataclass
class Branch:
    """The ZnTrack Branch class for managing experiments."""

    project: Project
    name: str
    repo: git.Repo = dataclasses.field(init=False, repr=False, default_factory=git.Repo)

    def create(self):
        """Create the branch."""
        self.repo.create_head(self.name)

    def queue(self, name: str):
        """Queue the branch to run."""
        active_branch = self.repo.active_branch
        self.repo.git.checkout(self.name)
        self.run(eager=False, repro=False)

        # if self.repo.is_dirty():
        # if len(self.repo.untracked_files) > 0:
        self.repo.git.add(A=True)
        self.repo.index.commit(f"parameters for {name}")
        run_dvc_cmd(["exp", "run", "--name", name, "--queue"])

        for node_uuid in self.graph.get_sorted_nodes():
            node = self.graph.nodes[node_uuid]["value"]
            node.state.rev = name
        active_branch.checkout()


@dataclasses.dataclass
class NodeGroup:
    """A group of nodes."""

    name: tuple[str]
    nwd: pathlib.Path
    nodes: list[Node]

    def _get_name_with_prefix(self, name: str) -> str:
        """Get the name with the group prefix."""
        if name.startswith(self.name):
            return name
        return f"{self.name}_{name}"

    def __contains__(self, item: typing.Union[Node, str]) -> bool:
        """Check if the Node is in the group."""
        if isinstance(item, Node):
            item = item.name
        else:
            item = self._get_name_with_prefix(item)
        return item in [node.name for node in self.nodes]

    def __iter__(self) -> typing.Iterator[Node]:
        """Iterate over the nodes in the group."""
        return iter(self.nodes)

    def __getitem__(self, name: int) -> Node:
        """Get the Node from the group."""
        name = self._get_name_with_prefix(name)
        for node in self.nodes:
            if node.name == name:
                return node
        raise KeyError(f"Node {name} not in group {self.name}")

    def __len__(self) -> int:
        """Get the number of nodes in the group."""
        return len(self.nodes)
