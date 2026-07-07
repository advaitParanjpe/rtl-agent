# Realistic failure corpus (project-authored)

Compact, project-owned RTL designs that each exercise a **different** failure
mechanism, all driven through the existing rtl-agent pipeline unchanged
(failure-intelligence run → fingerprint → stimulus minimization → generated
intervention candidates → experiment matrix → outcome classification → synthesized
debug summary). Every example shares one harness convention — a program-driven
testbench that loads the structured stimulus from `sim/stimulus.mem`
(`0x1`=send/payload, `0x2`=stall, else idle), drives the design, monitors
`payload_out` for the seeded corruption, and terminates non-zero on the fault.
The fault is a compile-time `` `ifdef INJECT_FAULT ``; `sim/run.sh` builds the
clean (passing reference) and faulted designs and runs both. The pipeline needs
no example-specific logic; `corpus.json` is the machine-readable manifest.

| Example | Failure class | Mechanism |
| --- | --- | --- |
| `fsm-sequencer` | FSM transition bug | A premature second `send` while ARMED (a protocol violation) drives an illegal FSM transition that corrupts the held payload; the FSM `state` and `payload_out` diverge. |
| `fifo-underflow` | FIFO underflow bug | Popping (`stall`) while the FIFO is empty underflows and returns undefined read data instead of a safe zero; `data_out` diverges. |
| `counter-overflow` | Counter/state-update bug | The saturating counter's boundary update corrupts the count instead of saturating; exactly the four increments to the boundary are the irreducible failing core; `count`/`payload_out` diverge. |

Each example directory contains the RTL (`rtl/`), the program-driven testbench
(`tb/`), the named simulator command (`sim/run.sh` + `rtl-agent.yaml`), and the
baseline failing stimulus (`failing-stimulus.json`). `scripts/failure_corpus_check.py`
is a gated Icarus-backed check that runs the full pipeline on every example and
asserts each completes with generated candidates and classified outcomes while
leaving the source repository byte-for-byte unchanged; it skips cleanly when the
simulator is absent.

These are demonstrations that the pipeline generalizes across failure classes,
not proofs of cause: every experiment outcome is an observed effect, never a
root-cause claim.
