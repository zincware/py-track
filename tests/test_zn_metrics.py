"""Test for metrics."""
import zntrack


class NodeWithMetrics(zntrack.Node):
    inputs = zntrack.zn.params()
    my_metrics = zntrack.zn.metrics()

    def run(self) -> None:
        self.my_metrics = self.inputs


def test_NodeWithMetrics(proj_path):
    with zntrack.Project(automatic_node_names=True) as project:
        node = NodeWithMetrics(inputs=3.1415)
        node2 = NodeWithMetrics(inputs={"pi": 3.1415})
        node3 = NodeWithMetrics(inputs=3)

    project.run()

    node.load()
    node2.load()
    node3.load()

    assert node.my_metrics == {"my_metrics": 3.1415}
    assert node2.my_metrics == {"pi": 3.1415}
    assert node3.my_metrics == {"my_metrics": 3}
