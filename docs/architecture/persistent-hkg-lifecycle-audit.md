# Persistent HKG Lifecycle and Counterfactual Evidence Integration Audit

Status: completed architecture and implementation-planning audit. No runtime behavior was changed.

This document uses four labels deliberately:

- **Confirmed** means observed in current source, tests, or generated artifacts.
- **Inference** means a conclusion drawn from those confirmed contracts.
- **Proposed** means behavior for the next implementation milestone; it does not exist yet.
- **Unresolved** means a bounded issue the implementation must settle or reject explicitly.

## 1. Executive Summary

**Confirmed.** The HKG already has a useful deterministic core. `build_hkg(...)` in
`src/rtl_agent/hkg/builder.py` constructs typed `HkgGraph` objects from `FailureBundle` objects,
`write_graph(...)` emits sorted JSON, `HkgQuery` provides read-only queries, and
`lookup_historical_failure(...)` projects canonical-fingerprint matches into historical memory.
Repeated construction from the same typed bundle is byte-identical. A real failure-corpus run
produced 69 nodes, 167 edges, and three canonical clusters.

**Confirmed.** The core is not a persistent lifecycle. There is no standard store, source index,
atomic update, graph integrity manifest, explicit build/update CLI, source conflict policy, or MVP
consumer. `run_mvp_demo(...)` creates real minimized-stimulus, intervention, matrix, comparison,
ranking, repair-suggestion, package, JSON, and Markdown artifacts, but it neither ingests them into
the HKG nor passes HKG memory to `generate_repair_suggestions(...)`. The corpus HKG check ingests
failure-intelligence plus clustering only; counterfactual HKG tests use synthetic typed objects.

**Decision.** The smallest appropriate persistence is a local two-file store at
`.rtl-agent/hkg/`: canonical `hkg.json` plus `hkg-manifest.json`. The graph remains a typed JSON
document. The manifest is the commit/integrity record: it records the graph SHA-256 and the sorted,
root-relative, hash-cited source artifact index. A database, server, and generic graph platform are
not justified.

**Decision.** A dedicated HKG lifecycle service owns all creation and updates. Lifecycle mutation
is invoked only by explicit `hkg-build` and `hkg-update` commands. Failure-intelligence and MVP
completion remain free of hidden writes. `run-mvp-demo` gains only an optional read-only HKG input
for historical lookup; callers explicitly run `hkg-update` after a successful demo when they want
to retain it.

**Decision.** One coherent implementation milestone is safe if kept to this vertical slice:
correct persistent identities/provenance, validated adapters for failure runs/packages and MVP
directories, deterministic build/update/idempotence, three minimal lifecycle commands, optional
historical-memory use by MVP repair suggestions, tests, and one hermetic end-to-end check. These
parts must land together because persistent updating is unsafe with current global leaf/candidate
IDs, and historical reuse cannot be honestly tested until real MVP evidence is ingested.

## 2. Confirmed Current State

### HKG APIs

**Confirmed.** `src/rtl_agent/hkg/models.py` owns `HKG_SCHEMA_VERSION = 1`, nine node types,
eight edge types, `Provenance`, `HkgNode`, `HkgEdge`, and `HkgGraph`. `HkgGraph` contains a caller-
supplied `graph_id`, counts, sorted nodes/edges, warnings, disclaimer, and parser notes. It has no
source registry, revision, graph digest, or lifecycle metadata.

**Confirmed.** `FailureBundle` is the builder boundary. It accepts typed Python objects:

- required manifest and fingerprint;
- optional signal-source map, driver trace, divergence graph, and failure report;
- optional experiment matrix and intervention-template report;
- optional lists of experiment comparisons and intervention rankings;
- caller-supplied provenance for optional counterfactual objects.

`load_failure_bundle(failure_id, run_dir, matrix_path=None, interventions_path=None)` also accepts
runtime file paths, loads the run manifest and selected run artifacts, computes the fingerprint,
and optionally loads a matrix/template file. It does not load an MVP directory as a coherent unit,
does not load comparisons/rankings from `mvp-demo-summary.json`, and does not call `inspect_run`.
Malformed optional run artifacts are silently returned as absent by `_read_optional(...)`.

**Confirmed.** `build_hkg(...)` sorts bundles by `failure_id`; `_GraphBuilder.finalize(...)` sorts
node IDs, edge IDs, attributes, provenance, counts, and warnings. `serialize_graph(...)` additionally
sorts all JSON keys. `write_graph(...)` writes directly to an arbitrary caller-selected path; it is
not atomic.

**Confirmed.** `load_graph(...)` in `hkg/query.py` validates JSON through `HkgGraph`, but it only
wraps `OSError`. It does not enforce an exact supported schema version, verify counts, uniqueness,
edge endpoints, canonical serialization, provenance paths/hashes, or a graph digest.

### Existing graph content

**Confirmed.** Failure-intelligence evidence contributes:

