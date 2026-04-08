from collections import deque

from logging import getLogger
logger = getLogger(__name__)

class Node:
    def __init__(self, guid: str) -> None:
        self.forward: list[str] = []
        self.backward: list[str] = []
        self.guid: str = guid
        self.label = "ERROR"
        self.type = "ERROR"
    
    def fill_details(self, guid: str, label: str, type: str, **kwargs) -> None:
        self.label: str = label
        self.type: str = type
        self.guid: str = guid

    def add_forward(self, guid: str) -> None:
        self.forward.append(guid)

    def add_backward(self, guid: str) -> None:
        self.backward.append(guid)

    def __repr__(self) -> str:
        return f"{self.type} '{self.label}' ({self.guid})"


class PathFinder:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.blank_nodes: set[str] = set() # nodes for which backward link is missing

    def get_or_add(self, guid: str) -> Node:
        node = self.nodes.get(guid)
        if not node:
            node = Node(guid)
            self.nodes[guid] = node
        return node

    def add_connection(self, row: dict[str, str]):
        node_a_guid = row["guid"]
        node_b_guid = row.get("guidLnk") # may be empty if node has no connections
        lnkType = row.get("lnkType")
        #
        node_a = self.get_or_add(node_a_guid)
        node_a.fill_details(**row)
        #
        if not node_b_guid:
            return
        logger.warning(f"Adding connection {node_a_guid} {lnkType} {node_b_guid}")
        # now node b is safe
        node_b = self.get_or_add(node_b_guid)
        match lnkType:
            case "contains": # bidir
                node_a.add_forward(node_b_guid)
                node_b.add_forward(node_a_guid)
            case "containedIn":
                node_a.add_backward(node_b_guid)
                node_b.add_backward(node_a_guid)
            case "connectedTo":
                node_a.add_forward(node_b_guid)
            case "connectedFrom":
                node_a.add_backward(node_b_guid)
            case _:
                raise ValueError(f"Unknown lnk type {node_a_guid} {lnkType} {node_b_guid} ")


    def _dfs(self, start: str, getter):
        visited: set[str] = set()
        stack: list[str] = [start]
        while stack:
            node = stack.pop()
            if node not in visited:
                visited.add(node)
                stack.extend(getter(self.nodes[node]))
        return visited
    

    def get_islands(self):
        remaining = set(self.nodes.keys())
        islands: list[list[Node]] = []

        while remaining:
            start = next(iter(remaining))

            reachable_from = self._dfs(start, lambda n: n.forward)
            reachable_to   = self._dfs(start, lambda n: n.backward)

            island = reachable_from | reachable_to

            islands.append([self.nodes[n] for n in island])

            remaining -= island

        return islands

    
    def get_unreachable(self, start_guid = None):
        start = start_guid or next(iter(self.nodes))
        
        reachable_from_start = self._dfs(start, lambda n: n.forward)
        reachable_to_start  = self._dfs(start, lambda n: n.backward)

        reachable = reachable_from_start | reachable_to_start # use & for strongly connected check
        all_nodes = set(self.nodes.keys())
        
        return [self.nodes[n] for n in (all_nodes - reachable)]
    
    def get_path(self, guid_a: str, guid_b: str):
        if guid_a not in self.nodes or guid_b not in self.nodes:
            raise ValueError("Provided guids do not exist in the pathing cache")

        queue = deque([(guid_a, [self.nodes[guid_a]])])  # store node and path to it
        visited = set([guid_a])
        
        while queue:
            node, path = queue.popleft()

            if node == guid_b: 
                return path
            
            for n in self.nodes[node].forward:
                if n not in visited:
                    visited.add(n)
                    queue.append((n, path + [self.nodes[n]]))
        
        return None
        
