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
import shutil
import tempfile
import typing

import znjson

from zntrack.utils.config import config

log = logging.getLogger(__name__)


# https://stackoverflow.com/questions/42033142/is-there-an-easy-way-to-check-if-an-object-is-json-serializable-in-python
def is_jsonable(x: dict) -> bool:
    """

    Parameters
    ----------
    x: dict
        Dictionary to check, if it is json serializable.

    Returns
    -------
    bool: Whether the dict was serializable or not.

    """
    try:
        json.dumps(x)
        return True
    except (TypeError, OverflowError):
        return False


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
