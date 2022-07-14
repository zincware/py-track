"""
Description: The SplitZnTrackOption is used to for serializing objects and stroring the
parameters / attributes in one file (params.yaml) and the rest, which is not considered
a parameter in another (zntrack.json)
"""
import logging
import typing

from zntrack import utils
from zntrack.core.zntrackoption import ZnTrackOption

log = logging.getLogger(__name__)


def split_value(input_val) -> (typing.Union[dict, list], typing.Union[dict, list]):
    """Split input_val into data for params.yaml and zntrack.json

    Parameters
    ----------
    input_val: dict
        A dictionary of shape {_type: str, value: any} from ZnJSON

    Returns
    -------
    params_data: dict|list
        A dictionary containing the data considered a parameter
    input_val: dict|list
        A dictionary containing the constant data which is not considered a parameter


    """
    if isinstance(input_val, (list, tuple)):
        data = [split_value(x) for x in input_val]
        params_data, _ = zip(*data)
    else:
        if input_val["_type"] in ["zn.method"]:
            params_data = input_val["value"].pop("kwargs")
            params_data["_cls"] = input_val["value"].pop("cls")
        else:
            # things that are not zn.method and do not have kwargs, such as pathlib, ...
            params_data = input_val.pop("value")
    return params_data, input_val


def combine_values(cls_dict: dict, params_val):
    """Combine values from params.yaml and zntrack.json

    Parameters
    ----------
    cls_dict: dict
        loaded from zntrack.json
    params_val:
        Parameters from params.yaml

    Returns
    -------
    Loaded object of type cls_dict[_type]

    """
    result = cls_dict
    if result["_type"] in ["zn.method"]:
        try:
            result["value"]["cls"] = params_val.pop("_cls")
        except KeyError:
            # using old file where the cls is stored in zntrack.json and not params.yaml
            pass
        result["value"]["kwargs"] = params_val
    else:
        # things that are not zn.method and do not have kwargs, such as pathlib, ...
        result["value"] = params_val

    return utils.decode_dict(result)


class SplitZnTrackOption(ZnTrackOption):
    """Method to split a value into params.yaml and zntrack.json

    Serialize data into params.yaml if human-readable and the type in zntrack.json
    """

    def save(self, instance):
        """Overwrite the save method

        This save method tries to split the value into params.yaml and zntrack.json.
        This allows e.g. having pathlib.Path() as a zn.params or a dataclass as zn.Method
        where the path as string / the dataclass as dict is stored in params.yaml
        """
        value = self.__get__(instance, self.owner)
        serialized_value = utils.encode_dict(value)

        try:
            # if znjson was used to serialize the data, it will have a _type key
            params_data, zntrack_data = split_value(serialized_value)

            # Write to params.yaml
            utils.file_io.update_config_file(
                file=utils.Files.params,
                node_name=instance.node_name,
                value_name=self.name,
                value=params_data,
            )

            # write to zntrack.json
            utils.file_io.update_config_file(
                file=utils.Files.zntrack,
                node_name=instance.node_name,
                value_name=self.name,
                value=zntrack_data,
            )
        except (KeyError, AttributeError, TypeError):
            # KeyError if serialized_value is a normal dict
            # AttributeError when serialized_value.pop does not exist
            # TypeError <..>
            super().save(instance)

    def get_data_from_files(self, instance):
        """Overwrite the load method

        Try to load from zntrack.json / params.yaml in a combined approach first,
        if no entry in zntrack.json is found, load from params.yaml only without
        deserializing.
        """
        file = self.get_filename(instance)
        try:
            # Check that we can read it
            _ = utils.file_io.read_file(utils.Files.zntrack)[instance.node_name][
                self.name
            ]

            params_values = utils.file_io.read_file(utils.Files.params)
            cls_dict = utils.file_io.read_file(utils.Files.zntrack)
            # select <node><attribute> from the full params / zntrack file
            params_values = params_values[instance.node_name][self.name]
            cls_dict = cls_dict[instance.node_name][self.name]

            if isinstance(cls_dict, list):
                values = [combine_values(*x) for x in zip(cls_dict, params_values)]
            else:
                values = combine_values(cls_dict, params_values)

            if isinstance(values, (list, tuple)):
                log.debug(f"Loading {instance.node_name} from {file}: ({values[:3]} ...)")
            else:
                log.debug(f"Loading {instance.node_name} from {file}: ({values})")
            return values
        except (AttributeError, KeyError, TypeError, FileNotFoundError):
            return super().get_data_from_files(instance)