- Failure nodes from the run manifest;
- CanonicalFingerprint nodes from `FailureFingerprintReport.canonical_digest`;
- Module, Signal, and SourceLocation nodes from source maps, driver traces, divergence graphs, and
  failure reports;
- `contains`, `originated_from`, `depends_on`, `drives`, and fingerprint `references` edges;
- FailureCluster nodes and `belongs_to_cluster` edges only when a cluster report is supplied.

**Confirmed.** Counterfactual typed objects contribute:

- Intervention nodes and failure-to-intervention `generated` edges from
  `InterventionTemplateReport`;
- Experiment and ObservedEffect nodes, tested-intervention/result-fingerprint `references` edges,
  and `produced` edges from `ExperimentMatrixReport`;
- comparison attributes and result fingerprint references from `ExperimentComparison`;
- ranking attributes on Intervention nodes and an intervention-to-experiment ranking reference
  from `InterventionRanking`.

**Confirmed.** Repair suggestions are not ingested. This is appropriate: they are derived guidance,
can consume historical memory themselves, and would create a feedback loop if persisted as primary
evidence.

### Current disconnections

**Confirmed.** `scripts/hkg_failure_corpus_check.py` builds real failure runs, fingerprints, and
clusters, but passes no MVP/matrix/intervention/comparison/ranking artifacts. In
`tests/test_hkg.py`, `_matrix()`, `_interventions()`, `_comparisons()`, and `_rankings()` are
synthetic. Therefore current graph construction has not been proven against the real serialized
counterfactual workflow.

**Confirmed.** `lookup_historical_failure(...)` is called only by HKG tests and the HKG corpus
check. `generate_repair_suggestions(...)` accepts `hkg_memory`, and unit tests exercise that
parameter, but `mvp_demo/service.py` does not pass it. `supervisor.py` can consume memory, but there
is no production lifecycle call site and supervisor integration is outside the next milestone.

**Confirmed.** README describes HKG as a Python API, explicitly not a CLI. `cli.py` has no HKG
commands. `AgentConfig` has a run artifact root but no HKG setting.

## 3. Runtime Artifact Flow

The required focused tests passed:

```text
.venv/bin/python -m pytest tests/test_hkg.py tests/test_supervisor.py \
  tests/test_repair_suggestions.py tests/test_mvp_demo.py -q
..................................... [100%]
```

The required scripts also passed:

```text
HKG failure corpus check passed (69 nodes, 167 edges, 3 clusters)
evidence artifact provenance check passed
```

**Confirmed.** A separate hermetic runtime audit used the production paths from
`scripts/evidence_artifact_provenance_check.py` and generated a real MVP directory. Its baseline
manifest contained 11 run-relative, SHA-256-cited artifacts. The MVP reduced a three-item stimulus
to one item, generated three interventions, executed three experiments, classified all three as
`failure_changed`, built three comparisons and rankings, emitted three repair suggestions, and
exported a 13-file validated failure package. Feeding those real files plus summary-embedded
comparisons/rankings into the current builder produced 35 nodes and 52 edges.

The observed directory flow was:

```text
mvp-demo/
  failure-package/package-manifest.json
  failure-package/run/run-manifest.json
  minimization/reduction-report.json
  minimization/minimized-stimulus.json
  generated/interventions.json
  generated/intervention-templates.json
  generated/diffs/*.diff
  matrix/experiment-matrix.json
  matrix/rows/<row>/run/run-manifest.json
  mvp-demo-summary.json
  mvp-demo-summary.md
```

**Confirmed.** The JSON/Markdown summary uses absolute paths for the baseline run, package,
reduction report, generated manifest, and matrix report, but matrix row `artifact_dir` values are
relative to `matrix/` (for example `rows/00-suppress_assignment-payload_out-94c0711e`). The recent
provenance check resolves and validates both forms. A persistent HKG must not preserve those
absolute paths as identity.

## 4. Current HKG Data Model

### Identity behavior

**Confirmed.** Current IDs are string concatenations:

| Entity | Current key |
| --- | --- |
| Failure | caller-provided `failure_id` |
| Canonical fingerprint | `canonical_digest` |
| Module | declaration name |
| Signal | leaf/identifier |
| Source location | `file_path:line` |
| Cluster | `cluster_id` |
| Intervention | `candidate_id` |
| Experiment | `intervention_id` |
| Observed effect | effect label |
| Edge | `type|source|target` |

**Confirmed.** These keys are adequate for one bounded graph but unsafe for a persistent multi-run
store. Signals named `state` in unrelated repositories collapse. Modules and source locations can
collapse across repositories. Candidate IDs and experiment IDs can recur in multiple MVP runs.
Edges with the same type/source/target but different roles collapse. `_GraphBuilder.node/edge` uses
first-writer-wins attributes, so a collision can silently preserve stale attributes.

**Confirmed.** Exact duplicate input objects do not create duplicate node/edge records because the
builder dictionaries key by ID and deduplicate identical provenance. Distinct bundles with distinct
failure IDs are order-normalized. Conflicting entities with the same ID are not diagnosed; equal
sort keys retain input order, so first-writer-wins can make serialized output order-dependent in
that conflict case.

