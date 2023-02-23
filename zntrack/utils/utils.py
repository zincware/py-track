"""ZnTrack utils."""

import contextlib
import json
import logging
import os
import pathlib
import platform
import select
import shutil
import subprocess
import sys
import tempfile

import dvc.cli
import git
import znjson

from zntrack.utils.config import config
from zntrack.utils.exceptions import DVCProcessError

log = logging.getLogger(__name__)


def timed_input(text, timeout=10, default=None, condition=None):
    """Input with a timeout.

    This input is not enforced and returns the default value if anything goes wrong.
    """
    try:
        if platform.system() == "Windows":
            log.debug("Windows does not support select.select - skipping.")
            return default
        print(text)
        inputs, _, _ = select.select([sys.stdin], [], [], timeout)
        if inputs:
            user_input = sys.stdin.readline().strip()
            if condition is not None:
                return condition(user_input)
            return user_input
        return default
    except:  # noqa: E722
        return default


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


def decode_dict(value):
    """Decode dict that was loaded without znjson."""
    return json.loads(json.dumps(value), cls=znjson.ZnDecoder)


def encode_dict(value) -> dict:
    """Encode value into a dict serialized with ZnJson."""
    return json.loads(json.dumps(value, cls=znjson.ZnEncoder))


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


def check_type(
    obj, types, allow_iterable=False, allow_none=False, allow_dict=False
) -> bool:
    """Check if the obj is of the given types.

    This includes recursive search for nested lists / dicts and fails
    if any of the values is not in types

    Parameters
    ----------
    obj:
        object to check
    types:
        single class or tuple of classes to check against
    allow_iterable:
        check list entries if a list is provided
    allow_none:
        accept None even if not in types.
    allow_dict:
        allow for {key: types}
    """
    if isinstance(obj, (list, tuple, set)) and allow_iterable:
        for value in obj:
            if check_type(value, types, allow_iterable, allow_none, allow_dict):
                continue
            return False
    elif isinstance(obj, dict) and allow_dict:
        for value in obj.values():
            if check_type(value, types, allow_iterable, allow_none, allow_dict):
                continue
            return False
    else:
        if allow_none and obj is None:
            return True
        if not isinstance(obj, types):
            return False

    return True


def update_nb_name(nb_name: str) -> str:
    """Check the config file for a nb_name if None provided."""
    if nb_name is None:
        return config.nb_name
    return nb_name


def module_to_path(module: str, suffix=".py") -> pathlib.Path:
    """Convert module a.b.c to path(a/b/c)."""
    return pathlib.Path(*module.split(".")).with_suffix(suffix)


def dvc_unlock():
    """Remove DVC lock file."""
    rwlock = pathlib.Path(".dvc/tmp/rwlock")
    assert rwlock.exists()
    rwlock.unlink()


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
    show_log = config.log_level < logging.INFO
    if not show_log:
        script = script[:2] + ["--quiet"] + script[2:]
    if config.log_level == logging.DEBUG:
        script = [x for x in script if x != "--quiet"]
        script = script[:2] + ["--verbose", "--verbose"] + script[2:]

    if config.dvc_api:
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
    else:
        script = ["dvc"] + script
        try:
            # do not display the output if log.log_level > logging.INFO
            output = subprocess.run(script, check=True, capture_output=True)
            log.info(output.stdout.decode())
        except subprocess.CalledProcessError as err:
            raise DVCProcessError(
                f"Subprocess call with cmd: \n \"{' '.join(script)}\" \n"
                f"# failed after stdout: \n{err.stdout.decode()}"
                f"# with stderr: \n{err.stderr.decode()}"
            ) from err


def load_node_dependency(value):
    """Load a Node dependency if passed only a class.

    Parameters
    ----------
    value: anything
        This function creates an instance of value if it is a class of node. Otherwise,
        it does nothing.

    Returns
    -------
    value:
        If value was subclass of Node, it returns an instance of value, otherwise
        it returns value
    """
    from zntrack.core.base import Node

    if isinstance(value, (list, tuple)):
        value = [load_node_dependency(x) for x in value]
    with contextlib.suppress(TypeError):
        if issubclass(value, Node):
            value = value.load()
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


def convert_to_list(value) -> list:
    """Convert value to a list if it is not already one.

    If 'value is None', return an empty list.
    """
    if not isinstance(value, (list, tuple)):
        if value is None:
            return []
        return [value]
    return value
