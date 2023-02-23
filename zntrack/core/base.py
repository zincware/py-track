"""ZnTrack Node class module."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import pathlib
import shutil
import typing

import zninit
import znjson

from zntrack import dvc, meta, utils, zn
from zntrack.core.dvcgraph import (
    DVCRunOptions,
    ZnTrackInfo,
    filter_ZnTrackOption,
    handle_dvc,
    prepare_dvc_script,
    run_post_dvc_cmd,
)
from zntrack.core.jupyter import jupyter_class_to_file
from zntrack.core.zntrackoption import ZnTrackOption
from zntrack.zn import Nodes as ZnNodes
from zntrack.zn import params as zn_params
from zntrack.zn.dependencies import NodeAttribute, getdeps

log = logging.getLogger(__name__)

EXCEPTION_OR_LST_EXCEPTIONS = typing.Union[
    typing.Type[Exception], typing.Collection[typing.Type[Exception]], None
]


def update_dependency_options(value):
    """Handle Node dependencies.

    The default value is created upton instantiation of a ZnTrackOption,
    if a new class is created via Instance.load() it does not automatically load
    the default_value Nodes, so we must to this manually here and call update_options.
    """
    if isinstance(value, (list, tuple)):
        for item in value:
            update_dependency_options(item)
    if isinstance(value, Node):
        value._update_options()


def handle_deps(value) -> typing.List[str]:
    """Find all dependencies of value.

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
    elif isinstance(value, (Node, NodeAttribute)):
        for file in value.affected_files:
            deps_files.append(pathlib.Path(file).as_posix())
    elif isinstance(value, (str, pathlib.Path)):
        deps_files.append(pathlib.Path(value).as_posix())
    elif value is not None:
        raise ValueError(f"Type {type(value)} ({value}) is not supported!")

    return deps_files


def _handle_nodes_as_methods(nodes: dict):
    """Write the graph for all zn.Nodes ZnTrackOptions.

    zn.Nodes ZnTrackOptions will require a dedicated graph to be written.
    They are shown in the dvc dag and have their own parameter section.
    The name is <nodename>-<attributename> for these Nodes. They only
    have a single hash output to be available for DVC dependencies.

    Attributes
    ----------
    nodes: dict
        A dictionary of {option_name: zntrack.Node}
    """
    for node in nodes.values():
        if node is not None:
            node.write_graph(run=True, call_args=f"--name={node.node_name} --hash-only")


BaseNodeTypeT = typing.TypeVar("BaseNodeTypeT", bound="Node")


class LoadViaGetItem(type):
    """Metaclass for adding getitem support to load."""

    def __getitem__(cls: Node, item: typing.Union[str, dict]) -> BaseNodeTypeT:
        """Allow Node[<nodename>] to access an instance of the Node.

        Attributes
        ----------
        item: str|dict
            Can be a string, for load(name=item)
            Can be a dict for load(**item) | e.g. {name:"nodename", lazy:True}

        Raises
        ------
        ValueError: if you don't pass a dict or string.

        """
        if not isinstance(item, (str, dict)):
            raise ValueError(
                f"Can only load {cls} with type (str, dict). Found {type(item)}"
            )

        return cls.load(**item) if isinstance(item, dict) else cls.load(name=item)

    def __matmul__(cls, other: str) -> typing.Union[NodeAttribute, typing.Any]:
        """Shorthand for: getdeps(Node, other).

        Parameters
        ----------
        other: str
            Name of the class attribute

        Returns
        -------
        NodeAttribute
        """
        if not isinstance(other, str):
            raise ValueError(
                f"Can not compute 'Node @ {type(other)}'. Expected 'Node @ str'."
            )
        return getdeps(cls, other)


