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

from zntrack.utils.config import config
from typing import Dict, Any
import hashlib
import base64

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
    temp_dir = tempfile.TemporaryDirectory()

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

def dict_hash(dictionary: Dict[str, Any], length: int = 22) -> str:
    """Convert dictionary to a (truncated) md5 hash

    Parameters
    ----------
    dictionary: dict
        any json serializable dictionary
    length: int, default=22
        length of the hash. The max length is 24, but the hash value can be
        truncated for convenience and e.g. shorter file names

    References
    ----------
    https://www.doc.ic.ac.uk/~nuric/coding/how-to-hash-a-dictionary-in-python.html

    Returns
    -------
    md5_hash_base64: str
        The base64 encoded and truncated md5 hash of the dictionary

    """
    md5_hash = hashlib.md5()

    encoded_dict = json.dumps(dictionary, sort_keys=True).encode()
    md5_hash.update(encoded_dict)
    md5_hash_base64 = base64.b64encode(md5_hash.digest())
    # convert to string
    md5_hash_base64 = md5_hash_base64.decode("utf-8")

    return md5_hash_base64[:length]
