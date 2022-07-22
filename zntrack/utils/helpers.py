import typing

from zntrack.utils.structs import ZnTypes


def isnode(node) -> bool:
    """Check if node contains a Node instance or class"""
    from zntrack.core.base import Node

    if isinstance(node, (list, tuple)):
        return any([isnode(x) for x in node])
    else:
        try:
            if isinstance(node, Node) or issubclass(node, Node):
                return True
        except TypeError:
            pass
    return False


def filter_ZnTrackOption(
    data,
    cls,
    zn_type: typing.Union[ZnTypes, typing.List[ZnTypes]],
    return_with_type=False,
    allow_none: bool = False,
) -> dict:
    """Filter the descriptor instances by zn_type

    Parameters
    ----------
    data: List[ZnTrackOption]
        The ZnTrack options to query through
    cls:
        The instance the ZnTrack options are attached to
    zn_type: str
        The zn_type of the descriptors to gather
    return_with_type: bool, default=False
        return a dictionary with the Descriptor.dvc_option as keys
    allow_none: bool, default=False
        Use getattr(obj, name, None) instead of getattr(obj, name) to yield
        None when an AttributeError occurs.

    Returns
    -------
    dict:
        either {attr_name: attr_value}
        or
        {descriptor.dvc_option: {attr_name: attr_value}}

    """
    if not isinstance(zn_type, (tuple, list)):
        zn_type = [zn_type]
    data = [x for x in data if x.zn_type in zn_type]
    if return_with_type:
        types_dict = {x.dvc_option: {} for x in data}
        for entity in data:
            if allow_none:
                # avoid AttributeError
                value = getattr(cls, entity.name, None)
            else:
                value = getattr(cls, entity.name)
            types_dict[entity.dvc_option].update({entity.name: value})
        return types_dict
    if allow_none:
        return {x.name: getattr(cls, x.name, None) for x in data}
    # avoid AttributeError
    return {x.name: getattr(cls, x.name) for x in data}
