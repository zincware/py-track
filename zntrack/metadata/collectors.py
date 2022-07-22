import dataclasses


@dataclasses.dataclass
class NodeInfo:
    author: str = None
    license: str = None
    short_description: str = None
    long_description: str = None

    def update_from_docstring(self, docstring: str):
        self.long_description = docstring


class RunInfo:
    # TODO what is available via DVC already
    start_time = None
