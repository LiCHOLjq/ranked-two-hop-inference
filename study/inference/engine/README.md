# External exact inference with PySDD

This experiment compares the UCLA SDD compiler and weighted model counter via PySDD 1.0.6 with the archived C++ pair-local kernel. Selection takes the lowest case index in every fresh generator-seed, dataset and size block, yielding 20 full matrices. The input SHA-256 values in the raw records match the original workload index.

The SDD uses one Bernoulli variable for each incident first-hop witness and one for each supported second-hop edge. Variables are numbered in score order, creating a witness at its first incidence. The initial vtree is balanced. The primary run fixes it. The sensitivity run enables the library's automatic garbage collection and minimization on the same matrices. The vtree audit checks the complete initial variable order and that the child subtrees of every internal node differ by at most one leaf.

Each selected method runs in its own process on one logical core. Method order is deterministically shuffled within each case and round. Both implementations parse the same dense input. The SDD setup time includes building all output circuits, creating all weighted model counters and assigning literal weights. Its evaluation phase repeatedly propagates the same weights through the prebuilt circuits. Each timed C++ call constructs its prefix state and returns the complete vector. Both evaluation loops run for at least 20 ms. Process launch, imports, input parsing and printing are outside the reported setup and evaluation columns. Parsing has a separate measurement in the raw files. The SDD subprocess had a 12 s wall-clock cap from launch and a 768 MiB resident-memory threshold polled every 10 ms. Sampled RSS can overshoot that threshold. The first resource stop ends that case's trials. Raw records retain the last completed phase, the termination reason and all available output vectors. Cap exits are censored observations. The table summarizes only completed inputs, with medians over three rounds per case and then across cases. The automatic configuration uses one trial per case.

## Recompute the summaries

Run from the repository root. Python's standard library is sufficient for rechecking the stored vectors and regenerating the two summaries.

~~~sh
ENGINE=study/inference/engine
python3 "$ENGINE/summarize.py" "$ENGINE/evidence"
python3 "$ENGINE/summarize.py" "$ENGINE/evidence/automatic" --rounds 1
~~~

The primary run completed all ten small queries, three of five larger Cora queries and one of five larger OGB queries. The six bounded exits comprised five RSS stops and one wall-time stop. The 635 distinct output coordinates across the completed cases agreed with the paired kernels within a maximum absolute difference of about 1.11e-16. With automatic minimization, four larger Cora and zero larger OGB queries completed, in addition to all ten small ones. All six exits in that configuration reached the wall-time cap. A different circuit encoding, variable order, vtree or resource budget could change the completion rates.

## Re-run on Linux

The server used CPython 3.12.3 and one logical core of an Intel Xeon w9-3475X. The published PySDD release wheel used for the run was pysdd-1.0.6-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl with SHA-256 8a352aa1ac8c8562d44bd93d5cd15d1fd09eab97214aad6df55bf2440717e35c. The dependency supplies the native SDD compiler and WMC implementation. [PySDD 1.0.6](https://pypi.org/project/PySDD/1.0.6/) · [PySDD weighted model counter](https://pysdd.readthedocs.io/en/stable/classes/WmcManager.html)

From the repository root, unpack the workloads as in the top-level README, install the dependency in a Python 3.12 environment, and run the following commands with new output directory names.

~~~sh
python3 -m pip install pysdd==1.0.6
python3 -m zipfile -e data/workloads.zip .
EXP=study/experiments/graph_queries
ENGINE=study/inference/engine
g++ -std=c++17 -O3 -march=native "$EXP/source/k2.cpp" -o ./sdd_comparison_k2
python3 "$ENGINE/benchmark.py" "$EXP/results/cases.json" "$PWD/sdd_comparison_k2" sdd_fixed
python3 "$ENGINE/summarize.py" sdd_fixed
python3 "$ENGINE/sensitivity.py" "$EXP/results/cases.json" "$PWD/sdd_comparison_k2" sdd_automatic
python3 "$ENGINE/summarize.py" sdd_automatic --rounds 1
python3 "$ENGINE/check_vtree.py" "$EXP/results/cases.json" sdd_fixed/environment.json
~~~

The environment files list the script hashes and binary fingerprint. The sensitivity driver derives its executable scripts from the primary sources by changing only the automatic-transformation setting and the number of rounds.
