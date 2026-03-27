from prototypes.utils.sparql.common import split_camel_case, preprocess_str

class BlockAttribute:
    def __init__(self, attrLabel: str, attrComment: str, attrValue: str = "", attrUnit: str = "", attrType: str = "", **kwargs) -> None:
        self.label = attrLabel
        self.descr = attrComment
        self.value = attrValue
        self.unit = attrUnit
        self.type = attrType
        self.subattrs: dict[str, BlockAttribute] = {}


class Connection:
    def __init__(self, lnk: str, lnkType: str, lnkLabel: str, **kwargs) -> None:
        self.type = split_camel_case(lnkType)
        self.guid = lnk
        self.label = lnkLabel

class Block:
    def __init__(self, s: str, label: str, description: str, type: str, **kwargs) -> None:
        self.guid = s
        self.label = label
        self.descr = description
        self.type = preprocess_str(type)
        self.attrs: dict[str, BlockAttribute] = {}
        self.connections: list[Connection] = []

    def add_attr(self, **kwargs) -> None:
        rootAttr = kwargs.get("rootAttr")
        attr = kwargs.get("attr")
        if rootAttr is None or attr is None: # ignore empty args
            return 
        # assume max 2 levels deep
        if rootAttr == attr: 
            self.attrs[rootAttr] = BlockAttribute(**kwargs)
        else: 
            self.attrs[rootAttr].subattrs[attr] = BlockAttribute(**kwargs)
    
    def add_connection(self, **kwargs) -> None:
        if kwargs.get("lnkLabel") is None: # ignore empty args
            return
        self.connections.append(Connection(**kwargs))

    def to_sentences(self) -> tuple[list[str], list[str]]:
        """ tuple[sentences, ids]
        """
        res = [f"Instance `{self.label}` [`{self.guid}`]", f"`{self.label}` is {self.type}", f"`{self.label}` is described as {self.descr}"]
        for a in self.attrs.values():
            if a.value: 
                res.append(f"`{self.label}` has `{a.label}` with value `{a.value} {a.unit}` described as {a.descr}")
            else:
                res.append(f"`{self.label}` has `{a.label}` described as {a.descr}")
            for sa in a.subattrs.values():
                if sa.value: 
                    res.append(f"`{self.label}` has `{a.label}` with `{sa.label}` equal `{sa.value} {sa.unit}`")
                else:
                    res.append(f"`{self.label}` has `{a.label}` with `{sa.label}`")
        for c in self.connections:
            res.append(f"`{self.label}` {c.type} `{c.label}` [`{c.guid}`]")
        return res, [f"{self.guid}:{i}" for i in range(len(res))]
    
    def __repr__(self) -> str:
        s, _ = self.to_sentences()
        return f"{s}"
