import os
from typing import Any, Callable, Literal, Optional, TypeVar, Union, overload

import pandas as pd
from zninit.descriptor import _Empty_TYPE

_T = TypeVar("_T")
_P = TypeVar("_P", bound=Union[str, bytes, os.PathLike])

def outs() -> Any: ...
def metrics() -> dict[str, Any]: ...
@overload
def params(
    default: Literal[_Empty_TYPE.Empty] = ...,
    owner=...,
    instance=...,
    name=...,
    use_repr: bool = ...,
    repr_func: Callable = ...,
    check_types: bool = False,
    metadata: Optional[dict] = ...,
    frozen: bool = False,
    on_setattr: Optional[Callable] = ...,
) -> Any: ...
@overload
def params(
    default: _T,
    owner=...,
    instance=...,
    name=...,
    use_repr: bool = ...,
    repr_func: Callable = ...,
    check_types: bool = False,
    metadata: Optional[dict] = ...,
    frozen: bool = False,
    on_setattr: Optional[Callable] = ...,
) -> _T: ...
@overload
def deps() -> Any: ...
@overload
def deps(data: _T) -> _T: ...
@overload
def deps(data1: _T, *data: _T) -> tuple[_T, ...]: ...
def plots(*data, **kwargs) -> pd.DataFrame: ...
@overload
def outs_path(*, dvc_option: str = ..., **kwargs) -> Any: ...
@overload
def outs_path(args: _P, *, dvc_option: str = ..., **kwargs) -> _P: ...
@overload
def outs_path(arg1: _P, *args: _P, dvc_option: str = ..., **kwargs) -> tuple[_P, ...]: ...
@overload
def metrics_path(*, dvc_option: str = ..., **kwargs) -> Any: ...
@overload
def metrics_path(args: _P, *, dvc_option: str = ..., **kwargs) -> _P: ...
@overload
def metrics_path(
    arg1: _P, *args: _P, dvc_option: str = ..., **kwargs
) -> tuple[_P, ...]: ...
@overload
def params_path(**kwargs) -> Any: ...
@overload
def params_path(args: _P, **kwargs) -> _P: ...
@overload
def params_path(arg1: _P, *args: _P, **kwargs) -> tuple[_P, ...]: ...
@overload
def deps_path(**kwargs) -> Any: ...
@overload
def deps_path(args: _P, **kwargs) -> _P: ...
@overload
def deps_path(arg1: _P, *args: _P, **kwargs) -> tuple[_P, ...]: ...
@overload
def plots_path(*, dvc_option: str = ..., **kwargs) -> Any: ...
@overload
def plots_path(args: _P, *, dvc_option: str = ..., **kwargs) -> _P: ...
@overload
def plots_path(
    arg1: _P, *args: _P, dvc_option: str = ..., **kwargs
) -> tuple[_P, ...]: ...
