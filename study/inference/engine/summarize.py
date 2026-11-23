"""Recompute the SDD comparison from the raw paired server timings."""
import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("root", type=Path)
parser.add_argument("--rounds", type=int, default=3)
args = parser.parse_args()
root = args.root
records = [json.loads(line) for line in (root/"runs.jsonl").read_text().splitlines()]
cases = defaultdict(list)
for r in records:
    cases[r["case"]].append(r)
by_case = []
for case, runs in sorted(cases.items()):
    r, last = runs[0], runs[-1]
    status = last["sdd"]["status"]
    row = dict(case=case, dataset=r["dataset"], scale=r["scale"], seed=r["seed"],
               W=r["W"], L=r["L"], E=r["E"], status=status, rounds=len(runs))
    if status == "ok":
        assert len(runs) == args.rounds and all(t["sdd"]["status"]=="ok" for t in runs)
        # Re-check each coordinate and the index alignment in each round.
        for t in runs:
            got, ref = t["sdd"]["phases"][-1]["values"], t["sparse"]["values"]
            assert len(got)==len(ref)==r["L"]
            assert max(abs(x-y) for x,y in zip(got,ref))==t["max_abs_error"]<=1e-10
        vals = [t["sdd"]["phases"][-1] for t in runs]
        row.update(sdd_setup_ms=1000*statistics.median(v["compile_s"]+v["weight_setup_s"] for v in vals),
                   sdd_evaluate_ms=1000*statistics.median(v["evaluate_s"] for v in vals),
                   sparse_us=1e6*statistics.median(t["sparse"]["seconds"] for t in runs),
                   sdd_parse_ms=1000*statistics.median(v["parse_s"] for v in vals),
                   sparse_parse_ms=1000*statistics.median(t["sparse"]["setup_seconds"] for t in runs),
                   max_abs_error=max(t["max_abs_error"] for t in runs))
    else:
        assert status in {"time_limit","memory_limit"}
    by_case.append(row)
fields=list(dict.fromkeys(k for row in by_case for k in row))
with (root/"case_summary.csv").open("w",newline="") as out:
    writer=csv.DictWriter(out,fields)
    writer.writeheader()
    writer.writerows(by_case)
strata = []
for scale in ("small","large"):
    for dataset in ("cora","ogbn_arxiv_20k"):
        rows=[r for r in by_case if (r["scale"],r["dataset"])==(scale,dataset)]
        if not rows:
            continue
        ok=[r for r in rows if r["status"]=="ok"]
        group=dict(scale=scale,dataset=dataset,total=len(rows),completed=len(ok),
                   exit_counts=dict(Counter(r["status"] for r in rows)))
        if ok:
            for col in ("sdd_setup_ms","sdd_evaluate_ms","sparse_us","sdd_parse_ms","sparse_parse_ms"):
                group[col]=statistics.median(r[col] for r in ok)
            group["max_abs_error"]=max(r["max_abs_error"] for r in ok)
            group["coordinates"]=sum(r["L"] for r in ok)
        strata.append(group)
assert sum(s["total"] for s in strata)==len(cases)==20
(root/"summary.json").write_text(json.dumps(strata,indent=2)+"\n")

