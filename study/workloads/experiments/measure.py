"""Run on Linux with the archived expansion binaries and input directory."""
import argparse
import datetime as dt
import decimal
import gzip
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
from pathlib import Path

import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_matrix(path):
    with path.open() as source:
        w, n = map(int, source.readline().split())
        a = np.fromstring(source.readline(), sep=' ')
        b = np.fromstring(source.read(), sep=' ').reshape(w, n)
    return a, b


def write_matrix(path, a, b):
    with path.open('w') as stream:
        print(len(a), b.shape[1], file=stream)
        print(*a, file=stream)
        for row in b:
            print(*row, file=stream)


def eligible(case):
    methods = ['sparse', 'component', 'recompute']
    if case['family'] == 'fresh_real':
        methods += ['direct']
        if case['w'] <= 18:
            methods += ['enumeration']
    return methods


def invoke(archive, path, method, budget):
    if method == 'component':
        command = [archive/'component', path, str(budget)]
    else:
        command = [archive/'k2', path, method, str(budget)]
    output = subprocess.check_output(command, text=True, timeout=300)
    return json.loads(output, parse_float=str)


def emit(stream, data):
    stream.write(json.dumps(data, separators=(',', ':')) + '\n')


def time_block(stream, study, case, variants, methods, archive):
    for rnd in range(3):
        schedule = [(arm, m) for arm in variants for m in methods]
        random.Random(f"{study}/{case['index']}/{rnd}").shuffle(schedule)
        for order, (arm, m) in enumerate(schedule):
            path, info = variants[arm]
            record = invoke(archive, path, m, .02)
            emit(stream, dict(study=study, case=case['index'], arm=arm, round=rnd,
                              order=order, **info, result=record))


def decimal_inputs(path):
    D = decimal.Decimal
    with path.open() as stream:
        w, n = map(int, stream.readline().split())
        a = list(map(D, stream.readline().split()))
        support = []
        for _ in range(w):
            support.append([(i, D(v)) for i, v in enumerate(stream.readline().split())
                            if v not in ('0', '0.0') and D(v) != 0])
    return a, support, n


def signed_oracle(a, support, rank, precision):
    """Use forward/backward products to omit one factor without division."""
    with decimal.localcontext() as context:
        context.prec = precision
        one = decimal.Decimal(1)
        def negative_events(length):
            h = one
            deletions = [one] * (rank-1)
            for first, row in zip(a, support):
                present = [(i, one-b) for i, b in row if i < length]
                left = [one]
                for _, q in present:
                    left.append(left[-1] * q)
                common = one - first + first * left[-1]
                h *= common
                local = [common] * (rank-1)
                right = one
                for k in range(len(present)-1, -1, -1):
                    i, q = present[k]
                    if i < rank-1:
                        local[i] = one - first + first * left[k] * right
                    right *= q
                deletions = [x*y for x, y in zip(deletions, local)]
            return h, deletions
        before, del_before = negative_events(rank-1)
        after, del_after = negative_events(rank)
        return sum(x-y for x, y in zip(del_before, del_after)) - (rank-2)*(before-after)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('archive', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--cpu', type=int, default=10)
    args = ap.parse_args()
    archive, out = args.archive.resolve(), args.out.resolve()
    out.mkdir()
    generated = out/'generated'
    generated.mkdir()
    os.sched_setaffinity(0, {args.cpu})
    expected = {'k2':'c853896321a0009998e5bbb36ca73608723be72688d453c6414182cadb15b8cf',
                'component':'e97e5a4c99c0cbb83c9b5cf372f158b29339128688667323c99188687201ea2f'}
    actual = {k:digest(archive/k) for k in expected}
    assert actual == expected, actual
    meta = dict(start_utc=utc(), cpu_affinity=sorted(os.sched_getaffinity(0)),
                platform=platform.platform(), python=platform.python_version(), numpy=np.__version__,
                cpu=subprocess.check_output(['lscpu', '-J'], env=dict(os.environ, LC_ALL='C'), text=True),
                binaries=actual, driver_sha256=digest(Path(__file__)), budget_seconds=.02, rounds=3)
    dump(out/'environment.json', meta)
    cases = json.loads((archive/'results/cases.json').read_text())
    small = [c for c in cases if c['family']=='fresh_real' and c['scale']=='small']
    ogb = [c for c in cases if c['family']=='fresh_real' and c['scale']=='large'
           and c['dataset']=='ogbn_arxiv_20k']
    late = [c for c in cases if c['family']=='scaling' and c['n']>=1024]
    assert (len(small), len(ogb), len(late)) == (50, 25, 6)
    def original(c):
        path = archive/'results/inputs'/c['input']
        assert digest(path)==c['sha256']
        return path
    dump(out/'case_manifest.json', small + ogb + late)
    with gzip.open(out/'timings.jsonl.gz','wt') as timing, gzip.open(out/'endpoint_enumeration.jsonl.gz','wt') as enum:
        for c in ogb+[c for c in late if c['n']==2048]:
            time_block(timing, 'stage', c, {'original':(original(c),{})}, eligible(c), archive)
        print('stage complete', flush=True)
        for c in small:
            path = original(c)
            a, b = load_matrix(path)
            wide = generated/f"{c['index']}_wide.txt"
            b2 = b.copy()
            mask = b > 0
            b2[mask] = .1+.8*(b[mask]-.4)/.5
            write_matrix(wide, .1+.8*(a-.25)/.55, b2)
            time_block(timing, 'ranges', c, {'original':(path,{}),'wide':(wide,{})}, eligible(c), archive)
        print('ranges complete', flush=True)
        for c in small+ogb:
            path = original(c)
            a, b = load_matrix(path)
            support = np.flatnonzero(b)
            marks = np.random.Generator(np.random.PCG64(701900+c['index'])).random(len(support))
            variants = {'0':(path, {'marked':0})}
            for dose in (1,5,20):
                selected = support[marks < dose/100]
                modified = b.copy()
                modified.flat[selected] = 1.
                target = generated/f"{c['index']}_dose{dose}.txt"
                write_matrix(target, a, modified)
                variants[str(dose)] = (target, {'marked':len(selected)})
            time_block(timing, 'endpoint', c, variants, ['sparse'], archive)
            if c['scale']=='small':
                for arm, (target, _) in variants.items():
                    emit(enum,dict(case=c['index'],arm=arm,result=invoke(archive,target,'enumeration',0)))
        print('endpoint complete', flush=True)
    checks = []
    for c in late:
        path = original(c)
        a, support, n = decimal_inputs(path)
        full = {m:invoke(archive,path,m,0) for m in ('sparse','recompute','component')}
        archived = [json.loads((archive/'results/values'/f"{c['index']:03d}_r{r}_sparse.json").read_text(),
                               parse_float=str) for r in range(3)]
        for j in (n//2,3*n//4,n):
            low=signed_oracle(a,support,j,80)
            high=signed_oracle(a,support,j,120)
            checks.append(dict(case=c['index'],n=n,j=j,reference80=str(low),reference120=str(high),
                               kernels={m:str(v['values'][j-1]) for m,v in full.items()},
                               archived_sparse=[str(v[j-1]) for v in archived]))
        print(f"late case {c['index']} complete",flush=True)
    dump(out/'late_checks.json', checks)
    dump(out/'generated_hashes.json',{p.name:digest(p) for p in sorted(generated.iterdir())})
    meta['end_utc']=utc()
    dump(out/'environment.json',meta)


if __name__ == '__main__':
    main()