class NodeBase(zninit.ZnInit):
    """NodeBase helper is used to define the lower bound __init__.

     That __init__ is applied as super call when using the
        automatically generated __init__.

    Attributes
    ----------
    is_loaded: bool
        if the class is loaded this can be used to only run certain code, e.g. in the init
    node_name: str
        first priority is if requested via kwargs
        second is having the class attribute set in the class definition
        last if both above are None it will be set to __class__.__name__
    nwd: pathlib.Path
        The 'node working directory' which is typically 'nodes/<node_name>'.
    is_attribute: bool, default = False
        If the Node is not used directly but through e.g. zn.Nodes() as a dependency
        this can be set to True. It will disable all outputs in the params.yaml file
        except for the zn.Hash().
    """

    is_loaded: bool = False
    _module = None
    _is_attribute = False

    def __init__(self, **kwargs):
        """__init__ of NodeBase."""
        self.is_loaded = kwargs.pop("is_loaded", False)
        name = kwargs.pop("name", None)
        if kwargs:
            raise TypeError(f"'{kwargs}' are an invalid keyword argument")
        if name is not None:
            # overwrite node_name attribute
            self.node_name = name

        for data in self._descriptor_list:
            if data.zn_type == utils.ZnTypes.DEPS:
                update_dependency_options(data.default)

    @property
    def node_name(self) -> str:
        """Get the node name."""
        return self.__dict__.get("node_name", self.__class__.__name__)

    @node_name.setter
    def node_name(self, value: str):
        """Set the node name.

        Thereby, resetting 'self.nwd'.
        """
        self.__dict__["node_name"] = value
        self.__dict__["nwd"] = None

    @property
    def nwd(self) -> pathlib.Path:
        """Get the node working directory."""
        nwd = self.__dict__.get("nwd")
        if nwd is None:
            nwd = pathlib.Path("nodes", self.node_name)
        return nwd

    @nwd.setter
    def nwd(self, value: pathlib.Path):
        """Set the node working directory and create the directory."""
        self.__dict__["nwd"] = value

    @property
    def _descriptor_list(self) -> typing.List[zninit.descriptor.DescriptorTypeT]:
        """Get all descriptors of this instance."""
        descriptors = zninit.get_descriptors(ZnTrackOption, self=self)
        if self._is_attribute:
            allowed_types = [
                utils.ZnTypes.PARAMS,
                utils.ZnTypes.HASH,
                utils.ZnTypes.DEPS,
                utils.ZnTypes.META,
            ]
            return [x for x in descriptors if x.zn_type in allowed_types]
        return descriptors


