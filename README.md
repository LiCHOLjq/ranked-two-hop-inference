# Pair-Local Exact Top-Two Inference for Uncertain Two-Hop Graph Filters

This repository accompanies the paper by Jiaquan Li, Ji Li, Yijie Zhang, Guanning Li, Junxiao Li and Chuanwen Li. It contains the C++17 kernels, the serialized query matrices used in the experiments, the recorded method outputs and the Python analyses that generate the numerical comparisons.

## Additional experiments and mathematical checks

The experiments include an external exact-inference comparison on 20 matched graph queries. The release contains paired timings and full vectors, the fixed-vtree and automatic-minimization runs, the resource limits and all retained stop records. The original workload index and matrices are reused. [PySDD comparison and reproduction commands](study/inference/engine/README.md)

The support analysis recomputes the expected fraction of matrices free of certain edges at each marking rate and identifies the query sizes on which direct evaluation attains the control minimum. [Support analysis and case-level data](study/inference/diagnostics/README.md)

Run the following standard-library command to enumerate small edge worlds and verify the cutoff identities for cuts one through four and the three-hop counterexample. The output counters and exact fractions can be compared with the [server result](study/inference/theory/server_summary.json).

~~~sh
python study/inference/theory/verify_cutoffs.py
~~~

## Reproduce the results

Run these commands from the repository root with Python 3.11 or newer. NumPy 2.4.0 was used to verify the archived results with Python 3.11.14.

```sh
python -m pip install numpy==2.4.0
python verify_replication.py --report report.json
```

The verifier checks the release files against `MANIFEST.sha256`, expands the workloads in a temporary directory and regenerates 37 published analysis outputs from the staged copy, including the external-engine outcomes and structural diagnostics. It compares every CSV field, JSON value and LaTeX table line with the recorded results. For the certain-edge experiment it also checks all 300 input fingerprints, the measured driver and binary fingerprints, and 300 sparse plus 200 enumeration vectors shared between campaigns. Expect the final line to end with `reproduced 37 outputs.` The report lists each regenerated file.

## Code and evidence

| Question | Files |
|---|---|
| How are the top-two probabilities computed? | [Pair-local, direct, incidence-only and enumeration kernels](study/experiments/graph_queries/source/k2.cpp) and [component-local control](study/experiments/graph_queries/source/component.cpp) |
| Which methods ran on each query? | [325-case workload index](study/experiments/graph_queries/results/cases.json), [4,715 round-level timing records](study/experiments/graph_queries/results/runs.csv) and [historical exact-control results](study/evidence/final_raw_runs.csv) |
| How are case-level timings and sampling errors aggregated? | [Exact-control envelope, predictions and probability grid](study/workloads/analysis/analyze_archive.py) and [sampling and seed comparisons](study/workloads/analysis/sampling_and_seeds.py) |
| How do loading costs, probability ranges and late ranks affect results? | [Follow-up measurements and replay commands](study/workloads/experiments/README.md) for 2,748 timed invocations on 81 reused source cases |
| Which cases determine the reported contrasts? | [Audit of prediction, seed blocks, sampling, probability support, degree and endpoint contrasts](study/comparisons/analysis/audit_notes.md) |
| What happens when second-hop edges become certain? | [Timing protocol and Linux build commands](study/comparisons/endpoint/PROTOCOL.md), [300 per-query and rate comparisons](study/comparisons/endpoint/evidence/endpoint_cases.csv) and [generated table](study/comparisons/endpoint/endpoint_table.tex) from 4,284 method invocations |

The 325-case campaign includes 96 historical replay cases. The historical sampling study contributes five estimates per historical case, for 480 estimates. A query matrix begins with its witness and terminal counts, followed by one first-hop probability per witness and a row-major witness-by-terminal matrix of second-hop probabilities. The columns follow the terminal score order. A zero entry in the matrix denotes an unsupported edge.

[Download the workload archive](data/workloads.zip) to inspect the individual matrices, reference vectors and historical sampling records. To run the measurement protocols or work directly with these files, unpack it once from the repository root using the command below. Repeating the Linux timings requires a C++17 compiler and a CPU with the extended-precision `long double` representation used in the experiments. Wall-clock results depend on hardware, compiler flags and run conditions.

```sh
python -m zipfile -e data/workloads.zip .
```

## Data provenance

The graph-based queries use Cora and a 20,000-node breadth-first sample of ogbn-arxiv. In the prepared Cora graph, the authors symmetrized the citation edges, projected features to 64 dimensions and L2-normalized them. In the ogbn-arxiv sample, they symmetrized the citation edges and normalized the original 128-dimensional features. The edge probabilities were assigned by the experiment. This release contains derived query matrices, their case metadata, synthetic workloads and computed numerical results. The providers linked below distribute the upstream datasets.

* Cora is the LINQS citation dataset described by Prithviraj Sen et al. in *Collective Classification in Network Data* (2008). [Dataset provider](https://linqs.org/datasets/) · [Paper](https://linqs.org/assets/resources/sen-aim08.pdf)
* The ogbn-arxiv data come from the Open Graph Benchmark, introduced by Weihua Hu et al. in *Open Graph Benchmark: Datasets for Machine Learning on Graphs* (2020). OGB distributes ogbn-arxiv under the Open Data Commons Attribution License. [Dataset and license](https://ogb.stanford.edu/docs/nodeprop/#ogbn-arxiv) · [ODC Attribution License](https://opendatacommons.org/licenses/by/1-0/)

The serialized matrices, output vectors and timing records retain their measured values. The endpoint driver's archived environment records the hash of the file used on the server. The distributed copy changes the command-line help text naming the input directory. The verifier checks both file fingerprints and regenerates the treatment matrices and cross-campaign vector comparisons.
