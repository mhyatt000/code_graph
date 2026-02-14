"""Static call graph analyzer using ast.NodeVisitor.

Nodes: dir, file, class, function
Edges: imports, calls, has (attribute/containment), is (subclass/inheritance)

Future edges: decorates
"""

import ast
import sys
from pathlib import Path


class Node:
    """A node in the call graph."""

    __slots__ = ("id", "kind", "label", "party", "loc")

    def __init__(self, id: str, kind: str, label: str, party: str = "1st", loc: int = 0):
        self.id = id
        self.kind = kind  # dir | file | class | function
        self.label = label
        self.party = party  # "1st" | "3rd"
        self.loc = loc  # lines of code

    def dot_id(self) -> str:
        return '"' + self.id.replace('"', '\\"') + '"'

    def dot_attrs(self) -> str:
        shape = {"dir": "folder", "file": "note", "class": "box", "function": "ellipse"}
        color_1st = {"dir": "#cccccc", "file": "#aaddff", "class": "#ffddaa", "function": "#ddffdd"}
        color_3rd = {"dir": "#e0e0e0", "file": "#d0d0d0", "class": "#d0d0d0", "function": "#d0d0d0"}
        s = shape.get(self.kind, "ellipse")
        colors = color_1st if self.party == "1st" else color_3rd
        c = colors.get(self.kind, "#ffffff")
        # Scale node width by LOC (min 0.5, max 3.0)
        w = max(0.5, min(3.0, 0.5 + self.loc / 50))
        h = max(0.3, min(2.0, 0.3 + self.loc / 80))
        return f'[label="{self.label}" shape={s} style=filled fillcolor="{c}" party="{self.party}" loc={self.loc} width={w:.2f} height={h:.2f}]'


class Edge:
    """A directed edge in the call graph."""

    __slots__ = ("src", "dst", "kind")

    def __init__(self, src: str, dst: str, kind: str):
        self.src = src
        self.dst = dst
        self.kind = kind  # imports | calls | has | is

    def dot_attrs(self) -> str:
        styles = {
            "imports": 'style=dashed color="#6666cc" fontcolor="#6666cc"',
            "calls": 'color="#cc3333" fontcolor="#cc3333"',
            "has": 'style=dotted color="#666666" fontcolor="#666666"',
            "is": 'style=bold color="#33aa33" fontcolor="#33aa33"',
        }
        return f'[label="{self.kind}" {styles.get(self.kind, "")}]'


class Graph:
    """Collects nodes and edges, writes DOT."""

    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []

    def add_node(self, id: str, kind: str, label: str, party: str = "1st", loc: int = 0):
        if id not in self.nodes:
            self.nodes[id] = Node(id, kind, label, party=party, loc=loc)

    def add_edge(self, src: str, dst: str, kind: str):
        self.edges.append(Edge(src, dst, kind))

    def write_dot(self, path: str):
        lines = ["digraph callgraph {", "  rankdir=LR;", "  node [fontname=Helvetica fontsize=10];", "  edge [fontname=Helvetica fontsize=8];", ""]
        for n in self.nodes.values():
            lines.append(f"  {n.dot_id()} {n.dot_attrs()};")
        lines.append("")
        for e in self.edges:
            src = self.nodes[e.src].dot_id() if e.src in self.nodes else f'"{e.src}"'
            dst = self.nodes[e.dst].dot_id() if e.dst in self.nodes else f'"{e.dst}"'
            lines.append(f"  {src} -> {dst} {e.dot_attrs()};")
        lines.append("}")
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")


