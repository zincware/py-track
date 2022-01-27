from __future__ import annotations

import dataclasses
import logging
import pathlib
import subprocess
import sys
import typing

from zntrack.core.parameter import ZnTrackOption
from zntrack.utils import config
from zntrack.utils.utils import dict_hash

from .jupyter import jupyter_class_to_file

log = logging.getLogger(__name__)


def handle_deps(value) -> list:
    """Find all dependencies of value

    Parameters
    ----------
    value: any
        list, string, tuple, Path or Node instance

    Returns
    -------
    list:
        A list of strings like ["--deps", "<path>", --deps, "<path>", ...]

    """
    script = []
    if isinstance(value, list) or isinstance(value, tuple):
        for x in value:
            script += handle_deps(x)
    else:
        if isinstance(value, GraphWriter):
            for file in value.affected_files:
                script += ["--deps", pathlib.Path(file).as_posix()]
        elif isinstance(value, str) or isinstance(value, pathlib.Path):
            script += ["--deps", pathlib.Path(value).as_posix()]
        elif value is None:
            pass
        else:
            raise ValueError(f"Type {type(value)} is not supported!")

    return script


def get_dvc_arguments(options: dict) -> list:
    """Get the activated options

    Returns
    -------
    list: A list of strings for the subprocess call, e.g.:
        ["--no-commit", "--external"]
    """
    out = []

    for dvc_option, value in options.items():
        if value:
            out.append(f"--{dvc_option.replace('_', '-')}")
        else:
            if dvc_option == "no_exec":
                log.warning(
                    "You will not be able to see the stdout/stderr "
                    "of the process in real time!"
                )
    return out


def handle_dvc(value, dvc_args) -> list:
    """Convert list of dvc_paths to a dvc input string

    >>> handle_dvc("src/file.txt", "outs") == ["--outs", "src/file.txt"]
    """
    if not (isinstance(value, list) or isinstance(value, tuple)):
        value = [value]

    def option_func(_dvc_path):
        return f"--{dvc_args}"

    def posix_func(dvc_path):
        return pathlib.Path(dvc_path).as_posix()

    # double list comprehension https://stackoverflow.com/a/11869360/10504481
    return [f(x) for x in value for f in (option_func, posix_func)]


@dataclasses.dataclass
class DescriptorList:
    """Dataclass to collect all descriptors of some parent class"""

    parent: GraphWriter
    data: typing.List[ZnTrackOption] = dataclasses.field(default_factory=list)

    def filter(
        self, zntrack_type: typing.Union[str, list], return_with_type=False
    ) -> dict:
        """Filter the descriptor instances by zntrack_type

        Parameters
        ----------
        zntrack_type: str
            The zntrack_type of the descriptors to gather
        return_with_type: bool, default=False
            return a dictionary with the Descriptor.metadata.dvc_option as keys

        Returns
        -------
        dict:
            either {attr_name: attr_value}
            or
            {descriptor.dvc_option: {attr_name: attr_value}}

        """
        if not isinstance(zntrack_type, list):
            zntrack_type = [zntrack_type]
        data = [x for x in self.data if x.metadata.zntrack_type in zntrack_type]
        if return_with_type:
            types_dict = {x.metadata.dvc_option: {} for x in data}
            for x in data:
                types_dict[x.metadata.dvc_option].update(
                    {x.name: getattr(self.parent, x.name)}
                )
            return types_dict
        return {x.name: getattr(self.parent, x.name) for x in data}

    @property
    def full_data_dict(self) -> dict:
        return {x.name: getattr(self.parent, x.name) for x in self.data}

    @property
    def hash(self) -> str:
        return dict_hash(self.full_data_dict)[1:]  # remove the sign


