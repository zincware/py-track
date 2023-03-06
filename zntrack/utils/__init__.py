"""Standard python init file for the utils directory."""
import enum
import logging
import pathlib
import sys

import dvc.cli

from zntrack.utils import cli
from zntrack.utils.node_wd import nwd

__all__ = [
    "cli",
    "node_wd",
]

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
        if the dvc cli command fails
    """
    dvc_short_string = " ".join(script[:5])
    if len(script) > 5:
        dvc_short_string += " ..."
    log.warning(f"Running DVC command: '{dvc_short_string}'")
    # do not display the output if log.log_level > logging.INFO
    # show_log = config.log_level < logging.INFO
    # if not show_log:
    #     script = script[:2] + ["--quiet"] + script[2:]
    # if config.log_level == logging.DEBUG:
    #     script = [x for x in script if x != "--quiet"]
    #     script = script[:2] + ["--verbose", "--verbose"] + script[2:]

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
