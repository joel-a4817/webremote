#!/usr/bin/env python3

import hashlib
import json
import plistlib
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CAPTURE = ROOT / "capture.py"
DESTINATION = ROOT / "devices" / "ipad-speaker"
REQUIRED = (
    ROOT / "request.bplist",
    ROOT / "request.json",
    ROOT / "request-structure.json",
)


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def occurrences(payload, value):
    positions = []
    position = 0
    while True:
        position = payload.find(value, position)
        if position < 0:
            return positions
        positions.append(position)
        position += 1


def main():
    if not CAPTURE.is_file():
        fail(f"Missing capture script: {CAPTURE}")

    print("iPad speaker return-route capture")
    print()
    print("Before continuing:")
    print("  1. AirPlay Music to any external receiver.")
    print("  2. Keep Music open on Now Playing.")
    print()
    print("When the native picker opens, select the local iPad speaker once.")
    print("The existing capture exits automatically after the outbound request.")
    print()

    for path in REQUIRED:
        path.unlink(missing_ok=True)

    result = subprocess.run(
        [sys.executable, "-u", str(CAPTURE)],
        cwd=ROOT,
    )

    if result.returncode != 0:
        fail(f"capture.py exited with status {result.returncode}")

    missing = [str(path) for path in REQUIRED if not path.is_file()]
    if missing:
        fail("Capture completed without files: " + ", ".join(missing))

    DESTINATION.mkdir(parents=True, exist_ok=True)

    for source in REQUIRED:
        shutil.copy2(source, DESTINATION / source.name)

    payload_path = DESTINATION / "request.bplist"
    payload = payload_path.read_bytes()

    try:
        archive = plistlib.loads(payload)
    except Exception as error:
        fail(f"Captured request is not a valid binary plist: {error}")

    known_identifiers = {
        "rt4817 base UID": b"07b32858-19ad-447c-898c-13d7f0ea07fe",
        "rt4817 legacy UID": b"07b32858-19ad-447c-898c-13d7f0ea07fe-airplay",
        "Samsung Q80 UID": b"4C:C9:5E:D9:9E:B3",
    }

    known_occurrences = {
        name: occurrences(payload, value)
        for name, value in known_identifiers.items()
    }

    report = {
        "captureType": "return-to-local-ipad-speaker",
        "capturedAtUTC": datetime.now(timezone.utc).isoformat(),
        "payloadBytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "validBinaryPlist": isinstance(archive, dict),
        "archiveKeys": sorted(archive.keys()) if isinstance(archive, dict) else [],
        "knownIdentifierOccurrences": known_occurrences,
    }

    report_path = DESTINATION / "capture-report.json"
    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print("Capture preserved:")
    print(f"  {DESTINATION}")
    print()
    print(f"Payload bytes: {report['payloadBytes']}")
    print(f"SHA-256: {report['sha256']}")
    print(f"Valid binary plist: {report['validBinaryPlist']}")
    print(f"Archive keys: {report['archiveKeys']}")
    print("Known external identifier offsets:")
    for name, positions in known_occurrences.items():
        print(f"  {name}: {positions}")
    print()
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