class Node(NodeBase, metaclass=LoadViaGetItem):
    """Main parent class for all ZnTrack Node.

    The methods implemented in this class are primarily loading and saving parameters.
    This includes restoring the Node from files and saving results to files after run.

    Attributes
    ----------
    _run_and_save: bool, default = False
        True if inside 'run_and_save'
    """

    _init_subclass_basecls_ = NodeBase
    _init_descriptors_ = [
        zn.params,
        zn.deps,
        zn.Method,
        zn.Nodes,
        meta.Text,
    ] + dvc.options
    _run_and_save: bool = False

    @utils.deprecated(
        reason=(
            "Please check out https://zntrack.readthedocs.io/en/latest/_tutorials/"
            "migration_guide_v3.html for a migration tutorial from "
            "ZnTrack v0.2 to v0.3"
        ),
        version="v0.3",
    )
    def __call__(self, *args, **kwargs):
        """Still here for a depreciation warning for migrating to class based ZnTrack."""

    def __repr__(self):
        """__repr__ of Node."""
        hex_id = hex(id(self))  # TODO replace by git rev in the future
        status = "known" if self._graph_entry_exists else "unknown"
        # TODO add a state: available which checks e.g. via dvc status
        #  or later if loading by revision is available otherwise
        #  if the outputs are available
        obj = self.__class__.__name__
        return (
            f"<ZnTrack {obj}: status: {status}, loaded: {self.is_loaded}, name:"
            f" {self.node_name}, id: {hex_id}>"
        )

    def __hash__(self):
        """Compute the hash based on the parameters and node_name.

        Ignore 'not serializable' here so it will not raise an error.

        Returns
        -------
        hash value based on the parameters and node_name. If there are some errors,
        during the collection of the parameters, it will return super hash.

        """
        try:
            params_dict = self.zntrack.collect(zn_params)
            params_dict["node_name"] = self.node_name

            return hash(
                json.dumps(
                    params_dict,
                    sort_keys=True,
                    cls=znjson.ZnEncoder,
                    default=lambda o: "<not serializable>",
                )
            )
        except utils.exceptions.GraphNotAvailableError:
            return super().__hash__()

    def __matmul__(self, other: str) -> typing.Union[NodeAttribute, typing.Any]:
        """Shorthand for: getdeps(Node, other).

        Parameters
        ----------
        other: str
            Name of the class attribute

        Returns
        -------
        NodeAttribute
        """
        if not isinstance(other, str):
            raise ValueError(
                f"Can not compute 'Node @ {type(other)}'. Expected 'Node @ str'."
            )
        return getdeps(self, other)

    def save_plots(self):
        """Save the zn.plots.

        Similar to DVC Live this  can be used to save the plots during a run
        for live output.
        """
        for option in self._descriptor_list:
            if option.zn_type is utils.ZnTypes.PLOTS:
                option.save(instance=self)

    def save(self, results: bool = False, hash_only: bool = False):
        """Save Class state to files.

        Parameters
        ----------
        results: bool, default=False
            Save changes in zn.<option>.
            By default, this function saves e.g. parameters from zn.params / dvc.<option>,
            but does not save results  that are stored in zn.<option>.
            Set this option to True if they should be saved, e.g. in run_and_save

        hash_only: bool, default = False
            Only save zn.Hash and nothing else. This is required for usage as zn.Nodes
        """
        if hash_only:
            try:
                zninit.get_descriptors(zn.Hash, self=self)[0].save(instance=self)
            except IndexError as err:
                raise utils.exceptions.DescriptorMissingError(
                    "Could not find a hash descriptor. Please add zn.Hash()"
                ) from err
            return

        if not results:
            # Reset everything in params.yaml and zntrack.json before saving
            utils.file_io.clear_config_file(utils.Files.params, node_name=self.node_name)
            utils.file_io.clear_config_file(utils.Files.zntrack, node_name=self.node_name)
        # Save dvc.<option>, dvc.deps, zn.Method

        for option in self._descriptor_list:
            if results:
                if option.zn_type in utils.VALUE_DVC_TRACKED:
                    # only save results
                    option.save(instance=self)
            else:
                if option.zn_type not in utils.VALUE_DVC_TRACKED + utils.GIT_TRACKED:
                    # save all dvc.<options>
                    option.save(instance=self)
                else:
                    # Create the path for DVC to write a .gitignore file
                    # for the filtered files
                    option.mkdir(instance=self)

    def _update_options(self, lazy=None):
        """Update all ZnTrack options inheriting from ZnTrackOption.

        This will overwrite the value in __dict__ even it the value was changed
        """
        if lazy is None:
            lazy = utils.config.lazy
        for option in self._descriptor_list:
            if option.allow_lazy:
                self.__dict__[option.name] = utils.LazyOption
            if not lazy:
                # trigger loading the data into memory
                value = getattr(self, option.name)
                with contextlib.suppress(AttributeError):
                    value._update_options(lazy=False)
        self.is_loaded = True

    @classmethod
    def load(cls, name=None, lazy: bool = None) -> Node:
        """Classmethod that yield a Node object.

        This method does
        1. create a new instance of Node
        2. call Node._load() to update the instance

        Parameters
        ----------
        lazy: bool
            The default value is defined by config.lazy = True.
            If false, all instances will be loaded. If true, the value is only
            read when first accessed.
        name: str, default = None
            Name of the Node / stage in dvc.yaml.
            If not explicitly defined in Node(name=<...>).write_graph()
            this should remain None.

        Returns
        -------
        Instance of this class with the state loaded from files

        Examples
        --------
        Always have this, so that the name can be passed through

        def __init__(self, **kwargs):
            super().__init__(**kwargs)

        """
        if not (isinstance(name, str) or (name is None)):
            raise ValueError(f"name must be string or None. Found {name}.")
        if lazy is None:
            lazy = utils.config.lazy
        try:
            instance = cls(name=name, is_loaded=True)
        except TypeError as type_error:
            if not getattr(cls.__init__, "uses_auto_init", False):
                # when not using the automatic init all arguments must have a
                # default value and the super call is required. It would still be
                # using new + init from Node class to circumvent required
                # arguments in the automatic init
                raise TypeError(
                    f"Unable to create a new instance of {cls}. Check that all arguments"
                    " default to None. It must be possible to instantiate the class via"
                    f" {cls}() without passing any arguments. Furthermore, the"
                    " '**kwargs' must be passed to the 'super().__init__(**kwargs)'"
                    "See the ZnTrack documentation for more information."
                ) from type_error

            instance = object.__new__(cls)
            Node.__init__(instance, name=name, is_loaded=True)
        assert instance.node_name is not None, (
            "The name of the Node is not set. Probably missing"
            " 'super().__init__(**kwargs)' inside the custom '__init__'."
        )
        instance._update_options(lazy=lazy)

        if utils.config.nb_name is not None:
            # TODO maybe check if it exists and otherwise keep default?
            instance._module = f"{utils.config.nb_class_path}.{cls.__name__}"
        return instance

    def run_and_save(self):
        """Call run and save afterwards.

        Method used e.g. by dvc repro.
        """
        self._run_and_save = True
        try:
            self.nwd.mkdir(exist_ok=True, parents=True)
            if not self.is_loaded:
                # Save e.g. the parameters if the Node is not loaded
                #  this can happen, when using this method outside 'dvc repro'
                self.save()
            self.run()
            self.save(results=True)
        finally:
            self._run_and_save = False

    # @abc.abstractmethod
    def run(self):
        """Overwrite this method for the actual calculation."""
        raise NotImplementedError

    @property
    def module(self) -> str:
        """Module from which to import <name>.

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

    @property
    def affected_files(self) -> typing.Set[pathlib.Path]:
        """List of all files that can be changed by this instance."""
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
        """Use jupyter_class_to_file to convert ipynb to py.

        Parameters
        ----------
        nb_name: str
            Notebook name when not using config.nb_name (this is not recommended)
        """
        jupyter_class_to_file(nb_name=nb_name, module_name=cls.__name__)

    @property
    def zntrack(self) -> ZnTrackInfo:
        """Get a ZnTrackInfo object."""
        return ZnTrackInfo(parent=self)

    @property
    def _graph_entry_exists(self) -> bool:
        """If this Graph exists in the dvc.yaml file."""
        try:
            file_content = utils.file_io.read_file(utils.Files.dvc)
        except FileNotFoundError:
            file_content = {}

        return self.node_name in file_content.get("stages", {})

    def write_graph(  # noqa: C901
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
        write_desc: bool = False,
        *,
        call_args: str = None,
    ):
        """Write the DVC file using run.

        If it already exists it'll tell you that the stage is already persistent and
        has been run before. Otherwise, it'll run the stage for you.

        Parameters
        ----------
        silent: bool
            If called with no_exec=False this allows to hide the output from the
            subprocess call.
        nb_name: str
            Notebook name when not using config.nb_name (this is not recommended)
        notebook: bool, default = True
            convert the notebook to a py File
        no_commit:
            dvc parameter
        external:
            dvc parameter
        always_changed:
            dvc parameter
        no_exec:
            dvc parameter
        run: bool
            inverse of no_exec. Will overwrite no_exec if set.
        force:
            dvc parameter
        no_run_cache:
            dvc parameter
        dry_run: bool, default = False
            Only return the script but don't actually run anything
        write_desc: bool, default = True
            Save the Node.__doc__ to the 'dvc.yaml' Node description.
        call_args: str, default = None
            Custom call args. Defaults to '.load(name='{self.node_name}').run_and_save()'

        Notes
        -----
        If the dependencies for a stage change this function won't necessarily tell you.
        Use 'dvc status' to check, if the stage needs to be rerun.

        """
        if not dry_run:
            self.nwd.mkdir(parents=True, exist_ok=True)
            _handle_nodes_as_methods(self.zntrack.collect(ZnNodes))

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
            force=force,
        )

        # Jupyter Notebook
        nb_name = utils.update_nb_name(nb_name)
        if not dry_run:
            if nb_name is not None and notebook:
                self.convert_notebook(nb_name)

        custom_args = []
        dependencies = []
        # Handle Parameter
        params_list = filter_ZnTrackOption(
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
            call_args = f"--name={self.node_name}"

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
        if not dry_run:
            self.save()

        log.debug(
            "If you are using a jupyter notebook, you may not be able to see the "
            "output in real time!"
        )

        if dry_run:
            return script
        utils.run_dvc_cmd(script)

        run_post_dvc_cmd(descriptor_list=self._descriptor_list, instance=self)

        for option in self._descriptor_list:
            if option.zn_type in utils.GIT_TRACKED:
                option.save(instance=self)

        if write_desc:
            utils.file_io.update_desc(
                file=utils.Files.dvc, node_name=self.node_name, desc=self.__doc__
            )

        if not no_exec:
            utils.run_dvc_cmd(["repro", self.node_name])

    @contextlib.contextmanager
    def operating_directory(
        self,
        prefix="ckpt",
        remove_on: EXCEPTION_OR_LST_EXCEPTIONS = None,
        move_on: EXCEPTION_OR_LST_EXCEPTIONS = Exception,
        disable: bool = None,
    ) -> bool:
        """Work in an operating directory until successfully finished.

        This context manager will replace $nwd$ with 'prefix_$nwd$' and move the files
        to $nwd$ when successfully finished. This can be useful, when you are running
        e.g., on hardware with limited execution time and can't use 'dvc checkpoints'.
        When successfully finished, all files will be moved from 'temp_$nwd$' to $nwd$.
        You can call 'dvc repro' multiple times to continue from 'temp_$nwd$'.
        If used properly this will result in reproducible data but:
        - checkpoints will not be removed if parameters change. Always remove a
            checkpoint, when running with new parameters!
        - checkpoints are not versioned. If you want to checkpoint e.g., model training,
            use 'dvc checkpoints'.

        Parameters
        ----------
        prefix: str, default = 'ckpt'
            Prefix for the temporary directory
        remove_on: Exception or list of Exceptions, default = None
            If one of the exceptions in 'remove_on' is raised, the operating directory
             will be removed. Otherwise, it will remain and reused upton the next run.
        move_on: Exception, default = Exception
            If one of the exceptions in 'move_on' is raised, the operating directories
            content is moved to $nwd$ and the directory will be removed.
            This helps, in the case of an error to not restart from an already
            failed data point.
        disable: bool, default = False
            Disable the operating directory. Yields True.


        Yields
        ------
        new_ckpt: bool
            True if creating a new checkpoint. False if the checkpoint already existed.
        """
        if disable is None:
            disable = utils.config.disable_operating_directory
        if disable:
            yield True
            return

        nwd = self.nwd
        nwd_new = self.nwd.with_name(f"{prefix}_{self.nwd.name}")
        nwd_is_new = not nwd_new.exists()

        remove = False
        move = False
        remove_on = utils.utils.convert_to_list(remove_on)
        move_on = utils.utils.convert_to_list(move_on)

        if self._run_and_save:
            utils.update_gitignore(prefix=prefix)

            if nwd_is_new:
                log.info(f"Creating new operating directory: {nwd_new}")
                log.warning(
                    "Experimental Feature: operating directory is currently not"
                    " compatible with 'dvc exp --temp' or 'dvc exp --queue'"
                )
                # TODO add a unique path per node.
                # TODO check on windows!
                shutil.copytree(nwd, nwd_new, copy_function=os.link)
            else:
                log.info(f"Continuing inside operating directory: {nwd_new}.")

            self.nwd = nwd_new
            try:
                yield nwd_is_new
            except Exception as err:
                log.warning("Node execution was interrupted.")
                remove = any(isinstance(err, e) for e in remove_on)
                move = any(isinstance(err, e) for e in move_on)
                # finally -> ...
                remove = utils.utils.timed_input(
                    text=(
                        "Do you want to remove the operating directory?"
                        f" [y/n]({'y' if remove else 'n'}): "
                    ),
                    default=remove,
                    timeout=10,
                    condition=lambda x: x.lower() in ["y", "yes", "j"],
                )
                raise err
            finally:
                # Save e.g. `zn.outs` before stopping.
                if remove:
                    log.info(f"Removing operating directory: {nwd_new}")
                    shutil.rmtree(nwd_new)
                    return
                self.save(results=True)
                self.nwd = nwd
                if move:  # only  called if Exception in move_on
                    log.info(f"Moving files from '{nwd_new}' to {nwd}")
                    utils.move_nwd(nwd_new, nwd)
                    return

            log.info(f"Finished successfully. Moving files from {nwd_new} to {nwd}")
            utils.move_nwd(nwd_new, nwd)
        else:
            # if not inside 'run_and_save' no directory should be created. ?!?!?!
            self.nwd = nwd_new
            try:
                yield nwd_is_new
            finally:
                self.nwd = nwd
