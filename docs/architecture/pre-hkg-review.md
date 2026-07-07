# Pre-HKG Architecture Review

Status: design/review only (no behavior change). Prepared before starting the
Hardware Knowledge Graph (HKG) to identify the stable services, data contracts,
and integration points the HKG should consume.

Guiding principle across the whole system, which the HKG must not violate:
**"Models propose. Tools decide."** Everything is deterministic, read-only with
respect to source repositories, evidence-cited, and makes **no causal / root-cause
claim**. The HKG is an ingestion/indexing layer over existing evidence; it does
not produce new analysis.

---

## 1. Current service pipeline

The end-to-end flow (composed by `run_mvp_demo`, exposed as `rtl-agent
run-mvp-demo`) chains existing services, each of which is independently usable:

```
failing regression (named command over a structured stimulus)
  → run-failure-intelligence   (build a failure-intelligence run: the evidence unit)
  → inspect-run                (validate the run: manifest + per-artifact hashes)
  → export-failure-package     (portable, self-contained copy of a validated run)
  → fingerprint-run            (exact / family / canonical identity digests)
  → minimize-stimulus          (ddmin the failing stimulus → minimized counterexample)
  → generate-interventions     (evidence-anchored, reviewable intervention manifest)
  → run-experiment-matrix      (apply each intervention in an isolated worktree, re-run,
                                classify vs the minimized-counterexample reference)
  → outcome classification     (8 observed-effect labels per experiment)
  → experiment comparison      (structured per-experiment diff vs the original failure)
  → multi-failure clustering   (group failures by canonical fingerprint identity)
  → intervention ranking       (deterministic informativeness score per intervention)
  → report synthesis           (coherent evidence-backed debug summary)
```

Everything to the left of `generate-interventions` produces **evidence**;
everything to the right **reads** that evidence and produces typed reports. The
HKG plugs in on the reading side (Section 5).

Foundational primitives shared by all services:

- **RunStore** (`artifacts/`) — the on-disk run directory + append-only event log.
- **CommandRunner** (`execution/`) — runs a single named configured command
  (`argv`, cwd, timeout, output cap); the only way anything is executed.
- **GitWorktreeManager** (`git/`) — isolated worktrees; the source repo is never
  modified, and nothing is committed or pushed.
- Config (`config.py`) — `AgentConfig` (repository path, allowed working paths,
  protected paths, named commands, execution limits).

---

## 2. Stable input/output contracts

All reports and manifests are **pydantic v2 models with a `SCHEMA_VERSION`**
(additive-only evolution is the established convention). Current versions: most
are `1`; the failure-intelligence run manifest is at `3`. The HKG must pin the
schema versions it ingests and tolerate additive fields.

Contracts the HKG will depend on most (module → model → schema const):

| Contract | Model | Version const |
| --- | --- | --- |
| Failure-intelligence run manifest | `FailureIntelligenceRunManifest` | `FAILURE_INTELLIGENCE_RUN_SCHEMA_VERSION` (3) |
| Failure report (aggregated evidence) | `FailureReport` | `FAILURE_REPORT_SCHEMA_VERSION` |
| Signal → source map | `SignalSourceMapReport` | `SIGNAL_SOURCE_MAP_SCHEMA_VERSION` |
| Driver / dependency trace | `RtlDriverTraceReport` | `RTL_DRIVER_TRACE_SCHEMA_VERSION` |
| Failure divergence graph | `FailureDivergenceGraphReport` | `FAILURE_DIVERGENCE_GRAPH_SCHEMA_VERSION` |
| Failure fingerprint (identity) | `FailureFingerprintReport` | `FAILURE_FINGERPRINT_SCHEMA_VERSION` |
| Stimulus reduction | `StimulusReductionReport` | `STIMULUS_REDUCTION_SCHEMA_VERSION` |
| Intervention manifest / candidates | `InterventionManifest` / `InterventionTemplateReport` | `INTERVENTION_MANIFEST_SCHEMA_VERSION` / `INTERVENTION_TEMPLATE_SCHEMA_VERSION` |
| Experiment matrix (rows) | `ExperimentMatrixReport` / `MatrixRow` | `EXPERIMENT_MATRIX_SCHEMA_VERSION` |
| Per-experiment comparison | `ExperimentComparison` | `EXPERIMENT_COMPARISON_SCHEMA_VERSION` |
| Failure clustering | `FailureClusterReport` | `FAILURE_CLUSTERING_SCHEMA_VERSION` |
| Intervention ranking | `InterventionRanking` | `INTERVENTION_RANKING_SCHEMA_VERSION` |
| MVP demo summary (composition) | `MvpDemoSummary` | `MVP_DEMO_SCHEMA_VERSION` |

Input contracts (things the pipeline consumes): the **structured stimulus**
(`StructuredStimulus`: ordered id/index/kind/payload items) and the **manual
intervention representation** (patch or structured `replace_text` edit, reused by
both the counterfactual runner and the experiment matrix).

