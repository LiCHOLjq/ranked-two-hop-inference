"""Inspect the initial PySDD vtree for each variable count used in the benchmark."""
import argparse
import json
from pathlib import Path

from pysdd.sdd import SddManager
from sdd_vector import matrix


def inspect(node):
    if node.is_leaf():
        return [node.var()], 0
    left, dl = inspect(node.left())
    right, dr = inspect(node.right())
    return left + right, max(dl, dr, abs(len(left)-len(right)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("environment", type=Path)
    args = parser.parse_args()
    chosen = set(json.loads(args.environment.read_text())["inputs"])
    checks = []
    for row in json.loads(args.cases.read_text()):
        if row["index"] not in chosen:
            continue
        _, columns = matrix(args.cases.parent/"inputs"/row["input"])
        n = max(1, sum(map(len,columns))+len({w for col in columns for w,_ in col}))
        for auto in (False,True):
            mgr = SddManager(var_count=n,auto_gc_and_minimize=auto)
            order, imbalance = inspect(mgr.vtree())
            if order != list(range(1,n+1)) or imbalance>1:
                raise ValueError("Unexpected initial vtree")
            checks.append(dict(case=row["index"], variables=n, auto=auto,
                               max_sibling_leaf_count_difference=imbalance))
    print(json.dumps(checks, indent=2))

