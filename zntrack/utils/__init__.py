"""Standard python init file for the utils directory."""

import dataclasses
import enum
import json
import logging
import os
import pathlib
import shutil
import sys
import tempfile
import typing as t

import dvc.cli
import znflow
import znjson

from zntrack.utils import cli
from zntrack.utils.config import DISABLE_TMP_PATH, config

__all__ = [
    "cli",
    "node_wd",
    "config",
    "DISABLE_TMP_PATH",
]

if t.TYPE_CHECKING:
    from zntrack import Node, Project


class LazyOption:
    """Indicates that the value of the field should is loaded lazily."""

    def __init__(self) -> None:
        """Constructor.

        Raises
        ------
        NotImplementedError:
            This class is not meant to be instantiated.
        """
        raise NotImplementedError("This class is not meant to be instantiated.")


log = logging.getLogger(__name__)


def module_handler(obj) -> str:
    """Get the module for the Node.

    There are three cases that have to be handled here:
        1. Run from __main__ should not have __main__ as module but
            the actual filename.
        2. Run from a Jupyter Notebook should not return the launchers name
            but __main__ because that might be used in tests
        3. Return the plain module if the above are not fulfilled.

    Parameters
    ----------
    obj:
        Any object that implements __module__
    """
    if config.nb_name:
        try:
            return f"{config.nb_class_path}.{obj.__name__}"
        except AttributeError:
            return f"{config.nb_class_path}.{obj.__class__.__name__}"
    if obj.__module__ != "__main__":
        if hasattr(obj, "_module_"):  # allow module override
            return obj._module_
        return obj.__module__
    if pathlib.Path(sys.argv[0]).stem == "ipykernel_launcher":
        # special case for e.g. testing
        return obj.__module__
    return pathlib.Path(sys.argv[0]).stem


def deprecated(reason, version="v0.0.0"):
    """Depreciation Warning."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            log.critical(
                f"DeprecationWarning for {func.__name__}: {reason} (Deprecated since"
                f" {version})"
            )
            return func(*args, **kwargs)

        return wrapper

    return decorator


class DVCProcessError(Exception):
    """DVC specific message for CalledProcessError."""


def run_dvc_cmd(script, stdout=None):
    """Run the DVC script via subprocess calls.

    Parameters
    ----------
    script: tuple[str]|list[str]
        A list of strings to pass the subprocess command
    stdout: callable, optional
        A callable to which the stdout is passed. If None, the stdout is
        passed to log.warning.

    Raises
    ------
    DVCProcessError:
        if the dvc cli command fails.
    """
    dvc_short_string = " ".join(script[:5])
    if len(script) > 5:
        dvc_short_string += " ..."
    if stdout is None:
        stdout = log.warning
    stdout(f"Running DVC command: '{dvc_short_string}'")
    # do not display the output if log.log_level > logging.INFO
    show_log = config.log_level < logging.INFO
    if not show_log:
        script = script[:2] + ["--quiet"] + script[2:]
    if config.log_level == logging.DEBUG:
        script = [x for x in script if x != "--quiet"]
        script = script[:2] + ["--verbose", "--verbose"] + script[2:]

    return_code = dvc.cli.main(script)
    if return_code != 0:
        raise DVCProcessError(
            f'DVC CLI failed ({return_code}) for cmd: \n "dvc'
            f' {" ".join(x for x in script if x != "--quiet")}" '
        )
    # fix for https://github.com/iterative/dvc/issues/8631
    for logger_name, logger in logging.root.manager.loggerDict.items():
        if logger_name.startswith("zntrack"):
            logger.disabled = False
    return return_code


def update_key_val(values, instance):
    """Update the keys {rev, remote} based on the instance state.

    If the value of keys is None, the value is updated based on the instance
    state. Otherwise, it is assumed the Node depends on a specific rev or remote.
    """
    if isinstance(values, (list, tuple)):
        return [update_key_val(v, instance) for v in values]
    if isinstance(values, dict):
        for key, val in values.items():
            if key == "rev" and val is None:
                values[key] = instance.state.rev
            elif key == "remote" and val is None:
                values[key] = instance.state.remote
            elif isinstance(val, dict):
                update_key_val(val, instance)
        return values


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
    AVAILABLE : int
        the Node instance was loaded and results are available.
    """

    UNKNOWN = 0
    PENDING = 1
    RUNNING = 2
    FINISHED = 3
    FAILED = 4
    AVAILABLE = 5


