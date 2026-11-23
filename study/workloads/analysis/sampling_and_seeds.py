"""Reproduce the fixed-budget sampling and fresh-query seed-block summaries."""
import csv
import json
from collections import defaultdict
from itertools import groupby
from math import comb, isclose
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
CAMPAIGN = PROJECT / "experiments" / "graph_queries"
ORIGINAL = PROJECT.parent / "historical/sampling"


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def save_rows(name, rows):
    with (HERE / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def group_name(dataset, scale):
    if dataset == "synthetic":
        return "Synthetic"
    graph = {"cora": "Cora", "ogbn_arxiv_20k": "OGB20k"}[dataset]
    return f"{graph} {scale}"


def sampling():
    cases, observations = [], []
    for workload_seed in (5202, 5203, 5204):
        directory = ORIGINAL / f"seed_{workload_seed}"
        archive = read_rows(directory / "runs.csv")
        for name, group in groupby(archive, key=lambda row: row["case"]):
            records = list(group)
            exact = next(r for r in records if r["method"] == "sparse")
            estimates = [r for r in records if r["method"] == "static_rb"]
            assert sorted(int(r["seed"]) for r in estimates) == list(range(6301, 6306))
            idx = exact["case_index"]
            direct = json.loads((directory / f"values_{idx}_direct.json").read_text())
            stratum = next((group_name(dataset, "large" if "_large_" in name else "small")
                            for dataset in ("cora", "ogbn_arxiv_20k") if name.startswith(dataset)),
                           "Synthetic")
            errors, times = [], []
            for row in estimates:
                assert int(row["repeats"]) == 1
                vector = json.loads((directory / f"values_{idx}_static_rb_{row['seed']}.json").read_text())
                assert len(vector) == len(direct)
                error = max((abs(x - y) for x, y in zip(vector, direct)), default=0)
                assert isclose(error, float(row["max_error_vs_direct"]), abs_tol=1e-23)
                time_ms = float(row["seconds"]) * 1000
                errors.append(error)
                times.append(time_ms)
                observations.append(dict(workload_seed=workload_seed, case=name, stratum=stratum,
                                         sampling_seed=row["seed"], max_error=error, rb_ms=time_ms))
            sparse_ms = float(exact["seconds"]) * 1000
            cases.append(dict(workload_seed=workload_seed, case=name, stratum=stratum,
                              sparse_ms=sparse_ms, rb_ms=median(times), max_error=median(errors),
                              rb_to_sparse=median(times) / sparse_ms))
    assert len(cases) == 96 and len(observations) == 480
    save_rows("sampling_observations.csv", observations)
    save_rows("sampling_cases.csv", cases)
    strata = []
    for name in sorted({r["stratum"] for r in cases}):
        group = [r for r in cases if r["stratum"] == name]
        draws = [r for r in observations if r["stratum"] == name]
        stats = {key: median(r[key] for r in group) for key in ("sparse_ms","rb_ms","rb_to_sparse","max_error")}
        strata.append(dict(stratum=name, cases=len(group), draws=len(draws), **stats,
                           worst=max(r["max_error"] for r in draws),
                           passed=sum(r["max_error"] <= 1e-10 for r in draws)))
    return strata


def seed_blocks():
    raw = read_rows(CAMPAIGN / "results/runs.csv")
    meta = json.loads((CAMPAIGN / "results/cases.json").read_text())
    times = defaultdict(lambda: defaultdict(list))
    for r in raw:
        if r["family"] == "fresh_real":
            times[int(r["case"])][r["method"]].append(float(r["seconds"]))
    blocks = defaultdict(list)
    for m in meta:
        if m["family"] == "fresh_real":
            by_method = {k: median(v) for k,v in times[m["index"]].items()}
            proposed = by_method.pop("sparse")
            blocks[group_name(m["dataset"], m["scale"]), m["seed"]].append(min(by_method.values())/proposed)
    assert len(blocks) == 20 and all(len(v) == 5 for v in blocks.values())
    results = []
    for name in sorted({name for name, seed in blocks}):
        values = [median(blocks[name,seed]) for seed in range(5205,5210)]
        positives = sum(x > 1 for x in values)
        n = sum(x != 1 for x in values)
        p = min(1, 2 * sum(comb(n,i) for i in range(min(positives,n-positives)+1)) / 2**n)
        results.append(dict(stratum=name, block_medians=values, positives=positives, n=n, two_sided_p=p))
    running = 0
    for i, row in enumerate(sorted(results,key=lambda r:r["two_sided_p"])):
        running = max(running, min(1, (len(results)-i) * row["two_sided_p"]))
        row["holm_p"] = running
    return results


if __name__ == "__main__":
    result = {"sampling": sampling(), "fresh_blocks": seed_blocks()}
    path = HERE / "sampling_and_seeds.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(path.read_text())