### Provenance behavior

**Confirmed.** Run artifact provenance is partly strong: `_provenance_by_kind(...)` carries the
manifest artifact path, schema version, and SHA-256. However, it records `artifact.kind` as
`Provenance.artifact_id`, not the manifest's actual `RunArtifact.artifact_id`.

**Confirmed.** Run-manifest provenance has no manifest content hash. Fingerprint provenance stores
the semantic `exact_digest` in `content_sha256`, even though that is not a SHA-256 of serialized
fingerprint artifact bytes and no fingerprint file exists. Matrix/template provenance correctly
hashes file bytes. Comparison/ranking provenance exists only if the caller supplies it manually.

**Inference.** Current graph entities do not consistently retain enough information to revalidate
or relocate all sources. This is a narrow HKG provenance defect, not a reason to change the source
artifact schemas.

## 5. Provenance and Identity Analysis

### Reusable source-of-truth contracts

**Confirmed.** The failure-intelligence source of truth is
`FailureIntelligenceRunManifest` schema 3 plus `inspect_run(...)`: `run_id`, actual
`RunArtifact.artifact_id`, `kind`, `run_relative` path, schema version, and SHA-256. Package
relocation is supported by `FailurePackageManifest` schema 1: `run_id`, package-relative paths,
SHA-256, schema versions, and `run_relative_path`; the packaged `run/` itself passes
`inspect_run(...)`.

**Confirmed.** Existing semantic identities should be reused:

- failure identity: `FailureFingerprintReport.canonical_digest` for observed-failure equality;
- failure occurrence: run manifest `run_id` scoped by an HKG source record;
- minimized stimulus: `StimulusReductionReport.minimized_stimulus_digest`, computed by
  `stimulus_digest(...)` over ordered semantic items;
- intervention: `InterventionCandidate.semantic_digest` and matrix `intervention_digest`;
- experiment: `MatrixRow.experiment_digest`, which hashes target commit, baseline family,
  stimulus digest, command, and intervention digest;
- result failure: `MatrixRow.result_canonical_digest`;
- cluster: `cluster-<canonical_digest[:16]>` for canonical clusters.

**Proposed.** Every persistent provenance record gains `source_id`; `artifact_id` uses the source
artifact's actual ID where one exists; `path` is POSIX and relative to that source root; and
`content_sha256` always means SHA-256 of exact file bytes. Semantic digests remain attributes and
must never be placed in `content_sha256`.

### Stable v2 entity keys

**Proposed.** Scope occurrence-specific entities to their source; keep semantic shared entities
global:

| Entity | Proposed stable key |
| --- | --- |
| Source | `failure-run:<run_id>`; `mvp:<target_commit>:<demo_id>` |
| Failure occurrence | `failure:<failure-source-id>` |
| Canonical fingerprint | `canonical_fingerprint:<canonical_digest>` |
| Module | `module:<failure-source-id>:<repo-relative-file>:<name>` |
| Signal | `signal:<failure-source-id>:<full-name-or-leaf>` |
| Source location | `source_location:<failure-source-id>:<repo-relative-file>:<line>` |
| Canonical cluster | `failure_cluster:cluster-<canonical-digest-prefix>` |
| Intervention occurrence | `intervention:<mvp-source-id>:<semantic_digest>` |
| Experiment occurrence | `experiment:<mvp-source-id>:<experiment_digest>` |
| Observed effect | `observed_effect:<label>` |
| Edge | `type|source|target|role` |

**Proposed.** Labels retain current human IDs (`run_id`, `candidate_id`, etc.). Attributes retain
the complete semantic digest. This prevents cross-repository conflation while still allowing
queries to group by canonical, semantic, or experiment digest.

**Unresolved, with a bounded rule.** `demo_id` is derived from the output directory name and is not
globally unique. Combining it with `target_commit` is the best existing logical source key.
Different content under the same key must be rejected as a source-identity conflict. No MVP source
schema field is required in v1; a future additive immutable MVP run ID can be considered only if
real collisions become operationally common.

## 6. Persistence Format Decision

### Options considered

1. **One `HkgGraph` JSON file.** Smallest, but cannot declare its own byte hash or maintain a
   validated source index without overloading graph nodes.
2. **Canonical graph JSON plus a small manifest.** Matches run/package conventions and permits an
   atomic commit marker, graph hash, source registry, and corruption detection.
3. **Database or custom graph store.** No repository evidence requires concurrent writers,
   partial graph queries at scale, transactions across processes, or remote access.

**Decision.** Use option 2.

### Exact format

**Proposed.** Standard store directory and filenames:

```text
.rtl-agent/hkg/
  hkg.json
  hkg-manifest.json
```

