"""Replay on Linux with locally rebuilt binaries and explicitly supplied hashes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

from analyze import summarize

FROZEN_DRIVER = '4c705380c58d172438094faa1f4ede149d06010a8cd95e05bf4a7d434ef7d55c'
ORIGINAL_BINARIES = {
    'k2': 'c853896321a0009998e5bbb36ca73608723be72688d453c6414182cadb15b8cf',
    'component': 'e97e5a4c99c0cbb83c9b5cf372f158b29339128688667323c99188687201ea2f'
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, help='Expansion root with binaries and results/')
    parser.add_argument('out', type=Path, help='Fresh directory')
    parser.add_argument('--cpu', type=int, default=None, help='Default: first CPU permitted to this process')
    parser.add_argument('--k2-sha256', required=True)
    parser.add_argument('--component-sha256', required=True)
    args = parser.parse_args()
    archive, out = args.archive.resolve(), args.out.resolve()
    hashes = {'k2': args.k2_sha256.lower(), 'component': args.component_sha256.lower()}
    if not hasattr(os, 'sched_getaffinity'):
        parser.error('Portable remeasurement requires Linux CPU affinity support.')
    allow = sorted(os.sched_getaffinity(0))
    cpu = allow[0] if args.cpu is None else args.cpu
    if cpu not in allow:
        parser.error(f'CPU {cpu} is outside the allowed affinity list {allow}')
    for name, expected in hashes.items():
        if not re.fullmatch('[0-9a-f]{64}', expected) or sha(archive/name) != expected:
            parser.error(f'Expected SHA-256 does not match local {name}')
    base = Path(__file__).with_name('measure.py')
    if sha(base) != FROZEN_DRIVER:
        parser.error('Published measurement source fingerprint does not match')
    # Adapt just the expected binary fingerprints in a separate copy. The
    # local source and the recorded study retain the original binary checks.
    code = base.read_bytes()
    for name, frozen in ORIGINAL_BINARIES.items():
        if code.count(frozen.encode()) != 1:
            parser.error(f'Cannot uniquely locate {name} fingerprint in the frozen driver')
        code = code.replace(frozen.encode(), hashes[name].encode(), 1)
    out.mkdir()
    driver = out/'measure_rebuild.py'
    driver.write_bytes(code)
    write_json(out/'replay_manifest.json', dict(original_driver=FROZEN_DRIVER,
               replay_driver=sha(driver),original_binaries=ORIGINAL_BINARIES,local_binaries=hashes,cpu=cpu))
    evidence = out/'evidence'
    env = dict(os.environ, LC_ALL='C', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    subprocess.run([sys.executable, str(driver),str(archive), str(evidence), '--cpu', str(cpu)],
                   check=True, env=env)
    with tarfile.open(evidence/'generated_inputs.tar.gz','w:gz') as target:
        target.add(evidence/'generated',arcname='generated')
    files=['environment.json','case_manifest.json','timings.jsonl.gz','late_checks.json',
           'endpoint_enumeration.jsonl.gz','generated_hashes.json','generated_inputs.tar.gz']
    write_json(evidence/'transfer.json',dict(origin='local portable replay',hashes={x:sha(evidence/x) for x in files}))
    summarize(evidence,archive)
    print('Verified portable replay at',evidence/'summary.json')


if __name__ == '__main__':
    main()
