from __future__ import annotations

import dataclasses
import json
import logging
import pathlib
import typing

import znjson

from zntrack import descriptor, utils
from zntrack.core.jupyter import jupyter_class_to_file
from zntrack.core.zntrackoption import ZnTrackOption
from zntrack.descriptor import BaseDescriptorType
from zntrack.metadata.collectors import NodeInfo, RunInfo
from zntrack.zn import Nodes as zn_nodes
from zntrack.zn import params as zn_params
from zntrack.zn.dependencies import NodeAttribute

log = logging.getLogger(__name__)


def handle_deps(value) -> typing.List[str]:
    """Find all dependencies of value

    Parameters
    ----------
    value: any
        list, string, tuple, Path or Node instance

    Returns
    -------
    list:
        A list dependency files

    """
    deps_files: typing.List[str] = []
    if isinstance(value, (list, tuple)):
        for lst_val in value:
            deps_files += handle_deps(lst_val)
    else:
        if isinstance(value, (GraphWriter, NodeAttribute)):
            for file in value.affected_files:
                deps_files.append(pathlib.Path(file).as_posix())
        elif isinstance(value, (str, pathlib.Path)):
            deps_files.append(pathlib.Path(value).as_posix())
        elif value is None:
            pass
        else:
            raise ValueError(f"Type {type(value)} ({value}) is not supported!")

    return deps_files


@dataclasses.dataclass
class DVCRunOptions:
    """Collection of DVC run options

    Attributes
    ----------
    All attributes are documented under the dvc run method.

    References
    ----------
    https://dvc.org/doc/command-reference/run#options
    """

    no_commit: bool
    external: bool
    always_changed: bool
    no_run_cache: bool
    no_exec: bool
    force: bool

    @property
    def dvc_args(self) -> list:
        """Get the activated options
        Returns
        -------
        list: A list of strings for the subprocess call, e.g.:
            ["--no-commit", "--external"]
        """
        out = []
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if value:
                out.append(f"--{field_name.replace('_', '-')}")
        return out


def handle_dvc(value, dvc_args) -> list:
    """Convert list of dvc_paths to a dvc input string

    >>> handle_dvc("src/file.txt", "outs") == ["--outs", "src/file.txt"]
    """
    if not isinstance(value, (list, tuple)):
        value = [value]

    def option_func(_dvc_path):
        return f"--{dvc_args}"

    def posix_func(dvc_path):
        if dvc_args == "params":
            # add :to the end to indicate that it actually is a file.
            try:
                return f"{pathlib.Path(dvc_path).as_posix()}:"
            except TypeError as err:
                raise ValueError(
                    f"dvc.params does not support type {type(dvc_path)}"
                ) from err
        return pathlib.Path(dvc_path).as_posix()

    # double list comprehension https://stackoverflow.com/a/11869360/10504481
    return [f(x) for x in value for f in (option_func, posix_func)]


def prepare_dvc_script(
    node_name,
    dvc_run_option: DVCRunOptions,
    custom_args: list,
    nb_name,
    module,
    func_or_cls,
    call_args,
) -> list:
    """Prepare the dvc cmd to be called by subprocess

    Parameters
    ----------
    node_name: str
        Name of the Node
    dvc_run_option: DVCRunOptions
        dataclass to collect special DVC run options
    custom_args: list[str]
        all the params / deps / ... to be added to the script
    nb_name: str|None
        Notebook name for jupyter support
    module: str like "src.my_module"
    func_or_cls: str
        The name of the Node class or function to be imported and run
    call_args: str
        Additional str like "(run_func=True)" or ".load().run_and_save"

    Returns
    -------

    list[str]
        The list to be passed to the subprocess call

    """
    script = ["dvc", "run", "-n", node_name]
    script += dvc_run_option.dvc_args
    script += custom_args

    if nb_name is not None:
        script += ["--deps", utils.module_to_path(module).as_posix()]

    import_str = f"""{utils.get_python_interpreter()} -c "from {module} import """
    import_str += f"""{func_or_cls}; {func_or_cls}{call_args}" """
    script += [import_str]
    log.debug(f"dvc script: {' '.join([str(x) for x in script])}")
    return script


ZN_COLLECT_TYPE = typing.Type[
    typing.Union[NodeInfo, RunInfo, descriptor.BaseDescriptorType]
]


