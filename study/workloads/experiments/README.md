# Supplementary server measurements

The recorded run is `measurements`. It adds 348 stage-timing records, 1,500 fixed-query probability-range records and 900 certain-edge mixture records. The independent checks comprise 200 small mixture vectors against enumeration and 18 late ranks against an 80- and 120-digit decimal oracle. These counts are separate from the original campaign's 4,715 timing records. The four supplementary analyses reuse 81 unique original matrices. See [PROTOCOL.md](PROTOCOL.md) for the selection and timing rules set before execution.

## Replay the recorded analysis

Python 3 and NumPy are required. Set `EXP` to the directory that contains the archived expansion's `results/` directory. In a Bash shell, run the following from the directory containing this README.

```bash
python analyze.py measurements --archive "$EXP"
```

The analysis verifies the recorded binary-output and generated-input file hashes, checks all 275 transformed inputs against the frozen matrices, regenerates the probability maps and endpoint masks, checks vector ranges and total mass, compares the small-case vectors to their references, and verifies the decimal oracle against exact enumeration on two tiny graphs. It then regenerates the five case-level CSVs and `summary.json`. It also recovers stage timings directly from the original expansion CSV.

| Record | Contents |
| --- | --- |
| `timings.jsonl.gz` | Timed invocations, including within-round order, exact method, fallback reason when emitted, repeat count, loader and kernel clocks and full vector. C++ decimal output is preserved, with noninteger values stored as strings. |
| `endpoint_enumeration.jsonl.gz` | Independently enumerated reference vectors on every small case–rate pair. |
| `late_checks.json` | Raw oracle values at 80 and 120 digits, three kernels' printed values, and archived sparse entries from three rounds. |
| `case_manifest.json`, `generated_hashes.json`, `generated_inputs.tar.gz` | Source selection, provenance, and the actual 275 transformed matrices. Inputs shared across studies appear just once in the 81-case manifest. |
| `environment.json`, `transfer.json`, `run.log` | Environment, CPU affinity, original executable and driver fingerprints, evidence hashes, and completion record. |
| `stage_cases.csv`, `archived_stage_cases.csv`, `ranges_cases.csv`, `endpoint_cases.csv`, `late_cases.csv` | Case-level analysis values with case IDs indexing the manifest. |

## Repeat timings on another Linux machine

Use Python 3 with NumPy, `lscpu`, a C++17 compiler, and sufficient disk space for the dense inputs. The historical timing driver `measure.py` checks the two original executable fingerprints; the recorded checksums are in `environment.json`. For newly compiled executables, the adjacent `portable_replay.py` creates a separately fingerprinted copy of the historical driver with the two explicitly supplied binary checksums. It records both sets of hashes, verifies all outputs, and writes to a fresh destination.

The expansion root must contain `results/cases.json`, `results/runs.csv`, the 81 named original files in `results/inputs/`, and the 18 archived sparse output files in `results/values/` for cases 100, 101, 143, 144, 186 and 187 (rounds 0, 1 and 2, using three-digit case IDs). Point `SRC` at the directory containing the frozen `k2.cpp` and `component.cpp`. These commands assume Bash and GNU coreutils.

```bash
g++ -std=c++17 -O3 -march=native "$SRC/k2.cpp" -o "$EXP/k2"
g++ -std=c++17 -O3 -march=native "$SRC/component.cpp" -o "$EXP/component"
k2_hash=$(sha256sum "$EXP/k2" | cut -d' ' -f1)
component_hash=$(sha256sum "$EXP/component" | cut -d' ' -f1)
python portable_replay.py "$EXP" portable-run \
  --k2-sha256 "$k2_hash" --component-sha256 "$component_hash"
```

The command uses the first CPU permitted to the process. On the measurement server, the specified CPU was `--cpu 10`. The replay writes environmental fingerprints and results under `portable-run/`. Machine-specific timing differences are expected. The independent late-rank comparisons depend on the host's `long double` representation. Hosts where it has the same exponent range as binary64 may also underflow in the kernel itself.

## Findings and interpretation

- In the original campaign, adding the shared text loader gives median two-stage gains of 1.618× on larger OGB and 1.363× at length 2048. Both repeat measurements round to 1.376×. The large-scale post-acceleration loader share exceeds 99% in both runs.
- Widening the synthetic probabilities on the same 50 small queries kept every measured win/loss classification. The median within-case change in speedup was −0.00029 on Cora and +0.00102 on OGB.
- At a 1% per-edge certain-edge rate, all 25 larger OGB cases fell back to direct evaluation, with an 11.81× median paired cost. The same rate triggered 5 small Cora and 7 small OGB cases.
- The largest late-rank relative discrepancy against the 120-digit oracle was at most 2.04×10⁻¹⁷ in the rerun sparse kernel. The original binary64 serialization lost six positive values, one at each of two late ranks on each of the three largest inputs, in each of the three archived rounds.
