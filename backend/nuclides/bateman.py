"""
Bateman solver for radioactive decay chains, with branching.

Solves dN_k/dt = -lambda_k N_k + sum_j b(j->k) lambda_j N_j for the whole decay graph below one parent, in closed form:

    N_k(t) = sum_i c(k,i) exp(-lambda_i t)

with the coefficients found in topological order (each nuclide's source term is a sum of exponentials, whose particular
solutions are c = amplitude / (lambda_k - lambda_i); the homogeneous part makes N_k(0) = 0). Branches that split and rejoin
(Pa-234 / Pa-234m -> U-234) need nothing special.

The arithmetic is done with 80-digit decimals. In ordinary floating point the closed form loses most of its digits when
half-lives differ by many orders of magnitude (U-238 at 4.5e9 years and Po-214 at 164 microseconds are 23 orders apart); with
80 digits that cancellation is harmless and the result is exact to double precision, with no dependency beyond the standard
library. A chain of 20 nuclides at 50 time points takes a few milliseconds.
"""

import math
from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

PRECISION = 80

# graph: nuclide -> (half-life in seconds or None when stable, ((daughter, branching fraction), ...)); a nuclide that is not
# in the graph at all is treated as stable
Graph = Dict[str, Tuple[Optional[float], Sequence[Tuple[str, float]]]]


def is_radioactive(graph: Graph, name: str) -> bool:
    entry = graph.get(name)
    return bool(entry and entry[0] and entry[0] > 0 and math.isfinite(entry[0]))


def topological_order(graph: Graph, parent: str) -> List[str]:
    """
    The radioactive nuclides reachable from `parent`, parent first and every nuclide after all of its parents. Among the
    candidates the one reached through the larger branching fraction comes first, so the main line of a chain reads in order.
    """
    nodes: List[str] = []
    seen = set()
    stack = [parent]
    while stack:
        n = stack.pop()
        if n in seen or not is_radioactive(graph, n):
            continue
        seen.add(n)
        nodes.append(n)
        stack.extend(d for d, _ in graph[n][1])

    indegree = {n: 0 for n in nodes}
    for n in nodes:
        for d, _ in graph[n][1]:
            if d in indegree:
                indegree[d] += 1

    order: List[str] = []
    ready = [parent]
    while ready:
        n = ready.pop(0)
        order.append(n)
        for d, _ in sorted(graph[n][1], key=lambda p: -p[1]):
            if d in indegree:
                indegree[d] -= 1
                if indegree[d] == 0:
                    ready.append(d)
    if len(order) != len(nodes):
        raise ValueError("decay graph has a cycle")
    return order


def _distinct_lambdas(lam: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """Nudge decay constants that coincide (the closed form divides by their difference) by a relative 1e-15."""
    items = sorted(lam.items(), key=lambda kv: kv[1])
    out = dict(lam)
    eps = Decimal("1e-15")
    for (_, a), (nb, b) in zip(items, items[1:]):
        if abs(out[nb] - a) <= abs(a) * eps:
            out[nb] = a * (1 + 2 * eps)
    return out


def solve_chain(graph: Graph, parent: str, activity_bq: float, times_s: Iterable[float]) -> Dict[str, List[float]]:
    """
    Activity (Bq) of every radioactive nuclide below `parent` at each time, starting from `activity_bq` of the parent alone.
    Returns {nuclide: [A(t0), A(t1), ...]} in topological order (parent first). Stable nuclides are not included.
    """
    times = [float(t) for t in times_s]
    if not is_radioactive(graph, parent):
        raise ValueError(f"{parent} is stable or unknown")
    if not (activity_bq > 0) or not math.isfinite(activity_bq):
        raise ValueError("activity must be positive")

    order = topological_order(graph, parent)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        ln2 = Decimal(2).ln()
        lam = _distinct_lambdas({n: ln2 / Decimal(repr(graph[n][0])) for n in order})

        parents_of: Dict[str, List[Tuple[str, Decimal]]] = defaultdict(list)
        for n in order:
            for d, frac in graph[n][1]:
                if d in lam:
                    parents_of[d].append((n, Decimal(repr(float(frac)))))

        coeffs: Dict[str, Dict[str, Decimal]] = {}
        n0 = Decimal(repr(float(activity_bq))) / lam[parent]
        for k in order:
            if k == parent:
                coeffs[k] = {parent: n0}
                continue
            source: Dict[str, Decimal] = defaultdict(Decimal)
            for j, frac in parents_of[k]:
                for i, c in coeffs[j].items():
                    source[i] += frac * lam[j] * c
            ck: Dict[str, Decimal] = {}
            total = Decimal(0)
            for i, amplitude in source.items():
                ci = amplitude / (lam[k] - lam[i])
                ck[i] = ci
                total += ci
            ck[k] = -total                      # N_k(0) = 0
            coeffs[k] = ck

        series: Dict[str, List[float]] = {k: [] for k in order}
        for t in times:
            td = Decimal(repr(t))
            decay = {i: (-lam[i] * td).exp() for i in order}
            for k in order:
                n_k = sum((c * decay[i] for i, c in coeffs[k].items()), Decimal(0))
                a_k = lam[k] * n_k
                series[k].append(float(a_k) if a_k > 0 else 0.0)
    return series