class ZnTrackInfo:
    """Helping class for access to ZnTrack information"""

    def __init__(self, parent):
        self._parent = parent

    def collect(self, zntrackoption: ZN_COLLECT_TYPE) -> dict:
        """Collect the values of all ZnTrackOptions of the passed type

        Parameters
        ----------
        zntrackoption:
            Any cls of a ZnTrackOption such as zn.params

        Returns
        -------
        dict:
            A dictionary of {option_name: option_value} for all found options of
            the given type zntrackoption.
        """
        if isinstance(zntrackoption, (list, tuple)):
            raise ValueError(
                "collect only supports single ZnTrackOptions. Found"
                f" {zntrackoption} instead."
            )

        if zntrackoption in (NodeInfo, RunInfo):
            for option in dir(type(self._parent)):
                value = getattr(type(self._parent), option)
                if isinstance(value, zntrackoption):
                    return {option: value}

        options = descriptor.get_descriptors(zntrackoption, self=self._parent)
        return {x.name: x.__get__(self._parent) for x in options}


class GraphWriter:
    """Write the DVC Graph

    Main method that handles writing the Graph / dvc.yaml file

    node_name: str
        first priority is by passing it through kwargs
        second is having the class attribute set in the class definition
        last if both above are None it will be set to __class__.__name__
    is_attribute: bool, default = False
        If the Node is not used directly but through e.g. zn.Nodes() as a dependency
        this can be set to True. It will disable all outputs in the params.yaml file
        except for the zn.Hash().
    """

    node_name = None
    _module = None
    _is_attribute = False

    def __init__(self, **kwargs):
        name = kwargs.pop("name", None)
        if name is not None:
            # overwrite node_name attribute
            self.node_name = name
        if self.node_name is None:
            # set default value of node_name attribute
            self.node_name = self.__class__.__name__
        if len(kwargs) > 0:
            raise TypeError(f"'{kwargs}' are an invalid keyword argument")

    def __hash__(self):
        """compute the hash based on the parameters and node_name"""
        params_dict = self.zntrack.collect(zn_params)
        params_dict["node_name"] = self.node_name

        return hash(json.dumps(params_dict, sort_keys=True, cls=znjson.ZnEncoder))

    @property
    def _descriptor_list(self) -> typing.List[BaseDescriptorType]:
        """Get all descriptors of this instance"""
        descriptors = descriptor.get_descriptors(ZnTrackOption, self=self)
        if self._is_attribute:
            allowed_types = [utils.ZnTypes.PARAMS, utils.ZnTypes.HASH, utils.ZnTypes.DEPS]
            return [x for x in descriptors if x.zn_type in allowed_types]
        return descriptors

    @property
    def module(self) -> str:
        """Module from which to import <name>

        Used for from <module> import <name>

        Notes
        -----
        this can be changed when using nb_mode
        """
        if self._module is None:
            if utils.config.nb_name is not None:
                return f"{utils.config.nb_class_path}.{self.__class__.__name__}"
            return utils.module_handler(self.__class__)
        return self._module

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
        raise NotImplementedError

    @property
    def affected_files(self) -> typing.Set[pathlib.Path]:
        """list of all files that can be changed by this instance"""
        files = []
        for option in self._descriptor_list:
            file = option.get_filename(self)
            if option.zn_type in utils.VALUE_DVC_TRACKED:
                files.append(file)
            elif option.zn_type in utils.FILE_DVC_TRACKED:
                value = getattr(self, option.name)
                if isinstance(value, (list, tuple)):
                    files += value
                else:
                    files.append(value)
            # deps or params are not affected files

        files = [x for x in files if x is not None]
        return set(files)

    @classmethod
    def convert_notebook(cls, nb_name: str = None):
        """Use jupyter_class_to_file to convert ipynb to py

        Parameters
        ----------
        nb_name: str
            Notebook name when not using config.nb_name (this is not recommended)
        """
        jupyter_class_to_file(nb_name=nb_name, module_name=cls.__name__)

    def _handle_nodes_as_methods(self):
        """Write the graph for all zn.Nodes ZnTrackOptions

        zn.Nodes ZnTrackOptions will require a dedicated graph to be written.
        They are shown in the dvc dag and have their own parameter section.
        The name is <nodename>-<attributename> for these Nodes and they only
        have a single hash output to be available for DVC dependencies.
        """
        for attribute, node in self.zntrack.collect(zn_nodes).items():
            if node is None:
                continue
            node.node_name = f"{self.node_name}-{attribute}"
            node._is_attribute = True
            node.write_graph(
                run=True,
                call_args=f".load(name='{node.node_name}').save(results=True)",
            )

    def write_graph(
        self,
        silent: bool = False,
        nb_name: str = None,
        notebook: bool = True,
        no_commit: bool = False,
        external: bool = False,
        always_changed: bool = False,
        no_exec: bool = True,
        force: bool = True,
        no_run_cache: bool = False,
        dry_run: bool = False,
        run: bool = None,
        *,
        call_args: str = None,
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
        notebook: bool, default = True
            convert the notebook to a py File
        no_commit: dvc parameter
        external: dvc parameter
        always_changed: dvc parameter
        no_exec: dvc parameter
        run: bool, inverse of no_exec. Will overwrite no_exec if set.
        force: dvc parameter
        no_run_cache: dvc parameter
        dry_run: bool, default = False
            Only return the script but don't actually run anything
        call_args: str, default = None
            Custom call args. Defaults to '.load(name='{self.node_name}').run_and_save()'

        Notes
        -----
        If the dependencies for a stage change this function won't necessarily tell you.
        Use 'dvc status' to check, if the stage needs to be rerun.

        """

        self._handle_nodes_as_methods()

        if silent:
            log.warning(
                "DeprecationWarning: silent was replaced by 'zntrack.config.log_level ="
                " logging.ERROR'"
            )
        if run is not None:
            no_exec = not run

        log.debug("--- Writing new DVC file ---")

        dvc_run_option = DVCRunOptions(
            no_commit=no_commit,
            external=external,
            always_changed=always_changed,
            no_run_cache=no_run_cache,
            no_exec=no_exec,
            force=force,
        )

        # Jupyter Notebook
        nb_name = utils.update_nb_name(nb_name)
        if nb_name is not None and notebook:
            self.convert_notebook(nb_name)

        custom_args = []
        dependencies = []
        # Handle Parameter
        params_list = utils.helpers.filter_ZnTrackOption(
            data=self._descriptor_list, cls=self, zn_type=[utils.ZnTypes.PARAMS]
        )
        if len(params_list) > 0:
            custom_args += [
                "--params",
                f"{utils.Files.params}:{self.node_name}",
            ]
        zn_options_set = set()
        for option in self._descriptor_list:
            if option.zn_type == utils.ZnTypes.DVC:
                value = getattr(self, option.name)
                custom_args += handle_dvc(value, option.dvc_args)
            # Handle Zn Options
            elif option.zn_type in utils.VALUE_DVC_TRACKED:
                zn_options_set.add(
                    (
                        f"--{option.dvc_args}",
                        option.get_filename(self).as_posix(),
                    )
                )
            elif option.zn_type == utils.ZnTypes.DEPS:
                value = getattr(self, option.name)
                dependencies += handle_deps(value)

        for dependency in set(dependencies):
            custom_args += ["--deps", dependency]

        for pair in zn_options_set:
            custom_args += pair

        if call_args is None:
            call_args = f".load(name='{self.node_name}').run_and_save()"

        script = prepare_dvc_script(
            node_name=self.node_name,
            dvc_run_option=dvc_run_option,
            custom_args=custom_args,
            nb_name=nb_name,
            module=self.module,
            func_or_cls=self.__class__.__name__,
            call_args=call_args,
        )

        # Add command to run the script

        self.save()

        log.debug(
            "If you are using a jupyter notebook, you may not be able to see the "
            "output in real time!"
        )

        if dry_run:
            return script
        utils.run_dvc_cmd(script)

        run_post_dvc_cmd(descriptor_list=self._descriptor_list, instance=self)

    @property
    def zntrack(self) -> ZnTrackInfo:
        return ZnTrackInfo(parent=self)


def run_post_dvc_cmd(descriptor_list, instance):
    """Run all post-dvc-cmds like plots modify"""
    for desc in descriptor_list:
        if desc.post_dvc_cmd(instance) is not None:
            utils.run_dvc_cmd(desc.post_dvc_cmd(instance))
