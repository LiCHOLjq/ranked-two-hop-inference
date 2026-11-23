"""Verify the release hashes, then rebuild numerical outputs in a disposable copy."""
import argparse
import csv
from decimal import Decimal
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


WORKLOADS = Path("study/workloads")
COMPARISONS = Path("study/comparisons")
EXPANSION = Path("study/experiments/graph_queries")
RUN = WORKLOADS / "experiments/measurements"
ARCHIVE_TABLES = (
    "archive_envelopes.csv", "archive_verification.json", "envelope_summary.csv",
    "method_counts.csv", "probability_center_contrasts.csv", "probability_grid.csv",
    "proxy_abstentions.csv", "proxy_confusion.csv", "proxy_disagreements.csv",
    "proxy_settings.csv", "structure_cases.csv", "unit_costs.csv",
)
SAMPLING_TABLES = ("sampling_and_seeds.json", "sampling_cases.csv", "sampling_observations.csv")
FOLLOWUP_TABLES = (
    "stage_cases.csv", "archived_stage_cases.csv", "ranges_cases.csv", "endpoint_cases.csv",
    "late_cases.csv", "summary.json",
)
CONTROL_TABLES = ("rule_accuracy.csv", "sign_blocks.csv", "sampling_ratios.csv", "grid_supports.csv",
                 "degree_fit.csv", "endpoint_common.csv")


def analyses():
    analysis = WORKLOADS / "analysis"
    audit = COMPARISONS / "analysis"
    endpoint = COMPARISONS / "endpoint"
    support = Path("study/inference/diagnostics")
    engine = Path("study/inference/engine")
    primary = engine / "evidence"
    automatic = primary / "automatic"
    return [
        ([support / "analyze_supports.py", "."], [support / f for f in
            ("marking_sensitivity.csv", "small_controls.csv", "small_summary.csv")]),
        ([engine / "summarize.py", primary], [primary / f for f in ("summary.json", "case_summary.csv")]),
        ([engine / "summarize.py", automatic, "--rounds", "1"],
            [automatic / f for f in ("summary.json", "case_summary.csv")]),
        ([analysis / "analyze_archive.py"], [analysis / f for f in ARCHIVE_TABLES]),
        ([analysis / "sampling_and_seeds.py"], [analysis / f for f in SAMPLING_TABLES]),
        ([WORKLOADS / "experiments/analyze.py", RUN, "--archive", EXPANSION], [RUN / f for f in FOLLOWUP_TABLES]),
        ([audit / "audit_controls.py"], [audit / f for f in CONTROL_TABLES]),
        ([endpoint / "analyze.py", endpoint / "evidence", "--table", endpoint / "endpoint_table.tex"],
         [endpoint / "evidence/summary.json", endpoint / "evidence/endpoint_cases.csv", endpoint / "endpoint_table.tex"]),
    ]


def safe_name(name):
    path = PurePosixPath(name)
    if path.as_posix() != name or path.is_absolute() or any(c in name for c in (":", "\\")) or ".." in path.parts:
        raise ValueError(f"Invalid manifest path {name}")
    return name


def stage(source, destination):
    """Copy exactly the listed payload to the fresh directory, checking each byte."""
    completed = set()
    manifest = (source / "MANIFEST.sha256").read_text(encoding="utf-8")
    for line in manifest.splitlines():
        expected, name = line.split("  ", 1)
        safe_name(name)
        if name in completed or name == "MANIFEST.sha256":
            raise ValueError(f"Duplicate or self-referencing member {name}")
        data = (source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"SHA-256 mismatch for {name}")
        out = destination / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        completed.add(name)
    with ZipFile(destination / "data/workloads.zip") as archive:
        for entry in archive.infolist():
            name = safe_name(entry.filename)
            if name in completed:
                raise ValueError(f"Conflicting workload entry {name}")
            out = destination / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(archive.read(entry))
            completed.add(name)
    return len(completed)


def parsed(path, data):
    text = data.decode("utf-8-sig")
    if path.suffix == ".json":
        return json.loads(text, parse_float=Decimal)
    if path.suffix == ".csv":
        return list(csv.reader(io.StringIO(text, newline="")))
    return text.splitlines()


