"""Standard python init file for the utils directory."""
import enum
import logging
import os
import pathlib
import shutil
import sys
import tempfile
import unittest.mock

import dvc.cli
import git

from zntrack.utils import cli
from zntrack.utils.config import config

__all__ = [
    "cli",
    "node_wd",
    "config",
]


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


def run_dvc_cmd(script):
    """Run the DVC script via subprocess calls.

    Parameters
    ----------
    script: tuple[str]|list[str]
        A list of strings to pass the subprocess command
    Raises
    ------
    DVCProcessError:
        if the dvc cli command fails.
    """
    dvc_short_string = " ".join(script[:5])
    if len(script) > 5:
        dvc_short_string += " ..."
    log.warning(f"Running DVC command: '{dvc_short_string}'")
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
            f"DVC CLI failed ({return_code}) for cmd: \n \"{' '.join(script)}\" "
        )
    # fix for https://github.com/iterative/dvc/issues/8631
    for logger_name, logger in logging.root.manager.loggerDict.items():
        if logger_name.startswith("zntrack"):
            logger.disabled = False
    return return_code


def capture_run_dvc_cmd(script) -> str:
    """Try to caputre the output of the DVC command."""
    with unittest.mock.patch("dvc.ui.ui.write") as magic_mock:
        run_dvc_cmd(script)
    return magic_mock.call_args.args[0]


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
    """

    UNKNOWN = 0
    PENDING = 1
    RUNNING = 2
    FINISHED = 3
    FAILED = 4


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


def convert_to_list(value) -> list:
    """Convert value to a list if it is not already one.
    
    If 'value is None', return an empty list.
    """
    if not isinstance(value, (list, tuple)):
        return [] if value is None else [value]
    return value


def update_gitignore(prefix) -> None:
    """Add 'nodes/<prefix>_*' to the gitignore file, if not already there."""
    ignore = f"nodes/{prefix}_*"

    repo = git.Repo(".")
    if repo.ignored(ignore):
        return

    gitignore = pathlib.Path(".gitignore")
    with gitignore.open("a", encoding="utf-8") as file:
        file.write("\n# ZnTrack operating directory \n")
        file.write(f"{ignore}\n")
