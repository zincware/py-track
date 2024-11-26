import zntrack.examples


def test_repro_twice(proj_path) -> None:
    project = zntrack.Project()

    with project:
        a = zntrack.examples.AddNumbers(a=1, b=2, name="NodeA")

    project.repro()

    assert a.c == 3

    project = zntrack.Project()
    with project:
        a = zntrack.examples.AddNumbers(a=1, b=4, name="NodeA")

    project.repro()

    assert a.c == 5
