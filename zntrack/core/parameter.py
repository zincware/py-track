"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description: Node parameter
"""
from __future__ import annotations

import logging
import pathlib

from zntrack.descriptor import Descriptor
from zntrack.utils import decode_dict, file_io

log = logging.getLogger(__name__)

import dataclasses


@dataclasses.dataclass
class File:
    path: pathlib.Path
    key: str = None
    tracked: bool = False  # the file itself is an affected_file
    value_tracked: bool = False  # the getattr(instance, self.name) is an affected file


class ZnTrackOption(Descriptor):
    """Descriptor for all DVC options

    This class handles the __get__ and __set__ for the DVC options.
    For most cases this means storing them in the __init__ and keeping track of,
    which Options are used.
    This is required to allow for load=True which updates all ZnTrackOptions,
    based on the computed or otherwise stored values.
    """

    def __init__(self, default_value=None, **kwargs):
        """Instantiate a ZnTrackOption Descriptor

        Does only support kwargs and no args!

        Parameters
        ----------
        default_value:
            Any default value to __get__ if the __set__ was never called.
        """

        super().__init__(default_value)
        self.name = kwargs.get("name", None)

    def __repr__(self):
        return f"{self.__class__}({hex(id(self))}) for <{self.metadata.dvc_option}>"

    def __str__(self):
        return f"{self.metadata.dvc_option} / {self.name}"

    def update_default(self):
        """Update default_value

        The default value is created upton instantiation of this descriptor,
        if a new class is created via Instance.load() it does not automatically load
        the default_value Nodes, so we must to this manually here
        """
        try:
            for value in self.default_value:
                # cheap trick because circular imports - TODO find clever fix!
                if hasattr(value, "_load"):
                    value._load()
        except TypeError:
            if hasattr(self.default_value, "_load"):
                self.default_value._load()

    def get_filename(self, instance) -> File:
        """Get the name of the file this ZnTrackOption will save its values to"""
        filename_dict = {
            "params": File(path=pathlib.Path("params.yaml"), key=instance.node_name),
            "iterable": File(path=pathlib.Path("params.yaml"), key=instance.node_name),
            "deps": File(path=pathlib.Path("zntrack.json"), key=instance.node_name),
            "dvc": File(
                path=pathlib.Path("zntrack.json"),
                key=instance.node_name,
                value_tracked=True,
            ),
            "method": File(path=pathlib.Path("zntrack.json"), key=instance.node_name),
            # replace this with also params.json!
            "zn": File(
                path=pathlib.Path(
                    "nodes", instance.node_name, f"{self.metadata.dvc_option}.json"
                ),
                tracked=True,
            ),
            "metadata": File(
                path=pathlib.Path(
                    "nodes", instance.node_name, f"{self.metadata.dvc_option}.json"
                ),
                tracked=True,
            ),
        }
        return filename_dict[self.metadata.zntrack_type]

    def save(self, instance):
        """Save this descriptor for the given instance to file

        Parameters
        ----------
        instance: Node
            instance where the Descriptor is attached to.
            Similar to __get__(instance) this requires the instance
            to be passed manually.
        """
        file = self.get_filename(instance)

        file_io.update_config_file(
            file.path,
            node_name=file.key,
            value_name=self.name,
            value=self.__get__(instance, self.owner),
        )

    def mkdir(self, instance):
        """Create a parent directory

        For parameters that are saved in e.g. nodes/<node_name>/file.json
        the nodes/<node_name>/ directory is created here. This is required
        for DVC to create a .gitignore file in these directories.
        """
        file = self.get_filename(instance)
        file.path.parent.mkdir(exist_ok=True, parents=True)

    def load(self, instance):
        """Load this descriptor value into the given instance

        Updates the instance.__dict__

        Parameters
        ----------
        instance: Node
            instance where the Descriptor is attached to.
            Similar to __get__(instance) this requires the instance
            to be passed manually.
        """
        file = self.get_filename(instance)
        try:
            file_content = file_io.read_file(file.path)
            # The problem here is, that I can not / don't want to load all Nodes but only
            # the ones, that are in [self.node_name][self.name] for deserializing
            if file.key is not None:
                values = decode_dict(file_content[file.key].get(self.name, None))
            else:
                values = decode_dict(file_content.get(self.name, None))

            log.debug(f"Loading {file.key} from {file}: ({values})")
            instance.__dict__.update({self.name: values})
        except (FileNotFoundError, KeyError):
            pass
