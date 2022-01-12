import logging
import pathlib
import subprocess
import typing

from zntrack.descriptor.base import DescriptorIO
from zntrack.utils import config

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
                script += ["--deps", file]
        else:
            script += ["--deps", value]

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


class GraphWriter(DescriptorIO):
    _node_name = None

    def __init__(self, *args, **kwargs):
        self.node_name = kwargs.get("name", None)

    @property
    def node_name(self):
        if self._node_name is None:
            return self.__class__.__name__
        return self._node_name

    @node_name.setter
    def node_name(self, value):
        self._node_name = value

    def save(self):
        raise NotImplementedError

    def module(self) -> str:
        raise NotImplementedError

    @property
    def affected_files(self) -> typing.Set[pathlib.Path]:
        """list of all files that can be changed by this instance"""
        files = []
        for option in self._descriptor_list.data:
            value = getattr(self, option.name)
            if option.metadata.zntrack_type == "zn":
                # Handle Zn Options
                files.append(
                    pathlib.Path("nodes")
                    / self.node_name
                    / f"{option.metadata.dvc_option}.json"
                )
            elif option.metadata.zntrack_type == "dvc":
                if value is None:
                    pass
                elif isinstance(value, list) or isinstance(value, tuple):
                    files += [pathlib.Path(x) for x in value]
                else:
                    files.append(pathlib.Path(value))
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
    ):
        """Write the DVC file using run.

        If it already exists it'll tell you that the stage is already persistent and
        has been run before. Otherwise it'll run the stage for you.

        Parameters
        ----------
        silent: bool
            If called with no_exec=False this allows to hide the output from the
            subprocess call.

        Notes
        -----
        If the dependencies for a stage change this function won't necessarily tell you.
        Use 'dvc status' to check, if the stage needs to be rerun.

        """

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
        if nb_name is None:
            nb_name = config.nb_name

        # Jupyter Notebook
        if nb_name is not None:
            self._module = f"{config.nb_class_path}.{self.__class__.__name__}"

            jupyter_class_to_file(
                silent=silent, nb_name=nb_name, module_name=self.__class__.__name__
            )

            script += [
                "--deps",
                pathlib.Path(*self.module.split(".")).with_suffix(".py").as_posix(),
            ]

        # Handle Parameter
        if len(self._descriptor_list.filter(zntrack_type="params")) > 0:
            script += [
                "--params",
                f"params.yaml:{self.node_name}",
            ]
        zn_options_set = set()
        for option in self._descriptor_list.data:
            value = getattr(self, option.name)
            # Handle DVC options
            if option.metadata.zntrack_type == "dvc":
                if isinstance(value, list) or isinstance(value, tuple):
                    for x in value:
                        script += [f"--{option.metadata.dvc_args}", x]
                else:
                    script += [f"--{option.metadata.dvc_args}", value]
            # Handle Zn Options
            elif option.metadata.zntrack_type == "zn":
                zn_options_set.add(
                    (
                        f"--{option.metadata.dvc_args}",
                        pathlib.Path("nodes")
                        / self.node_name
                        / f"{option.metadata.dvc_option}.json",
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

        subprocess.check_call(script)
