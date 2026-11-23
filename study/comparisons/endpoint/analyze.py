"""Verify the timed records and regenerate the case ledger, summary and LaTeX table."""

import argparse
import csv
import gzip
import hashlib
import json
import math
import random
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import median

GROUPS = ("Small Cora", "Small OGB", "Larger OGB")
DOSES = (0, 1, 5, 20)
TOL = Decimal("1e-10")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text())


def verify(directory):
    digests = load(directory/"transfer.json")
    check(set(digests) == {"inputs.json", "environment.json", "timings.jsonl.gz"}, "Incomplete receipt")
    for name, expected in digests.items():
        actual = hashlib.sha256((directory/name).read_bytes()).hexdigest()
        check(actual == expected, f"Fingerprint mismatch: {name}")
    env = load(directory/"environment.json")
    inputs = {(x["case"],x["dose"]): x for x in load(directory/"inputs.json")}
    check(len(inputs) == 300, "Expected 300 case/rate pairs")
    check(env["rounds"] == 3 and env["budget_seconds"] == .02, "Timing protocol mismatch")
    cases = sorted({case for case, _ in inputs})
    check(len(cases) == 75, "Expected 75 cases")
    expected_order = {}
    for case in cases:
        for rnd in range(3):
            schedule = []
            for dose in DOSES:
                item = inputs[case,dose]
                methods = ["sparse", "recompute", "component", "direct"]
                if item["w"] <= 18:
                    methods.append("enumeration")
                check(item["methods"] == methods, "Incorrect envelope membership")
                schedule.extend((dose, method) for method in methods)
            random.Random(f"endpoint-envelope-r2/{case}/{rnd}").shuffle(schedule)
            for order,(dose,method) in enumerate(schedule):
                expected_order[case,dose,method,rnd] = order
    records = {}
    with gzip.open(directory/"timings.jsonl.gz","rt") as source:
        for line in source:
            row = json.loads(line)
            result = row["result"]
            case, dose, rnd, method = row["case"], row["dose"], row["round"], result["method"]
            key = case, dose, method, rnd
            check(key not in records and expected_order.get(key) == row["order"], f"Schedule mismatch: {key}")
            item = inputs[case,dose]
            t = float(result["seconds"])
            check(math.isfinite(t) and t > 0 and result["repeats"] >= 1 and
                  t * result["repeats"] >= .02*(1-1e-12), f"Timing budget mismatch: {key}")
            if method == "sparse":
                marked = item["marked"] > 0
                check(result["endpoint_fallback"] == marked and
                      result["fallback_reason"] == ("b_equals_one" if marked else ""), f"Dispatch mismatch: {key}")
            vector = tuple(map(Decimal, result["values"]))
            check(len(vector) == item["n"] and all(p.is_finite() and -TOL <= p <= 1 + TOL for p in vector)
                  and sum(vector) <= 2 + TOL, f"Invalid output: {key}")
            records[key] = t, vector
    check(records.keys() == expected_order.keys() and len(records) == env["records"] == 4284, "Missing records")
    return inputs, records


def analyze(directory, table):
    inputs, records = verify(directory)
    ledger = []
    for (case,dose), item in sorted(inputs.items()):
        medians = {}
        reference = records[case,dose,"direct",0][1]
        max_error = Decimal(0)
        for method in item["methods"]:
            times = []
            for rnd in range(3):
                timing, vector = records[case,dose,method,rnd]
                times.append(timing)
                check(vector == records[case,dose,method,0][1], "Nondeterministic kernel output")
                error = max(abs(x-y) for x,y in zip(vector,reference))
                max_error = max(max_error, error)
            medians[method] = median(times)
        check(max_error <= TOL, "Direct comparison tolerance exceeded")
        control = min((m for m in medians if m != "sparse"), key=medians.get)
        ratio = medians[control] / medians["sparse"]
        row = dict(case=case, dose=dose, group=item["group"], w=item["w"], n=item["n"],
                   edges=item["edges"], marked=item["marked"], triggered=int(item["marked"] > 0),
                   fastest_control=control, speedup=ratio, win=int(ratio>1),
                   max_abs_error=str(max_error))
        for method in ("sparse","recompute","component","direct","enumeration"):
            row[method+"_us"] = 1e6*medians[method] if method in medians else ""
        ledger.append(row)
    with (directory/"endpoint_cases.csv").open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(ledger[0]))
        writer.writeheader()
        writer.writerows(ledger)
    summary = []
    for group in GROUPS:
        for dose in DOSES:
            section = [r for r in ledger if (r["group"],r["dose"])==(group,dose)]
            check(len(section) == 25, "Unexpected stratum size")
            ratios = [r["speedup"] for r in section]
            summary.append(dict(group=group,dose=dose,n=len(section),triggered=sum(r["triggered"] for r in section),
                                eligible_enumeration=sum(r["enumeration_us"] != "" for r in section),
                                median_speedup=median(ratios),wins=sum(r["win"] for r in section),
                                minimum=min(ratios),maximum=max(ratios),
                                control_counts=dict(Counter(r["fastest_control"] for r in section))))
    outputs = dict(timed_invocations=len(records),case_rate_pairs=len(ledger),
                   method_counts=dict(Counter(key[2] for key in records)),
                   max_abs_error=str(max(Decimal(r["max_abs_error"]) for r in ledger)),strata=summary)
    (directory/"summary.json").write_text(json.dumps(outputs, indent=2)+"\n")
    if table:
        lines = [
            r"\begin{table}[htbp]", r"\centering",
            r"\caption{Paired kernel speedup against the full eligible exact-control envelope at each certain-edge marking probability. Each cell gives the median of 25 within-case ratios (strict wins/25). Each ratio uses the fastest control median divided by the sparse dispatcher median on the same matrix, with three timing rounds per method. Enumeration is eligible on all small cases and on seven larger OGB cases.}",
            r"\label{tab:endpoint-envelope}", r"\small", r"\begin{tabular}{lrrrr}", r"\toprule",
            r"Stratum & $p=0$ & $p=0.01$ & $p=0.05$ & $p=0.20$ \\", r"\midrule",
        ]
        for group in GROUPS:
            cells = [f"{x['median_speedup']:.4f} ({x['wins']}/25)" for x in summary if x["group"]==group]
            lines.append(" & ".join([group]+cells)+r" \\")
        lines += [r"\bottomrule",r"\end{tabular}",r"\end{table}"]
        table.write_text("\n".join(lines)+"\n")
    print(f"Verified {len(records)} invocations across {len(ledger)} case/rate pairs.")


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("--table",type=Path, help="Write the paper table to this file")
    args = parser.parse_args()
    analyze(args.directory, args.table)
