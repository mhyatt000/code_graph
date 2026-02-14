import networkx as nx
from pyvis.network import Network
import pydot


def main():
    # Read the graph.dot file
    graphs = pydot.graph_from_dot_file("graph.dot")
    # graphs = pydot.graph_from_dot_file("classes.dot")
    pydot_graph = graphs[0]

    # Convert to NetworkX graph, preserving DOT attributes
    G = nx.DiGraph()
    for node in pydot_graph.get_nodes():
        name = node.get_name()
        if name in ('node', 'edge', 'graph', ''):
            continue
        attrs = node.obj_dict.get("attributes", {})
        G.add_node(name, **attrs)
    for edge in pydot_graph.get_edges():
        attrs = edge.obj_dict.get("attributes", {})
        G.add_edge(edge.get_source(), edge.get_destination(), **attrs)

    # Visualize
    visualize(G)


def visualize(G: nx.DiGraph, out="graph.html"):
    net = Network(
        height="1000px",
        width="100%",
        directed=True,
        notebook=False,
        cdn_resources="in_line",
    )

    # Better physics defaults for large graphs
    net.barnes_hut(
        gravity=-80000,
        central_gravity=0.3,
        spring_length=250,
        spring_strength=0.001,
        damping=0.09,
    )

    for node, data in G.nodes(data=True):
        fillcolor = data.get("fillcolor", "#cccccc").strip('"')
        label = data.get("label", node.split(".")[-1]).strip('"')
        shape = data.get("shape", "dot").strip('"')
        # Map DOT shapes to pyvis shapes
        pyvis_shape = {"ellipse": "dot", "box": "box", "note": "triangle", "folder": "diamond"}.get(shape, "dot")
        net.add_node(
            node,
            label=label,
            title=node.strip('"'),
            color=fillcolor,
            shape=pyvis_shape,
        )

    for u, v, data in G.edges(data=True):
        edge_color = data.get("color", "#cc3333").strip('"')
        edge_label = data.get("label", "").strip('"')
        net.add_edge(u, v, color=edge_color, title=edge_label)

    net.write_html(out, open_browser=True)


if __name__ == "__main__":
    main()
