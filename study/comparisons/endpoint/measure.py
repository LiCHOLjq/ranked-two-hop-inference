"""Remeasure the paired certain-edge envelope using the archived matrices (Linux)."""

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

FROZEN = {
    "k2": "c853896321a0009998e5bbb36ca73608723be72688d453c6414182cadb15b8cf",
    "component": "e97e5a4c99c0cbb83c9b5cf372f158b29339128688667323c99188687201ea2f",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def prepare(archive, prior, staging):
    cases = {c["index"]: c for c in json.loads((prior/"case_manifest.json").read_text())
             if c["family"] == "fresh_real"}
    hashes = json.loads((prior/"generated_hashes.json").read_text())
    with (prior/"endpoint_cases.csv").open() as csv_file:
        archived = list(csv.DictReader(csv_file))
    variants = {}
    with tarfile.open(prior/"generated_inputs.tar.gz", "r:gz") as bundle:
        for row in archived:
            case_id, dose = int(row["case"]), int(row["dose"])
            case = cases[case_id]
            if dose == 0:
                path = archive/"results"/"inputs"/case["input"]
                expected = case["sha256"]
            else:
                name = f"{case_id}_dose{dose}.txt"
                path = staging/name
                path.write_bytes(bundle.extractfile("generated/" + name).read())
                expected = hashes[name]
            if sha(path) != expected:
                raise ValueError(f"Input fingerprint mismatch: {case_id}/{dose}")
            fields = path.read_text().split()
            w, n = map(int, fields[:2])
            b = list(map(float, fields[2+w:]))
            marked = sum(p == 1.0 for p in b)
            if ((w, n, len(b)) != (case["w"], case["n"], w*n)
                or marked != int(row["marked"]) or sum(p > 0 for p in b) != case["edges"]):
                raise ValueError(f"Input dimensions/support/marks mismatch: {case_id}/{dose}")
            methods = ["sparse", "recompute", "component", "direct"]
            if w <= 18:
                methods.append("enumeration")
            info = dict(case=case_id, group=row["group"], dose=dose, marked=marked,
                        w=w, n=n, edges=case["edges"], input=path.name, sha256=expected, methods=methods)
            if (case_id, dose) in variants:
                raise ValueError("Duplicate input")
            variants[case_id, dose] = (path, info)
    if set(variants) != {(i, d) for i in cases for d in (0, 1, 5, 20)} or len(cases) != 75:
        raise ValueError("Unexpected endpoint design")
    return variants


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path, help="Expansion root with k2, component and results/inputs/")
    p.add_argument("prior", type=Path, help="Frozen workloads/experiments/run_* directory")
    p.add_argument("out", type=Path, help="New evidence directory")
    p.add_argument("--cpu", type=int)
    p.add_argument("--k2-sha256", default=FROZEN["k2"])
    p.add_argument("--component-sha256", default=FROZEN["component"])
    args = p.parse_args()
    archive, prior, out = args.archive.resolve(), args.prior.resolve(), args.out.resolve()
    allowed = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {allowed[0] if args.cpu is None else args.cpu})
    binaries = {name: sha(archive/name) for name in FROZEN}
    if binaries != {"k2": args.k2_sha256, "component": args.component_sha256}:
        p.error("Executable fingerprints differ from the expected values")
    out.mkdir()
    meta = dict(start_utc=utc(), cpu_affinity=sorted(os.sched_getaffinity(0)), platform=platform.platform(),
                python=platform.python_version(), binaries=binaries, driver_sha256=sha(Path(__file__)),
                budget_seconds=0.02, rounds=3, lscpu=json.loads(subprocess.check_output(["lscpu","-J"])),
                prior={n: sha(prior/n) for n in ("case_manifest.json", "endpoint_cases.csv",
                                                  "generated_hashes.json", "generated_inputs.tar.gz")})
    dump(out/"environment.json", meta)
    count = 0
    with tempfile.TemporaryDirectory() as temp:
        variants = prepare(archive, prior, Path(temp))
        dump(out/"inputs.json", [info for _, info in variants.values()])
        with gzip.open(out/"timings.jsonl.gz", "wt", compresslevel=5) as timing:
            for i, case in enumerate(sorted({c for c, dose in variants}), 1):
                for rnd in range(3):
                    schedule = [(d, m) for d in (0, 1, 5, 20) for m in variants[case,d][1]["methods"]]
                    random.Random(f"endpoint-envelope-r2/{case}/{rnd}").shuffle(schedule)
                    for order, (dose, method) in enumerate(schedule):
                        path = variants[case,dose][0]
                        cmd = ([archive/"component", path] if method == "component" else
                               [archive/"k2", path, method])
                        payload = subprocess.check_output(cmd+["0.02"], text=True, timeout=300)
                        result = json.loads(payload, parse_float=str)
                        timing.write(json.dumps(dict(case=case, dose=dose, round=rnd, order=order,
                                                     result=result), separators=(",",":"))+"\n")
                        count += 1
                if i % 10 == 0:
                    print(f"Measured {i}/75 cases ({count} invocations)", flush=True)
    meta.update(end_utc=utc(), records=count)
    dump(out/"environment.json", meta)
    dump(out/"transfer.json", {n: sha(out/n) for n in ("environment.json","inputs.json","timings.jsonl.gz")})
    print(f"Completed {count} timed invocations", flush=True)


if __name__ == "__main__":
    main()