class CallGraphVisitor(ast.NodeVisitor):
    """Walks a single file's AST and populates the graph."""

    def __init__(self, graph: Graph, filepath: str, root: Path):
        self.graph = graph
        self.filepath = filepath
        self.rel_path = str(Path(filepath).relative_to(root))
        self.file_id = f"file:{self.rel_path}"
        self._scope: list[str] = []  # stack of node ids for current scope

    def _current_scope_id(self) -> str:
        return self._scope[-1] if self._scope else self.file_id

    def _make_id(self, kind: str, name: str) -> str:
        parent = self._current_scope_id()
        return f"{parent}::{kind}:{name}"

    def analyze(self):
        with open(self.filepath, "r") as f:
            source = f.read()
        try:
            tree = ast.parse(source, filename=self.filepath)
        except SyntaxError:
            return

        file_loc = source.count("\n") + (1 if source and not source.endswith("\n") else 0)
        self.graph.add_node(self.file_id, "file", Path(self.rel_path).name, loc=file_loc)
        self._scope.append(self.file_id)

        # Process imports and top-level definitions
        self.visit(tree)
        self._scope.pop()

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            mod_id = f"file:{alias.name}"
            self.graph.add_node(mod_id, "file", alias.name, party="3rd")
            self.graph.add_edge(self._current_scope_id(), mod_id, "imports")

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module is None:
            return
        mod_id = f"file:{node.module}"
        self.graph.add_node(mod_id, "file", node.module, party="3rd")
        self.graph.add_edge(self._current_scope_id(), mod_id, "imports")

    def visit_ClassDef(self, node: ast.ClassDef):
        cls_id = self._make_id("class", node.name)
        loc = (node.end_lineno or node.lineno) - node.lineno + 1
        self.graph.add_node(cls_id, "class", node.name, loc=loc)
        self.graph.add_edge(self._current_scope_id(), cls_id, "has")

        # Inheritance: "is" edges
        for base in node.bases:
            base_name = _resolve_name(base)
            if base_name:
                base_id = f"class:{base_name}"
                self.graph.add_node(base_id, "class", base_name, party="3rd")
                self.graph.add_edge(cls_id, base_id, "is")

        self._scope.append(cls_id)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_function(node)

    def _visit_function(self, node):
        func_id = self._make_id("function", node.name)
        loc = (node.end_lineno or node.lineno) - node.lineno + 1
        self.graph.add_node(func_id, "function", node.name, loc=loc)
        self.graph.add_edge(self._current_scope_id(), func_id, "has")

        # TODO: future "decorates" edge
        # for dec in node.decorator_list: ...

        self._scope.append(func_id)
        # Walk only the direct body for calls — skip nested func/class defs
        # (those get their own visit_ calls via generic_visit)
        self._walk_body_for_calls(node)
        # Recurse into nested class/function defs
        self.generic_visit(node)
        self._scope.pop()

    def _walk_body_for_calls(self, node):
        """Walk AST nodes for Call nodes, but stop at nested function/class defs."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # these get their own scope via visit_*
            if isinstance(child, ast.Call):
                self._handle_call(child)
                # still walk call arguments for nested calls like f(g())
            self._walk_body_for_calls(child)

    def _handle_call(self, node: ast.Call):
        called = _resolve_name(node.func)
        if called is None:
            return

        # Try to resolve to a known node; fall back to a bare function node
        target_id = self._resolve_target(called)
        self.graph.add_edge(self._current_scope_id(), target_id, "calls")

    def _resolve_target(self, name: str) -> str:
        """Best-effort resolution of a called name to an existing node id."""
        # For dotted names like self.foo, obj.bar, Module.func — extract the attr
        short_name = name.rsplit(".", 1)[-1] if "." in name else name

        # First try exact full name match
        for nid, n in self.graph.nodes.items():
            if n.label == name and n.kind in ("function", "class"):
                return nid

        # Then try the short (attribute) name — prefer matches in the same file
        same_file = []
        other = []
        for nid, n in self.graph.nodes.items():
            if n.label == short_name and n.kind in ("function", "class"):
                if nid.startswith(self.file_id):
                    same_file.append(nid)
                else:
                    other.append(nid)
        if same_file:
            return same_file[0]
        if other:
            return other[0]

        # Create a placeholder using the short name so the graph stays readable
        placeholder_id = f"function:{name}"
        self.graph.add_node(placeholder_id, "function", short_name, party="3rd")
        return placeholder_id


def _resolve_name(node: ast.expr) -> str | None:
    """Extract a dotted name string from an AST expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        val = _resolve_name(node.value)
        if val:
            return f"{val}.{node.attr}"
        return node.attr
    return None


def build_graph(root_dir: str) -> Graph:
    root = Path(root_dir).resolve().parent if Path(root_dir).is_file() else Path(root_dir).resolve().parent
    target = Path(root_dir).resolve()

    # If given a relative path like "lgrey", resolve from cwd
    if not target.exists():
        target = Path.cwd() / root_dir
        root = Path.cwd()

    if target.is_file():
        root = target.parent.parent  # so relative path includes the dir
        py_files = [target]
    else:
        root = target.parent
        py_files = sorted(target.rglob("*.py"))

    graph = Graph()

    # Add directory nodes
    dirs_seen = set()
    for f in py_files:
        rel = Path(f).relative_to(root)
        parts = rel.parts[:-1]  # directory parts
        for i in range(len(parts)):
            dir_path = "/".join(parts[: i + 1])
            dir_id = f"dir:{dir_path}"
            if dir_id not in dirs_seen:
                graph.add_node(dir_id, "dir", parts[i])
                dirs_seen.add(dir_id)
                # Parent dir -> child dir "has" edge
                if i > 0:
                    parent_id = f"dir:{'/'.join(parts[:i])}"
                    graph.add_edge(parent_id, dir_id, "has")

        # Dir -> file "has" edge
        file_id = f"file:{rel}"
        dir_path = "/".join(parts)
        if dir_path:
            graph.add_edge(f"dir:{dir_path}", file_id, "has")

    # Analyze each file
    for filepath in py_files:
        visitor = CallGraphVisitor(graph, str(filepath), root)
        visitor.analyze()

    return graph


def main():
    root_dir = sys.argv[1] if len(sys.argv) > 1 else "lgrey"
    graph = build_graph(root_dir)

    out = "graph.dot"
    graph.write_dot(out)

    n_by_kind = {}
    for n in graph.nodes.values():
        n_by_kind[n.kind] = n_by_kind.get(n.kind, 0) + 1

    e_by_kind = {}
    for e in graph.edges:
        e_by_kind[e.kind] = e_by_kind.get(e.kind, 0) + 1

    print(f"Wrote {out}")
    print(f"  Nodes: {len(graph.nodes)} {n_by_kind}")
    print(f"  Edges: {len(graph.edges)} {e_by_kind}")


if __name__ == "__main__":
    main()
