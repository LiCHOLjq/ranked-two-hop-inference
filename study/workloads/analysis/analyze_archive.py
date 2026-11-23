"""Rebuild the study's structural and numerical tables from immutable inputs.

Run python workloads/analysis/analyze_archive.py from the study package.
Files are written beside this script. Only the Python standard library is needed.
"""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import correlation, linear_regression, median

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
EXP = ROOT / "experiments/graph_queries"
RECORDS = EXP / "results"
METHODS = ("sparse", "component", "recompute", "direct", "enumeration")
REAL_STRATA = ("Cora small", "OGB small", "Cora larger", "OGB larger", "Synthetic")


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def save(name, rows):
    with (OUT / (name + ".csv")).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def json_file(path):
    return json.loads(path.read_text(encoding="utf-8"))


def structure(case):
    data = (RECORDS / "inputs" / case["input"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == case["sha256"]
    header, first, *matrix = data.splitlines()
    w, n = map(int, header.split())
    assert len(first.split()) == w and len(matrix) == w
    degrees = [0] * n
    parents = list(range(n))
    pairs = 0
    support_hash = hashlib.sha256()

    def find(i):
        while i != parents[i]:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for row in matrix:
        support = bytes(float(x) > 0 for x in row.split())
        assert len(support) == n
        support_hash.update(support)
        terminals = [j for j, present in enumerate(support) if present]
        pairs += len(terminals) * (len(terminals) - 1) // 2
        for j in terminals:
            degrees[j] += 1
            parents[find(j)] = find(terminals[0])
    roots = [find(i) for i in range(n)]
    later = Counter()
    comp = inc = comp_predecessors = 0
    for i in reversed(range(n)):
        later_count = later[roots[i]]
        comp += later_count * degrees[i]
        comp_predecessors += later_count
        inc += (n - 1 - i) * degrees[i]
        later[roots[i]] += 1
    edges = sum(degrees)
    assert (n, w, edges, pairs, len(later)) == tuple(
        case[k] for k in ("n", "w", "edges", "pair_updates", "terminal_components")
    )
    assert pairs <= comp <= inc
    return dict(L=n, W=w, E=edges, Q=pairs, C=comp, I=inc, components=len(later),
                global_predecessor_visits=n*(n-1)//2, component_predecessor_visits=comp_predecessors,
                support_hash=support_hash.hexdigest(), U=w+n+edges+pairs)


def stratum(case):
    if "dataset" not in case:
        return case["family"]
    if case["dataset"] == "synthetic":
        return "Synthetic"
    dataset = {"cora": "Cora", "ogbn_arxiv_20k": "OGB"}[case["dataset"]]
    size = {"small": "small", "large": "larger"}[case["scale"]]
    return f"{dataset} {size}"


def time_metrics(times):
    controls = {k: v for k, v in times.items() if k != "sparse"}
    best = min(controls.values())
    winners = [k for k, t in controls.items() if t == best]
    assert len(winners) == 1, "Timing tie requires explicitly reporting joint attainment."
    return dict(winner=winners[0], speedup=best/times["sparse"],
                no_enum_speedup=min(t for k,t in controls.items() if k != "enumeration")/times["sparse"],
                matched_speedup=min(times["recompute"],times["component"])/times["sparse"],
                enum_eligible=int("enumeration" in times),
                **{m+"_us": times[m]*1e6 if m in times else "" for m in METHODS})


def confusion(rows):
    result = dict(cases=len(rows))
    for label in ("matched", "full"):
        for pred in ("sparse", "tie", "control"):
            for observed in ("win", "loss", "tie"):
                result[f"{label}_{pred}_{observed}"] = sum(
                    r["prediction"] == pred and r[label+"_outcome"] == observed for r in rows
                )
        result[label+"_binary_correct"] = sum(r[label+"_strict_correct"] for r in rows)
    return result


def classify(r):
    r["prediction"] = "sparse" if r["Q"] < min(r["C"], r["I"]) else "tie"
    for label, key in (("full","speedup"), ("matched","matched_speedup")):
        ratio = r[key]
        r[label+"_outcome"] = "win" if ratio > 1 else "loss" if ratio < 1 else "tie"
        r[label+"_strict_correct"] = (r["prediction"] == "sparse") == (ratio > 1)


def envelope_groups(archived, cases):
    summaries = []
    for family, rows in (("Archived", archived), ("Replay", cases), ("Fresh", cases)):
        for st in REAL_STRATA:
            subset = [r for r in rows if r["stratum"] == st and r["campaign"] == family]
            if not subset:
                continue
            wins = Counter(r["winner"] for r in subset)
            summaries.append(dict(campaign=family,stratum=st,cases=len(subset),
                enum_eligible=sum(r["enum_eligible"] for r in subset),
                **{m:wins[m] for m in METHODS[1:]},
                full_median=median(r["speedup"] for r in subset),
                no_enum_median=median(r["no_enum_speedup"] for r in subset),
                wins=sum(r["speedup"]>1 for r in subset),
                no_enum_wins=sum(r["no_enum_speedup"]>1 for r in subset)))
    return summaries


def grid_results(cases, timing):
    grid = []
    cells = defaultdict(list)
    for c in cases:
        if c["family"] == "probability":
            cells[(c["a"], c["b"])].append(c)
    for (a,b), group in sorted(cells.items()):
        errors = {}
        for method in METHODS[:3]:
            cell_errors = []
            for c in group:
                idx = c["index"]
                ref = json_file(RECORDS/"values"/f"{idx:03d}_reference.json")
                for raw in timing[idx,method]:
                    assert raw["reference"] == "full_direct"
                    path = RECORDS/"values"/f"{idx:03d}_r{raw['round']}_{method}.json"
                    values = json_file(path)
                    assert len(ref) == len(values) == c["L"]
                    error = max(abs(x-y) for x,y in zip(ref, values))
                    assert error == float(raw["max_abs_error"])
                    cell_errors.append(error)
            errors[method+"_maxerr"] = max(cell_errors)
        grid.append(dict(a=a,b=b,supports=len(group),**errors,
            speedup_median=median(c["speedup"] for c in group),
            sparse_us=median(c["sparse_us"] for c in group),
            control_us=median(min(c["component_us"],c["recompute_us"]) for c in group),
            incidence_us=median(c["recompute_us"] for c in group),
            component_us=median(c["component_us"] for c in group),
            incidence_winner=sum(c["winner"]=="recompute" for c in group)))
    return grid


def main():
    meta = json_file(RECORDS/"cases.json")
    rows = read_csv(RECORDS/"runs.csv")
    timing = defaultdict(list)
    for r in rows:
        assert r["passed"] == "True" and not r["fallback_reason"]
        timing[int(r["case"]),r["method"]].append(r)
    old = defaultdict(dict)
    archived_rows = read_csv(ROOT/"evidence/final_raw_runs.csv")
    for r in archived_rows:
        key = (int(r["seed"]),r["case"])
        assert r["method"] not in old[key]
        old[key][r["method"]] = float(r["seconds"])
    original_summary = {int(r["index"]): r for r in read_csv(EXP/"case_summary.csv")}
    old_summary = {(int(r["seed"]),r["case"]): r for r in read_csv(ROOT/"evidence/exact_control_cases.csv")}
    cases = []
    archived = []
    for c in meta:
        idx, family = c["index"], c["family"]
        campaign = {"replay":"Replay","fresh_real":"Fresh"}.get(family,"Sweep")
        methods = list(METHODS[:3])
        if campaign != "Sweep":
            methods += ["direct"] + (["enumeration"] if c["w"] <= 18 else [])
        times = {}
        for m in methods:
            items = timing[idx,m]
            assert sorted(int(r["round"]) for r in items) == list(range(5 if family=="replay" else 3))
            times[m] = median(float(r["seconds"]) for r in items)
        case = dict(index=idx, name=c["name"], family=family, campaign=campaign, stratum=stratum(c),
                    seed=c["seed"], sha256=c["sha256"], degree=c.get("degree",""),
                    blocks=c.get("imposed_components",""), a=c.get("a_value",""), b=c.get("b_value",""),
                    **structure(c), **time_metrics(times))
        assert float(original_summary[idx]["speedup"]) == case["speedup"]
        classify(case)
        case["ns_per_unit"] = 1000 * case["sparse_us"]/case["U"]
        cases.append(case)
        if family == "replay":
            old_key = (c["seed"],c["original_name"])
            assert set(old[old_key]) == set(times)
            historic = dict(index=idx,name=c["name"],campaign="Archived",stratum=case["stratum"],
                            **time_metrics(old[old_key]))
            assert float(old_summary[old_key]["speedup"]) == historic["speedup"]
            archived.append(historic)
    assert len(cases) == len(meta) == len(original_summary) == 325
    assert len(old) == len(archived) == 96 and len(rows) == 4715 and len(archived_rows) == 433
    for seed in (8101,8102,8103):
        supports = [c["support_hash"] for c in cases if c["seed"]==seed and c["family"]=="probability"]
        assert len(supports) == 25 and len(set(supports)) == 1
    save("structure_cases",cases)
    save("archive_envelopes", archived)
    groups = envelope_groups(archived,cases)
    save("envelope_summary", groups)
    assert len(groups) == 14
    counts = []
    for family in ("archived","replay","fresh_real","scaling","degree","components","probability"):
        source = archived_rows if family == "archived" else [r for r in rows if r["family"]==family]
        freq = Counter(r["method"] for r in source)
        counts.append(dict(family=family,**{m:freq[m] for m in METHODS},total=len(source)))
    save("method_counts",counts)
    strata = defaultdict(list)
    settings = defaultdict(list)
    for c in cases:
        strata[c["campaign"],c["stratum"]].append(c)
        if c["campaign"]=="Sweep":
            family = c["family"]
            key = {"scaling":(c["L"],),"degree":(c["degree"],),"components":(c["blocks"],),
                   "probability":(c["a"],c["b"])}[family]
            settings[family,key].append(c)
    conf = [dict(campaign=camp,stratum=st,**confusion(group)) for (camp,st),group in strata.items()]
    conf.append(dict(campaign="All",stratum="All",**confusion(cases)))
    save("proxy_confusion", conf)
    detailed = [dict(family=f,setting=",".join(map(str,k)),**confusion(g)) for (f,k),g in sorted(settings.items())]
    save("proxy_settings",detailed)
    save("proxy_disagreements",[c for c in cases if not (c["full_strict_correct"] and c["matched_strict_correct"])])
    save("proxy_abstentions",[c for c in cases if c["prediction"]=="tie"])
    work = []
    for (family,key), group in sorted(settings.items(),key=lambda kv:(kv[0][0]!="scaling",kv[0])):
        if family in ("scaling","degree"):
            work.append(dict(family=family,value=key[0],cases=len(group),
                median_Q=median(c["Q"] for c in group),median_U=median(c["U"] for c in group),
                sparse_us=median(c["sparse_us"] for c in group),ns_per_unit=median(c["ns_per_unit"] for c in group),
                min_ns=min(c["ns_per_unit"] for c in group),max_ns=max(c["ns_per_unit"] for c in group),
                Q_share=median(c["Q"]/c["U"] for c in group)))
    save("unit_costs", work)
    degree = [c for c in cases if c["family"]=="degree"]
    fractions = [c["Q"]/c["U"] for c in degree]
    costs = [c["ns_per_unit"] for c in degree]
    cost_fit = linear_regression(fractions,costs)
    grid = grid_results(cases,timing)
    save("probability_grid",grid)
    centre_contrasts = []
    by_support = defaultdict(list)
    for c in cases:
        if c["family"] == "probability":
            by_support[c["seed"],c["a"]].append(c)
    for (seed,a), group in sorted(by_support.items()):
        center, = [c for c in group if c["b"]==0.5]
        rest = [c for c in group if c["b"]!=0.5]
        assert len(rest)==4
        centre_contrasts.append(dict(seed=seed,a=a,**{
            key+"_ratio":center[key]/median(r[key] for r in rest)
            for key in ("sparse_us","recompute_us","speedup")}))
    save("probability_center_contrasts",centre_contrasts)
    flags = [a["index"] for a in archived if (a["speedup"]>1)!=(cases[a["index"]]["speedup"]>1)]
    partition_winners = {str(key[0]):dict(Counter(c["winner"] for c in group))
                         for (family,key),group in settings.items() if family=="components"}
    result = dict(verified_input_hashes=len(cases),distinct_serialized_inputs=len({c["sha256"] for c in cases}),
                  checked_paired_speedups=len(cases)+len(archived),probability_vectors_independently_compared=675,
                  recorded_timing_rows=len(rows),archived_timing_rows=len(archived_rows),
                  replay_flipped_case_indices=flags,confusion=conf[-1],partition_winners=partition_winners,
                  degree_descriptive_fit=dict(n=len(degree),intercept=cost_fit.intercept,
                      slope=cost_fit.slope,r_squared=correlation(fractions,costs)**2))
    (OUT/"archive_verification.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")


if __name__ == "__main__":
    main()
