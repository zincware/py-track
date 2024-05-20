"""The base class for all fields."""

import abc
import contextlib
import enum
import json
import logging
import pathlib
import shutil
import typing

import yaml
import zninit

from zntrack.utils import LazyOption, config

if typing.TYPE_CHECKING:
    from zntrack.core.node import Node

log = logging.getLogger(__name__)


class FieldGroup(enum.Enum):
    """Characterizes the group of a field."""

    PARAMETER = enum.auto()
    RESULT = enum.auto()


class Field(zninit.Descriptor, abc.ABC):
    """Base class for fields.

    Handles all the file I/O for the given field.

    Attributes
    ----------
    dvc_option : str
        The dvc command option for this field.

    """

    dvc_option: str = None
    group: FieldGroup = None

    @abc.abstractmethod
    def save(self, instance: "Node"):
        """Save the field to disk.

        Parameters
        ----------
        instance : Node
            The Node instance to save the field for.

        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_data(self, instance: "Node") -> any:
        """Get the value of the field from the file."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_files(self, instance: "Node") -> list:
        """Get the files affected by this field.

        Parameters
        ----------
        instance : Node
            The Node instance to get the affected files for.

        Returns
        -------
        list
            The affected files.

        """
        raise NotImplementedError

    def load(self, instance: "Node", lazy: bool = None):
        """Load the field from disk.

        Parameters
        ----------
        instance : Node
            The Node instance to load the field for.
        lazy : bool, optional
            Whether to load the field lazily.
            This only applies to 'LazyField' classes.

        """
        try:
            instance.__dict__[self.name] = self.get_data(instance)
        except FileNotFoundError:
            # if something was not loaded, we set the loaded state to False
            log.warning(f"Could not load field {self.name} for node {instance.name}.")
            instance.state.loaded = False

    def get_stage_add_argument(self, instance: "Node") -> typing.List[tuple]:
        """Get the dvc stage add argument for this field.

        Parameters
        ----------
        instance : Node
            The Node instance to get the stage add argument for.

        Returns
        -------
        typing.List[tuple]
            The stage add argument for this field.

        """
        return [
            (f"--{self.dvc_option}", pathlib.Path(x).as_posix())
            for x in self.get_files(instance)
        ]

    def get_optional_dvc_cmd(
        self, instance: "Node", git_only_repo: bool
    ) -> typing.List[typing.List[str]]:
        """Get optional dvc commands that will be executed beside the main dvc command.

        This could be 'plots modify ...' or 'stage add --name node_helper'

        Parameters
        ----------
        instance : Node
            The Node instance to get the optional dvc commands for.
        git_only_repo : bool
            Whether the repo is a git only repo or has a dvc remote.

        Returns
        -------
        typing.List[str]
            The optional dvc commands.

        """
        return []

    def _write_value_to_config(self, value, instance: "Node", encoder=None):
        """Write the value of this field to the zntrack config file.

        Parameters
        ----------
        value: any
            The value to write to the config file.
        instance : Node
            The node instance to which this field belongs.
        encoder : json.JSONEncoder, optional
            The JSON encoder to use, by default None.

        """
        try:
            with open(config.files.zntrack, "r") as f:
                zntrack_dict = json.load(f)
        except FileNotFoundError:
            zntrack_dict = {}

        if instance.name not in zntrack_dict:
            zntrack_dict[instance.name] = {}
        zntrack_dict[instance.name][self.name] = value
        # use the __dict__ to avoid the nwd replacement
        with open(config.files.zntrack, "w") as f:
            json.dump(zntrack_dict, f, indent=4, cls=encoder)

    def get_zntrack_data(self, instance: "Node") -> dict:
        """Get the data that will be written to the zntrack config file."""
        return {}

    def get_dvc_data(self, instance: "Node") -> dict:
        """Get the data that will be written to the dvc config file."""
        return {}

    def get_params_data(self, instance: "Node") -> dict:
        """Get the data that will be written to the params file."""
        return {}


class DataIsLazyError(Exception):
    """Exception to raise when a field is accessed that contains lazy data."""


