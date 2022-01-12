from __future__ import annotations

import dataclasses
import json
import logging
import pathlib
import typing

import yaml
import znjson

from .descriptor import Descriptor

log = logging.getLogger(__name__)


@dataclasses.dataclass
class DescriptorList:
    parent: DescriptorIO
    data: typing.List[Descriptor] = dataclasses.field(default_factory=list)

    def filter(self, zntrack_type, return_with_type=False):
        data = [x for x in self.data if x.metadata.zntrack_type == zntrack_type]
        if return_with_type:
            types_dict = {x.metadata.dvc_option: {} for x in data}
            for x in data:
                types_dict[x.metadata.dvc_option].update(
                    {x.name: getattr(self.parent, x.name)}
                )
            return types_dict
        return {x.name: getattr(self.parent, x.name) for x in data}


class DescriptorIO:
    @property
    def _descriptor_list(self) -> DescriptorList:
        """Get all descriptors of this instance"""
        descriptor_list = []
        for option in vars(type(self)).values():
            if isinstance(option, Descriptor):
                descriptor_list.append(option)
        return DescriptorList(parent=self, data=descriptor_list)

    @staticmethod
    def _read_file(file: pathlib.Path) -> dict:
        """Read a json/yaml file

        Parameters
        ----------
        file: pathlib.Path
            The file to read

        Returns
        -------
        dict:
            Content of the json/yaml file
        """
        if file.suffix in [".yaml", ".yml"]:
            with file.open("r") as f:
                file_content = yaml.safe_load(f)
        elif file.suffix == ".json":
            file_content = json.loads(file.read_text())
        else:
            raise NotImplementedError(f"File with suffix {file.suffix} is not supported")
        return file_content

    @staticmethod
    def _write_file(file: pathlib.Path, value: dict):
        """Save dict to file

        Store dictionary to json or yaml file

        Parameters
        ----------
        file: pathlib.Path
            File to save to
        value: dict
            Any serializable data to save
        """
        if file.suffix in [".yaml", ".yml"]:
            file.write_text(yaml.safe_dump(value, indent=4))
        elif file.suffix == ".json":
            file.write_text(json.dumps(value, indent=4, cls=znjson.ZnEncoder))

    def _save_to_file(
        self, file: pathlib.Path, zntrack_type: typing.Union[str, list], key: str = None
    ):
        try:
            file_content = self._read_file(file)
        except FileNotFoundError:
            file_content = {}

        if isinstance(zntrack_type, list):
            values = {}
            for type_ in zntrack_type:
                values.update(self._descriptor_list.filter(type_))
        else:
            values = self._descriptor_list.filter(zntrack_type)
        if key is not None:
            file_content[key] = values
        else:
            file_content = values

        log.debug(f"Saving {key} to {file}: ({values})")
        self._write_file(file, file_content)

    def _load_from_file(
        self,
        file: pathlib.Path,
        key: str = None,
        raise_file_error: bool = False,
        raise_key_error: bool = True,
    ):
        try:
            file_content = self._read_file(file)
            # The problem here is, that I can not / don't want to load all Nodes but only
            # the ones, that are in [self.node_name], so we only deserialize them
            if key is not None:
                values = json.loads(json.dumps(file_content[key]), cls=znjson.ZnDecoder)
            else:
                values = json.loads(json.dumps(file_content), cls=znjson.ZnDecoder)
            log.debug(f"Loading {key} from {file}: ({values})")
            self.__dict__.update(values)
        except FileNotFoundError as e:
            if raise_file_error:
                raise e
            else:
                pass
        except KeyError as e:
            if raise_key_error:
                raise e
            else:
                pass
