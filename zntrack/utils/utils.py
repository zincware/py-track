"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description:
"""

import json
import logging
import os
import pathlib
import shutil
import sys
import tempfile
import typing

import znjson

from zntrack.utils.config import config

log = logging.getLogger(__name__)


def cwd_temp_dir(required_files=None) -> tempfile.TemporaryDirectory:
    """Change into a temporary directory

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
    temp_dir = tempfile.TemporaryDirectory()  # add ignore_cleanup_errors=True in Py3.10?

    if config.nb_name is not None:
        shutil.copy(config.nb_name, temp_dir.name)
    if required_files is not None:
        for file in required_files:
            shutil.copy(file, temp_dir.name)

    os.chdir(temp_dir.name)

    return temp_dir


def deprecated(reason, version="v0.0.0"):
    """Depreciation Warning"""

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
    """Decode dict that was loaded without znjson"""
    return json.loads(json.dumps(value), cls=znjson.ZnDecoder)


def get_auto_init(fields: typing.List[str]):
    """Automatically create a __init__ based on fields
    Parameters
    ----------
    fields: list[str]
        A list of strings that will be used in the __init__, e.g. for [foo, bar]
        it will create __init__(self, foo=None, bar=None) using **kwargs
    """

    def auto_init(self, **kwargs):
        """Wrapper for the __init__"""
        for field in fields:
            try:
                setattr(self, field, kwargs.pop(field))
            except KeyError:
                pass
        super(type(self), self).__init__(**kwargs)

    return auto_init


def module_handler(obj) -> str:
    """Get the module for the Node

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
    if obj.__module__ == "__main__":
        if pathlib.Path(sys.argv[0]).stem == "ipykernel_launcher":
            # special case for e.g. testing
            if config.notebook is not None:
                return pathlib.Path(config.notebook).stem
            return obj.__module__
        return pathlib.Path(sys.argv[0]).stem
    return obj.__module__


def check_type(obj, types, allow_iterable=False, allow_none=False) -> bool:
    """Check if the obj is of any of the given types

    Parameters
    ----------
    obj: object to check
    types: single class or tuple of classes to check against
    allow_iterable: check list entries if a list is provided
    allow_none: accept None even if not in types.

    Returns
    -------

    """
    if isinstance(obj, (list, tuple, set)) and allow_iterable:
        for value in obj:
            if allow_none and value is None:
                continue
            if not isinstance(value, types):
                return False
    else:
        if allow_none and obj is None:
            return True
        if not isinstance(obj, types):
            return False

    return True