def crosscheck_endpoint(root):
    endpoint = root / COMPARISONS / "endpoint"
    evidence = endpoint / "evidence"
    prior = root / RUN
    environment = json.loads((evidence / "environment.json").read_bytes())
    driver = endpoint / "measure.py"
    # Distribution changes only argparse help for the endpoint driver's "prior" argument.
    original_driver = "1d5b20e1e2ad6c8b96df9da9f89b53bedd6d04b698b3e9a16d0e7f5bdc880a43"
    packaged_driver = "3623550906ceb44274cae89f33889648919f5bfd5df9c91cd420405784ca6ca0"
    if environment["driver_sha256"] != original_driver:
        raise ValueError("Unexpected recorded timing-driver fingerprint")
    if hashlib.sha256(driver.read_bytes()).hexdigest() != packaged_driver:
        raise ValueError("Unexpected distributed timing-driver fingerprint")
    binaries = {}
    for line in (root / EXPANSION / "binary_hashes.txt").read_text().splitlines():
        checksum, name = line.split()
        binaries[PurePosixPath(name).name] = checksum
    if environment["binaries"] != binaries:
        raise ValueError("Timed executable fingerprints differ across campaigns")
    previous = {name: hashlib.sha256((prior / name).read_bytes()).hexdigest() for name in
                ("case_manifest.json", "endpoint_cases.csv", "generated_hashes.json", "generated_inputs.tar.gz")}
    if previous != environment["prior"]:
        raise ValueError("The predecessor evidence differs from the timed campaign's inputs")
    with TemporaryDirectory(dir=root) as staging:
        variants = runpy.run_path(str(driver))["prepare"](root / EXPANSION, prior, Path(staging))
    inputs = [description for _, description in variants.values()]
    if inputs != json.loads((evidence / "inputs.json").read_bytes()):
        raise ValueError("The measured treatments differ from the archived matrices")

    def vectors(path, method):
        result = {}
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["result"]["method"] == method and row.get("round", 0) == 0 and row.get("study", "endpoint") == "endpoint":
                    dose = row["dose"] if "dose" in row else int(row["arm"])
                    result[row["case"], dose] = tuple(map(Decimal, row["result"]["values"]))
        return result

    expected = {"sparse": 300, "enumeration": 200}
    for method, source in (("sparse", "timings.jsonl.gz"), ("enumeration", "endpoint_enumeration.jsonl.gz")):
        old = vectors(prior / source, method)
        current = vectors(evidence / "timings.jsonl.gz", method)
        if len(old) != expected[method] or any(current.get(key) != values for key, values in old.items()):
            raise ValueError(f"The {method} vectors disagree across campaigns")
    return {"matrix_hashes_and_metadata": len(inputs), "predecessor_file_hashes": len(previous),
            "binary_fingerprints": len(binaries), "recorded_and_distributed_driver_hashes_checked": True, "matching_vectors": expected}


def rebuild(root, command, products):
    """Remove each published output from scratch space before reconstructing it."""
    contents = {}
    for relative in products:
        path = root / relative
        contents[relative] = parsed(path, path.read_bytes())
        path.unlink()
    process = subprocess.run([sys.executable, "-E", "-B", "-X", "utf8", *command], cwd=root,
                             capture_output=True, text=True, encoding="utf-8")
    if process.returncode:
        raise RuntimeError(f"Failed to run {command[0]}\n{process.stdout}\n{process.stderr}")
    for relative, expected in contents.items():
        path = root / relative
        if parsed(path, path.read_bytes()) != expected:
            raise ValueError(f"Recomputed values differ in {relative.as_posix()}")
    return {"script": command[0].as_posix(), "matching_outputs": [p.as_posix() for p in products]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=Path(__file__).resolve().parent,
                        help="Repository root (default: script directory)")
    parser.add_argument("--report", type=Path, help="Write the verification result as JSON")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="ranked-query-replication-") as scratch:
        root = Path(scratch)
        count = stage(args.source.resolve(), root)
        provenance = crosscheck_endpoint(root)
        checks = [rebuild(root, command, outputs) for command, outputs in analyses()]
        theory = Path("study/inference/theory")
        expected = json.loads((root / theory / "server_summary.json").read_bytes())
        actual = json.loads(subprocess.check_output([sys.executable, "-B", theory / "verify_cutoffs.py"], cwd=root))
        for result in (expected, actual):
            result.pop("python")
        if actual != expected:
            raise ValueError("Independent rational enumeration disagrees with the server record")
    import numpy
    report = {"verified_release_and_workload_files": count, "reconstructed_outputs": sum(len(c["matching_outputs"]) for c in checks),
              "python": sys.version.split()[0], "numpy": numpy.__version__,
              "rational_world_checks": actual, "certain_edge_crosschecks": provenance, "analyses": checks}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {count} release and workload files and reproduced {report['reconstructed_outputs']} outputs.")


if __name__ == "__main__":
    main()
