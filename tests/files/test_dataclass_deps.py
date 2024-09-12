import dataclasses
import json
import pathlib

import yaml

import zntrack

CWD = pathlib.Path(__file__).parent.resolve()


@dataclasses.dataclass
class Thermostat:
    temperature: float
    friction: float = 0.1


class MLThermostat(zntrack.Node):
    temp: float = zntrack.params()


class MD(zntrack.Node):
    thermostat: Thermostat | list[Thermostat | MLThermostat] = zntrack.deps()
    steps: int = zntrack.params()


def test_deps_outside_graph(proj_path):
    thermostat = Thermostat(temperature=300)

    with zntrack.Project() as project:
        md = MD(thermostat=thermostat, steps=100)

    with project.group("multiple_deps"):
        ml = MLThermostat(temp=300)

        t1 = Thermostat(temperature=300, friction=0.05)
        t2 = Thermostat(temperature=400)
        md2 = MD(thermostat=[t1, ml, t2], steps=100)

    project.build()

    # TODO: lists / dicts / tuples
    assert md.name == "MD"
    assert md2.name == "multiple_deps_MD"

    node = md.from_rev()
    assert node.thermostat.temperature == thermostat.temperature

    node2 = md2.from_rev(name=md2.name)
    assert isinstance(node2.thermostat[0], Thermostat)
    assert isinstance(node2.thermostat[1], MLThermostat)
    assert isinstance(node2.thermostat[2], Thermostat)
    assert node2.thermostat[0].temperature == t1.temperature
    assert node2.thermostat[1].temp == ml.temp
    assert node2.thermostat[2].temperature == t2.temperature

    assert json.loads(
        (CWD / "zntrack_config" / "dataclass_deps.json").read_text()
    ) == json.loads((proj_path / "zntrack.json").read_text())
    assert yaml.safe_load(
        (CWD / "dvc_config" / "dataclass_deps.yaml").read_text()
    ) == yaml.safe_load((proj_path / "dvc.yaml").read_text())
    assert (CWD / "params_config" / "dataclass_deps.yaml").read_text() == (
        proj_path / "params.yaml"
    ).read_text()


if __name__ == "__main__":
    test_deps_outside_graph(None)