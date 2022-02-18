"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description:
"""
from __future__ import annotations

import inspect
import logging

from zntrack import utils
from zntrack.core.dvcgraph import GraphWriter
from zntrack.zn import params

log = logging.getLogger(__name__)


def update_dependency_options(value):
    """Handle Node dependencies

    The default value is created upton instantiation of a ZnTrackOption,
    if a new class is created via Instance.load() it does not automatically load
    the default_value Nodes, so we must to this manually here and call update_options.
    """
    if isinstance(value, (list, tuple)):
        [update_dependency_options(x) for x in value]
    if isinstance(value, Node):
        value.update_options()


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
        super().__init__(**kwargs)
        self.is_loaded = kwargs.pop("is_loaded", False)
        for data in self._descriptor_list:
            if data.zntrack_type == utils.ZnTypes.deps:
                update_dependency_options(data.default_value)

    @utils.deprecated(
        reason=(
            "Please check out https://zntrack.readthedocs.io/en/latest/_tutorials/"
            "migration_guide_v3.html for a migration tutorial from "
            "ZnTrack v0.2 to v0.3"
        ),
        version="v0.3",
    )
    def __call__(self, *args, **kwargs):
        """Still here for a depreciation warning for migrating to class based ZnTrack"""

    def __init_subclass__(cls, **kwargs):
        """Add a dataclass-like init if None is provided"""

        # User provides an __init__
        if cls.__dict__.get("__init__") is not None:
            return cls

        # attach an automatically generated __init__ if None is provided
        zn_option_fields, sig_params = [], []
        for name, item in cls.__dict__.items():
            if isinstance(item, params):
                # For the new __init__
                zn_option_fields.append(name)

                # For the new __signature__
                sig_params.append(
                    inspect.Parameter(
                        name=name, kind=inspect.Parameter.POSITIONAL_OR_KEYWORD
                    )
                )

        # Add new __init__ to the sub-class
        setattr(cls, "__init__", utils.get_auto_init(fields=zn_option_fields))

        # Add new __signature__ to the sub-class
        signature = inspect.Signature(parameters=sig_params)
        setattr(cls, "__signature__", signature)

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
        for option in self._descriptor_list:
            if results:
                # Save all
                option.save(instance=self)
            elif option.zntrack_type not in [utils.ZnTypes.results]:
                # Filter out zn.<options>
                option.save(instance=self)
            else:
                # Create the path for DVC to write a .gitignore file
                # for the filtered files
                option.mkdir(instance=self)

    def update_options(self):
        """Update all ZnTrack options inheriting from ZnTrackOption

        This will overwrite the value in __dict__ even it the value was changed
        """
        for option in self._descriptor_list:
            log.debug(f"Updating {option.name} for {self}")
            try:
                self.__dict__[option.name] = option.get_data_from_files(instance=self)
            except (FileNotFoundError, KeyError) as err:
                # FileNotFound can happen, if a stage is added as a dependency but the
                #  respective files aren't written yet
                # KeyError can happen if e.g. params.yaml exists but does not yet contain
                #  the key for the given stage
                log.debug(f"Could not load {option.name} for {self} because of {err}")
        self.is_loaded = True

    @classmethod
    def load(cls, name=None) -> Node:
        """classmethod that yield a Node object

        This method does
        1. create a new instance of Node
        2. call Node._load() to update the instance

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
            try:
                instance = cls()
                if name not in (None, cls.__name__):
                    instance.node_name = name
                log.warning(
                    "Can not pass <name> to the super.__init__ and trying workaround!"
                    " This can lead to unexpected behaviour and can be avoided by passing"
                    " ( **kwargs) to the super().__init__(**kwargs)"
                )
            except TypeError as err:
                raise TypeError(
                    f"Unable to create a new instance of {cls}. Check that all arguments"
                    " default to None. It must be possible to instantiate the class via"
                    f" {cls}() without passing any arguments. See the ZnTrack"
                    " documentation for more information."
                ) from err

        instance.update_options()

        if utils.config.nb_name is not None:
            # TODO maybe check if it exists and otherwise keep default?
            instance._module = f"{utils.config.nb_class_path}.{cls.__name__}"
        return instance

    def run_and_save(self):
        """Main method to run for the actual calculation"""
        self.run()
        self.save(results=True)

    # @abc.abstractmethod
    def run(self):
        """Overwrite this method for the actual calculation"""
        raise NotImplementedError
