"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description:
"""
from __future__ import annotations

import logging

from zntrack.core.dvcgraph import GraphWriter
from zntrack.utils.config import config
from zntrack.utils.utils import deprecated

log = logging.getLogger(__name__)


class Node(GraphWriter):
    """Main parent class for all ZnTrack Node

    The methods implemented in this class are primarily loading and saving parameters.
    This includes restoring the Node from files and saving results to files after run.

    Attributes
    ----------
    is_loaded: bool
        if the class is loaded this can be used to only run certain code, e.g. in the init
    """

    is_loaded: bool = False

    def __init__(self, **kwargs):
        self.is_loaded = kwargs.pop("is_loaded", False)
        super().__init__(**kwargs)

    @deprecated(
        reason=(
            "Please check out https://zntrack.readthedocs.io/en/latest/_tutorials/"
            "migration_guide_v3.html for a migration tutorial from "
            "ZnTrack v0.2 to v0.3"
        ),
        version="v0.3",
    )
    def __call__(self, *args, **kwargs):
        """Still here for a depreciation warning for migrating to class based ZnTrack"""
        pass

    def save(self, results: bool = False):
        """Save Class state to files

        Parameters
        -----------
        results: bool, default=False
            Save changes in zn.<option>.
            By default, this function saves e.g. parameters but does not save results
            that are stored in zn.<option> and primarily zn.params / dvc.<option>
            Set this option to True if they should be saved, e.g. in run_and_save
        """
        # Save dvc.<option>, dvc.deps, zn.Method
        for option in self._descriptor_list.data:
            if results:
                # Save all
                option.save(instance=self)
            elif option.metadata.zntrack_type not in ["zn", "metrics"]:
                # Filter out zn.<options>
                option.save(instance=self)
            else:
                # Create the path for DVC to write a .gitignore file
                # for the filtered files
                option.mkdir(instance=self)

    def _load(self):
        """Load class state from files"""
        for option in self._descriptor_list.data:
            option.load(instance=self)
        self.is_loaded = True

    @classmethod
    def load(cls, name=None) -> Node:
        """

        Parameters
        ----------
        name: Node name

        Returns
        -------
        Instance of this class with the state loaded from files

        Examples
        --------
        Always have this, so that the name can be passed through

        def __init__(self, **kwargs):
            super().__init__(**kwargs)

        """

        try:
            instance = cls(name=name, is_loaded=True)
        except TypeError:
            log.warning(
                "Can not pass <name> to the super.__init__ and trying workaround! This"
                " can lead to unexpected behaviour and can be avoided by passing ("
                " **kwargs) to the super().__init__(**kwargs)"
            )
            instance = cls()
            if name not in (None, cls.__name__):
                instance.node_name = name

        if config.nb_name is not None:
            # TODO maybe check if it exists and otherwise keep default?
            instance._module = f"{config.nb_class_path}.{cls.__name__}"

        instance._load()

        return instance

    def run_and_save(self):
        """Main method to run for the actual calculation"""
        self.run()
        self.save(results=True)

    # @abc.abstractmethod
    def run(self):
        """Overwrite this method for the actual calculation"""
        raise NotImplementedError
