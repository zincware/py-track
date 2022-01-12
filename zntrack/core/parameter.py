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

from zntrack.descriptor import Descriptor

log = logging.getLogger(__name__)


class ZnTrackOption(Descriptor):
    """Descriptor for all DVC options

    This class handles the __get__ and __set__ for the DVC options.
    For most cases this means storing them in the __init__ and keeping track of,
    which Options are used.
    This is required to allow for load=True which updates all ZnTrackOptions,
    based on the computed or otherwise stored values.

    Attributes
    ----------
    option: str
        One of the given options of DVC. The string should also be defined
        inside the dataclass!
    load: bool
        Load this Option  to memory when the stage is called with Stage(load=True)
        This is true for zn.<option> and false for dvc.<option>.

    """

    def __init__(self, default_value=None, **kwargs):
        """Instantiate a ZnTrackOption Descriptor

        Does only support kwargs and no args!

        Parameters
        ----------
        name: str
            Required when __set_name__ can not be used, e.g. if the ZnTrackOption
            is defined in the __init__ on not on a class level. It defines
            the name of the descriptor (for self.attr it would be attr).
        option: str
            One of the given options of DVC. The string should also be defined
            inside the dataclass!
        load: bool
            Load this Option  to memory when the stage is called with Stage(load=True)
            This is usually true for zn.<option> and false for dvc.<option>.
            The simplest example is dvc.result() (== zn.outs())
        """

        super().__init__(default_value)
        self.name = kwargs.get("name", None)

    def __repr__(self):
        return f"{self.__class__}({hex(id(self))}) for <{self.name}>"

    def __str__(self):
        return f"{self.metadata.dvc_option} / {self.name}"
