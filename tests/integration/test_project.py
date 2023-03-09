import zntrack


class WriteIO(zntrack.Node):
    inputs = zntrack.zn.params()
    outputs = zntrack.zn.outs()

    def run(self) -> None:
        self.outputs = self.inputs


def test_WriteIO(tmp_path_2):
    """Test the WriteIO node."""
    with zntrack.Project() as project:
        node = WriteIO(inputs="Hello World")

    project.run()
    node.load()
    assert node.outputs == "Hello World"

    with project.create_experiment(name="exp1"):
        node.inputs = "Hello World"

    with project.create_experiment(name="exp2"):
        node.inputs = "Lorem Ipsum"

    project.run_exp()
    assert node.from_rev(rev="exp1").inputs == "Hello World"
    assert node.from_rev(rev="exp1").outputs == "Hello World"

    assert node.from_rev(rev="exp2").inputs == "Lorem Ipsum"
    assert node.from_rev(rev="exp2").outputs == "Lorem Ipsum"