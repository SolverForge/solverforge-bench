#!/usr/bin/env python3
"""Generate, or check, the committed hospital-at-scale corpus.

``--check`` regenerates every instance in memory and fails unless the
committed files and manifest match byte for byte, so a generator change can
never silently alter a published instance.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hospital_scale_bench.generator import (
    GENERATOR_VERSION,
    GROUPS,
    HORIZON_DAYS,
    TIERS,
    generate,
)
from solverforge_bench.corpus import (
    encode_document,
    manifest_bytes,
    sha256_hex,
    write_or_check,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "hospital"


def render() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    entries = []
    for tier in TIERS:
        instance, witness = generate(tier)
        instance_path = f"instances/{tier.name}.json.gz"
        witness_path = f"witnesses/{tier.name}.witness.json.gz"
        files[instance_path] = encode_document(instance)
        files[witness_path] = encode_document(witness)
        entries.append(
            {
                "name": tier.name,
                "employees": tier.employees,
                "shifts": tier.shifts,
                "seed": tier.seed,
                "instance_path": instance_path,
                "instance_sha256": sha256_hex(files[instance_path]),
                "witness_path": witness_path,
                "witness_sha256": sha256_hex(files[witness_path]),
            }
        )
    files["manifest.json"] = manifest_bytes(
        {
            "description": (
                "Synthetic hospital rostering at scale, generated witness-first by "
                "hospital_scale_bench.generator. No official reference exists."
            ),
            "generator_version": GENERATOR_VERSION,
            "horizon_days": HORIZON_DAYS,
            "instances": entries,
            "groups": GROUPS,
        }
    )
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on any drift.")
    args = parser.parse_args()

    files = render()
    drift = write_or_check(DATA_DIR, files, check=args.check)
    if drift:
        for relative in drift:
            print(f"drift: {relative} does not match the generator", file=sys.stderr)
        return 1
    verb = "reproduces from the generator" if args.check else "written"
    print(f"hospital-scale corpus {verb} ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