class LazyField(Field):
    """Base class for fields that are loaded lazily."""

    def get_value_except_lazy(self, instance):
        """Get the value of the field.

        If the value is lazy, raise an Error.

        Raises
        ------
        DataIsLazyError
            If the value is lazy.
        """
        with contextlib.suppress(KeyError):
            if instance.__dict__[self.name] is LazyOption:
                raise DataIsLazyError()

        return getattr(instance, self.name, None)

    def __get__(self, instance, owner=None):
        """Load the field from disk if it is not already loaded."""
        if instance is None:
            return self
        if instance.__dict__.get(self.name) is LazyOption:
            self.load(instance, lazy=False)

        return super().__get__(instance, owner)

    def load(self, instance: "Node", lazy: bool = None):
        """Load the field from disk.

        Parameters
        ----------
        instance : Node
            The Node instance to load the field for.
        lazy : bool, optional
            Whether to load the field lazily, by default 'zntrack.config.lazy'.
        """
        if lazy in {None, True} and config.lazy:
            instance.__dict__[self.name] = LazyOption
        else:
            super().load(instance)


class PlotsMixin(Field):
    """DVC Plots Option including 'dvc plots modify' command."""

    def __init__(
        self,
        *args,
        template=None,
        x=None,
        y=None,
        x_label=None,
        y_label=None,
        title=None,
        use_global_plots: bool = True,
        **kwargs,
    ):
        """Create a DVCOption field.

        Attributes
        ----------
        use_global_plots : bool
            Save the plots config not in 'stages' but in 'plots' in the dvc.yaml file.
        """
        super().__init__(*args, **kwargs)
        self.plots_options = {}
        self.use_global_plots = use_global_plots
        if self.use_global_plots:
            if self.dvc_option == "plots":
                self.dvc_option = "outs"
            elif self.dvc_option == "plots-no-cache":
                self.dvc_option = "outs-no-cache"
        if template is not None:
            self.plots_options["--template"] = pathlib.Path(template).as_posix()
        if x is not None:
            self.plots_options["-x"] = x
        if y is not None:
            self.plots_options["-y"] = y
        if x_label is not None:
            self.plots_options["--x-label"] = x_label
        if y_label is not None:
            self.plots_options["--y-label"] = y_label
        if title is not None:
            self.plots_options["--title"] = title

    def save(self, instance: "Node"):
        """Save plots options to dvc.yaml, if use_global_plots is True."""
        if self.plots_options.get("--template") is not None:
            template = pathlib.Path(self.plots_options["--template"]).resolve()
            if pathlib.Path.cwd() not in template.parents:
                # copy template to dvc_plots/templates if it is not in the cwd
                template_dir = pathlib.Path.cwd() / "dvc_plots" / "templates"
                template_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(template, template_dir)
                self.plots_options["--template"] = (
                    (template_dir / template.name)
                    .relative_to(pathlib.Path.cwd())
                    .as_posix()
                )

        with contextlib.suppress(NotImplementedError):
            super().save(instance=instance)
        if not self.use_global_plots:
            return

        dvc_file = config.files.dvc
        if not dvc_file.exists():
            dvc_file.write_text(yaml.safe_dump({}))
        dvc_config = yaml.safe_load(dvc_file.read_text())
        plots = dvc_config.get("plots", [])

        # remove leading "-/--"
        for key in list(self.plots_options):
            if key.startswith("--"):
                self.plots_options[key[2:]] = self.plots_options[key]
                del self.plots_options[key]
            elif key.startswith("-"):
                self.plots_options[key[1:]] = self.plots_options[key]
                del self.plots_options[key]
        # replace "-" with "_"
        for key in list(self.plots_options):
            if key.replace("-", "_") != key:
                self.plots_options[key.replace("-", "_")] = self.plots_options[key]
                del self.plots_options[key]

        for file in self.get_files(instance):
            replaced = False
            for entry in plots:  # entry: dict{filename: {x:, y:, ...}}
                if pathlib.Path(file) == pathlib.Path(next(iter(entry))):
                    entry = {pathlib.Path(file).as_posix(): self.plots_options}
                    replaced = True
            if not replaced:
                plots.append({pathlib.Path(file).as_posix(): self.plots_options})

        dvc_config["plots"] = plots
        dvc_file.write_text(yaml.dump(dvc_config))

    def get_optional_dvc_cmd(
        self, instance: "Node", git_only_repo: bool
    ) -> typing.List[typing.List[str]]:
        """Add 'dvc plots modify' to this option."""
        if not self.use_global_plots:
            cmds = []
            for file in self.get_files(instance):
                cmd = ["plots", "modify", pathlib.Path(file).as_posix()]
                for key, value in self.plots_options.items():
                    cmd.append(f"{key}")
                    cmd.append(pathlib.Path(value).as_posix())
                cmds.append(cmd)
            return cmds
        else:
            return []
