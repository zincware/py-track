"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description: Node core
"""

from __future__ import annotations

import logging
import subprocess
import json

from .data_classes import SlurmConfig
from .parameter import ZnTrackOption
from zntrack.core.data_classes import DVCParams, ZnParams, DVCOptions
from pathlib import Path
from zntrack.utils import is_jsonable, serializer, deserializer, config
from zntrack.utils.types import ZnTrackType, ZnTrackStage

from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from zntrack.utils.type_hints import TypeHintParent

log = logging.getLogger(__name__)


class ZnTrackProperty:
    """Map the correct ZnTrack instance to the correct cls

    This is required, because we use setattr(TYPE(cls)) and not on the
    instance, so we need to distinguish between different instances,
    otherwise there is only a single cls.zntrack for all instances!

    We save the Node instance in self.__dict__ to avoid this.
    """

    def __get__(self, instance, owner):
        """

        Parameters
        ----------
        instance: TypeHintParent
            An instance of the decorated function
        owner

        Returns
        -------
        Node:
            the zntrack property to handle Node
        """
        try:
            return instance.__dict__["zntrack"]
        except KeyError:
            instance.__dict__["zntrack"] = ZnTrackParent(instance)
            return instance.__dict__["zntrack"]

    def __set__(self, instance, value):
        raise NotImplementedError("Can not change zntrack property!")


class ZnTrackParent(ZnTrackType):
    """Parent class to be applied within the decorator"""

    def __init__(self, child):
        """Constructor for the DVCOp parent class"""
        log.debug(f"New instance of {self} with {child}")
        self.child: TypeHintParent = child

        # Parameters that will be overwritten by "child" classes
        self.slurm_config: SlurmConfig = SlurmConfig()

        self.running = False  # is set to true, when run_dvc
        self.load = False
        self.has_metadata = False

        self.nb_mode = False  # notebook mode

        self.dvc_options: DVCOptions = DVCOptions()

        # Property Storage
        self._dvc = None
        self._zn = None

        self._module = None
        self._stage_name = None

    #################################
    # decorating methods
    #################################

    def pre_init(self, name: str, load: bool, has_metadata: bool):
        """Function to be called prior to the init

        Parameters
        ----------
        name: str
            Custom name for the stage/Node that will overwrite the autogenerated
            name based on the class.__name__
        load: bool
            set the stage to be loaded
        has_metadata: bool
            check by the decorator if any methods write to self.metadata.
            This can e.g. be TimeIt decorators.
        """
        self.stage_name = name
        self.load = load
        self.has_metadata = has_metadata

    def post_init(self):
        """Post init command

        This command is executed after the init of the "child" class.
        It handles:
        - updating which attributes are parameters and descriptors_from_file

        """
        self.update_options_defined_in_init()
        if self.has_metadata:
            self.add_metadata_descriptor()
        if self.load:
            self.load_internals()
            self.child.__dict__.update(self.zn.internals)
            # update_dvc is not necessary but also should not hurt?!
            self.update_dvc()

    def pre_call(self):
        """Method to be run before the call"""
        if self.load:
            raise ValueError("This stage is being loaded and can not be called.")

    def post_call(
        self, dvc_options: DVCOptions, slurm: bool, silent: bool,
    ):
        """Method after call

        This function should always be the last one in the __call__ method,
        it handles file IO and DVC execution

        Parameters
        ----------
        dvc_options: DVCOptions
            Dataclass collecting all the optional DVC options, e.g. force, external,...
        slurm: bool, default=False
            Use `SRUN` with self.slurm_config for this stage - WARNING this doesn't
            mean that every stage uses slurm and you may accidentally run stages on
            your HEAD Node. You can check the commands in dvc.yaml!
        silent: bool
            If called with no_exec=False this allows to hide the output from the
            subprocess call.

        """
        self.update_dvc()
        self.save_internals()

        if config.no_dvc:
            return

        self.dvc_options = dvc_options
        self.write_dvc(slurm, silent)

    def pre_run(self):
        """Command to be run before run

        Updates internals.

        """
        self.running = True

    def post_run(self):
        """Method to be executed after run

        Save all zn.<option> from the child.__dict__
        to files so that they can be loaded again
        """

        desc_from_file = {}
        for attr, val in self.zntrack_options.items():
            if val.load:
                try:
                    desc_from_file[val.option].update(
                        {val.name: getattr(self.child, attr)}
                    )
                except KeyError:
                    desc_from_file[val.option] = {val.name: getattr(self.child, attr)}

        self.zn.internals = desc_from_file

    #################################
    # stand-alone methods
    #################################

    def add_metadata_descriptor(self):
        """Create a descriptor which is called metadata

        this descriptor is a metrics option in DVC,
        similar to `metadata=zn.metrics()`
        """
        log.debug("Adding ZnTrackOption for cls.metadata ")
        py_track_option = ZnTrackOption(option="metadata", name="metadata", load=True)

        setattr(type(self.child), "metadata", py_track_option)

    def update_options_defined_in_init(self):
        """Fix ZnTrackOption as attribute of the parent class

        This is required, if the znTrackOption is defined inside the __init__
        because that means :code:`ZnTrackOption in vars(hello_world)` but we require
        :code:`ZnTrackOption in vars(hello_world.__class__)` so with this code we update
        the parent class

        Notes
        -----
        It should be preferred to set them not in the __init__ but under the class
        definition to make them parts of the parent class
            >>> class HelloWorld:
            >>>     option=ZnTrackOption()


        """

        remove_from__dict__ = []

        for attr, value in vars(self.child).items():
            if isinstance(value, ZnTrackOption):
                # this is not hard coded, because when overwriting
                # ZnTrackOption those custom descriptors also need to be applied!
                log.warning(
                    f"DeprecationWarning: please move the definition "
                    f"of {attr} from __init__ to class level!"
                )

                log.debug(
                    f"Updating {attr} with {value.option} / {attr} "
                    f"and default {value.default_value}"
                )

                value: ZnTrackOption  # or child instances
                ParsedZnTrackOption = value.__class__
                try:
                    log.debug(f"Updating {attr} with ZnTrackOption!")

                    py_track_option = ParsedZnTrackOption(
                        option=value.option,
                        default_value=value.default_value,
                        name=attr,
                        load=value.load,
                    )

                    setattr(type(self.child), attr, py_track_option)
                    remove_from__dict__.append(attr)
                except ValueError:
                    log.warning(f"Skipping {attr} update - might already be fixed!")

        # Need to remove them from __dict__, because when setting them inside
        #  the __init__ the __dict__ is set and we don't want that!
        for attr in remove_from__dict__:
            log.debug(f"removing: {self.child.__dict__.pop(attr, None)} ")

    #################################
    # properties
    #################################

    @property
    def zn(self) -> ZnParams:
        """Get instance of the ZnParams dataclass initialized with the stage name"""
        if self._zn is None:
            self._zn = ZnParams(node_name=self.stage_name)
        return self._zn

    @property
    def dvc(self) -> DVCParams:
        """Get the DVCParams initialized with the stage name"""
        if self._dvc is None:
            self._dvc = DVCParams(node_name=self.stage_name)
        return self._dvc

    @property
    def python_interpreter(self) -> str:
        """Find the most suitable python interpreter

        Try to run subprocess check calls to see, which python interpreter
        should be selected

        Returns
        -------
        interpreter: str
            Name of the python interpreter that works with subprocess calls

        """

        for interpreter in ["python3", "python"]:
            try:
                subprocess.check_call(
                    [interpreter, "--version"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                log.debug(f"Using command {interpreter} for dvc!")
                return interpreter

            except subprocess.CalledProcessError:
                log.debug(f"{interpreter} is not working!")
        raise ValueError(
            "Could not find a working python interpreter to work with subprocesses!"
        )

    @property
    def name(self) -> str:
        """required for the dvc run command

        Used in
        .. code-block::

            self.python_interpreter -c f"from {self.module} import {self.name};"
                f'{self.name}(load=True).run()"'

        Returns
        -------
        str: Name of this class

        """
        return self.child.__class__.__name__

    @property
    def module(self) -> str:
        """Module from which to import <name>

        Used for from <module> import <name>

        Notes
        -----
        this can be changed when using nb_mode
        """
        if self._module is None:
            self._module = self.child.__class__.__module__
        return self._module

    @property
    def stage_name(self) -> str:
        """Get the stage name"""
        if self._stage_name is None:
            return self.name
        return self._stage_name

    @stage_name.setter
    def stage_name(self, value):
        """Set the stage name"""
        self._stage_name = value

    @property
    def zntrack_options(self) -> Dict[str, ZnTrackOption]:
        """Get all ZnTracKOptions in child

        Returns
        -------
        dict:
            A dictionary containing all ZnTrackOptions and their corresponding name
            in child as {name: ZnTrackOption}
        """
        zntrack_options = {}
        for attr, val in vars(type(self.child)).items():
            if isinstance(val, ZnTrackOption):
                zntrack_options[attr] = val
        return zntrack_options

    @property
    def has_user_params(self) -> bool:
        """Check for any dvc.params()

        Returns
        --------
        bool:
            If the Node has any dvc.params() that will be passed to the params file
             and are of interest to the user
        """
        return "params" in self.dvc.internals

    #################################
    # more complex functions
    #################################

    def update_dvc(self):
        """Update the DVCParams with the options from self.dvc

        This method searches for all ZnTrackOptions that are defined within the __init__
        """

        log.debug(f"checking for instance {self.child}")
        for attr, val in self.zntrack_options.items():
            option = val.option
            if option == "params":
                # params is processed  differently
                continue
            elif val.load:
                file = self.zn.node_path / getattr(self.zn, option)
                # We want the filename to be metadata from the zn
                #  but the dvc option is metrics
                #  TODO filename and option should be coupled more loosely
                #    for load=True options to avoid this part here!
                if option == "metadata":
                    option = "metrics"
                self.dvc.update(file, option)
            else:
                child_val = getattr(self.child, attr)
                log.debug(f"processing {attr} - {child_val}")
                # check if it is a Node, that has to be handled extra

                if isinstance(child_val, list) or isinstance(child_val, tuple):
                    # process lists/tuples if more than a single value is given
                    for item in child_val:
                        self.dvc.update(item, option)
                else:
                    self.dvc.update(child_val, option)

    def write_dvc(
        self, slurm: bool = False, silent: bool = False,
    ):
        """Write the DVC file using run.

        If it already exists it'll tell you that the stage is already persistent and
        has been run before. Otherwise it'll run the stage for you.

        Parameters
        ----------
        slurm: bool, default = False
            Use SLURM to run DVC stages on a Cluster.
        silent: bool
            If called with no_exec=False this allows to hide the output from the
            subprocess call.

        Notes
        -----
        If the dependencies for a stage change this function won't necessarily tell you.
        Use 'dvc status' to check, if the stage needs to be rerun.

        """
        if not silent:
            log.warning("--- Writing new DVC file! ---")

        script = ["dvc", "run", "-n", self.stage_name]

        script += self.dvc.dvc_arguments

        if self.has_user_params:
            script += [
                "--params",
                f"{self.dvc.internals_file}:{self.stage_name}",
            ]

        if self.nb_mode:
            script += [
                "--deps",
                Path(*self.module.split(".")).with_suffix(".py").as_posix(),
            ]

        script.extend(self.dvc_options.dvc_arguments)

        if slurm:
            log.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            log.warning(
                "Make sure, that every stage uses SLURM! If a stage does not have SLURM"
                " enabled, the command will be run on the HEAD NODE! Check the dvc.yaml"
                " file before running! There are no checks implemented to test, "
                "that only SRUN is in use!"
            )
            log.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

            script.append("srun")
            script.append("-n")
            script.append(f"{self.slurm_config.n}")
        #
        script.append(
            f"""{self.python_interpreter} -c "from {self.module} import {self.name}; """
            f"""{self.name}(load=True, name='{self.stage_name}').run()" """
        )
        log.debug(f"running script: {' '.join([str(x) for x in script])}")

        log.debug(
            "If you are using a jupyter notebook, you may not be able to see the "
            "output in real time!"
        )
        process = subprocess.run(script, capture_output=True)
        if not silent:
            if len(process.stdout) > 0:
                log.info(process.stdout.decode())
            if len(process.stderr) > 0:
                log.warning(process.stderr.decode())

    def save_internals(self):
        """Write all changed descriptor_parameters to file

        Update e.g. the parameters, out paths, etc. in the zntrack.json file
        """
        descriptor_parameters = {}

        for attr, val in self.zntrack_options.items():
            if val.load:
                continue
            option_dict = descriptor_parameters.get(val.option, {})
            # Values in the dictionary are of HIGHER PRIORITY, because some
            #  methods e.g. use a descriptor and store the values in a serialized
            #  way in the __dict__ (e.g. zn.Methods())
            try:
                option_dict[val.name] = self.child.__dict__[attr]
            except KeyError:
                # if the values are not stored in the __dict__
                #  they are often only accessible via a getattr.
                #  Although this is of LESS PRIORITY!
                option_dict[val.name] = getattr(self.child, attr)

            descriptor_parameters[val.option] = option_dict

        log.debug(f"Serializing {descriptor_parameters}")
        self.dvc.internals = serializer(descriptor_parameters)

    def load_internals(self):
        """Load the descriptor_parameters from the zntrack.json file"""
        try:
            log.debug(f"un-serialize {self.dvc.internals}")
            stage_internals = deserializer(self.dvc.internals)

            # stage_internals = {param: {param1: val1, ...}, deps: {deps1: val1, ...}}

            for option in stage_internals.values():
                for key, val in option.items():
                    if isinstance(val, ZnTrackStage):
                        # Load the ZnTrackStage
                        self.child.__dict__[key] = val.load_zntrack_node()
                    elif isinstance(val, list):
                        try:
                            self.child.__dict__[key] = [
                                item.load_zntrack_node() for item in val
                            ]
                        except AttributeError:
                            # Everything except the ZnTrackStage
                            self.child.__dict__[key] = val
                    else:
                        # Everything except the ZnTrackStage
                        self.child.__dict__[key] = val

        except KeyError:
            log.debug(f"No descriptor_parameters found for {self.stage_name}")