Provenance contract: every run artifact is recorded in the manifest as a
`RunArtifact` with `artifact_id`, `kind`, `relative_path`, optional
`schema_version`, and a `sha256`. `inspect-run` validates a run by re-hashing;
`export-failure-package` produces a portable, hash-verified copy. **This
artifact-id + sha256 + schema-version triple is the ingestion contract the HKG
should key provenance on.**

---

## 3. Main report / model types

- **Evidence models** (produced once per failure): `FailureReport`,
  `SignalSourceMapReport`, `RtlDriverTraceReport`, `FailureDivergenceGraphReport`,
  `WaveformComparisonReport`, `RelevantSignalReductionReport`.
- **Identity model**: `FailureFingerprintReport` — carries `exact_digest`,
  `family_digest`, `canonical_digest` plus the component fields the digests are
  built from (`assertion_identity`, `earliest_divergent_signals`,
  `canonical_divergence`, `mapped_sources`, `driver_dependency_shape`,
  `graph_shape`, unresolved/ambiguous markers, etc.). `FingerprintComparisonReport`
  gives `exact_match` / `family_match` / `canonical_match` + `match_kind`.
- **Counterfactual models**: `InterventionTemplateReport` (+ `InterventionCandidate`),
  `InterventionManifest` (+ `InterventionEntry`, `ReplaceEdit`),
  `ExperimentMatrixReport` (+ `MatrixRow`), `ExperimentComparison`
  (+ `FingerprintRelationship`, `SignalChange`), `InterventionRanking`
  (+ `RankingFactor`).
- **Aggregation models**: `FailureClusterReport` (+ `FailureCluster`,
  `FailureClusterMember`), `MvpDemoSummary` (+ stage refs, notable effects,
  evidence references, next-debug checks).

---

## 4. Reusable evidence artifacts

A validated failure-intelligence run directory is the reusable evidence unit.
Its artifacts (all deterministic, hash-recorded in `run-manifest.json`):

- `repository-map.json` — discovered RTL structure.
- `failing-slice.json` / `passing-slice.json` — bounded waveform windows.
- `comparison.json` — waveform comparison (divergent signals, transition/xz).
- `signal-source-map.json` — VCD signal → RTL declaration (exact/probable/
  ambiguous/unresolved).
- `driver-trace.json` — driver statements per signal (file/line/kind/text/guard/
  lhs/rhs) + dependency edges.
- `divergence-graph.json` — divergent nodes (time, failing/passing value, xz) +
  edges + roots.
- `reduced-slice.json` — relevant-signal reduction.
- `failure-report.json` — aggregated, cited facts (earliest divergence
  signals/time, ranked signals, source locations, driver evidence, evidence gaps).
- `run-manifest.json` — the provenance index (artifact ids + hashes + schema
  versions + failure window).

The **fingerprint** is derived on demand from these (not stored in the run by
default). The failure package is a portable bundle of the above.

These are exactly the graph-shaped inputs the HKG will index: signals,
source locations, driver/dependency edges, divergence nodes, and the fingerprint
identity that ties equivalent failures together.

---

## 5. Where the HKG should plug in

The HKG is a **read-only ingestion + indexing layer on the reading side of the
pipeline**. It should consume, never produce:

1. **Failure identity** ← `FailureFingerprintReport.canonical_digest` (primary
   node key), `family_digest` (soft link), `exact_digest` (exact-dup detection).
2. **Structural evidence** ← `driver-trace.json` + `divergence-graph.json` +
   `signal-source-map.json`: signal nodes, source-location nodes (file:line),
   driver/dependency edges, divergence facts. This is the naturally graph-shaped
   data.
3. **Cluster membership** ← `FailureClusterReport` (canonical-keyed clusters,
   representatives, related-cluster links).
4. **Counterfactual evidence** ← `ExperimentMatrixReport` rows +
   `ExperimentComparison` + `InterventionRanking`: intervention → observed effect
   → result fingerprint, with the comparison and ranking metadata as edge
   attributes.
5. **Provenance** ← run manifests (artifact id + sha256 + schema version) as
   pointers, so every HKG node/edge cites the exact evidence it came from.

Recommended integration seam: a new `hkg` module that takes **already-produced
run directories / typed reports** as input (like `failure_clustering` and
`intervention_ranking` do today) and emits a typed, versioned graph model. It
must not call the simulator, must not re-run analysis, and must not modify any
existing service. Reuse `member_from_fingerprint` and `cluster_failures` for the
identity/cluster layer rather than re-deriving.

---

## 6. What HKG v0 should store

- **Failure-identity nodes** keyed by `canonical_digest` (stable across benign
  variation), with `family_digest` as a coarser relationship and `exact_digest`
  for exact duplicates.
- **Signal nodes** (from `earliest_divergent_signals` / mapped leaves) and
  **source-location nodes** (`file:line` from mapped sources / driver statements),
  each carrying its mapping status (exact/probable/ambiguous/unresolved).
- **Driver / dependency edges** (source_signal → depends_on, with
  statement_kind + evidence file/line) from the driver trace and divergence graph.
- **Cluster nodes**: canonical cluster id, members, representative, related-cluster
  links, observed-outcome distribution.
