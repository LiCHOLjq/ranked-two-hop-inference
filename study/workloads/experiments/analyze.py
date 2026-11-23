"""Verify the retrieved supplement and summarize case-level paired measurements."""
import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal as D
import gzip
import hashlib
from itertools import product
import json
from pathlib import Path
from statistics import median
import tarfile
import numpy as np

from measure import signed_oracle


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csvfile(path, rows):
    with path.open('w',newline='') as out:
        writer=csv.DictWriter(out,list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def records(path):
    with gzip.open(path,'rt') as stream:
        yield from map(json.loads,stream)


def validate_oracle():
    """Enumerate independent edge worlds for small multi-witness fixtures."""
    inputs=[([D('.5')], [[(j,D('.5')) for j in range(3)]]),
            ([D('.2'),D('.8')], [[(0,D('.3')),(1,D('1'))],[(1,D('.25')),(2,D('.5'))]])]
    for a,support in inputs:
        edges=[(w,j,p) for w,row in enumerate(support) for j,p in row]
        rates=list(a)+[p for w,j,p in edges]
        truth=[D(0)]*3
        for state in product((0,1),repeat=len(rates)):
            mass=D(1)
            for bit,rate in zip(state,rates):
                mass*=rate if bit else 1-rate
            chosen=sorted({j for k,(w,j,p) in enumerate(edges)
                           if state[w] and state[len(a)+k]})
            for j in chosen[:2]:
                truth[j]+=mass
        for j in range(3):
            assert signed_oracle(a,support,j+1,120)==truth[j]


def verify_inputs(bundle_path, cases, archive):
    """Compare generated treatments with frozen bytes and regenerate every mask."""
    lookup={c['index']:c for c in cases}
    originals={}
    for idx,c in lookup.items():
        source=archive/'results/inputs'/c['input']
        assert digest(source)==c['sha256']
        w,n=c['w'],c['n']
        v=np.fromstring(source.read_text(),sep=' ')
        assert list(v[:2])==[w,n]
        originals[idx]=(v[2:2+w],v[2+w:].reshape(w,n))
    with tarfile.open(bundle_path) as bundle:
        for item in bundle.getmembers():
            if not item.isfile():
                continue
            code,arm=Path(item.name).stem.split('_')
            idx=int(code)
            a,b=originals[idx]
            v=np.fromstring(bundle.extractfile(item).read().decode(),sep=' ')
            assert tuple(v[:2].astype(int))==b.shape
            a2,b2=v[2:2+len(a)],v[2+len(a):].reshape(b.shape)
            assert np.array_equal(b2>0,b>0)
            if arm=='wide':
                assert np.array_equal(a2,.1+.8*(a-.25)/.55)
                assert np.array_equal(b2[b>0],.1+.8*(b[b>0]-.4)/.5)
            else:
                active=np.flatnonzero(b)
                rng=np.random.Generator(np.random.PCG64(701900+idx))
                marked=active[rng.random(len(active))<int(arm[4:])/100]
                expect=b.copy()
                expect.flat[marked]=1.
                assert np.array_equal(a,a2) and np.array_equal(expect,b2)


def archived_stages(archive, selected):
    timings=defaultdict(lambda:defaultdict(list))
    with (archive/'results/runs.csv').open() as source:
        for r in csv.DictReader(source):
            idx=int(r['case'])
            if idx not in selected:
                continue
            timings[idx][r['method']].append(float(r['seconds']))
            if r['method']=='sparse':
                timings[idx]['load'].append(float(r['setup_seconds']))
    result=[]
    for i,values in timings.items():
        assert all(len(x)==3 for x in values.values())
        d=median(values.pop('load'))
        sp=median(values.pop('sparse'))
        base,m=min((median(v),m) for m,v in values.items())
        result.append(dict(case=i,group=selected[i],load_ms=d*1e3,sparse_ms=sp*1e3,
                           baseline_ms=base*1e3,baseline=m,f=base/(base+d),
                           sparse_load_fraction=d/(sp+d),s=base/sp,paired_total=(d+base)/(d+sp)))
    assert len(result)==28
    return result


def summarize(path,archive):
    validate_oracle()
    for name, expected in json.loads((path/'transfer.json').read_text())['hashes'].items():
        assert digest(path/name)==expected
    gen=json.loads((path/'generated_hashes.json').read_text())
    with tarfile.open(path/'generated_inputs.tar.gz') as bundle:
        got={Path(f.name).name:hashlib.sha256(bundle.extractfile(f).read()).hexdigest()
             for f in bundle.getmembers() if f.isfile()}
    assert got==gen and len(got)==275
    cases={c['index']:c for c in json.loads((path/'case_manifest.json').read_text())}
    verify_inputs(path/'generated_inputs.tar.gz',cases.values(),archive)
    raw=list(records(path/'timings.jsonl.gz'))
    lookup=defaultdict(list)
    study_count=Counter()
    for r in raw:
        result=r['result']
        idx=r['case']
        key=(r['study'],idx,r['arm'],result['method'])
        lookup[key].append(r)
        study_count[r['study']]+=1
        values=[D(x) for x in result['values']]
        assert len(values)==cases[idx]['n'] and all(x.is_finite() for x in values)
        assert min(values)>=D('-1e-10') and max(values)<=1+D('1e-10') and sum(values)<=2+D('1e-10')
        assert float(result['setup_seconds'])>0 and float(result['seconds'])>0
    for group in lookup.values():
        assert sorted(r['round'] for r in group)==[0,1,2]
    assert study_count['ranges']==1500 and study_count['endpoint']==900
    def med(study,idx,arm,method,metric='seconds'):
        return median(float(r['result'][metric]) for r in lookup[study,idx,arm,method])
    def winning(study,idx,arm):
        controls=[(med(study,idx,arm,m),m) for s,i,a,m in lookup
                  if (s,i,a)==(study,idx,arm) and m!='sparse']
        return min(controls)
    def gap(ref,values):
        return max(abs(D(x)-D(y)) for x,y in zip(ref,values))
    stages=[]
    ranges=[]
    endpoints=[]
    late=[]
    enums={(r['case'],r['arm']):r['result']['values'] for r in records(path/'endpoint_enumeration.jsonl.gz')}
    assert len(enums)==200
    for idx,c in cases.items():
        key=lambda s,a,m:(s,idx,a,m)
        if key('stage','original','sparse') in lookup:
            d=med('stage',idx,'original','sparse','setup_seconds')
            sp=med('stage',idx,'original','sparse')
            baseline,m=winning('stage',idx,'original')
            ref_method='recompute' if c['family']=='scaling' else 'direct'
            ref=lookup[key('stage','original',ref_method)][0]['result']['values']
            stage_error=max(gap(ref,r['result']['values']) for (s,i,a,m),rs in lookup.items()
                            if (s,i)==('stage',idx) for r in rs)
            assert stage_error<=D('1e-10')
            stages.append(dict(case=idx,group='Scale 2048' if c['family']=='scaling' else 'Larger OGB',
                               load_ms=d*1e3,sparse_ms=sp*1e3,baseline_ms=baseline*1e3,baseline=m,
                               f=baseline/(baseline+d),sparse_load_fraction=d/(sp+d),s=baseline/sp,
                               paired_total=(d+baseline)/(d+sp),reference=ref_method,max_abs_error=str(stage_error)))
        if key('ranges','original','sparse') in lookup:
            row=dict(case=idx,group='Cora' if c['dataset']=='cora' else 'OGB')
            for arm in ('original','wide'):
                baseline,m=winning('ranges',idx,arm)
                row[arm]=baseline/med('ranges',idx,arm,'sparse')
                row[arm+'_control']=m
                ref=lookup[key('ranges',arm,'direct')][0]['result']['values']
                err=max(gap(ref,r['result']['values']) for (s,i,a,m),rs in lookup.items()
                        if (s,i,a)==('ranges',idx,arm) for r in rs)
                assert err<=D('1e-10')
                row[arm+'_max_error']=str(err)
            row['paired_change']=row['wide']-row['original']
            row['paired_factor']=row['wide']/row['original']
            ranges.append(row)
        if key('endpoint','0','sparse') in lookup:
            for arm in ('0','1','5','20'):
                group=lookup[key('endpoint',arm,'sparse')]
                marked={r['marked'] for r in group}
                assert len(marked)==1
                marked=marked.pop()
                reason='b_equals_one' if marked else ''
                assert all(r['result']['fallback_reason']==reason and
                           r['result']['endpoint_fallback']==bool(marked) for r in group)
                sp=med('endpoint',idx,arm,'sparse')
                err=None
                if (idx,arm) in enums:
                    err=max(gap(enums[idx,arm],r['result']['values']) for r in group)
                    assert err<=D('1e-10')
                endpoints.append(dict(case=idx,group=('Small '+('Cora' if c['dataset']=='cora' else 'OGB')
                         if c['scale']=='small' else 'Larger OGB'),dose=int(arm),marked=marked,edges=c['edges'],
                         fallback=int(bool(marked)),time_us=sp*1e6,penalty=sp/med('endpoint',idx,'0','sparse'),
                         enum_error='' if err is None else str(err)))
    for row in json.loads((path/'late_checks.json').read_text()):
        ref=D(row['reference120'])
        assert ref>0
        assert abs(D(row['reference80'])-ref)/ref<D('1e-70')
        for m,x in dict(**row['kernels'],**{'archived_sparse_'+str(i):y for i,y in
                                             enumerate(row['archived_sparse'])}).items():
            delta=abs(ref-D(x))
            late.append(dict(case=row['case'],L=row['n'],j=row['j'],method=m,ref=str(ref),
                             observed=x,absolute=str(delta),relative=str(delta/ref),
                             precision_rel_gap=str(abs(D(row['reference80'])-ref)/ref)))
            assert delta<=D('1e-10')
    assert (len(stages),len(ranges),len(endpoints),len(late))==(28,50,300,108)
    historical=archived_stages(archive,{r['case']:r['group'] for r in stages})
    for name,data in [('stage',stages),('ranges',ranges),('endpoint',endpoints),('late',late)]:
        csvfile(path/(name+'_cases.csv'),data)
    csvfile(path/'archived_stage_cases.csv',historical)
    def groupmed(rows,group,fields):
        keys=sorted(set(r[group] for r in rows))
        return {k:{f:median(r[f] for r in rows if r[group]==k) for f in fields} for k in keys}
    stage=groupmed(stages,'group',['load_ms','sparse_ms','baseline_ms','f','sparse_load_fraction','s','paired_total'])
    archived=groupmed(historical,'group',list(stage['Larger OGB']))
    ran=groupmed(ranges,'group',['original','wide','paired_change','paired_factor'])
    for k in ran:
        sub=[r for r in ranges if r['group']==k]
        ran[k]['changed_win_status']=sum((r['original']>1)!=(r['wide']>1) for r in sub)
        for arm in ('original','wide'):
            ran[k][arm+'_wins']=sum(r[arm]>1 for r in sub)
            ran[k][arm+'_maximum_error']=str(max(D(r[arm+'_max_error']) for r in sub))
    endpoint={}
    for k in sorted(set(r['group'] for r in endpoints)):
        endpoint[k]={}
        for dose in [0,1,5,20]:
            subset=[r for r in endpoints if r['group']==k and r['dose']==dose]
            triggered=[r for r in subset if r['fallback']]
            endpoint[k][dose]=dict(n=len(subset),triggers=len(triggered),time_us=median(r['time_us'] for r in subset),
                     penalty=median(r['penalty'] for r in subset),conditional_penalty=
                     median(r['penalty'] for r in triggered) if triggered else None,
                     max_enum_error=max((D(r['enum_error']) for r in subset if r['enum_error']),default=None))
    late_summary={}
    for m in ['sparse','component','recompute','archived_sparse_0']:
        sel=[r for r in late if r['method']==m]
        late_summary[m]=dict(max_abs=max(D(r['absolute']) for r in sel),max_rel=max(D(r['relative']) for r in sel))
    archive_zeros=sum(D(r['observed'])==0 for r in late if r['method']=='archived_sparse_0')
    report=dict(timing_rows=dict(study_count),stage=stage,archived_stage=archived,
                ranges=ran,endpoint=endpoint,late=late_summary,archived_zero_coordinates=archive_zeros,
                min_ref=min(D(r['ref']) for r in late),max_ref=max(D(r['ref']) for r in late),
                precision_max_rel=max(D(r['precision_rel_gap']) for r in late),verified=True)
    (path/'summary.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--archive',type=Path,default=Path(__file__).resolve().parents[2]/'experiments/graph_queries')
    args=parser.parse_args()
    print(json.dumps(summarize(args.run,args.archive),indent=2,default=str))
