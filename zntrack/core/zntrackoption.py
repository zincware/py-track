"""Node parameter"""
from __future__ import annotations

import copy
import logging
import pathlib
import typing

from zntrack import descriptor, utils

log = logging.getLogger(__name__)


def uses_node_name(zn_type, instance) -> typing.Union[str, None]:
    """Check if the given metadata is associated with using the node_name as dict key

    Everything in nodes/<node_name>/ does not need it as key, because the directory
    is already named after the node. On the other side, parameters for example
    require the usage of node_name as a key inside the params.yaml file.

    Parameters
    ----------
    zn_type: utils.ZnTypes
    instance:
        Any instance object with the node_name attribute

    Returns
    -------
    str
        returns the node_name if it is being used, otherwise returns None

    """
    if zn_type in utils.VALUE_DVC_TRACKED:
        return None
    return instance.node_name


class ZnTrackOption(descriptor.Descriptor):
    """Descriptor for all DVC options

    This class handles the __get__ and __set__ for the DVC options.
    For most cases this means storing them in the __init__ and keeping track of,
    which Options are used.
    This is required to allow for load=True which updates all ZnTrackOptions,
    based on the computed or otherwise stored values.

    Attributes
    ----------
    file: str
        Either the zntrack file or the parameter file
    dvc_option: str|utils.DVCOptions
        The cmd to use with DVC, e.g. dvc --outs ... would be "outs"
    zn_type: utils.ZnTypes
        The internal ZnType to select the correct ZnTrack behaviour
    allow_lazy: bool, default=True
        Allow this option to be lazy loaded.
    """

    file = None
    dvc_option: str = None
    zn_type: utils.ZnTypes = None
    allow_lazy: bool = True

    def __init__(self, default_value=None, **kwargs):
        """Constructor for ZnTrackOptions

        Attributes
        ----------
        default_value: Any
            The default value of the descriptor
        filename:
            part of the kwargs, optional filename overwrite.

        Raises
        ------
        ValueError: If dvc_option is None and the class name is not in utils.DVCOptions

        """
        if default_value is not None and self.zn_type in utils.VALUE_DVC_TRACKED:
            raise ValueError(f"Can not set default to a tracked value ({self.zn_type})")
        if self.dvc_option is None:
            # use the name of the class as DVCOption if registered in DVCOptions
            self.dvc_option = utils.DVCOptions(self.__class__.__name__).value

        self.filename = kwargs.pop("filename", self.dvc_option)
        super().__init__(default_value=default_value, **kwargs)

    @property
    def dvc_args(self) -> str:
        """replace python variables '_' with '-' for dvc"""
        return self.dvc_option.replace("_", "-")

    def post_dvc_cmd(self, instance) -> typing.List[str]:
        """Optional DVC cmd to run at the end

        Returns
        -------
        cmd: list[str]
            Get a list for subprocess call to run after the main dvc cmd was executed.
            E.g. ["plots", "modify", ...]
        """
        return None

    def __repr__(self):
        return f"{super().__repr__()} for <{self.__str__()}>"

    def __str__(self):
        return f"{self.dvc_option} / {self.name}"

    def __get__(self, instance, owner=None):
        self._instance = instance

        if instance is None:
            return self
        elif instance.is_loaded:
            is_lazy_option = instance.__dict__.get(self.name) is utils.LazyOption
            is_not_in_dict = self.name not in instance.__dict__

            if is_lazy_option or is_not_in_dict:
                # the __dict__ only needs to be updated if __dict__ does
                # not contain self.name or self.name is LazyOption
                try:
                    # load data and store it in the instance
                    instance.__dict__[self.name] = self.get_data_from_files(instance)
                    log.debug(f"instance {instance} updated from file")
                except (KeyError, FileNotFoundError, AttributeError) as err:
                    # do not load default value, because a loaded instance should always
                    #  load from files.
                    if not utils.config.allow_empty_loading:
                        # allow overwriting this
                        raise AttributeError(
                            f"Could not load {self.name} for {instance}"
                        ) from err
        else:
            # if the instance is not loaded, there is no LazyOption handling
            try:
                return instance.__dict__[self.name]
            except KeyError:
                # instead of .get(name, default_value) we make a copy of the default value
                #  because it could be changed.
                instance.__dict__[self.name] = copy.deepcopy(self.default_value)

        return instance.__dict__[self.name]

    def get_filename(self, instance) -> pathlib.Path:
        """Get the name of the file this ZnTrackOption will save its values to"""
        if uses_node_name(self.zn_type, instance) is None:
            return pathlib.Path("nodes", instance.node_name, f"{self.filename}.json")
        return pathlib.Path(self.file)

    def save(self, instance):
        """Save this descriptor for the given instance to file

        Parameters
        ----------
        instance: Node
            instance where the Descriptor is attached to.
            Similar to __get__(instance) this requires the instance
            to be passed manually.
        """
        if instance.__dict__.get(self.name) is utils.LazyOption:
            # do not save anything if __get__/__set__ was never used
            return
        utils.file_io.update_config_file(
            file=self.get_filename(instance),
            node_name=uses_node_name(self.zn_type, instance),
            value_name=self.name,
            value=self.__get__(instance, self.owner),
        )

    def mkdir(self, instance):
        """Create a parent directory

        For parameters that are saved in e.g. nodes/<node_name>/file.json
        the nodes/<node_name>/ directory is created here. This is required
        for DVC to create a .gitignore file in these directories.
        """
        file = self.get_filename(instance)
        file.parent.mkdir(exist_ok=True, parents=True)

    def get_data_from_files(self, instance):
        """Load the value/s for the given instance from the file/s

        Parameters
        ----------
        instance: Node
            instance where the Descriptor is attached to.
            Similar to __get__(instance) this requires the instance
            to be passed manually.

        Returns
        -------
        any:
            returns the value loaded from file/s for the given instance.
        """
        file = self.get_filename(instance)
        file_content = utils.file_io.read_file(file)
        # The problem here is, that I can not / don't want to load all Nodes but
        # only the ones, that are in [self.node_name][self.name] for deserializing
        if uses_node_name(self.zn_type, instance) is not None:
            values = utils.decode_dict(file_content[instance.node_name][self.name])
        else:
            values = utils.decode_dict(file_content[self.name])
        if isinstance(values, (list, tuple)):
            log.debug(f"Loading {instance.node_name} from {file}: ({values[:3]} ...)")
        else:
            log.debug(f"Loading {instance.node_name} from {file}: ({values})")
        return values
