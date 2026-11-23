"""Rebuild the control and endpoint analyses from the extracted replication archive.

Run with Python 3.10+ and the standard library. The optional output directory
defaults to this script's directory. No benchmark or network access is needed.
"""
import argparse
import csv
import gzip
import json
from collections import defaultdict
from math import comb, isclose
from pathlib import Path
from statistics import correlation, linear_regression, median


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
RECORDS = PROJECT / "experiments/graph_queries/results"
PRIOR = PROJECT / "workloads"
SAMPLING = PROJECT.parent / "historical/sampling"
ENDPOINT = PRIOR / "experiments/measurements"
RATES = (1, 5, 20)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def campaign():
    """Reassemble each eligible method's time from its own recorded rounds."""
    meta = read_json(RECORDS / "cases.json")
    structure = {int(row["index"]): row for row in read_csv(PRIOR / "analysis/structure_cases.csv")}
    runs = defaultdict(lambda: defaultdict(dict))
    for row in read_csv(RECORDS / "runs.csv"):
        idx, method, rnd = int(row["case"]), row["method"], int(row["round"])
        assert rnd not in runs[idx][method] and row["passed"] == "True"
        runs[idx][method][rnd] = float(row["seconds"])
    cases = []
    assert len(meta) == len(structure) == len(runs) == 325
    for case in meta:
        idx = case["index"]
        expected = {"sparse", "recompute", "component"}
        if case["family"] in {"replay", "fresh_real"}:
            expected.add("direct")
            if case["w"] <= 18:
                expected.add("enumeration")
        assert expected == set(runs[idx])
        rounds = range(5 if case["family"] == "replay" else 3)
        assert all(sorted(series) == list(rounds) for series in runs[idx].values())
        times = {method: median(series.values()) for method, series in runs[idx].items()}
        controls = {m: t for m, t in times.items() if m != "sparse"}
        counts = structure[idx]
        assert counts["sha256"] == case["sha256"]
        q, c, i, u = (int(counts[k]) for k in ("Q", "C", "I", "U"))
        assert q == case["pair_updates"] and q <= c <= i
        assert u == case["w"] + case["n"] + case["edges"] + q
        matched = min(times["recompute"], times["component"]) / times["sparse"]
        cases.append(dict(**case, times=times, strict=q < c, matched=matched,
                          full=min(controls.values()) / times["sparse"], share=q/u,
                          u=u, cost=times["sparse"]*1e9/u, stratum=counts["stratum"]))
    return cases


def rule_results(cases):
    results = []
    for target in ("matched", "full"):
        ties = [r for r in cases if not r["strict"]]
        strict = [r for r in cases if r["strict"]]
        correct_ties = sum(r[target] <= 1 for r in ties)
        correct_strict = sum(r[target] > 1 for r in strict)
        correct = correct_ties + correct_strict
        constant = sum(r[target] > 1 for r in cases)
        results.append(dict(target=target, cases=len(cases), correct_rule=correct,
                            correct_constant=constant, advantage_cases=correct-constant,
                            advantage_pp=100*(correct-constant)/len(cases),
                            ties=len(ties), ties_correct=correct_ties, strict=len(strict),
                            strict_correct=correct_strict))
    return results


def sign_results(cases):
    blocks = defaultdict(lambda: defaultdict(list))
    for case in cases:
        if case["family"] == "fresh_real":
            blocks[case["stratum"]][case["seed"]].append(case["full"])
    results = []
    for name, by_seed in sorted(blocks.items()):
        assert sorted(by_seed) == list(range(5205, 5210))
        assert all(len(v) == 5 for v in by_seed.values())
        values = [median(by_seed[seed]) for seed in sorted(by_seed)]
        n = sum(v != 1 for v in values)
        wins = sum(v > 1 for v in values)
        p = min(1, 2 * sum(comb(n, k) for k in range(min(wins, n-wins)+1)) / 2**n)
        results.append(dict(stratum=name, non_tied=n, positive=wins, raw_p=p,
                            **{f"seed_{s}": v for s, v in zip(sorted(by_seed), values)}))
    assert len(results) == 4
    running = 0
    for i, row in enumerate(sorted(results, key=lambda x: x["raw_p"])):
        running = max(running, min(1, (len(results)-i)*row["raw_p"]))
        row.update(holm_p=running, five_block_raw_floor=2/2**5,
                   four_stratum_holm_floor=min(1, len(results)*2/2**5))
    return results


