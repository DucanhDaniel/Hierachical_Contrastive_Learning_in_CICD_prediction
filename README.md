# Project3 — Hierarchical Contrastive Learning for CI Build Failure Classification

A research project that classifies failed **GitHub Actions runs from Java/Kotlin projects** using build logs, CI context, and structured code-diff features. Predictions follow a three-level label tree: **fault-containing artifact → remediation stage → failure type**.

The pipeline covers collection, rule-based labeling, human review, dataset export, model training, and comparison with rule, TF-IDF, and LLM baselines. See [DESCRIPTION.md](DESCRIPTION.md) for the Vietnamese project overview.

---

## Features

### Data collection and labeling

- **GitHub Actions crawler** — collects runs, jobs, and available logs for pull-request and push events, with checkpoints, retries, and incremental collection.
- **Evidence-based rules** — retain supporting log evidence; unresolved cases remain `?` for review.
- **Human review tools** — support blind labeling, adjudication, leaf-label review, and offline evaluation of proposed rules before integration.
- **Run-level datasets** — combine log chunks, CI metadata, repository folds, and links to commit diffs in Parquet files.

### Classification and evaluation

- **UniXcoder encoder** — encodes log chunks and CI context; attention pools chunks into jobs and jobs into runs, with optional attention over individual lines.
- **Hierarchical learning** — three classification heads with cross-entropy (`ce`), hierarchical contrastive learning (`hcl`), soft tree-aware contrastive learning (`soft`), or hierarchical proxies (`proxy`).
- **Structured inputs** — add failure-stage/tool indicators and code-diff summaries; ablations can remove these features or the hierarchy.
- **Cross-repository evaluation** — five repository folds, macro-F1 at each label level, and tests on original logs and logs with rule evidence masked.
- **Uncertainty analysis** — MC Dropout and confidence-based routing help identify predictions requiring human review.

### Experimental demo

The Gradio interface in `src/project3/demo/` accepts a failed GitHub Actions run URL or a bundled example. It displays hierarchical labels, suggested actions, uncertainty, and highly weighted log lines. It requires a separately prepared demo bundle and trained checkpoints; the Colab workflow is in `scripts/colab/p3_demo.ipynb`.

### Processing flow

```text
GitHub Actions runs / jobs / logs + commit diffs
    → rule labels + human review
    → run dataset + log chunks + structured features
    → UniXcoder + hierarchical attention
    → artifact / remediation stage / failure type
    → suggested action + supporting log lines + uncertainty
```

The current task is classification **after a CI failure**. Earlier work on predicting CI outcomes from commit diffs is retained under `legacy/`. Suggested actions do not execute reruns or change pull-request merge status.

---

## Project Structure

```text
project3/
├── src/project3/
│   ├── crawl/                # GitHub API, checkpoints, log rules, failure-stage extraction
│   ├── pipeline/             # Orchestration, diffs, dataset export, human/rule review
│   ├── model/                # Packing, label tree, baselines, training, evaluation
│   │   └── nn/               # UniXcoder network, attention, losses, samplers
│   └── demo/                 # Experimental Gradio interface and inference
├── configs/                  # Repository lists and current labeling rules
├── scripts/
│   ├── kaggle/               # Crawl, diff, model, and baseline runners
│   ├── colab/                # Training, analysis, and demo notebooks
│   └── analysis/             # Ablations, ensembles, uncertainty analysis
├── tests/                    # Python unittest suite
├── docs/                     # Requirements, label design, experiment notes, reports
├── data/                     # Local datasets and outputs; excluded from Git
├── legacy/                   # Earlier approach and archived implementation
├── pyproject.toml            # Package metadata and dependency groups
└── DESCRIPTION.md            # Vietnamese project overview
```

---

## Prerequisites

| Tool / resource | Requirement | Notes |
|-----------------|-------------|-------|
| Python | 3.14+ | Local package requirement in `pyproject.toml` |
| uv | Available on PATH | Dependency management using `uv.lock` |
| Git | Available on PATH | Cloning and commit-diff extraction |
| NVIDIA GPU / CUDA | Recommended for model training | CPU fallback is supported; `exp` uses the configured PyTorch CUDA 12.8 index |
| GitHub token | For authenticated collection | `GITHUB_TOKEN`, `GITHUB_ACCESS_TOKEN`, or `.env` |
| Kaggle / Colab | Optional | Remote collection, GPU training, and notebooks |

The bundled modeling code also supports Python 3.11+ on Kaggle/Colab through `project3_code.pyz`; this is separate from installing the full local package. Datasets, trained weights, and credentials are not included in a fresh clone.

---

## Getting Started

### 1. Install the project

```powershell
git clone https://github.com/DucanhDaniel/Hierachical_Contrastive_Learning_in_CICD_prediction.git
cd Hierachical_Contrastive_Learning_in_CICD_prediction

# Collection dependencies and the project package
uv sync

# Additional dependencies for dataset processing, baselines, and training
uv sync --group exp
```

Run commands below from the repository root. `uv run --group exp` uses the managed environment without manual activation.

### 2. Configure GitHub access

Create a local `.env` file when collecting GitHub data:

```dotenv
GITHUB_TOKEN=your_github_token
```

The token needs access to the repositories and Actions logs being requested. An environment variable can be used instead of `.env`.

### 3. Prepare data

For a small collection run in a separate work directory:

```powershell
uv run --group exp python -m project3.pipeline.run --repos dataease/dataease --days 14 --workdir data/demo
```

For the main dataset, after raw collection is available under the default `data/` paths:

