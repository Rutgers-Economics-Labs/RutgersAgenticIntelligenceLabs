from pathlib import Path

class OntologyView:
    """Thin wrapper around owlready2 World for local ontology access."""

    def __init__(self, onto_db_path: str):
        try:
            from owlready2 import World
        except ImportError:
            raise ImportError("owlready2 required: pip install 'rail[local]'")

        self._world = World(filename=onto_db_path)
        self._onto = list(self._world.ontologies.values())[0]

    def classes(self) -> list[str]:
        """List all OWL class names."""
        return [cls.name for cls in self._onto.classes()]

    def individuals(self, class_name: str) -> list:
        """List all individuals of a class."""
        cls = self._onto[class_name]
        if cls is None:
            raise ValueError(f"Class not found: {class_name}")
        return list(cls.instances())

    def get(self, uri: str):
        """Get an individual by URI fragment."""
        return self._world.search_one(iri=f"*{uri}")

    def search(self, q: str) -> list:
        """Search individuals by hasName property."""
        results = []
        for ind in self._onto.individuals():
            name = getattr(ind, "hasName", [])
            if name and q.lower() in str(name[0]).lower():
                results.append(ind)
        return results[:50]

    def neighbors(self, individual, depth: int = 1) -> dict:
        """Return a neighborhood subgraph around an individual."""
        visited = set()
        nodes = []
        edges = []

        def traverse(ind, d):
            if ind in visited or d < 0:
                return
            visited.add(ind)
            nodes.append({"iri": ind.iri, "name": getattr(ind, "hasName", [ind.name])[0]})
            for prop in ind.get_properties():
                for val in prop[ind]:
                    if hasattr(val, "iri"):
                        edges.append({"source": ind.iri, "target": val.iri, "property": prop.name})
                        traverse(val, d - 1)

        traverse(individual, depth)
        return {"nodes": nodes, "edges": edges}

    def sparql(self, query: str) -> list:
        """Run a SPARQL query against the ontology."""
        return list(self._world.sparql(query))