`src/rtl_agent/hkg/models.py` remains the graph schema owner and advances to HKG schema 2 for
source-scoped IDs and `Provenance.source_id`. A new lifecycle model module owns
`HKG_STORE_MANIFEST_SCHEMA_VERSION = 1` and typed source/artifact index records.

The manifest contains only deterministic fields: schema version, graph filename, HKG schema
version, graph SHA-256, graph/node/edge counts, and sorted sources. Each source records `source_id`,
kind (`failure_run`, `failure_package`, or `mvp_demo`), logical ID, source digest, and sorted
artifact records (`artifact_id`, root-relative path, schema version, byte SHA-256). It contains no
creation/update timestamp or absolute root, so rebuilding from relocated identical sources is
byte-identical.

Graph and manifest JSON use UTF-8, two-space indentation, sorted object keys, sorted lists, and one
trailing newline. Hashing is SHA-256 lowercase hex over exact file bytes, matching
`sha256_file(...)`, failure manifests, packages, and the provenance check.

Writes are staged in the store directory as temporary files, flushed, then replaced with
`Path.replace`: graph first, manifest last. The manifest is the commit marker. A crash between
replacements yields a graph/manifest hash mismatch and a clean validation failure; the prior store
can be restored by rerunning build from sources. No lock/concurrent-writer protocol is in v1.

Load-time validation checks manifest schema, safe filenames, graph hash, graph schema, canonical
serialization, counts, unique IDs, edge endpoints, source IDs, provenance source/artifact/path/hash
agreement, and disclaimers. Corrupt or incompatible stores are rejected; they are never partially
loaded. Existing schema-1 standalone graph files remain queryable through an explicit legacy
read-only path, but cannot be updated or used as trusted MVP memory. There is no migration
framework; rebuild from source artifacts is the migration.

## 7. Lifecycle Ownership Decision

**Decision.** A dedicated `rtl_agent.hkg.lifecycle` service owns normalization, validation,
ingestion, merge/rebuild, persistence, and inspection.

**Proposed ownership model:**

- `hkg-build` explicitly creates/replaces a store from a complete supplied source set.
- `hkg-update` explicitly validates and adds supplied sources to an existing store.
- `hkg-inspect` validates the stored graph/manifest without mutation.
- Failure-intelligence completion does not update HKG.
- MVP completion does not update HKG.
- `run-mvp-demo --hkg-store ...` may read prior memory only.

**Rationale.** Explicit lifecycle operations avoid hidden side effects, keep simulations and graph
mutation independently reproducible, support package relocation, and make source conflicts visible.
An automatic update after MVP would also make it difficult to exclude current evidence from a
lookup performed during that MVP.

## 8. Build and Update Semantics

### Build

**Proposed.** `build_store(sources, output, overwrite=False)`:

1. Normalize each input into a typed source adapter.
2. Validate every source before graph construction.
3. Derive source IDs/digests and reject duplicate IDs with different digests.
4. Sort sources by `(kind, source_id)`.
5. Build failure and MVP bundles using real typed artifacts.
6. Derive canonical cluster membership across all failure occurrences.
7. Finalize schema-2 graph and deterministic source manifest.
8. If output exists, refuse unless `overwrite`; with `overwrite`, replace only after full success.

No prior graph creates the canonical empty-or-populated store. An empty source list is rejected;
an empty valid graph is not useful as a lifecycle checkpoint.

### Update

**Proposed.** `update_store(store, sources)` validates the existing store, validates new sources,
then performs a transaction in memory. Existing source records need not still be present on disk;
their hash-cited materialized graph remains queryable. Newly supplied sources must be available and
valid.

The update unions exact compatible nodes/edges and sorted provenance. It rejects type, label, or
semantic-attribute conflicts for an existing ID. Canonical cluster nodes and membership edges are
the sole derived replacement set: recompute them from all failure/canonical edges so cluster size
and membership remain correct after adding a failure. The result must equal a clean build from the
same source set when those sources are available.

There is no delete, source replacement, or garbage collection in v1. Replacing changed evidence
requires `hkg-build --overwrite` with the complete authoritative source set.

## 9. Idempotence and Conflict Rules

**Proposed exact rules:**

- Rebuilding the same source set at any location produces byte-identical graph and manifest.
- Updating with an already-recorded `source_id` and identical source digest is a successful no-op.
- Updating with the same source ID and a different digest fails before writing.
- Adding a new failure run creates one new failure occurrence; a matching canonical digest reuses
  the canonical node and expands its cluster deterministically.
- Adding a new MVP run creates source-scoped intervention/experiment occurrences and links them to
  its baseline failure source.
- Ingesting a relocated failure package succeeds when package/run IDs, root-relative paths, and
  hashes are unchanged; original absolute `source_run_dir` is advisory only.
- If an artifact's bytes change while its logical source ID remains the same, reject. Do not
  first-writer-win and do not silently replace.
- Two runs with the same canonical fingerprint remain distinct Failure nodes linked to one
  CanonicalFingerprint node and one canonical cluster.
