"""Rebuild the marking-rate sensitivity and small-query case comparisons from the release."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path, help="release root containing the study directory")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    base = args.repository / "study"
    results = base / "experiments/graph_queries/results"
    cases = json.loads((results / "cases.json").read_text(encoding="utf-8"))
    timings = defaultdict(list)
    for row in read_rows(results / "runs.csv"):
        timings[int(row["case"]), row["method"]].append(float(row["seconds"]))
    groups = {"All records": cases}
    for case in cases:
        if case["family"] == "fresh_real":
            groups.setdefault(case["dataset"] + " " + case["scale"], []).append(case)
    expected = []
    for label, group in groups.items():
        for rate in (0, 0.001, 0.01, 0.05, 0.2):
            regular = mean((1 - rate) ** c["edges"] for c in group)
            expected.append(dict(group=label, cases=len(group), marking_rate=rate,
                                 regular_fraction=regular, trigger_fraction=1-regular))
    write_rows(args.out / "marking_sensitivity.csv", expected)
    ranges = {int(r["case"]): r for r in read_rows(base /
        "workloads/experiments/measurements/ranges_cases.csv")}
    controls = ("component", "recompute", "direct", "enumeration")
    small = []
    for c in cases:
        if c["family"] != "fresh_real" or c["scale"] != "small":
            continue
        idx = c["index"]
        times = {method: median(timings[idx, method])*1e6 for method in controls}
        winner = min(controls, key=times.get)
        small.append(dict(case=idx, dataset=c["dataset"], W=c["w"], L=c["n"], E=c["edges"],
                          Q=c["pair_updates"], control=winner, **{k+"_us": v for k,v in times.items()},
                          repeat_original_control=ranges[idx]["original_control"],
                          repeat_wide_control=ranges[idx]["wide_control"]))
    write_rows(args.out / "small_controls.csv", small)
    summary = []
    for dataset in ("cora", "ogbn_arxiv_20k"):
        g = [r for r in small if r["dataset"] == dataset]
        for label, subset in [("all", g), ("direct fastest", [r for r in g if r["control"]=="direct"]),
                              ("L <= 11", [r for r in g if r["L"] <= 11]),
                              ("L = 24", [r for r in g if r["L"] == 24])]:
            summary.append(dict(dataset=dataset, subset=label, cases=len(subset),
                                direct_minima=sum(r["control"]=="direct" for r in subset),
                                **{k+"_median": median(r[k] for r in subset) if subset else ""
                                   for k in ("W","L","E","Q","direct_us")}))
    write_rows(args.out / "small_summary.csv", summary)


if __name__ == "__main__":
    main()
