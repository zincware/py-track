from __future__ import annotations

import inspect
import logging
import typing

from zntrack import utils
from zntrack.core.dvcgraph import GraphWriter
from zntrack.core.zntrackoption import ZnTrackOption
from zntrack.descriptor import get_descriptors
from zntrack.zn.dependencies import NodeAttribute, getdeps

log = logging.getLogger(__name__)


def get_auto_init_signature(cls) -> (list, list):
    """Iterate over ZnTrackOptions in the __dict__ and save the option name
    and create a signature Parameter"""
    zn_option_names, signature_params = [], []
    _ = cls.__annotations__  # fix for https://bugs.python.org/issue46930
    descriptors = get_descriptors(ZnTrackOption, cls=cls)
    for descriptor in descriptors:
        if descriptor.zn_type in utils.VALUE_DVC_TRACKED:
            # exclude zn.outs / metrics / plots / ... options
            continue
        # For the new __init__
        zn_option_names.append(descriptor.name)

        # For the new __signature__
        signature_params.append(
            inspect.Parameter(
                name=descriptor.name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=cls.__annotations__.get(descriptor.name),
            )
        )
    return zn_option_names, signature_params


def update_dependency_options(value):
    """Handle Node dependencies

    The default value is created upton instantiation of a ZnTrackOption,
    if a new class is created via Instance.load() it does not automatically load
    the default_value Nodes, so we must to this manually here and call update_options.
    """
    if isinstance(value, (list, tuple)):
        for item in value:
            update_dependency_options(item)
    if isinstance(value, Node):
        value._update_options()


BaseNodeType = typing.TypeVar("BaseNodeType", bound="Node")


class LoadViaGetItem(type):
    """Metaclass for adding getitem support to load"""

    def __getitem__(cls: Node, item) -> BaseNodeType:
        """Allow Node[<nodename>] to access an instance of the Node

        Attributes
        ----------
        item: str|dict
            Can be a string, for load(name=item)
            Can be a dict for load(**item) | e.g. {name:"nodename", lazy:True}

        """
        if isinstance(item, dict):
            return cls.load(**item)
        return cls.load(name=item)

    def __matmul__(self, other: str) -> typing.Union[NodeAttribute, typing.Any]:
        """Shorthand for: getdeps(Node, other)

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


class Node(GraphWriter, metaclass=LoadViaGetItem):
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
        for data in self._descriptor_list:
            if data.zn_type == utils.ZnTypes.DEPS:
                log.debug(f"Updating dependencies for {data} in {self}")
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

    def __repr__(self):
        origin = super().__repr__()
        return f"{origin}(name={self.node_name})"

    def __matmul__(self, other: str) -> typing.Union[NodeAttribute, typing.Any]:
        """Shorthand for: getdeps(Node, other)

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

    def __init_subclass__(cls, **kwargs):
        """Add a dataclass-like init if None is provided"""
        super().__init_subclass__(**kwargs)
        # User provides an __init__
        for inherited in cls.__mro__:
            # Go through the mro until you find the Node class.
            # If found an init before that class it will implement super
            # if not add the fields to the __init__ automatically.
            if inherited == Node:
                log.debug("Found Node instance - adding dataclass-like __init__")
                break
            elif inherited.__dict__.get("__init__") is not None:
                if not getattr(inherited.__init__, "_uses_auto_init", False):
                    return cls

        # attach an automatically generated __init__ if None is provided
        zn_option_names, signature_params = get_auto_init_signature(cls)

        # Add new __init__ to the subclass
        setattr(
            cls,
            "__init__",
            utils.get_auto_init(fields=zn_option_names, super_init=Node.__init__),
        )

        # Add new __signature__ to the subclass
        signature = inspect.Signature(parameters=signature_params)
        setattr(cls, "__signature__", signature)

    def post_init(self):
        """Implement if cmds after the automatically generated __init__ should be run

        This only works if no __init__ is defined and the automatically generated
        __init__ from ZnTrack is used.
        """
        raise AttributeError(f"'{self.node_name}' object has no attribute 'post_init'")

    def save_plots(self):
        """Save the zn.plots

        Similar to DVC Live this  can be used to save the plots during a run
        for live output.
        """
        for option in self._descriptor_list:
            if option.zn_type is utils.ZnTypes.PLOTS:
                option.save(instance=self)

    def save(self, results: bool = False):
        """Save Class state to files

        Parameters
        -----------
        results: bool, default=False
            Save changes in zn.<option>.
            By default, this function saves e.g. parameters from zn.params / dvc.<option>,
            but does not save results  that are stored in zn.<option>.
            Set this option to True if they should be saved, e.g. in run_and_save
            If true changes in e.g. zn.params will not be saved.
        """
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
                if option.zn_type not in utils.VALUE_DVC_TRACKED:
                    # save all dvc.<options>
                    option.save(instance=self)
                else:
                    # Create the path for DVC to write a .gitignore file
                    # for the filtered files
                    option.mkdir(instance=self)

    def _update_options(self, lazy=None):
        """Update all ZnTrack options inheriting from ZnTrackOption

        This will overwrite the value in __dict__ even it the value was changed
        """
        log.debug(f"Updating options for {self}")
        if lazy is None:
            lazy = utils.config.lazy
        for option in self._descriptor_list:
            if option.allow_lazy:
                log.debug(f"Setting {option.name} to {utils.LazyOption}")
                self.__dict__[option.name] = utils.LazyOption
            if not lazy:
                # trigger loading the data into memory
                value = getattr(self, option.name)
                try:
                    value._update_options(lazy=False)
                except AttributeError:
                    # if lazy=False trigger update_options iteratively on
                    # all dependency Nodes
                    pass
        self.is_loaded = True

    @classmethod
    def load(cls, name=None, lazy: bool = None) -> Node:
        """classmethod that yield a Node object

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
        if lazy is None:
            lazy = utils.config.lazy
        try:
            instance = cls(name=name, is_loaded=True)
        except TypeError as type_error:
            try:
                instance = cls()
                if name not in (None, cls.__name__):
                    instance.node_name = name
                log.warning(
                    "Can not pass <name> to the super.__init__ and trying workaround!"
                    " This can lead to unexpected behaviour and can be avoided by"
                    " passing ( **kwargs) to the super().__init__(**kwargs) - Received"
                    f" '{type_error}'"
                )
            except TypeError as err:
                raise TypeError(
                    f"Unable to create a new instance of {cls}. Check that all arguments"
                    " default to None. It must be possible to instantiate the class via"
                    f" {cls}() without passing any arguments. See the ZnTrack"
                    " documentation for more information."
                ) from err

        instance._update_options(lazy=lazy)

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
