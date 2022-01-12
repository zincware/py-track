"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description:
"""
from importlib import import_module


class NoneType:
    """Class for checking set values

    This class is never used outside of Node, so it can be used
    to identify if the value has been changed via
    >>> value = NoneType
    >>> if value is NoneType:
    >>>     print("value is unchanged")
    >>> value = None
    >>> if value is not NoneType:
    >>>     print("value changed")

    which can not be done with any built in python type
    """

    pass


class ZnTrackStage:
    """Class to identify ZnTrackStages

    This is used internally to mark a class definition as a ZnTrackStage.
    In comparison to ZnTrackType this is used to mark a class as a Stage that has not
    been called.

    >>> type(vars(Stage)['zntrack']) == 'ZnTrackProperty'
    # can not use the following:
    >>> type(vars(Stage())['zntrack']) == 'ZnTrackType'

    """

    def __init__(self, module, cls, name):
        """

        Parameters
        ----------
        module: str
            Name of the module to import from
        cls: str
            Name of the class to import from the module
        name: str
            Name of the ZnTrack Node
        """
        self.module = module
        self.cls = cls
        self.name = name

    def load_zntrack_node(self):
        """Load the ZnTrackStage"""
        module = import_module(self.module)
        cls = getattr(module, self.cls)

        return cls.load(name=self.name)
