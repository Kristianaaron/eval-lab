import heapq


class ResolverError(Exception):
    pass


class CycleError(ResolverError):
    def __init__(self, cycle):
        self.cycle = list(cycle)
        super().__init__("dependency cycle: " + " -> ".join(self.cycle))


class MissingDependencyError(ResolverError):
    def __init__(self, missing):
        self.missing = sorted(set(missing))
        parts = ", ".join(f"{node} -> {dep}" for node, dep in self.missing)
        super().__init__("missing dependencies: " + parts)


def _normalize(graph, targets):
    if not isinstance(graph, dict):
        raise TypeError("graph must be a dict")
    deps = {}
    for node, raw in graph.items():
        if not isinstance(node, str):
            raise TypeError(f"node name must be str, got {node!r}")
        seen = []
        seen_set = set()
        for d in raw:
            if not isinstance(d, str):
                raise TypeError(f"dependency name must be str, got {d!r}")
            if d not in seen_set:
                seen_set.add(d)
                seen.append(d)
        deps[node] = seen

    if targets is None:
        considered = set(deps)
    else:
        targets = list(targets)
        for t in targets:
            if t not in deps:
                raise KeyError(t)
        considered = set()
        stack = list(targets)
        while stack:
            n = stack.pop()
            if n in considered:
                continue
            considered.add(n)
            for d in deps.get(n, ()):
                if d not in considered:
                    stack.append(d)
        # names that are missing are in `considered` but not in deps; drop them
        # for the sub-graph but keep them for the missing check below.

    missing = []
    for node in considered:
        if node not in deps:
            continue
        for d in deps[node]:
            if d not in deps:
                missing.append((node, d))
    if missing:
        raise MissingDependencyError(missing)
    sub = {n: deps[n] for n in considered}
    return sub


def _find_cycle(sub):
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in sub}
    for root in sorted(sub):
        if color[root] != WHITE:
            continue
        path = [root]
        iters = [iter(sub[root])]
        color[root] = GREY
        while path:
            try:
                nxt = next(iters[-1])
            except StopIteration:
                color[path.pop()] = BLACK
                iters.pop()
                continue
            if color[nxt] == GREY:
                idx = path.index(nxt)
                cyc = path[idx:]
                # rotate so the smallest node comes first
                k = cyc.index(min(cyc))
                cyc = cyc[k:] + cyc[:k]
                return cyc + [cyc[0]]
            if color[nxt] == WHITE:
                color[nxt] = GREY
                path.append(nxt)
                iters.append(iter(sub[nxt]))
    return None


def _kahn(sub):
    indeg = {n: len(sub[n]) for n in sub}
    dependents = {n: [] for n in sub}
    for n, ds in sub.items():
        for d in ds:
            dependents[d].append(n)
    ready = [n for n, k in indeg.items() if k == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        n = heapq.heappop(ready)
        order.append(n)
        for m in dependents[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                heapq.heappush(ready, m)
    if len(order) != len(sub):
        cycle = _find_cycle(sub)
        raise CycleError(cycle)
    return order, dependents


def resolve(graph, targets=None):
    sub = _normalize(graph, targets)
    order, _ = _kahn(sub)
    return order


def levels(graph, targets=None):
    sub = _normalize(graph, targets)
    order, _ = _kahn(sub)
    level = {}
    for n in order:
        ds = sub[n]
        level[n] = max((level[d] for d in ds), default=-1) + 1
    if not level:
        return []
    out = [[] for _ in range(max(level.values()) + 1)]
    for n, k in level.items():
        out[k].append(n)
    for group in out:
        group.sort()
    return out