- Duplicate candidates/rows inside one MVP source are rejected by existing manifest/matrix
  validation. Semantically repeated interventions or experiments in different MVP sources remain
  separate occurrences with shared digest attributes; they are not falsely collapsed into one
  historical event.
- HKG/store schema mismatch rejects update. Legacy graph schema 1 is read-only and must be rebuilt.
- A missing source artifact, unsafe path, manifest hash mismatch, package hash mismatch, malformed
  typed JSON, or cross-artifact ID/digest mismatch rejects that source and leaves the store bytes
  unchanged.

## 10. Counterfactual Evidence Mapping

The production flow and v1 graph mapping are:

| Stage | Current model/artifact and identity | Current provenance | Proposed HKG mapping |
| --- | --- | --- | --- |
| MVP demo | `MvpDemoSummary`, `mvp-demo-summary.json`; `demo_id` | schema 1; no declared file hash; mixed absolute/relative refs | source registry entry; no graph node |
| Minimized stimulus | `StimulusReductionReport`, `minimization/reduction-report.json`; `minimization_id`, `minimized_stimulus_digest`; `minimized-stimulus.json` | semantic digest but no artifact byte hash in report | put digest, classification, counts on experiments/generated relation; cite both files |
| Generated intervention | `InterventionTemplateReport`, `generated/intervention-templates.json`; candidate `candidate_id`, `semantic_digest`, source/file hashes; matrix-compatible `interventions.json` | no enclosing manifest hash | Intervention node; `generated` from baseline Failure; edit-site/signal references; cite both JSON files |
| Matrix entry | `ExperimentMatrixReport`, `matrix/experiment-matrix.json`; `matrix_id`; row `intervention_digest`, `experiment_digest` | row has relative `artifact_dir`; no matrix-declared byte hash | Experiment node keyed in MVP source scope by experiment digest; tested intervention reference |
| Execution result | `MatrixRow` plus `matrix/<artifact_dir>/commands/.../result.json` and optional validated `run/` | command/run artifacts exist; row records status, exit code, result digests | Experiment attributes and provenance; result canonical reference when present |
| Outcome classification | `MatrixRow.observed_effect` and rationale from `classify_observed_effect(...)` | embedded in matrix | ObservedEffect node and `produced` edge; rationale on experiment/edge |
| Experiment comparison | `ExperimentComparison` embedded in `mvp-demo-summary.json`; `intervention_id`, schema 1, fingerprint relation | no standalone file/hash | comparison attributes on Experiment; cite summary and matrix row |
| Intervention ranking | `InterventionRanking` embedded in summary; `intervention_id`, rank/score/factors/result cluster | no standalone file/hash | ranking is MVP-context metadata on the generated/tested relation, not global intervention identity |
| Repair suggestion | `RepairSuggestion` embedded in summary; `suggestion_id`, schema 1 | derived from current evidence and optional memory | do not ingest in HKG v1; regenerate as derived output |

**Confirmed.** The real audit output demonstrated these joins: the minimized digest in reduction,
matrix, and comparisons agreed; candidate IDs joined template candidates, manifest entries, matrix
rows, comparisons, rankings, suggestions, and Markdown; each matrix row's result canonical digest
resolved to its result run; ranking artifact references resolved under `matrix/`.

**Proposed.** The MVP adapter validates those joins and computes SHA-256 for every ingested file.
It resolves known files from the supplied MVP root, not from stored absolute paths. Absolute fields
must agree semantically where usable but are never persisted as identity or provenance paths.

**Missing provenance, handled without source schema change.** MVP has no package-style manifest for
its own generated/minimization/matrix/summary files. The HKG source adapter therefore creates the
sorted artifact index at ingestion and cross-validates duplicated IDs/digests across typed files.
This is sufficient for deterministic first ingestion and detects later same-source mutation. A new
MVP manifest is deferred unless this adapter proves insufficient in implementation.

## 11. Historical-Memory Integration Design

**Confirmed.** The current API accepts a `FailureFingerprintReport` or canonical string and returns
matching failure/cluster/intervention/experiment/ranking/provenance summaries. It has no exclusion
parameter. `run_mvp_demo(...)` fingerprints the current run in `_original_failure(...)`, and later
calls `generate_repair_suggestions(...)` without its existing optional `hkg_memory` argument.

**Proposed smallest safe wiring:**

1. Add optional `hkg_store: Path | None` to `run_mvp_demo` and `--hkg-store` to its CLI.
2. After `inspect_run` and current `fingerprint_run`, validate/load the store read-only.
3. Call `lookup_historical_failure(...)` with the current canonical fingerprint and an exclusion
   set containing the current failure source ID/run ID.
4. Pass the result to the existing `generate_repair_suggestions(..., hkg_memory=memory)` call.
5. Never update the HKG during the MVP run.

`lookup_historical_failure` should gain an optional exclusion argument and filter current failure
occurrences before cluster expansion. `seen_before` is true only when at least one non-excluded
historical failure remains. This prevents a previously ingested current baseline from describing
itself as history.

