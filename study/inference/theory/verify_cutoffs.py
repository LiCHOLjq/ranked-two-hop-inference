"""Check the cutoff proposition and the three-hop counterexample with exact rationals.

Run with Python 3.8+ and save standard output as JSON. No dependencies.
"""

from fractions import Fraction
from itertools import combinations, product
import json
from math import prod
import platform
from random import Random


def subsets_up_to(items, cutoff):
    for size in range(min(cutoff, len(items)) + 1):
        for subset in combinations(sorted(items), size):
            yield frozenset(subset)


def two_hop_worlds(first, second):
    """Enumerate physical edge draws independently of the deletion recurrence."""
    edges = [(w, i) for w, row in enumerate(second) for i, b in enumerate(row) if b]
    parameters = first + [second[w][i] for w, i in edges]
    probabilities = {}
    for bits in product((0, 1), repeat=len(parameters)):
        mass = prod(p if on else 1 - p for on, p in zip(bits, parameters))
        successful = frozenset(
            i for e, (w, i) in enumerate(edges) if bits[w] and bits[len(first) + e]
        )
        probabilities[successful] = probabilities.get(successful, 0) + mass
    assert sum(probabilities.values()) == 1
    return probabilities


def check_matrix(first, second, counts):
    worlds = two_hop_worlds(first, second)
    terminals = len(second[0])

    def failure(targets):
        return prod(
            1 - a + a * prod(1 - row[i] for i in targets)
            for a, row in zip(first, second)
        )

    for j in range(terminals):
        prefix = frozenset(range(j))
        extended = prefix | {j}
        for k in range(1, terminals + 1):
            oracle = sum(
                mass for y, mass in worlds.items() if j in y and len(y & prefix) < k
            )
            computed = sum(
                (-1) ** (len(successes) - len(removed))
                * (failure(prefix - removed) - failure(extended - removed))
                for successes in subsets_up_to(prefix, k - 1)
                for removed in subsets_up_to(successes, len(successes))
            )
            assert oracle == computed, (j, k, oracle, computed)
            counts["top_k_outputs"] += 1
            if failure(prefix) == 0:
                counts["outputs_at_zero_prefix_mass"] += 1

        if failure(extended) == 0:
            continue
        for removed in subsets_up_to(prefix, len(prefix)):
            old = failure(prefix - removed) / failure(prefix)
            new = failure(extended - removed) / failure(extended)
            shares_witness = any(row[j] and any(row[i] for i in removed) for row in second)
            if not shares_witness:
                assert new == old
                counts["unchanged_old_ratios"] += 1
            inserted = failure(extended - (removed | {j})) / failure(extended)
            assert inserted == old / (failure(extended) / failure(prefix))
            counts["new_entry_identities"] += 1


def three_hop():
    """Two length-three paths share only their first edge."""
    failures = [Fraction(0) for _ in range(3)]
    for common, left, left_last, right, right_last in product((0, 1), repeat=5):
        i = common and left and left_last
        j = common and right and right_last
        for n, event in enumerate((not i, not j, not (i or j))):
            if event:
                failures[n] += Fraction(1, 32)
    h_i, h_j, h_ij = failures
    old, new = 1 / h_i, h_j / h_ij
    assert (old, new) == (Fraction(8, 7), Fraction(28, 25))
    return {"worlds": 32, "old_ratio": str(old), "new_ratio": str(new)}


def main():
    rng = Random(19)
    counts = dict(top_k_outputs=0, outputs_at_zero_prefix_mass=0,
                  unchanged_old_ratios=0, new_entry_identities=0)
    half = Fraction(1, 2)
    choices = [Fraction(0), Fraction(1, 3), half, Fraction(2, 3)]
    for _ in range(10):
        second = [[rng.choice(choices) for _ in range(4)] for _ in range(2)]
        check_matrix([Fraction(1, 3), Fraction(3, 4)], second, counts)
    # A surely successful predecessor is present at every nonempty prefix.
    check_matrix([Fraction(1), half], [[Fraction(1), half, 0, half], [0, half, half, half]], counts)
    result = {"python": platform.python_version(), "seed": 19, "matrices": 11,
              "cutoffs": [1, 2, 3, 4], "two_hop_checks": counts, "three_hop": three_hop()}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
