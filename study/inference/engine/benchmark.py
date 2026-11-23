"""Run the stratified PySDD comparison on Linux with a pinned core."""
import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TIME_LIMIT_S = 12
RSS_LIMIT_KIB = 768 * 1024


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_sdd(path, cpu):
    with tempfile.TemporaryFile(mode="w+t") as output, tempfile.TemporaryFile(mode="w+t") as errors:
        start = time.monotonic()
        proc = subprocess.Popen(["taskset", "-c", str(cpu), sys.executable, str(ROOT/"sdd_vector.py"),
                                 str(path)], stdout=output, stderr=errors)
        reason, peak = None, 0
        while proc.poll() is None:
            try:
                for line in Path(f"/proc/{proc.pid}/status").read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        peak = max(peak, int(line.split()[1]))
            except FileNotFoundError:
                pass
            if peak >= RSS_LIMIT_KIB:
                reason = "memory_limit"
            elif time.monotonic() - start >= TIME_LIMIT_S:
                reason = "time_limit"
            if reason:
                proc.kill()
                proc.wait()
                break
            time.sleep(.01)
        elapsed = time.monotonic() - start
        output.seek(0)
        errors.seek(0)
        events = [json.loads(line) for line in output if line.strip()]
        if not reason and (proc.returncode or not events or events[-1].get("phase") != "success"):
            raise RuntimeError("Engine failure: " + errors.read()[-1500:])
        return dict(status=reason or "ok", wall_s=elapsed, peak_sampled_kib=peak,
                    phases=events)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cases", type=Path, help="Archived cases.json with sibling inputs/ directory")
    p.add_argument("kernel", type=Path, help="Compiled k2 executable")
    p.add_argument("output", type=Path)
    p.add_argument("--cpu", type=int)
    args = p.parse_args()
    args.output.mkdir()
    cpu = min(os.sched_getaffinity(0)) if args.cpu is None else args.cpu
    cases = {}
    for item in sorted(json.loads(args.cases.read_text()), key=lambda row: row["index"]):
        if item["family"] == "fresh_real":
            cases.setdefault((item["seed"], item["dataset"], item["scale"]), item)
    assert len(cases) == 20
    cpu_name = next(line.split(":",1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name"))
    stamp = lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    meta = dict(start_utc=stamp(), cpu=cpu, cpu_name=cpu_name, python=platform.python_version(),
                pysdd=importlib.metadata.version("pysdd"), kernel_sha256=sha(args.kernel),
                script_sha256={n:sha(ROOT/n) for n in ("sdd_vector.py","benchmark.py")},
                case_index_sha256=sha(args.cases), time_limit_s=TIME_LIMIT_S,
                sampled_rss_limit_kib=RSS_LIMIT_KIB, rss_poll_s=.01,
                inputs=[v["index"] for v in cases.values()])
    with (args.output/"runs.jsonl").open("w") as out:
        for key, row in cases.items():
            path = args.cases.parent/"inputs"/row["input"]
            if sha(path) != row["sha256"]:
                raise ValueError("Serialized input hash mismatch")
            for rnd in range(1,4):
                order = ["sdd","sparse"]
                random.Random(f"sdd/{row['index']}/{rnd}").shuffle(order)
                record = dict(case=row["index"], seed=row["seed"], dataset=row["dataset"],
                              scale=row["scale"], L=row["n"], W=row["w"], E=row["edges"],
                              input_sha256=row["sha256"], round=rnd, order=order)
                for method in order:
                    if method == "sdd":
                        record["sdd"] = compare_sdd(path,cpu)
                    else:
                        result = subprocess.check_output(["taskset","-c",str(cpu),str(args.kernel),
                                                         str(path),"sparse","0.02"],text=True)
                        record["sparse"] = json.loads(result)
                if record["sdd"]["status"] == "ok":
                    v = record["sdd"]["phases"][-1]["values"]
                    ref = record["sparse"]["values"]
                    assert len(v) == len(ref) == row["n"]
                    record["max_abs_error"] = max((abs(x-y) for x,y in zip(v,ref)), default=0.)
                    if record["max_abs_error"] > 1e-10:
                        raise ValueError("SDD full vector outside absolute tolerance")
                print(json.dumps(record, allow_nan=False, separators=(",",":")),file=out,flush=True)
                print(row["index"], rnd, record["sdd"]["status"], flush=True)
                if record["sdd"]["status"] != "ok":
                    break
    meta["end_utc"] = stamp()
    (args.output/"environment.json").write_text(json.dumps(meta, indent=2)+"\n")


if __name__ == "__main__":
    main()

