"""ZnTrack file I/O."""
import json
import logging
import pathlib
import typing

import yaml
import znjson

log = logging.getLogger(__name__)


def read_file(file: pathlib.Path) -> dict:
    """Read a json/yaml file without the znjson.Decoder.

    Parameters
    ----------
    file: pathlib.Path
        The file to read

    Raises
    ------
    ValueError: if the file type is not supported
    FileNotFoundError: if the file does not exist

    Returns
    -------
    dict:
        Content of the json/yaml file
    """
    if file.suffix in [".yaml", ".yml"]:
        file_content = yaml.safe_load(file.read_text())
    elif file.suffix == ".json":
        file_content = json.loads(file.read_text())
    else:
        raise ValueError(f"File with suffix {file.suffix} is not supported")
    return file_content


def write_file(file: pathlib.Path, value: dict, mkdir: bool = True):
    """Save dict to file.

    Store dictionary to json or yaml file

    Parameters
    ----------
    file: pathlib.Path
        File to save to
    value: dict
        Any serializable data to save
    mkdir: bool
        Create a parent directory if necessary
    """
    if mkdir:
        file.parent.mkdir(exist_ok=True, parents=True)

    if file.suffix in [".yaml", ".yml"]:
        file.write_text(yaml.safe_dump(value, indent=4, default_style="|"))
    elif file.suffix == ".json":
        file.write_text(json.dumps(value, indent=4, cls=znjson.ZnEncoder))
    else:
        raise ValueError(f"File with suffix {file.suffix} is not supported")


def clear_config_file(file: pathlib.Path, node_name: str):
    """Clear the entries in the files for the given node name.

    Parameters
    ----------
    file: pathlib.Path
        The file to read from, e.g. params.yaml / zntrack.json
    node_name: str
        The name of the Node
    """
    try:
        file_content = read_file(file)
    except FileNotFoundError:
        file_content = {}

    _ = file_content.pop(node_name, None)
    write_file(file, value=file_content)


def update_config_file(
    file: pathlib.Path,
    node_name: typing.Union[str, None],
    value_name: typing.Union[str, None],
    value,
):
    """Update a configuration file.

    The file structure for node_name is not None is something like
    >>> {node_name: {value_name: value}}
    and for node_name is None:
    >>> {value_name: value}

    Parameters
    ----------
    file: pathlib.Path
        The file to save to
    node_name: str|None
        the node_name, if None the file is assumed to be {value_name: value}
    value_name: str|None
        the key of the value to update, if None the file is assumed to
        be {node_name: value}.
    value:
        The value to write to the file
    """
    # Read file
    if node_name is None and value_name is None:
        raise ValueError("Either node_name or value_name must not be None")

    try:
        file_content = read_file(file)
    except FileNotFoundError:
        file_content = {}
    log.debug(f"Loading <{file}> content: {file_content}")
    if node_name is None:
        log.debug(f"Update <{value_name}> with: {value}")
        file_content[value_name] = value
    elif value_name is None:
        log.debug(f"Update <{node_name}> with: {value}")
        file_content[node_name] = value
    else:
        # select primary node name key
        node_content = file_content.get(node_name, {})
        log.debug(f"Gathered <{node_name}> content: {node_content}")
        # update with new value
        node_content[value_name] = value
        log.debug(f"Update <{value_name}> with: {value}")
        # save to file
        file_content[node_name] = node_content
    write_file(file, value=file_content)
    log.debug(f"Update <{file}> with: {file_content}")


def update_desc(file: pathlib.Path, node_name: str, desc: str):
    """Update the 'dvc.yaml' with a description."""
    if desc is not None:
        file_content = read_file(file)
        file_content["stages"][node_name]["desc"] = desc
        write_file(file, value=file_content)


def update_meta(file: pathlib.Path, node_name: str, data: dict):
    """Update the file (dvc.yaml) given the Node for 'meta' key with the data."""
    if data is not None:
        file_content = read_file(file)
        meta_data = file_content["stages"][node_name].get("meta", {})
        if not isinstance(meta_data, dict):
            raise ValueError(
                "The 'meta' key in the 'dvc.yaml' is not empty or was otherwise modified."
                " To use 'zntrack.meta' it is not possible to use that field otherwise."
            )
        meta_data.update(data)
        file_content["stages"][node_name]["meta"] = meta_data
        write_file(file, value=file_content)