def cwd_temp_dir(required_files=None) -> tempfile.TemporaryDirectory:
    """Change into a temporary directory.

    Helper for e.g. the docs to quickly change into a temporary directory
    and copy all files, e.g. the Notebook into that directory.

    Parameters
    ----------
    required_files: list, optional
        A list of optional files to be copied

    Returns
    -------
    temp_dir:
        The temporary  directory file. Close with temp_dir.cleanup() at the end.
    """
    temp_dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
    # add ignore_cleanup_errors=True in Py3.10?

    if config.nb_name is not None:
        shutil.copy(config.nb_name, temp_dir.name)
        if config.dvc_api:
            # TODO: why is this required?
            log.debug("Setting 'config.dvc_api=False' for use in Jupyter Notebooks.")
            config.dvc_api = False
    if required_files is not None:
        for file in required_files:
            shutil.copy(file, temp_dir.name)

    os.chdir(temp_dir.name)

    return temp_dir


@dataclasses.dataclass
class NodeName:
    """The name of a node."""

    groups: znflow.Group
    name: str
    varname: str = None
    suffix: int = 0
    use_varname: bool = False

    def __str__(self) -> str:
        """Get the node name."""
        name = []
        if self.groups is not None:
            name.extend(x for x in self.groups.names[0])
        if self.use_varname:
            name.append(self.varname)
        else:
            name.append(self.name)
        if self.suffix > 0 and self.use_varname:
            raise ValueError("Suffixes are not supported for magic names (varnames).")
        if self.suffix > 0:
            name.append(str(self.suffix))
        return "_".join(name)

    def get_name_without_groups(self) -> str:
        """Get the node name without the groups."""
        name = self.varname if self.use_varname else self.name
        if self.suffix > 0:
            name += f"_{self.suffix}"
        return name

    def update_suffix(self, project: "Project", node: "Node") -> None:
        """Update the suffix."""
        self.use_varname = project.magic_names

        node_names = []
        for node_uuid in project.graph.nodes:
            if node_uuid == node.uuid:
                continue
            node_names.append(project.graph.nodes[node_uuid]["value"].name)

        if project.automatic_node_names:
            while str(self) in node_names:
                self.suffix += 1


def get_nwd(node: "Node", mkdir: bool = False) -> pathlib.Path:
    """Get the node working directory.

    This is used instead of `node.nwd` because it allows
    for parameters to define if the nwd should be created.

    Attributes
    ----------
    node: Node
        The node instance for which the nwd should be returned.
    mkdir: bool, optional
        If True, the nwd is created if it does not exist.

    """
    try:
        nwd = node.__dict__["nwd"]
    except KeyError:
        if node.state.remote is None and node.state.rev is None and not node.state.loaded:
            nwd = pathlib.Path("nodes", znflow.get_attribute(node, "name"))
        else:
            try:
                with node.state.fs.open(config.files.zntrack) as f:
                    zntrack_config = json.load(f)
                nwd = zntrack_config[znflow.get_attribute(node, "name")]["nwd"]
                nwd = json.loads(json.dumps(nwd), cls=znjson.ZnDecoder)
            except (FileNotFoundError, KeyError):
                nwd = pathlib.Path("nodes", znflow.get_attribute(node, "name"))

    if mkdir:
        nwd.mkdir(parents=True, exist_ok=True)
    return nwd
