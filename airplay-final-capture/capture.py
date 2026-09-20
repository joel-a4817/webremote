#!/usr/bin/env python3

import hashlib
import json
import plistlib
import sys
import threading
from pathlib import Path

import frida


DIRECTORY = Path(__file__).resolve().parent

AGENT_PATH = (
    DIRECTORY
    / "capture-agent.js"
)

PAYLOAD_PATH = (
    DIRECTORY
    / "request.bplist"
)

METADATA_PATH = (
    DIRECTORY
    / "request.json"
)

STRUCTURE_PATH = (
    DIRECTORY
    / "request-structure.json"
)

RAW_CAPTURE_PATH = (
    DIRECTORY
    / "capture.json"
)

EXPECTED_CONTEXT = (
    "577E1BCA-2D9B-41C2-"
    "A8F8-C515CE8072D4"
)

EXPECTED_DEVICE_UID = (
    "07b32858-19ad-447c-"
    "898c-13d7f0ea07fe"
)

EXPECTED_MESSAGE_ID = (
    "216172782113783848"
)

complete = threading.Event()
captured = {}
script_error = {}


def log(text):
    print(
        text,
        flush=True,
    )


def normalize(value):
    if isinstance(value, bytes):
        return {
            "$bytesHex":
                value.hex(),
            "$length":
                len(value),
        }

    if isinstance(value, plistlib.UID):
        return {
            "$uid": value.data
        }

    if isinstance(value, dict):
        return {
            str(key):
                normalize(item)
            for key, item
            in value.items()
        }

    if isinstance(value, list):
        return [
            normalize(item)
            for item in value
        ]

    return value


def on_message(message, data):
    if message.get("type") != "send":
        script_error.update(
            message
        )

        log(
            "[agent] script error"
        )

        log(
            json.dumps(
                message,
                indent=2,
            )
        )

        complete.set()
        return

    payload = (
        message.get("payload")
        or {}
    )

    event = payload.get(
        "event",
        "(missing)",
    )

    log(
        f"[agent] {event}"
    )

    if event == "hook-unavailable":
        log(
            json.dumps(
                payload,
                indent=2,
            )
        )

    if event == "outbound-airplay-request":
        captured.update(
            payload
        )

        complete.set()


def find_music_ui_service(
    device
):
    for process in (
        device.enumerate_processes()
    ):
        if (
            process.name
            == "MusicUIService"
        ):
            return process

    return None


def main():
    log(
        "Connecting to Frida "
        "at 127.0.0.1:27042..."
    )

    device = (
        frida
        .get_device_manager()
        .add_remote_device(
            "127.0.0.1:27042"
        )
    )

    process = find_music_ui_service(
        device
    )

    if process is None:
        raise RuntimeError(
            "MusicUIService is not running. "
            "Open Music, start playback through "
            "Speaker, then open and close the "
            "native AirPlay picker once."
        )

    log(
        "Attaching to MusicUIService "
        f"PID {process.pid}..."
    )

    session = device.attach(
        process.pid
    )

    javascript = (
        AGENT_PATH.read_text(
            encoding="utf-8"
        )
    )

    script = session.create_script(
        javascript
    )

    script.on(
        "message",
        on_message,
    )

    script.load()

    log("")
    log(
        "Capture armed."
    )
    log(
        "Select rt4817 once in the "
        "native AirPlay picker."
    )
    log(
        "The capture exits automatically."
    )

    complete.wait()

    try:
        script.unload()
    finally:
        session.detach()

    if script_error:
        raise RuntimeError(
            "The Frida agent failed"
        )

    if not captured:
        raise RuntimeError(
            "No outbound AirPlay request "
            "was captured"
        )

    modification = (
        captured.get(
            "modificationData"
        )
        or {}
    )

    payload_hex = (
        modification.get("hex")
    )

    expected_length = (
        modification.get("length")
    )

    if not payload_hex:
        raise RuntimeError(
            "Captured request has no "
            "payload bytes"
        )

    payload = bytes.fromhex(
        payload_hex
    )

    if (
        len(payload)
        != expected_length
    ):
        raise RuntimeError(
            "Payload length mismatch: "
            f"{len(payload)} != "
            f"{expected_length}"
        )

    if (
        captured.get("messageID")
        != EXPECTED_MESSAGE_ID
    ):
        raise RuntimeError(
            "Unexpected XPC message ID: "
            f"{captured.get('messageID')}"
        )

    if (
        captured.get(
            "routingContextUID"
        )
        != EXPECTED_CONTEXT
    ):
        raise RuntimeError(
            "Unexpected routing context: "
            f"{captured.get('routingContextUID')}"
        )

    if not payload.startswith(
        b"bplist00"
    ):
        raise RuntimeError(
            "Payload is not a binary plist"
        )

    digest = hashlib.sha256(
        payload
    ).hexdigest()

    PAYLOAD_PATH.write_bytes(
        payload
    )

    raw_capture = dict(
        captured
    )

    raw_capture[
        "modificationData"
    ] = {
        "length":
            len(payload),
        "sha256":
            digest,
    }

    RAW_CAPTURE_PATH.write_text(
        json.dumps(
            raw_capture,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    metadata = {
        "sourceProcess":
            "MusicUIService",
        "pid":
            captured.get("pid"),
        "timestamp":
            captured.get(
                "timestamp"
            ),
        "api":
            captured.get("api"),
        "messageID":
            captured.get(
                "messageID"
            ),
        "customID":
            captured.get(
                "customID"
            ),
        "routingContextUID":
            captured.get(
                "routingContextUID"
            ),
        "expectedDeviceUID":
            EXPECTED_DEVICE_UID,
        "payloadLength":
            len(payload),
        "payloadSHA256":
            digest,
        "connection":
            captured.get(
                "connection"
            ),
        "message":
            captured.get(
                "message"
            ),
        "stack":
            captured.get(
                "stack"
            ),
    }

    METADATA_PATH.write_text(
        json.dumps(
            metadata,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    plist = plistlib.loads(
        payload
    )

    STRUCTURE_PATH.write_text(
        json.dumps(
            normalize(plist),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    structure_text = (
        STRUCTURE_PATH.read_text(
            encoding="utf-8"
        )
    )

    if (
        EXPECTED_DEVICE_UID
        not in structure_text
    ):
        log(
            "WARNING: UID was not visible "
            "in the normalized plist text."
        )

        log(
            "The raw payload was still "
            "captured intact."
        )

    log("")
    log(
        "Capture complete."
    )

    log(
        f"Payload: {PAYLOAD_PATH}"
    )

    log(
        f"Metadata: {METADATA_PATH}"
    )

    log(
        f"Structure: {STRUCTURE_PATH}"
    )

    log(
        f"Payload length: "
        f"{len(payload)} bytes"
    )

    log(
        f"Payload SHA-256: "
        f"{digest}"
    )

    log(
        f"Message ID: "
        f"{metadata['messageID']}"
    )

    log(
        f"Context: "
        f"{metadata['routingContextUID']}"
    )

    log("")
    log(
        "Caller stack:"
    )

    for frame in (
        metadata.get("stack")
        or []
    ):
        if isinstance(
            frame,
            dict,
        ):
            log(
                "  "
                + str(
                    frame.get("symbol")
                )
            )
        else:
            log(
                "  "
                + str(frame)
            )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log(
            "ERROR: "
            f"{type(error).__name__}: "
            f"{error}"
        )

        sys.exit(1)