No graph path means normal behavior with no memory. A valid empty/no-match graph produces
`seen_before=False`. Missing, corrupt, hash-mismatched, or incompatible memory adds a deterministic
warning/stage detail and continues without memory; untrusted bytes are never used. MVP execution
must remain valid because historical context is advisory.

No MVP schema field is required. Reuse existing `StageRef` with stage `historical-memory` and status
`used`, `no_match`, or `unavailable`; add an `Observation(category="historical_memory", ...)`; add
the HKG store to `evidence_references` when loaded. Render a short “Historical evidence” Markdown
section from that structured data. When memory is used, include canonical-match wording, prior
cluster/member/intervention counts, provenance, and the existing non-causality disclaimer. Do not
state same defect, cause, fix, or likelihood.

## 12. Proposed CLI Surface

Only three HKG commands are required in the first implementation milestone.

### `hkg-build`

- Inputs: repeatable `--failure-run PATH`, `--failure-package PATH`, and `--mvp-demo PATH`; at least
  one source required.
- Output: `--output DIR`, default `.rtl-agent/hkg`.
- Overwrite: refuse non-empty/existing store unless `--overwrite`.
- Validation: fully validate every source and build in memory before writing.
- Output: one concise JSON object on stdout containing status, store path, graph SHA-256, source,
  node, edge, and cluster counts.

### `hkg-update`

- Inputs: `--store DIR` default `.rtl-agent/hkg` plus one or more repeatable source options.
- Output: updates the same store atomically.
- Overwrite: none; identical source is a no-op, changed same-ID source is rejected.
- Validation: validate existing store and all supplied sources before mutation.
- Output: JSON with added/no-op source IDs, graph hash, and counts.

### `hkg-inspect`

- Inputs: `--store DIR` default `.rtl-agent/hkg`.
- Output: read-only JSON status to stdout; optional `--output` report is unnecessary in v1 because
  the result is compact.
- Validation: manifest, graph hash/schema/canonical bytes/counts/IDs/endpoints/provenance. It does
  not require historical source roots to remain mounted.

Exit codes follow current CLI conventions: 0 success/valid; 1 a readable store is invalid or a
build/update integrity conflict occurs; 2 usage errors or unreadable/malformed input paths. Typer
continues to own option-syntax errors. `hkg-query` and a query language are deferred; Python query
APIs already exist.

## 13. Schema and Compatibility Analysis

**Confirmed relevant constants:** HKG 1; failure-intelligence manifest 3 (inspection supports 2/3);
failure package 1; run inspection 1; fingerprint 1; clustering 1; stimulus reduction 1;
intervention template 1; intervention manifest 1; experiment matrix 1; experiment comparison 1;
intervention ranking 1; repair suggestion 1; MVP demo 1. All are defined in their respective
`*_models.py` modules except repair suggestions in `repair_suggestions.py`.

**Safe dependencies:** manifest run/artifact IDs, run-relative paths, SHA-256 and schema versions;
package paths/hashes/run provenance; canonical/family/exact digests; stimulus/intervention/
experiment semantic digests; candidate and row IDs; target commit; observed-effect labels;
comparison schema and fields; ranking fields; MVP fixed directory layout produced by the service.

**Informal or unstable fields:** absolute run/repository/output paths; `created_at`; output-directory-
derived `demo_id`, `generation_id`, `matrix_id`, and `minimization_id`; command artifact UUIDs;
free-form rationale/summary text; ranking scores outside one MVP; `artifact_dir` unless resolved
against the matrix root; fingerprint `source_run_dir`.

**Required HKG-only migration:** advance HKG to schema 2 for source-scoped stable IDs and
`Provenance.source_id`; add a store-manifest schema 1. Update builder/query/memory together. This is
necessary because current IDs conflate independent persistent sources and current provenance cannot
identify which relocated root a relative path belongs to.

**Avoided migrations:** no changes to failure run, package, reduction, intervention, matrix,
comparison, ranking, repair, MVP, config, or supervisor schemas. Existing source artifacts are
adapted and hash-indexed at ingestion. Existing HKG schema-1 files are not rewritten in place; they
remain legacy read-only and are rebuilt from source for lifecycle use.

## 14. Failure and Recovery Behavior

**Proposed.** Validation errors name source ID, artifact ID/path, expected value, and actual value.
Unsafe absolute/`..` provenance paths are rejected. Missing or tampered new sources never change
the store. Existing store corruption prevents update and trusted-memory use.

Build/update writes temporary graph and manifest files in the destination filesystem. Failure
before manifest replacement leaves either the old valid store or an obvious graph/hash mismatch.
Recovery is explicit rebuild from source; no journal or migration engine is needed.

Historical MVP fallback differs intentionally: an invalid optional HKG records `unavailable` and a
warning, then proceeds without memory. This preserves the MVP's existing no-memory behavior while
preventing unverified history from influencing suggestions.

## 15. Test Strategy

### Layer 1: focused unit tests

