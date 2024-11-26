import zntrack.examples


def test_nested_deps(proj_path) -> None:
    project = zntrack.Project()

    with project:
        a = zntrack.examples.AddNumbers(a=1, b=2)
        b = zntrack.examples.AddNumbers(a=1, b=2)
        c = zntrack.examples.AddNodeAttributes(a=a.c, b=b.c)

    project.repro()

    x = c.from_rev(name=c.name)
    assert x.a == 3
    assert c.a == 3
    assert x.a == c.a