- **Experiment/intervention records**: intervention id + template kind +
  confidence, its observed-effect label, the fingerprint relationship (exact/
  family/canonical match), the comparison summary, the ranking score/rank, and
  the artifact reference.
- **Provenance pointers only**: run id, artifact ids + sha256 + schema versions —
  references into the on-disk runs/packages, not copies of the evidence.

Everything above already exists as deterministic typed data; HKG v0 is
essentially "materialize these relationships into a queryable graph."

## 7. What HKG v0 should explicitly NOT store yet

- **Causal / root-cause edges or scores.** Forbidden by the product principle;
  observed-effect and informativeness are not causality.
- **Semantic RTL elaboration / netlist / AST.** Only textual driver evidence
  exists today; do not invent structural facts the pipeline never produced.
- **Raw waveforms or large blobs.** Store references + hashes to slices/packages,
  not the VCD/log contents.
- **Exact fingerprint values as identity.** The canonical fingerprint
  intentionally drops exact values, timing, and transition counts; do not
  re-introduce them as the identity key (they remain available on the exact/family
  digests for drill-down).
- **Cross-run temporal / historical inference** beyond canonical-identity equality
  and the existing family/related links. No trend, regression-over-time, or
  learned-similarity reasoning.
- **Cross-failure or cross-run intervention ranking.** Ranking scores are
  comparable only within a single demonstration (one original failure); do not
  store them as globally comparable.
- **LLM embeddings / learned representations, a server, or a UI.**

## 8. Risks / technical debt before HKG

1. **Unmerged milestone chain (blocker to resolve first).** Stages 53–59 (outcome
   classification, report synthesis, failure corpus, fingerprint stability, result
   comparison, multi-failure clustering, intervention ranking) live on an
   unmerged branch chain: `milestone/hypothesis-intervention-templates →
   milestone/mvp-counterfactual-demo → milestone/counterfactual-outcome-
   classification`. The HKG depends on the fingerprint canonical digest (stage 56)
   and the clustering/ranking/comparison layers (stages 57–59). **These must be
   merged to `main` in order before HKG implementation starts**, or the HKG will
   be built on an unmerged base.
2. **Two clustering layers.** `failure_family.cluster_fingerprints` (older, groups
   by *family* digest) and `failure_clustering.cluster_failures` (newer, groups by
   the more stable *canonical* digest) coexist. HKG v0 should standardize on the
   canonical clustering; the family clustering is coarser/legacy for this purpose.
   Document this so the HKG does not ingest two conflicting notions of "cluster."
3. **Family digest instability is intentional.** The family digest is
   window/length-sensitive (equivalent reproductions can differ); the canonical
   digest was added specifically to be stable. HKG identity **must** key on
   canonical, using family only as a soft "related" link.
4. **Canonical identity granularity.** Two different *defined-value* corruptions on
   the same signal share a canonical fingerprint (only x/z-vs-defined nature is
   preserved). HKG nodes will therefore be at that granularity; drill-down to
   exact/family digests is available when finer distinction is needed.
5. **Mapping quality varies.** Signal→source mappings can be ambiguous/unresolved;
   the HKG must carry mapping status on source-location nodes and not treat
   ambiguous mappings as ground truth.
6. **No persistence layer exists.** Everything today is per-run artifacts on disk;
   the HKG introduces the first cross-run store. v0 should define a minimal,
   deterministic, file-based graph artifact (consistent with the existing
   report-on-disk convention) rather than pulling in a database (out of scope).
7. **Evidence production needs a simulator.** Producing runs depends on Icarus
   (pilots are gated). HKG *ingestion* must be simulator-independent — it consumes
   existing run directories/packages, so it can be fully hermetically tested like
   `failure_clustering` and `intervention_ranking`.

---

## Summary: recommended HKG v0 scope

- A new read-only `hkg` module that ingests already-produced failure-intelligence
  runs / typed reports and materializes a **typed, versioned, deterministic graph
  artifact** (file-based, hash-cited provenance) of: canonical failure-identity
  nodes, signal + source-location nodes, driver/dependency edges, cluster
  membership, and intervention→observed-effect records.
- Reuse `fingerprint_run`, `member_from_fingerprint`, `cluster_failures`,
  `ExperimentComparison`, and `InterventionRanking`; add no new analysis.
- Store references + hashes to evidence, not copies; key identity on
  `canonical_digest`.
- Explicitly exclude causal edges, semantic elaboration, raw blobs, cross-run
  inference, cross-failure ranking, embeddings, databases, servers, and UIs.

## Blockers to resolve before HKG implementation

1. Merge the unmerged milestone chain (stages 53–59) to `main` in order — the HKG
   builds directly on the canonical fingerprint and the clustering/ranking/
   comparison layers.
2. Decide the single canonical clustering source (standardize on
   `failure_clustering`, canonical-keyed) so the HKG ingests one notion of cluster.
3. Confirm the HKG v0 persistence shape is a deterministic file-based graph
   artifact (no database) to stay within the established read-only, deterministic,
   hash-cited convention.