Extend `tests/test_hkg.py` and add `tests/test_hkg_lifecycle.py` for:

- schema-2 scoped IDs and actual provenance artifact IDs/hashes;
- deterministic serialization independent of source order/location;
- store manifest/hash and atomic write success;
- load-time count/endpoint/provenance/schema validation;
- identical-source no-op and duplicate input;
- changed same-ID conflict with unchanged store bytes;
- two runs sharing canonical identity but retaining distinct failure nodes;
- repeated intervention/experiment occurrences scoped by MVP source;
- cluster recomputation after update;
- missing, unsafe, malformed, and hash-mismatched source rejection;
- relocated package normalization;
- lookup self-exclusion.

Extend `tests/test_mvp_demo.py` and `tests/test_repair_suggestions.py` for memory used, no match,
absent store, corrupt/incompatible store fallback, JSON/Markdown disclosure, and no affirmative
causal language. `tests/test_supervisor.py` does not need extension because supervisor enforcement
is deferred.

### Layer 2: hermetic lifecycle integration

Use the Python-backed VCD emitter pattern from
`scripts/evidence_artifact_provenance_check.py` to generate a real failure run and MVP output in a
temporary directory. Build from the run/package, update with the real MVP, reopen from the store,
repeat update, relocate package/MVP directories, tamper one artifact, and run a later MVP with the
prior store. Assert byte identity/no-op, provenance, historical suggestion input, fallback, and
unchanged target repository.

### Layer 3: one registered example check

Add `scripts/hkg_lifecycle_check.py` and register it in `scripts/check.py`. It should be hermetic and
simulator-independent, reuse the same checked-in AXI/VCD fixtures and production services, exercise
real counterfactual artifacts, print stable store/node/edge/source counts, include tamper and absent-
memory controls, and reject causal wording. Extend `scripts/hkg_failure_corpus_check.py` only for
schema-2 query compatibility; do not make its Icarus-gated corpus path the sole lifecycle proof.

## 16. Explicitly Deferred Scope

The next milestone explicitly excludes:

- real OpenAI/Anthropic/other provider integration;
- supervisor output enforcement or automatic supervisor invocation;
- automatic RTL patch generation or application;
- repair suggestions as graph entities;
- database storage, locking for concurrent writers, server, API service, or UI;
- cross-repository graph federation or remote stores;
- graph embeddings, similarity learning, advanced graph algorithms, trends, or global rankings;
- generic migration framework or automatic schema-1 graph migration;
- deletion, garbage collection, source replacement during update, or partial rollback history;
- free-form natural-language graph querying or broad `hkg-query` CLI;
- source-artifact schema changes unless implementation proves the proposed adapters impossible;
- causal/root-cause claims.

## 17. Recommended Implementation Milestone

### Persistent HKG Lifecycle and Historical MVP Integration v1

Implement one deterministic local vertical slice that persists and updates a provenance-validated
HKG from real failure-intelligence runs, relocated failure packages, and MVP counterfactual outputs;
exposes minimal build/update/inspect CLI operations; and optionally supplies prior, self-excluded
HKG memory to later MVP repair suggestions with explicit JSON/Markdown disclosure and safe
no-memory fallback.

This should remain one milestone. Splitting persistence from real ingestion would institutionalize
unsafe v0 IDs; splitting ingestion from MVP memory would leave the product path disconnected and
the lifecycle unproven. The proposed adapters, CLI, and hermetic check keep the slice bounded.

## 18. Acceptance Criteria

1. `.rtl-agent/hkg/hkg.json` and `hkg-manifest.json` are canonical, deterministic, hash-validated,
   and atomically committed.
2. HKG schema 2 uses source-scoped occurrence IDs, actual artifact IDs, source IDs, true byte
   hashes, safe source-relative paths, and validated edge endpoints/counts.
3. `hkg-build`, `hkg-update`, and `hkg-inspect` implement the exact lifecycle/exit behavior above.
4. Build/update ingest validated original runs, relocated failure packages, and real MVP output
   directories through explicit source adapters.
5. Real minimized stimulus, interventions, matrix rows/results, classifications, comparisons, and
   rankings map into the existing bounded graph vocabulary with hash-cited provenance.
6. Repair suggestions remain derived and outside the graph.
7. Same-source rebuild/update is byte-identical/no-op; changed same-ID evidence, invalid hashes,
   unsafe paths, corrupt stores, and incompatible schemas are rejected without partial writes.
8. Two same-canonical runs remain distinct occurrences in one deterministic canonical cluster.
9. Relocated packages ingest without original absolute paths.
10. `run-mvp-demo --hkg-store` loads verified history, excludes current-run evidence, passes memory
    to repair suggestions, and discloses used/no-match/unavailable state in JSON and Markdown.
11. MVP remains successful with absent, empty/no-match, corrupt, or incompatible optional memory;
    corrupt memory is never trusted.
12. Unit, hermetic integration, registered lifecycle check, full `scripts/check.py`,
    `git diff --check`, and `git status --short` validation pass.