def sampling_results():
    by_stratum = defaultdict(list)
    for seed in (5202, 5203, 5204):
        path = SAMPLING / f"seed_{seed}"
        by_case = defaultdict(list)
        for row in read_csv(path / "runs.csv"):
            by_case[row["case"]].append(row)
        for name, records in by_case.items():
            if not name.startswith(("cora_", "ogbn_arxiv_20k_")):
                continue
            graph = "Cora" if name.startswith("cora_") else "OGB20k"
            size = "larger" if "_large_" in name else "small"
            exact, = [r for r in records if r["method"] == "sparse"]
            draws = [r for r in records if r["method"] == "static_rb"]
            assert sorted(int(r["seed"]) for r in draws) == list(range(6301, 6306))
            idx = exact["case_index"]
            direct = read_json(path / f"values_{idx}_direct.json")
            errors = []
            for row in draws:
                values = read_json(path / f"values_{idx}_static_rb_{row['seed']}.json")
                assert len(values) == len(direct)
                error = max((abs(x-y) for x, y in zip(values, direct)), default=0.)
                assert isclose(error, float(row["max_error_vs_direct"]), abs_tol=1e-23)
                errors.append(error)
            rb = median(float(r["seconds"])*1e3 for r in draws)
            sparse = float(exact["seconds"])*1e3
            by_stratum[f"{graph} {size}"].append((rb, sparse, errors))
    results = []
    for name, group in sorted(by_stratum.items()):
        assert len(group) == 15
        rb = median(r[0] for r in group)
        sparse = median(r[1] for r in group)
        errors = [error for _, _, vector_errors in group for error in vector_errors]
        results.append(dict(stratum=name, cases=len(group), estimates=len(errors),
                            sparse_ms=sparse, rb_ms=rb, unrounded_ratio=rb/sparse,
                            printed_sparse_ms=f"{sparse:.5f}", printed_rb_ms=f"{rb:.3f}",
                            printed_ratio=float(f"{rb:.3f}")/float(f"{sparse:.5f}"),
                            median_case_ratio=median(b/s for b, s, _ in group),
                            median_case_error=median(median(e) for _, _, e in group),
                            within_tolerance=sum(e <= 1e-10 for e in errors)))
    return results


def grid_results(cases):
    by_support = defaultdict(dict)
    by_cell = defaultdict(list)
    for case in cases:
        if case["family"] != "probability":
            continue
        a, b, seed = case["a_value"], case["b_value"], case["seed"]
        ctrl = case["times"]["recompute"]*1e6
        assert case["times"]["recompute"] < case["times"]["component"]
        sparse = case["times"]["sparse"]*1e6
        metrics = dict(control_us=ctrl, sparse_us=sparse, speedup=case["full"])
        by_support[a, seed][b] = metrics
        by_cell[a, b].append((metrics["speedup"], seed))
    assert len(by_cell) == 25 and all(len(v) == 3 for v in by_cell.values())
    cell_medians = {k: sorted(v)[1] for k, v in by_cell.items()}
    min_cell = min(cell_medians, key=lambda k: cell_medians[k][0])
    results = []
    for (a, seed), cells in sorted(by_support.items()):
        assert len(cells) == 5
        row = dict(a=a, seed=seed)
        for key, center in cells[0.5].items():
            other = median(record[key] for b, record in cells.items() if b != 0.5)
            row.update({f"center_{key}": center, f"other_{key}": other,
                        f"{key}_ratio": center/other})
        row["supplies_center_cell_median"] = seed == cell_medians[a, 0.5][1]
        row["supplies_grid_minimum"] = (a, 0.5) == min_cell and row["supplies_center_cell_median"]
        results.append(row)
    return results


