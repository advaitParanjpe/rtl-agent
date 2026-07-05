"""Re-vendor the pinned verilog-axis snapshot (manual, network-using helper).

This script is NOT part of ``scripts/check.py`` and is never run by canonical
validation; the checked-in snapshot under
``examples/external/verilog-axis/upstream/`` keeps the default suite fully
offline. Run it manually only when deliberately updating the pin:

    python3 scripts/vendor_verilog_axis.py [--commit <sha>]

It downloads the pinned files verbatim from the upstream commit, rewrites the
sha256 digests in ``PROVENANCE.json``, and preserves the recorded upstream URL,
license, and attribution. It never modifies upstream file contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "external" / "verilog-axis"
PROVENANCE = FIXTURE / "PROVENANCE.json"
RAW_BASE = "https://raw.githubusercontent.com/alexforencich/verilog-axis"

VENDORED_FILES = [
    "COPYING",
    "rtl/arbiter.v",
    "rtl/priority_encoder.v",
    "rtl/axis_arb_mux.v",
    "rtl/axis_demux.v",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", help="Upstream commit sha to pin (default: current pin).")
    args = parser.parse_args()

    record = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    commit = args.commit or record["upstream_commit"]

    digests: dict[str, str] = {}
    for relative in VENDORED_FILES:
        url = f"{RAW_BASE}/{commit}/{relative}"
        destination = FIXTURE / "upstream" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        print(f"fetching {url}")
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            payload = response.read()
        destination.write_bytes(payload)
        digests[f"upstream/{relative}"] = hashlib.sha256(payload).hexdigest()

    record["upstream_commit"] = commit
    record["retrieved"] = date.today().isoformat()
    record["files"] = dict(sorted(digests.items()))
    PROVENANCE.write_text(json.dumps(record, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"pinned {len(digests)} files at {commit}; PROVENANCE.json updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
