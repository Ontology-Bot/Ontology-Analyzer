from sqlmodel import Session, Field, SQLModel, Relationship, create_engine, select

class NodeEdgeLink(SQLModel, table=True):
    node_key: str | None = Field(default=None, foreign_key="node.key", primary_key=True)
    edge_key: str | None = Field(default=None, foreign_key="edge.key", primary_key=True)


class Edge(SQLModel, table = True):
    key: str | None = Field(default=None, primary_key=True)

    nodes: list["Node"] = Relationship(back_populates="edges", link_model=NodeEdgeLink)


class Node(SQLModel, table=True):
    key: str | None = Field(default=None, primary_key=True)
    value: str

    edges: list["Edge"] = Relationship(back_populates="nodes", link_model=NodeEdgeLink)

class HyperGraphDB:

    def __init__(self, filename = "database.db") -> None:
        sqlite_url = f"sqlite:///{filename}"
        self.engine = create_engine(sqlite_url, echo=True)
        SQLModel.metadata.create_all(self.engine)


    def add_hyperedge(self, edge_key: str, node_map: dict[str, str]):
        with Session(self.engine) as session:
            # 1. Prepare/Get the Edge
            edge = session.get(Edge, edge_key)
            if not edge:
                edge = Edge(key=edge_key)

            # 2. Process Nodes (Upsert-like behavior)
            edge_nodes = []
            for k, v in node_map.items():
                # Try to find existing node
                node = session.get(Node, k)
                
                if not node:
                    # Create new if doesn't exist
                    node = Node(key=k, value=v)
                    session.add(node) 
                    session.commit()
                
                edge_nodes.append(node)

            # 3. Link them
            edge.nodes = edge_nodes

            # 4. Commit
            session.add(edge)
            session.commit()


    def get_hyperedges(self, node_key: str):
        # get list of hyperedges by hypernode id
        with Session(self.engine) as session:
            node = session.get(Node, node_key)
            return node.edges if node else []