```powershell
uv run --group exp python -m project3.pipeline.run --repos-file configs/repos_100.txt --skip crawl
uv run --group exp python -m project3.pipeline.run_dataset
uv run --group exp python -m project3.model.pack
```

The default model pack is written to `data/kaggle_log_ds/`, including `runs.parquet`, `chunks.parquet`, `features.parquet`, `label_tree.json`, and `project3_code.pyz`. `model.pack` rebuilds its output directory; use `--out` to preserve a separate experiment snapshot. A collection using `--workdir` needs corresponding downstream paths; the main-dataset commands above use the default paths.

---

## Usage

### Train and evaluate

After preparing the pack, run a small smoke experiment:

```powershell
uv run --group exp python -m project3.model.train --data data/kaggle_log_ds --fold 0 --variants ce hcl --smoke --out smoke_results.json
```

For a full fold with line attention, saved representations, and a checkpoint:

```powershell
uv run --group exp python -m project3.model.train --data data/kaggle_log_ds --fold 0 --variants soft --line-attn --save-repr --save-model --out results_fold0.json
```

These are example configurations. Use the matching experiment report or notebook for its full settings. The first run downloads `microsoft/unixcoder-base` unless cached.

### Baselines and analysis

```powershell
# Rule and TF-IDF baselines; requires local run data and logs
uv run --group exp python -m project3.model.baselines all
uv run --group exp python -m project3.model.baselines fair

# Prepare LLM inputs, then score downloaded benchmark outputs
uv run --group exp python -m project3.model.llm prepare
uv run --group exp python -m project3.model.llm score path/to/benchmark_outputs

# Analyze outputs saved with --save-repr for the relevant folds
uv run --group exp python -m project3.model.routing data/results/log_model/v5_repr
```

For optional TF-IDF stacking experiments, export text with `python -m project3.model.tfidf --export-text`, then generate fold features with `python -m project3.model.tfidf` in the experiment environment. These features are required for `--tfidf`.

### Kaggle / Colab

```powershell
uv run --group exp python -m project3.model.kaggle kernel p3-log-x --folds 0 1 --variants ce soft
```

This generates a runner and metadata under `data/kaggle_kernels/p3-log-x/`. Uploading data and submitting the kernel are separate steps requiring Kaggle access. On Kaggle/Colab, add the pack's `project3_code.pyz` to `PYTHONPATH` and run `python -m project3.model.train ...` with the mounted data path and modeling dependencies installed.

---

## Command Reference

| Module | Purpose |
|--------|---------|
| `project3.pipeline.run` | Collection, labeling, commit aggregation, diffs, dataset export |
| `project3.pipeline.run_dataset` | Run-level dataset and log chunks |
| `project3.pipeline.label_ui` | Human labeling, adjudication, and evaluation |
| `project3.pipeline.rule_eval` | Offline evaluation of proposed rule changes |
| `project3.model.pack` | Package data and modeling code |
| `project3.model.train` | Train/evaluate one fold; save models and MC Dropout outputs |
| `project3.model.baselines` | Rule and TF-IDF comparisons |
| `project3.model.llm` | Prepare and score LLM benchmark cases |
| `project3.model.kaggle` | Generate a Kaggle kernel directory |
| `project3.model.routing` | Analyze attention, representations, and confidence routing |

Use `python -m <module> --help` for arguments. Most commands require outputs from earlier stages.

---

## Model Overview

### Label hierarchy

The current tree is defined in `src/project3/model/labels.py`:

| Level 1: artifact | Level 2: remediation stage | Level 3: failure types |
|-------------------|----------------------------|------------------------|
| Project (`du_an`) | While coding (`viet_code`) | `compile`, `quality`, `doc`, `buildconfig` |
| Project (`du_an`) | Local build before push (`build_local`) | `testfailure`, `license`, `compatibility`, `dependency` |
| Project (`du_an`) | CI before merge (`ci_merge`) | `itestfailure`, `flaky` |
| CI environment (`moi_truong`) | Fix CI configuration (`cau_hinh_ci`) | `git`, `androidsdk`, `infra` |
| CI environment (`moi_truong`) | Rerun (`chay_lai`) | `network`, `crash` |

The taxonomy defines 15 leaves. A model pack can exclude rare leaves according to its sample threshold; its `label_tree.json` records active labels. Older experiments may use a different tree.

### Architecture and evaluation

UniXcoder encodes selected error-centered log chunks and CI context. Attention aggregates **chunks → jobs → run**, optionally adding **lines → chunks**. Structured CI and diff features join the run representation before three classification heads. HCL adds supervised contrastive losses at all three levels; `soft` and `proxy` provide alternative tree-aware objectives.

For test fold `k`, validation uses `(k + 1) % 5` and training uses the other three repository folds. Evaluation includes full and evidence-masked logs, with separate analysis of human-labeled and rule-unresolved cases. Rule-derived labels are weak supervision; scores on those labels alone do not establish accuracy on independently reviewed failures.

---

## Development

```powershell
uv run --group exp python -m unittest discover -s tests
```

Further reading:

- [Current label-tree design](docs/cay-nhan-3-tang-2026-10-25.md)
- [Requirements and user stories](docs/dac-ta-yeu-cau-agile.md)
- [Transition to post-CI classification](docs/huong-moi-phan-loai-sau-ci.md)
- [Model experiment notes — 19 October 2026](docs/ket-qua-mo-hinh-log-2026-10-19.md)
- [Routing experiment notes — 20 October 2026](docs/ket-qua-dinh-tuyen-2026-10-20.md)

Experiment notes are dated snapshots; compare datasets, label trees, folds, and settings before comparing scores.
