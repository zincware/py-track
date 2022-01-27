import dataclasses


@dataclasses.dataclass(frozen=True)
class ZnTrackTypes:
    params: str = "params"
    deps: str = "deps"
    dvc: str = "dvc"
    zn: str = "zn"
    iterable: str = "iterable"
    method: str = "method"


zn_types = ZnTrackTypes()
