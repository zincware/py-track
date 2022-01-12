import dataclasses
import logging

log = logging.getLogger(__name__)


@dataclasses.dataclass
class Metadata:
    dvc_option: str
    zntrack_type: str

    @property
    def dvc_args(self):
        return self.dvc_option.replace("_", "-")


class Descriptor:
    metadata: Metadata = None

    def __init__(self, default_value=None):
        self.default_value = default_value
        self.owner = None
        self.instance = None
        self.name = ""

    def __set_name__(self, owner, name):
        self.owner = owner
        self.name = name

    def get(self, instance, owner):
        """Overwrite this method for custom get method"""
        raise NotImplementedError

    def set(self, instance, value):
        """Overwrite this method for custom set method"""
        raise NotImplementedError

    def __get__(self, instance, owner):
        if instance is None:
            return self
        log.debug(f"Get {self} from {instance}")
        try:
            return self.get(instance, owner)
        except NotImplementedError:
            return instance.__dict__.get(self.name, self.default_value)

    def __set__(self, instance, value):
        log.debug(f"Set {self} from {instance}")
        try:
            self.set(instance, value)
        except NotImplementedError:
            instance.__dict__[self.name] = value