def degree_results(cases):
    degree = [r for r in cases if r["family"] == "degree"]
    shares = [r["share"] for r in degree]
    costs = [r["cost"] for r in degree]
    fit = linear_regression(shares, costs)
    by_degree = defaultdict(list)
    for row in degree:
        by_degree[row["degree"]].append(row)
    settings = sorted(by_degree)
    units = [median(r["u"] for r in by_degree[d]) for d in settings]
    fractions = [median(r["share"] for r in by_degree[d]) for d in settings]
    assert all(x < y for x, y in zip(units, units[1:]))
    assert all(x < y for x, y in zip(fractions, fractions[1:]))
    return [dict(cases=len(degree), degree_levels=len(settings), intercept=fit.intercept,
                 slope=fit.slope, r_squared=correlation(shares, costs)**2,
                 first_setting_median_U=units[0], last_setting_median_U=units[-1],
                 first_setting_median_Q_fraction=fractions[0], last_setting_median_Q_fraction=fractions[-1])]


def endpoint_results():
    """Cross-check the 300 archived case/arm medians against the underlying timings."""
    runs = defaultdict(dict)
    with gzip.open(ENDPOINT / "timings.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["study"] == "endpoint":
                key = row["case"], int(row["arm"])
                result = row["result"]
                assert result["method"] == "sparse" and row["round"] not in runs[key]
                assert result["endpoint_fallback"] == bool(row["marked"])
                runs[key][row["round"]] = (float(result["seconds"]), row["marked"])
    by_stratum = defaultdict(lambda: defaultdict(dict))
    for row in read_csv(ENDPOINT / "endpoint_cases.csv"):
        idx, rate = int(row["case"]), int(row["dose"])
        raw = runs.pop((idx, rate))
        assert sorted(raw) == [0, 1, 2]
        assert all(marked == int(row["marked"]) for _, marked in raw.values())
        us = median(t for t, _ in raw.values())*1e6
        assert isclose(us, float(row["time_us"]), rel_tol=1e-14)
        assert int(row["fallback"]) == int(int(row["marked"]) > 0)
        by_stratum[row["group"]][idx][rate] = (bool(int(row["fallback"])), us)
    assert not runs
    results = []
    for name, by_case in sorted(by_stratum.items()):
        assert len(by_case) == 25 and all(set(r) == {0, *RATES} for r in by_case.values())
        cohorts = [{i for i, cases in by_case.items() if cases[r][0]} for r in RATES]
        assert cohorts[0] <= cohorts[1] <= cohorts[2]
        common = sorted(set.intersection(*cohorts))
        for rate, triggered in zip(RATES, cohorts):
            ratios = {i: by_case[i][rate][1]/by_case[i][0][1] for i in triggered}
            results.append(dict(stratum=name, rate_pct=rate, stratum_n=len(by_case),
                                triggered_n=len(triggered), triggered_median=median(ratios.values()),
                                common_n=len(common), common_median=median(ratios[i] for i in common),
                                common_case_ids=" ".join(str(i) for i in common)))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=HERE)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    cases = campaign()
    tables = {"rule_accuracy": rule_results(cases), "sign_blocks": sign_results(cases),
              "sampling_ratios": sampling_results(), "grid_supports": grid_results(cases),
              "degree_fit": degree_results(cases), "endpoint_common": endpoint_results()}
    for name, rows in tables.items():
        write_csv(out / f"{name}.csv", rows)
        print(f"{name}.csv  {len(rows)} rows")


if __name__ == "__main__":
    main()
