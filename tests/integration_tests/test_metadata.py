import zntrack


class NodeInfoNode(zntrack.Node):
    """This is a simple Test Node"""

    node_info = zntrack.NodeInfo(author="John Doe")

    def run(self):
        pass


def test_NodeInfoNode():
    assert NodeInfoNode.node_info.author == "John Doe"

    node = NodeInfoNode()
    node_info = node.zntrack.collect(zntrack.NodeInfo)
    assert node_info["node_info"].author == "John Doe"
    assert node_info["node_info"].long_description == "This is a simple Test Node"