class GraphWriter:
    """Write the DVC Graph

    Main method that handles writing the Graph / dvc.yaml file
    """

    _node_name = None
    _module = None

    def __init__(self, **kwargs):
        self.node_name = kwargs.get("name", None)

        [
            x.update_default()
            for x in self._descriptor_list.data
            if x.metadata.zntrack_type == "deps"
        ]

    @property
    def _descriptor_list(self) -> DescriptorList:
        """Get all descriptors of this instance"""
        descriptor_list = []
        for option in vars(type(self)).values():
            if isinstance(option, ZnTrackOption):
                descriptor_list.append(option)
        return DescriptorList(parent=self, data=descriptor_list)

    @property
    def node_name(self) -> str:
        """Name of this node"""
        if self._node_name is None:
            return self.__class__.__name__
        return self._node_name

    @node_name.setter
    def node_name(self, value):
        """Overwrite the default node name based on the class name"""
        self._node_name = value

    @property
    def module(self) -> str:
        """Module from which to import <name>

        Used for from <module> import <name>

        Notes
        -----
        this can be changed when using nb_mode
        """
        if self._module is None:
            if self.__class__.__module__ == "__main__":
                if pathlib.Path(sys.argv[0]).stem == "ipykernel_launcher":
                    # special case for e.g. testing
                    return self.__class__.__module__
                return pathlib.Path(sys.argv[0]).stem
            else:
                return self.__class__.__module__
        return self._module

    def save(self):
        """Some method to save the class state"""
        raise NotImplementedError

    @property
    def affected_files(self) -> typing.Set[pathlib.Path]:
        """list of all files that can be changed by this instance"""
        files = []
        for option in self._descriptor_list.data:
            file = option.get_filename(self)
            if file.tracked:
                files.append(file.path)
            elif file.value_tracked:
                value = getattr(self, option.name)
                if isinstance(value, list):
                    files += value
                else:
                    files.append(value)

        files = [x for x in files if x is not None]
        return set(files)

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

    def write_graph(
        self,
        silent: bool = False,
        nb_name: str = None,
        no_commit: bool = False,
        external: bool = False,
        always_changed: bool = False,
        no_exec: bool = True,
        force: bool = True,
        no_run_cache: bool = False,
        dry_run: bool = False,
        run: bool = None,
    ):
        """Write the DVC file using run.

        If it already exists it'll tell you that the stage is already persistent and
        has been run before. Otherwise it'll run the stage for you.

        Parameters
        ----------
        silent: bool
            If called with no_exec=False this allows to hide the output from the
            subprocess call.
        nb_name: str
            Notebook name when not using config.nb_name (this is not recommended)
        no_commit: dvc parameter
        external: dvc parameter
        always_changed: dvc parameter
        no_exec: dvc parameter
        run: bool, inverse of no_exec. Will overwrite no_exec if set.
        force: dvc parameter
        no_run_cache: dvc parameter
        dry_run: bool, default = False
            Only return the script but don't actually run anything

        Notes
        -----
        If the dependencies for a stage change this function won't necessarily tell you.
        Use 'dvc status' to check, if the stage needs to be rerun.

        """
        if run is not None:
            no_exec = not run

        if nb_name is None:
            nb_name = config.nb_name

        # Jupyter Notebook
        if nb_name is not None:
            self._module = f"{config.nb_class_path}.{self.__class__.__name__}"

            jupyter_class_to_file(
                silent=silent, nb_name=nb_name, module_name=self.__class__.__name__
            )

        self.save()

        if not silent:
            log.warning("--- Writing new DVC file! ---")

        script = ["dvc", "run", "-n", self.node_name]

        script += get_dvc_arguments(
            {
                "no_commit": no_commit,
                "external": external,
                "always_changed": always_changed,
                "no_exec": no_exec,
                "force": force,
                "no_run_cache": no_run_cache,
            }
        )

        # Jupyter Notebook
        if nb_name is not None:
            script += [
                "--deps",
                pathlib.Path(*self.module.split(".")).with_suffix(".py").as_posix(),
            ]

        # Handle Parameter
        if len(self._descriptor_list.filter(zntrack_type=["params", "method"])) > 0:
            script += [
                "--params",
                f"params.yaml:{self.node_name}",
            ]
        zn_options_set = set()
        for option in self._descriptor_list.data:
            value = getattr(self, option.name)
            if option.metadata.zntrack_type == "dvc":
                script += handle_dvc(value, option.metadata.dvc_args)
            # Handle Zn Options
            elif option.metadata.zntrack_type in ["zn", "metadata"]:
                zn_options_set.add(
                    (
                        f"--{option.metadata.dvc_args}",
                        option.get_filename(self).path.as_posix(),
                    )
                )
            elif option.metadata.zntrack_type == "deps":
                script += handle_deps(value)

        for pair in zn_options_set:
            script += pair

        # Add command to run the script
        cls_name = self.__class__.__name__
        script.append(
            f"""{self.python_interpreter} -c "from {self.module} import {cls_name}; """
            f"""{cls_name}.load(name='{self.node_name}').run_and_save()" """
        )
        log.debug(f"running script: {' '.join([str(x) for x in script])}")

        log.debug(
            "If you are using a jupyter notebook, you may not be able to see the "
            "output in real time!"
        )

        if dry_run:
            return script
        else:
            process = subprocess.run(script, capture_output=True, check=True)
            if not silent:
                if len(process.stdout) > 0:
                    log.info(process.stdout.decode())
                if len(process.stderr) > 0:
                    log.warning(process.stderr.decode())
