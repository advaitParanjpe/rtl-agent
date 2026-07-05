# External fixture: verilog-axis (subset)

Everything under `upstream/` is **third-party code vendored verbatim** from
[alexforencich/verilog-axis](https://github.com/alexforencich/verilog-axis),
pinned to commit `48ff7a7e2ef782cf778d47910cf85835c64b1bce`, under the MIT
license (`upstream/COPYING`, Copyright (c) 2014-2018 Alex Forencich).

The snapshot is intentionally minimal: an arbitrated AXI-stream mux router path
(`axis_arb_mux.v`, which instantiates `arbiter.v`, which instantiates
`priority_encoder.v`) plus the routing demux (`axis_demux.v`). No build
systems, testbenches, or unrelated upstream files are vendored.

Rules:

- Do **not** modify files under `upstream/` — not even to make rtl-agent
  analyses succeed. `scripts/external_axi_router_repo_check.py` verifies each
  file's sha256 against `PROVENANCE.json` and fails on any drift.
- Everything *outside* `upstream/` in this directory (this README and
  `PROVENANCE.json`) is project-owned fixture material, clearly separated from
  the upstream RTL.
- The external-repository check supplies real hierarchical signal names
  directly to `map-signals`; no waveform fixture is vendored for this pilot.

Re-vendoring (network, run manually and only when deliberately updating the
pin): `python3 scripts/vendor_verilog_axis.py` refreshes `upstream/` from the
pinned commit and rewrites the digests in `PROVENANCE.json`.
