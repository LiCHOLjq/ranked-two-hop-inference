"""Repeat one bounded trial per selected input with automatic SDD transformations."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def derive(name, destination, substitutions):
    src = (ROOT/name).read_text()
    for before, after in substitutions:
        if src.count(before) != 1:
            raise ValueError(f"Primary protocol changed: {name}")
        src = src.replace(before,after)
    (destination/name).write_text(src, encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cpu", type=int)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        derive("sdd_vector.py",tmp,[("auto_gc_and_minimize=False","auto_gc_and_minimize=True")])
        derive("benchmark.py",tmp,[("range(1,4)","range(1,2)")])
        cmd = [sys.executable,str(tmp/"benchmark.py"),str(args.cases.resolve()),
               str(args.kernel.resolve()),str(args.output.resolve())]
        if args.cpu is not None:
            cmd.extend(["--cpu",str(args.cpu)])
        subprocess.run(cmd,check=True)


if __name__ == "__main__":
    main()