13. No provider, network, database, simulator, mutable external repository, supervisor enforcement,
    generated patch, broad query language, or causal claim is introduced.

## 19. Expected Files to Change

Expected production changes are bounded to:

- `src/rtl_agent/hkg/models.py`
- `src/rtl_agent/hkg/builder.py`
- `src/rtl_agent/hkg/query.py`
- `src/rtl_agent/hkg/memory.py`
- `src/rtl_agent/hkg/lifecycle.py` (new)
- `src/rtl_agent/hkg/lifecycle_models.py` (new, if separating manifest models improves clarity)
- `src/rtl_agent/hkg/__init__.py`
- `src/rtl_agent/mvp_demo/service.py`
- `src/rtl_agent/mvp_demo/synthesis.py`
- `src/rtl_agent/cli.py`
- `README.md`

Expected validation changes:

- `tests/test_hkg.py`
- `tests/test_hkg_lifecycle.py` (new)
- `tests/test_mvp_demo.py`
- `tests/test_repair_suggestions.py` only if lookup-exclusion coverage is not cleaner elsewhere
- `scripts/hkg_lifecycle_check.py` (new)
- `scripts/hkg_failure_corpus_check.py`
- `scripts/check.py`

`mvp_demo_models.py`, source-artifact models/schemas, `config.py`, and `supervisor.py` should remain
unchanged unless a focused failing test proves the no-schema/no-supervisor plan impossible.

## 20. Exact Prompt for the Implementation Session

```text
Read AGENTS.md, project/current.md, the relevant HKG/MVP/provenance history and roadmap entries,
project/handoff.md only if ACTIVE, docs/architecture/pre-hkg-review.md, and
docs/architecture/persistent-hkg-lifecycle-audit.md.

Complete only the active milestone: Persistent HKG Lifecycle and Historical MVP Integration v1.

Implement the bounded vertical slice specified in the audit:

1. Add a deterministic local HKG store at .rtl-agent/hkg/ containing canonical hkg.json and
   hkg-manifest.json. Use SHA-256 over exact bytes, sorted/root-relative source artifact records,
   canonical JSON, graph-first/manifest-last atomic replacement, and strict load-time validation.
2. Advance only the HKG schema as required for source-scoped persistent identities and provenance.
   Provenance must carry a source ID, actual artifact ID, source-root-relative safe path, schema
   version, and true file-byte SHA-256. Do not place semantic fingerprint digests in content hashes.
3. Add a dedicated lifecycle service with validated adapters for original failure-intelligence run
   directories, relocated failure packages, and real MVP demo output directories. Reuse inspect_run,
   package hashes, existing typed models, and existing semantic digests. Do not add source-artifact
   schema fields unless a focused failing test proves the audit's adapter approach impossible.
4. Implement deterministic build/update/idempotence and conflict rules exactly as audited:
   identical source is a no-op; changed content under the same source identity rejects without
   writes; same-canonical failure runs remain distinct occurrences; canonical clusters recompute;
   repeated MVP evidence is source-scoped; source order and relocation do not change bytes.
5. Ingest real minimized-stimulus, intervention-template/manifest, experiment-matrix/result,
   observed-effect, comparison, and ranking evidence into the existing bounded graph vocabulary.
   Keep repair suggestions derived and out of the graph.
6. Add only hkg-build, hkg-update, and hkg-inspect CLI commands with the inputs, output paths,
   overwrite behavior, JSON summaries, validation, and exit codes specified by the audit. Do not add
   a broad hkg-query command or query language.
7. Add optional --hkg-store historical lookup to run-mvp-demo. Load verified history after the
   current fingerprint is available, exclude current-run evidence, pass the result to the existing
   generate_repair_suggestions(..., hkg_memory=...), disclose used/no-match/unavailable state in
   existing structured summary fields and Markdown, and preserve successful no-memory fallback.
   Do not wire or enforce the supervisor.
8. Add focused unit tests, hermetic lifecycle/MVP integration tests, and one registered
   scripts/hkg_lifecycle_check.py using the checked-in VCD/Python-emitter pattern. Include duplicate,
   relocation, tamper, unsafe-path, incompatible-schema, historical-use, self-exclusion, absent and
   corrupt memory, graph provenance, determinism, and non-causality assertions.

Do not implement external model providers, supervisor enforcement, patch generation, database,
server/UI, cross-repository federation, advanced graph algorithms, broad migrations, source
replacement/deletion, or natural-language querying. Do not perform unrelated refactoring.

Run focused tests while implementing. At completion run exactly:

python3 scripts/check.py
git diff --check
git status --short

Update project/history.md, project/roadmap.md, project/current.md, and project/handoff.md according
to AGENTS.md. Mark the milestone complete, set exactly one next milestone, commit the coherent
change, push the active branch, and return the standardized completion handoff with exact validation,
commit hash, branch/push status, architectural decisions, limitations, and next milestone.
```
