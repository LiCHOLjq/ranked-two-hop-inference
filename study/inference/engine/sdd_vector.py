"""Compile and weight a full top-two vector using the UCLA SDD package via PySDD."""
import argparse
import json
import time
from array import array
from pathlib import Path

from pysdd.sdd import SddManager


def matrix(path):
    tokens = iter(path.read_text().split())
    w, n = int(next(tokens)), int(next(tokens))
    a = [float(next(tokens)) for _ in range(w)]
    columns = [[] for _ in range(n)]
    for i in range(w):
        for column in columns:
            p = float(next(tokens))
            if p:
                column.append((i, p))
    if next(tokens, None) is not None:
        raise ValueError("unexpected trailing matrix entries")
    return a, columns


def compile_vector(a, columns):
    # Number a witness variable at first use; put incident edges in score order.
    weights = []
    witness_ids = {}
    literals = []
    for column in columns:
        terms = []
        for w, p in column:
            if w not in witness_ids:
                weights.append(a[w])
                witness_ids[w] = len(weights)
            weights.append(p)
            terms.append((witness_ids[w], len(weights)))
        literals.append(terms)
    if not weights:  # The package requires at least one declared variable.
        weights.append(0.5)
    mgr = SddManager(var_count=len(weights), auto_gc_and_minimize=False)
    roots = []
    zero = one_or_less = mgr.true()
    for terms in literals:
        y = mgr.false()
        for w, e in terms:
            y = y | (mgr.literal(w) & mgr.literal(e))
        roots.append(y & one_or_less)
        one_or_less = zero | (~y & one_or_less)
        zero = zero & ~y
    return mgr, roots, weights


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    args = parser.parse_args()
    start = time.perf_counter()
    a, columns = matrix(args.matrix)
    parsed = time.perf_counter()
    mgr, roots, weights = compile_vector(a, columns)
    built = time.perf_counter()
    print(json.dumps({"phase": "compiled", "parse_s": parsed - start,
                      "compile_s": built - parsed}), flush=True)
    # PySDD expects signed literals ordered -V,...,-1,1,...,V.
    init_start = time.perf_counter()
    literal_weights = array("d", [1 - x for x in reversed(weights)] + weights)
    counters = [root.wmc(log_mode=False) for root in roots]
    for counter in counters:
        counter.set_literal_weights_from_array(literal_weights)
    ready = time.perf_counter()
    repeats = 0
    while True:
        values = [counter.propagate() for counter in counters]
        repeats += 1
        elapsed = time.perf_counter() - ready
        if elapsed >= .02:
            break
    print(json.dumps({"phase": "success", "parse_s": parsed - start,
                      "compile_s": built - parsed, "weight_setup_s": ready - init_start,
                      "evaluate_s": elapsed / repeats, "repeats": repeats,
                      "values": values}, allow_nan=False))


if __name__ == "__main__":
    main()

