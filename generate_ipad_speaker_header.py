#!/usr/bin/env python3
from pathlib import Path
import hashlib
import plistlib
import sys

source = Path(sys.argv[1] if len(sys.argv) > 1 else "request.bplist")
destination = Path(sys.argv[2] if len(sys.argv) > 2 else "ipad_speaker_request.h")
payload = source.read_bytes()
archive = plistlib.loads(payload)
if not isinstance(archive, dict) or archive.get("$archiver") != "NSKeyedArchiver":
    raise SystemExit("ERROR: input is not the captured NSKeyedArchiver request")
if b"Endpoint.addOutputDevices" in payload:
    raise SystemExit("ERROR: this is an external-device connect request, not the iPad speaker request")
if b"OutputContext.setOutputDevices" not in payload:
    raise SystemExit("ERROR: local-speaker operation was not found in the request")

lines = [
    "#ifndef IPAD_SPEAKER_REQUEST_H",
    "#define IPAD_SPEAKER_REQUEST_H",
    "",
    "#include <stddef.h>",
    "#include <stdint.h>",
    "",
    "static const uint8_t kIPadSpeakerModificationPayload[] = {",
]
for offset in range(0, len(payload), 12):
    chunk = payload[offset:offset + 12]
    lines.append("    " + ", ".join(f"0x{value:02x}" for value in chunk) + ",")
lines += [
    "};",
    "",
    "static const size_t kIPadSpeakerModificationPayloadLength =",
    "    sizeof(kIPadSpeakerModificationPayload);",
    "",
    "#endif",
    "",
]
destination.write_text("\n".join(lines), encoding="utf-8")
print(f"PASS: wrote exact {len(payload)}-byte capture to {destination}")
print(f"SHA-256: {hashlib.sha256(payload).hexdigest()}")
