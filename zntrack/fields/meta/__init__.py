import pathlib
import typing

import yaml

from zntrack.fields.field import Field
from zntrack.utils import file_io


class Text(Field):
    """A metadata field."""

    dvc_option: str = "params"

    def get_affected_files(self, instance) -> list:
        """Get the params.yaml file."""
        return []

    def save(self, instance):
        """Save the field to disk."""
        if instance.state.loaded:
            return  # Don't save if the node is loaded from disk
        file_io.update_meta(
            file=pathlib.Path("dvc.yaml"),
            node_name=instance.name,
            data={self.name: getattr(instance, self.name)},
        )

    def load(self, instance):
        """Load the field from disk."""
        dvc_dict = yaml.safe_load(instance.state.get_file_system().read_text("dvc.yaml"))
        instance.__dict__[self.name] = dvc_dict["stages"][instance.name]["meta"].get(
            self.name, None
        )

    def get_stage_add_argument(self, instance) -> typing.List[tuple]:
        """Get the dvc command for this field."""
        return []