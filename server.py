# -*- coding: utf-8 -*-
#!/var/jb/usr/bin/python3
import cgi
import json
import math
import os
import random
import re
import plistlib
import shutil
import subprocess
import threading
import time
import unicodedata
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MEDIACTL = "/var/jb/usr/local/bin/mediactl"
PORT = 8765
WEBREMOTE_DIR = Path(__file__).resolve().parent
WEB_ROOT = WEBREMOTE_DIR / "web"
WEB_INDEX = WEB_ROOT / "index.html"
WEB_INCLUDE_PATTERN = re.compile(r'<!--#include\s+file="([A-Za-z0-9_./-]+)"\s*-->')
WEB_MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

def read_web_text(path):
    return path.read_text(encoding="utf-8")

def render_web_page():
    page = read_web_text(WEB_INDEX)
    def include(match):
        target = (WEB_ROOT / Path(match.group(1))).resolve()
        if WEB_ROOT.resolve() not in target.parents:
            raise RuntimeError("Invalid web include path")
        return read_web_text(target)
    return WEB_INCLUDE_PATTERN.sub(include, page)

def web_asset(relative):
    target = (WEB_ROOT / relative).resolve()
    if WEB_ROOT.resolve() not in target.parents or not target.is_file():
        return None
    return target
SONOBUS_CTL = WEBREMOTE_DIR / "sonobus-settingsctl.py"
ROUTING_STATE = WEBREMOTE_DIR / "routing-state.json"
SONOBUS_PROFILES = Path("/var/mobile/webremote/sonobus-profiles.json")
SONOBUS_LOCK = threading.RLock()
MUSIC_UPLOAD_DIRECTORY = Path('/var/mobile/Media/MusicUploads')
MUSIC_IMPORT_REQUEST = Path('/var/mobile/MediaCtlMusicImport-request.plist')
MUSIC_IMPORT_RESPONSE = Path('/var/mobile/MediaCtlMusicImport-response.plist')
ALLOWED_AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.aac', '.alac', '.wav'}
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
PENDING_DUPLICATES = {}
PENDING_DUPLICATE_TTL_SECONDS = 30 * 60
PENDING_DUPLICATES_FILE = Path(
    "/var/mobile/Media/PendingMusicDuplicates.json"
)
PENDING_DUPLICATES_LOCK = threading.Lock()
FILZA_IMPORT_LOCK = threading.Lock()
MUSIC_IMPORT_JOBS = {}
MUSIC_IMPORT_JOBS_LOCK = threading.Lock()
MUSIC_UPLOAD_SESSIONS = {}
MUSIC_UPLOAD_SESSIONS_LOCK = threading.Lock()


TRANSPORT_COMMANDS = {
    "/api/play": ["play"],
    "/api/pause": ["pause"],
    "/api/toggle": ["toggle"],
    "/api/next": ["next"],
    "/api/previous": ["previous"],
}


def timeout_process_result(
    error,
    message,
):
    stdout = error.stdout or ""

    if isinstance(stdout, bytes):
        stdout = stdout.decode(
            "utf-8",
            errors="replace",
        )

    stderr = error.stderr or ""

    if isinstance(stderr, bytes):
        stderr = stderr.decode(
            "utf-8",
            errors="replace",
        )

    return subprocess.CompletedProcess(
        error.cmd,
        124,
        stdout,
        stderr.strip() or message,
    )


def execute(arguments, timeout=10):
    try:
        return subprocess.run(
            [MEDIACTL, *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return timeout_process_result(
            error,
            "mediactl timed out",
        )

def restart_filza():
    # Preserve the proven foreground Filza workflow, but wake the iPad
    # before launching so uiopen cannot remain hidden behind the lock screen.
    wake = execute(["wake-screen"], timeout=5)
    if wake.returncode != 0:
        raise RuntimeError(
            wake.stderr.strip()
            or wake.stdout.strip()
            or "Could not wake iPad before opening Filza"
        )
    time.sleep(0.45)

    # Always start bridge work from a fresh Filza process.
    process_stopped = False

    for command in (
        ("/var/jb/usr/bin/killall", "-9", "Filza"),
        ("/usr/bin/killall", "-9", "Filza"),
        ("/var/jb/usr/bin/pkill", "-9", "-x", "Filza"),
        ("/usr/bin/pkill", "-9", "-x", "Filza"),
    ):
        if not Path(command[0]).exists():
            continue

        subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
        )
        process_stopped = True
        break

    if not process_stopped:
        raise RuntimeError("Neither killall nor pkill was found")
    time.sleep(0.75)

    for executable in ("/var/jb/usr/bin/uiopen", "/usr/bin/uiopen"):
        if not Path(executable).exists():
            continue

        result = subprocess.run(
            [executable, "filza://"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or "Could not launch Filza"
            )

        # Keep Filza in the foreground and allow the injected bridge
        # observer to initialize once for the complete selected batch.
        time.sleep(2.5)
        return

    raise RuntimeError("uiopen was not found")


def bridge_request_locked(payload, timeout=20, progress=None):
    request_id = str(uuid.uuid4())
    request = dict(payload)
    request["requestID"] = request_id
    MUSIC_IMPORT_REQUEST.parent.mkdir(parents=True, exist_ok=True)
    temporary = MUSIC_IMPORT_REQUEST.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        plistlib.dump(request, handle, fmt=plistlib.FMT_BINARY)
    os.replace(temporary, MUSIC_IMPORT_REQUEST)
    try:
        MUSIC_IMPORT_RESPONSE.unlink()
    except FileNotFoundError:
        pass
    if progress is not None:
        progress("triggering-filza")
    trigger = execute(["music-import-trigger"], timeout=5)
    if trigger.returncode != 0:
        raise RuntimeError(
            trigger.stderr.strip()
            or trigger.stdout.strip()
            or "Could not trigger the Filza music bridge"
        )
    if progress is not None:
        progress("filza-importing")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with MUSIC_IMPORT_RESPONSE.open("rb") as handle:
                response = plistlib.load(handle)
        except (FileNotFoundError, OSError, plistlib.InvalidFileException):
            time.sleep(0.1)
            continue
        if response.get("requestID") != request_id:
            time.sleep(0.1)
            continue
        if not response.get("ok"):
            raise RuntimeError(response.get("error") or "Filza music operation failed")
        return response
    raise TimeoutError("Filza did not complete the music operation; it may have exited")


def bridge_request(payload, timeout=20, progress=None):
    with FILZA_IMPORT_LOCK:
        if progress is not None:
            progress("waking-ipad")
        restart_filza()
        if progress is not None:
            progress("filza-ready")
        return bridge_request_locked(payload, timeout=timeout, progress=progress)


def _set_import_job(identifier, **values):
    with MUSIC_IMPORT_JOBS_LOCK:
        job = MUSIC_IMPORT_JOBS.setdefault(identifier, {})
        job.update(values)


def _get_import_job(identifier):
    with MUSIC_IMPORT_JOBS_LOCK:
        value = MUSIC_IMPORT_JOBS.get(identifier)
        return dict(value) if isinstance(value, dict) else None

def valid_song_identifier(value):
    return (
        isinstance(value, str)
        and value.isdecimal()
        and int(value) != 0
    )


def save_pending_duplicates_locked():
    PENDING_DUPLICATES_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = PENDING_DUPLICATES_FILE.with_suffix(
        ".tmp"
    )

    temporary.write_text(
        json.dumps(
            PENDING_DUPLICATES,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    os.replace(
        temporary,
        PENDING_DUPLICATES_FILE,
    )


def load_pending_duplicates():
    try:
        payload = json.loads(
            PENDING_DUPLICATES_FILE.read_text(
                encoding="utf-8"
            )
        )
    except (
        FileNotFoundError,
        OSError,
        json.JSONDecodeError,
    ):
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    valid = {}

    for token, pending in payload.items():
        if (
            isinstance(token, str)
            and isinstance(pending, dict)
            and isinstance(pending.get("new"), dict)
            and isinstance(pending.get("existing"), dict)
            and isinstance(pending.get("playlists"), list)
            and isinstance(
                pending.get("created"),
                (int, float),
            )
        ):
            valid[token] = pending

    with PENDING_DUPLICATES_LOCK:
        PENDING_DUPLICATES.clear()
        PENDING_DUPLICATES.update(valid)


def store_pending_duplicate(token, pending):
    with PENDING_DUPLICATES_LOCK:
        PENDING_DUPLICATES[token] = pending
        save_pending_duplicates_locked()


def get_pending_duplicate(token):
    with PENDING_DUPLICATES_LOCK:
        pending = PENDING_DUPLICATES.get(token)

        if pending is None:
            raise KeyError(token)

        return dict(pending)


def complete_pending_duplicate(token):
    with PENDING_DUPLICATES_LOCK:
        PENDING_DUPLICATES.pop(token, None)
        save_pending_duplicates_locked()


def prune_pending_duplicates():
    cutoff = (
        time.time()
        - PENDING_DUPLICATE_TTL_SECONDS
    )

    with PENDING_DUPLICATES_LOCK:
        expired = [
            (
                token,
                dict(pending),
            )
            for token, pending
            in PENDING_DUPLICATES.items()
            if pending.get("created", 0) < cutoff
        ]

        for token, _pending in expired:
            PENDING_DUPLICATES.pop(
                token,
                None,
            )

        if expired:
            save_pending_duplicates_locked()

    for token, pending in expired:
        try:
            identifier = str(
                pending["new"]["id"]
            )

            remove_song_from_library(
                identifier
            )

        except Exception:
            # Keep an unresolved import managed if cleanup
            # temporarily fails. It will be retried later.
            pending["created"] = time.time()

            with PENDING_DUPLICATES_LOCK:
                PENDING_DUPLICATES[token] = pending
                save_pending_duplicates_locked()


def normalized_metadata_text(value):
    return " ".join(
        unicodedata.normalize(
            "NFKC",
            str(value or ""),
        )
        .casefold()
        .split()
    )


def duplicate_identity_text(value):
    text = normalized_metadata_text(value)
    for marker in (
        " remaster", " remastered", " edit", " version",
        " radio mix", " album mix", " single mix",
    ):
        position = text.find(marker)
        if position > 0:
            text = text[:position]
    return "".join(
        character for character in text
        if character.isalnum() or character.isspace()
    ).strip()


def song_duplicate_key(song):
    title = duplicate_identity_text(song.get("title"))
    artist = duplicate_identity_text(song.get("artist"))
    album = duplicate_identity_text(song.get("album"))
    if not title:
        return None
    return title, artist or album

def mediactl_object(arguments, timeout=15):
    result = execute(
        arguments,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "mediactl failed"
        )

    try:
        payload = json.loads(
            result.stdout
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "mediactl returned invalid JSON"
        ) from error

    if not isinstance(payload, dict):
        raise RuntimeError(
            "mediactl returned invalid data"
        )

    return payload


def library_songs():
    payload = mediactl_object(
        ["songs-json"]
    )
    songs = payload.get("songs", [])

    if not isinstance(songs, list):
        raise RuntimeError(
            "Music returned an invalid song list"
        )

    return songs


def wait_for_library_song(
    identifier,
    timeout=6.0,
):
    deadline = time.monotonic() + timeout

    while True:
        songs = library_songs()

        match = next(
            (
                song
                for song in songs
                if str(song.get("id", ""))
                == identifier
            ),
            None,
        )

        if match is not None:
            return match

        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Imported song was not returned "
                "by the Music library"
            )

        time.sleep(0.25)


def song_playlist_names(identifier):
    payload = mediactl_object([
        "song-playlists-json",
        identifier,
    ])

    playlists = payload.get(
        "playlists",
        [],
    )

    if not isinstance(playlists, list):
        raise RuntimeError(
            "Music returned invalid playlist membership"
        )

    return [
        item["name"].strip()
        for item in playlists
        if (
            isinstance(item, dict)
            and item.get("included") is True
            and isinstance(item.get("name"), str)
            and item["name"].strip()
        )
    ]


def merge_playlist_names(*collections):
    merged = []
    seen = set()

    for collection in collections:
        for value in collection:
            name = str(value).strip()

            if name and name not in seen:
                seen.add(name)
                merged.append(name)

    return merged


def add_song_to_playlists(identifier, playlists):
    for playlist in merge_playlist_names(playlists):
        result = execute([
            "song-add-to-playlist",
            identifier,
            playlist,
        ])

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or "Could not add song to "
                + playlist
            )


def remove_song_from_library(identifier):
    if not valid_song_identifier(
        str(identifier)
    ):
        raise ValueError(
            "Invalid song ID"
        )

    result = execute(
        [
            "song-remove-from-library",
            str(identifier),
        ],
        timeout=15,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or
            "Apple Music library removal failed"
        )

    try:
        payload = json.loads(
            result.stdout
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "mediactl returned invalid removal data"
        ) from error

    if not isinstance(payload, dict):
        raise RuntimeError(
            "mediactl returned invalid removal data"
        )

    return payload


def process_import_batch_job(identifier, staged_items, playlists, staging_failures):
    imported = []
    duplicates = []
    failed = list(staging_failures)
    staged_paths = [item["staging"] for item in staged_items]
    total = len(staged_items)
    try:
        def progress(status, completed=0, progress_total=None):
            _set_import_job(
                identifier,
                status=status,
                completed=completed,
                total=total if progress_total is None else progress_total,
            )

        progress("opening-filza")
        existing_songs = library_songs()
        existing_by_key = {}
        for song in existing_songs:
            key = song_duplicate_key(song)
            if key is not None:
                existing_by_key.setdefault(key, []).append(song)

        with FILZA_IMPORT_LOCK:
            progress("waking-ipad")
            restart_filza()
            progress("filza-ready")
            metadata_response = bridge_request_locked({
                "action": "metadata-batch",
                "items": [{
                    "sourcePath": str(item["staging"]),
                    "title": Path(item["filename"]).stem,
                    "filename": item["filename"],
                } for item in staged_items],
            }, timeout=max(60, total * 8), progress=lambda status: progress(status))

            metadata_results = metadata_response.get("results", [])
            if not isinstance(metadata_results, list):
                raise RuntimeError("Filza returned invalid metadata preflight data")

            # Last selected file wins for duplicate tracks inside this batch.
            candidates_by_key = {}
            unkeyed = []
            progress("resolving-duplicates")
            for index, item in enumerate(staged_items):
                result = metadata_results[index] if index < len(metadata_results) else {
                    "ok": False, "error": "No metadata result"
                }
                if not result.get("ok"):
                    failed.append({
                        "filename": item["filename"],
                        "error": str(result.get("error") or "Metadata preflight failed"),
                    })
                    continue
                metadata = {
                    "title": result.get("title", ""),
                    "artist": result.get("artist", ""),
                    "album": result.get("album", ""),
                }
                key = song_duplicate_key(metadata)
                entry = {
                    "index": index,
                    "item": item,
                    "metadata": metadata,
                    "key": key,
                    "existing": existing_by_key.get(key, []) if key is not None else [],
                }
                if key is None:
                    unkeyed.append(entry)
                else:
                    previous = candidates_by_key.get(key)
                    if previous is not None:
                        duplicates.append({
                            "filename": previous["item"]["filename"],
                            "metadata": previous["metadata"],
                            "resolution": "superseded-by-later-upload",
                        })
                    candidates_by_key[key] = entry

            approved = sorted(
                [*unkeyed, *candidates_by_key.values()],
                key=lambda entry: entry["index"],
            )
            progress("triggering-filza")
            import_response = bridge_request_locked({
                "action": "import-batch",
                "items": [{
                    "sourcePath": str(entry["item"]["staging"]),
                    "title": entry["metadata"].get("title")
                        or Path(entry["item"]["filename"]).stem,
                    "filename": entry["item"]["filename"],
                } for entry in approved],
            }, timeout=max(60, max(1, len(approved)) * 20),
               progress=lambda status: progress(status)) if approved else {"results": []}

        results = import_response.get("results", [])
        if not isinstance(results, list):
            raise RuntimeError("Filza returned invalid batch data")

        progress("verifying-results")
        successful = []
        for index, entry in enumerate(approved):
            result = results[index] if index < len(results) else {
                "ok": False, "error": "Filza returned no result"
            }
            if not result.get("ok"):
                failed.append({
                    "filename": entry["item"]["filename"],
                    "error": str(result.get("error") or "Import failed"),
                })
                continue
            song_id = str(result.get("persistentID", ""))
            if not valid_song_identifier(song_id):
                failed.append({
                    "filename": entry["item"]["filename"],
                    "error": "Import returned an invalid song ID",
                })
                continue
            successful.append((entry, result, song_id))

        progress("refreshing-library")
        imported_ids = {song_id for _entry, _result, song_id in successful}
        library_by_id = {}
        deadline = time.monotonic() + 20.0
        while imported_ids and time.monotonic() < deadline:
            library_by_id = {
                str(song.get("id", "")): song for song in library_songs()
            }
            if imported_ids.issubset(library_by_id):
                break
            time.sleep(0.5)

        for number, (entry, result, song_id) in enumerate(successful, 1):
            try:
                progress("preserving-playlists", number - 1, max(1, len(successful)))
                old_songs = entry.get("existing", [])
                inherited_playlists = []
                for old_song in old_songs:
                    old_id = str(old_song.get("id", ""))
                    if valid_song_identifier(old_id):
                        inherited_playlists = merge_playlist_names(
                            inherited_playlists,
                            song_playlist_names(old_id),
                        )
                target_playlists = merge_playlist_names(inherited_playlists, playlists)
                add_song_to_playlists(song_id, target_playlists)

                # Configure the new file first, then remove every old matching
                # library copy so the replacement is atomic from the UI's view.
                removed_ids = []
                if old_songs:
                    progress("replacing-duplicates", number - 1, max(1, len(successful)))
                for old_song in old_songs:
                    old_id = str(old_song.get("id", ""))
                    if valid_song_identifier(old_id) and old_id != song_id:
                        remove_song_from_library(old_id)
                        removed_ids.append(old_id)
                if removed_ids:
                    duplicates.append({
                        "filename": entry["item"]["filename"],
                        "metadata": entry["metadata"],
                        "resolution": "replaced-existing",
                        "removedIDs": removed_ids,
                    })

                imported_song = library_by_id.get(song_id) or {
                    "id": song_id,
                    "title": entry["metadata"].get("title", ""),
                    "artist": entry["metadata"].get("artist", ""),
                    "album": entry["metadata"].get("album", ""),
                }
                imported.append({
                    "filename": entry["item"]["filename"],
                    "song": imported_song,
                    "import": result,
                })
            except Exception as error:
                failed.append({
                    "filename": entry["item"]["filename"],
                    "error": str(error),
                })
            progress("processing-library", number, max(1, len(successful)))

        message = (
            f"Import complete: {len(imported)} imported, "
            f"{len(duplicates)} duplicates replaced or collapsed, "
            f"{len(failed)} failed"
        )
        _set_import_job(identifier, status="done", completed=total, total=total, result={
            "ok": True,
            "imported": imported,
            "duplicates": duplicates,
            "failed": failed,
            "message": message,
        })
    except Exception as error:
        _set_import_job(identifier, status="failed", error=str(error))
    finally:
        for staging in staged_paths:
            try:
                staging.unlink()
            except OSError:
                pass

def _new_upload_session(playlists):
    identifier = str(uuid.uuid4())
    with MUSIC_UPLOAD_SESSIONS_LOCK:
        MUSIC_UPLOAD_SESSIONS[identifier] = {
            "playlists": list(playlists), "items": [], "failed": [],
            "created": time.time(),
        }
    return identifier


def _get_upload_session(identifier):
    with MUSIC_UPLOAD_SESSIONS_LOCK:
        return MUSIC_UPLOAD_SESSIONS.get(identifier)


def _pop_upload_session(identifier):
    with MUSIC_UPLOAD_SESSIONS_LOCK:
        return MUSIC_UPLOAD_SESSIONS.pop(identifier, None)


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)


def sonobus_profiles():
    try:
        payload = json.loads(SONOBUS_PROFILES.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        payload = {"selected": "default", "profiles": {"default": {"name": "Default", "username": "iPad4817", "group": "rt4817-camilladsp", "passwordRequired": False}}}
    if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), dict):
        raise RuntimeError("Invalid SonoBus profile store")
    return payload


def run_sonobus(args, timeout=12):
    if not SONOBUS_CTL.is_file():
        raise RuntimeError("SonoBus controller is not installed")
    result = subprocess.run([str(Path(os.sys.executable)), str(SONOBUS_CTL), *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "SonoBus command failed")
    return result.stdout.strip()


def sonobus_state():
    output = run_sonobus(["state"], timeout=5)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = {}
        for line in output.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if value in {"true", "false"}:
                payload[key] = value == "true"
            elif value in {"1.0", "0.0"} and key.endswith(("Muted", "Solo")):
                payload[key] = value == "1.0"
            else:
                payload[key] = value
    profiles = sonobus_profiles()
    payload["profiles"] = {
        identifier: {
            "name": profile.get("name", identifier),
            "username": profile.get("username", ""),
            "group": profile.get("group", ""),
            "passwordRequired": bool(profile.get("password", "") or profile.get("passwordRequired", False)),
        }
        for identifier, profile in profiles["profiles"].items()
    }
    payload["selectedProfile"] = profiles.get("selected", "")
    running = sonobus_running()
    payload["sonobusRunning"] = running

    # Read the current route from the iPad on every state refresh. The
    # selected destination remains independent and is still loaded from
    # routing-state.json.
    try:
        airplay = mediactl_object(["airplay-state-json"], timeout=5)
        payload["airplayAvailable"] = True
        payload["airplayConnected"] = bool(
            airplay.get("connected", False)
        )
        payload["airplayName"] = str(
            airplay.get("name") or ""
        )
        payload["airplayUID"] = str(
            airplay.get("uid") or ""
        )
        payload["airplaySource"] = str(
            airplay.get("source") or ""
        )
    except RuntimeError as error:
        payload["airplayAvailable"] = False
        payload["airplayConnected"] = None
        payload["airplayName"] = ""
        payload["airplayUID"] = ""
        payload["airplaySource"] = ""
        payload["airplayError"] = str(error)
    saved_preset = routing_state().get("activePreset", "")
    payload["activePreset"] = (
        saved_preset if saved_preset in SONOBUS_PRESETS else ""
    )
    payload["savedPreset"] = saved_preset
    return payload


def apply_sonobus(profile, state, password=None, launch=True):
    args = ["apply", "--username", profile.get("username", "iPad4817"), "--group", profile.get("group", "")]
    if password is not None:
        args += ["--password", password]
    args += [
        "--send-muted", "on" if state["sendMuted"] else "off",
        "--receive-muted", "on" if state["receiveMuted"] else "off",
        "--input-muted", "on" if state["inputMuted"] else "off",
        "--monitor-solo", "on" if state["monitorSolo"] else "off",
        "--peer", state.get("peer", "rt4817"),
        "--peer-format", "5",
    ]
    if launch:
        args.append("--launch")
    return run_sonobus(args)


ROUTING_LOCK = threading.RLock()

SONOBUS_PRESETS = {
    "listen": {"airplay": False, "receive": True},
    "cast": {"airplay": True, "receive": False},
    "relay": {"airplay": True, "receive": True},
    "local": {"airplay": False, "receive": False},
}



def _command_ok(arguments, label):
    result = execute(arguments)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"{label} failed")
    return result


def apply_routing_preset(preset_name):
    """Apply the complete preset atomically; failure always returns to Local."""
    if preset_name not in SONOBUS_PRESETS:
        force_local_routing()
        raise ValueError("Unknown routing preset; restored Local")
    preset = SONOBUS_PRESETS[preset_name]
    with ROUTING_LOCK:
        try:
            store = sonobus_profiles()
            selected = store.get("selected", "default")
            profile = store["profiles"].get(selected)
            if not isinstance(profile, dict):
                raise RuntimeError("Selected SonoBus profile is missing")
            # Always reapply the full receive policy. This makes profile and
            # setting changes effective instead of trusting stale app state.
            if preset["receive"]:
                apply_sonobus(profile, {
                    "sendMuted": True, "receiveMuted": False,
                    "inputMuted": True, "monitorSolo": False,
                }, password=str(profile.get("password") or ""), launch=True)
                deadline = time.monotonic() + 8.0
                while time.monotonic() < deadline and not sonobus_running():
                    time.sleep(.2)
                if not sonobus_running():
                    raise RuntimeError("SonoBus did not start")
            else:
                stop_sonobus()
            if preset["airplay"]:
                _command_ok(["airplay-disconnect"], "AirPlay disconnect")
                time.sleep(.35)
                _command_ok(["airplay-connect-default"], "AirPlay connection")
            else:
                _command_ok(["airplay-disconnect"], "AirPlay disconnect")
            save_routing_state(preset_name)
            return preset
        except Exception:
            try:
                force_local_routing()
            except Exception:
                pass
            raise

def routing_state():
    try:
        value = json.loads(ROUTING_STATE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def save_routing_state(name):
    _atomic_json(ROUTING_STATE, {"activePreset": name})


def force_local_routing():
    """Fail closed: no saved/recognized destination means local iPad audio."""
    stop_sonobus()
    result = execute(["airplay-disconnect"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "AirPlay disconnect failed")
    save_routing_state("local")


def restore_safe_routing():
    saved = str(routing_state().get("activePreset") or "")
    # Local is intentionally restored on every server start. Unknown or stale
    # state also fails closed instead of leaving either transport connected.
    if saved not in SONOBUS_PRESETS or saved == "local":
        force_local_routing()


def executable(name):
    found = shutil.which(name)
    if found:
        return found
    for root in ("/var/jb/usr/bin", "/var/jb/usr/local/bin", "/usr/bin", "/bin"):
        item = Path(root) / name
        if item.is_file() and os.access(item, os.X_OK):
            return str(item)
    return None


def sonobus_running():
    command = executable("ps")
    if command is None:
        return False
    try:
        result = subprocess.run(
            [command, "-A"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return any(
        line.split() and line.split()[-1].rsplit("/", 1)[-1] == "SonoBus"
        for line in result.stdout.splitlines()
    )


def stop_sonobus():
    if not sonobus_running():
        return
    command = executable("killall")
    if command:
        subprocess.run([command, "SonoBus"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4, check=False)


def restart_sonobus():
    stop_sonobus()
    time.sleep(0.8)
    command = executable("uiopen")
    if not command:
        raise RuntimeError("uiopen was not found")
    subprocess.Popen([command, "sonobus://"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)



class Handler(BaseHTTPRequestHandler):
    def send_data(self, status, content_type, data):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Cache-Control",
            "no-store, no-cache, must-revalidate"
        )
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()

        try:
            self.wfile.write(data)
        except (
            BrokenPipeError,
            ConnectionResetError,
        ):
            pass

    def send_json(self, status, payload):
        self.send_data(
            status,
            "application/json; charset=utf-8",
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )

    def mediactl_json(self, arguments):
        result = execute(arguments)

        if result.returncode != 0:
            self.send_json(
                500,
                {
                    "ok": False,
                    "error": (
                        result.stderr.strip()
                        or result.stdout.strip()
                        or "mediactl failed"
                    )
                }
            )
            return

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.send_json(
                500,
                {
                    "ok": False,
                    "error": "mediactl returned invalid JSON"
                }
            )
            return

        if not isinstance(payload, dict):
            self.send_json(
                500,
                {
                    "ok": False,
                    "error":
                        "mediactl returned a non-object JSON value",
                },
            )
            return

        payload["ok"] = True
        self.send_json(200, payload)

    def read_json_body(self):
        raw_length = self.headers.get(
            "Content-Length",
            "0",
        )

        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            raise ValueError("Invalid Content-Length")

        if length < 0 or length > 1048576:
            raise ValueError("Invalid Content-Length")

        if length == 0:
            return {}

        payload = json.loads(
            self.rfile.read(length)
        )

        if not isinstance(payload, dict):
            raise ValueError(
                "JSON body must be an object"
            )

        return payload

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            self.send_data(
                200,
                "text/html; charset=utf-8",
                render_web_page().encode("utf-8"),
            )
            return

        if path.startswith("/assets/"):
            asset = web_asset(path[len("/assets/"):])
            if asset is None:
                self.send_json(404, {"ok": False, "error": "Asset not found"})
                return
            self.send_data(
                200,
                WEB_MIME_TYPES.get(asset.suffix.lower(), "application/octet-stream"),
                asset.read_bytes(),
            )
            return

        if path == "/api/music/import/status":
            identifier = query.get("id", [""])[0]
            job = _get_import_job(identifier)
            if job is None:
                self.send_json(404, {"ok": False, "error": "Import job not found"})
            else:
                self.send_json(200, {"ok": True, **job})
            return
        if path == "/api/sonobus/state":
            try:
                with SONOBUS_LOCK:
                    state = sonobus_state()
                self.send_json(200, state)
            except Exception as error:
                self.send_json(500, {"ok": False, "error": str(error)})
            return

        if path == "/api/system/now-playing":
            self.mediactl_json(["system-now-playing-json"])
            return
        if path == "/api/volume":
            self.mediactl_json(
                ["volume-json"]
            )
            return
        if path == "/api/repeat":
            self.mediactl_json(
                ["repeat-json"]
            )
            return

        if path == "/api/shuffle":
            self.mediactl_json(
                ["shuffle-json"]
            )
            return

        if path == "/api/now-playing":
            self.mediactl_json(
                ["now-playing-json"]
            )
            return

        if path == "/api/airplay/devices":
            uiopen_paths = (
                "/var/jb/usr/bin/uiopen",
                "/usr/bin/uiopen",
            )

            open_music = None

            for uiopen_path in uiopen_paths:
                if not Path(uiopen_path).exists():
                    continue

                try:
                    open_music = subprocess.run(
                        [
                            uiopen_path,
                            "music://show-now-playing",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                except subprocess.TimeoutExpired as error:
                    open_music = timeout_process_result(
                        error,
                        "uiopen timed out",
                    )
                break

            if open_music is None:
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error":
                            "uiopen was not found",
                    },
                )
                return

            if open_music.returncode != 0:
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error": (
                            open_music.stderr.strip()
                            or open_music.stdout.strip()
                            or
                            "Could not open Music "
                            "Now Playing"
                        ),
                    },
                )
                return

            # Allow Now Playing to create and attach
            # its real Music-owned MPRouteButton.
            time.sleep(1.5)

            trigger = execute(
                ["airplay-show-picker"]
            )

            if trigger.returncode != 0:
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error": (
                            trigger.stderr.strip()
                            or trigger.stdout.strip()
                            or
                            "Could not trigger Music's "
                            "native AirPlay picker"
                        ),
                    },
                )
                return

            # The native picker is now visible and
            # MusicUIService is performing discovery.
            time.sleep(2.0)

            self.mediactl_json(
                ["airplay-devices-json"]
            )
            return


        if path == "/api/song/artwork":
            identifier = query.get("id", [""])[0]
            if not valid_song_identifier(identifier):
                self.send_data(404, "image/jpeg", b"")
                return
            try:
                image = subprocess.run(
                    [MEDIACTL, "song-artwork-jpeg", identifier],
                    capture_output=True, timeout=12, check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                self.send_data(404, "image/jpeg", b"")
                return
            if image.returncode == 0 and image.stdout.startswith(b"\xff\xd8\xff"):
                self.send_data(200, "image/jpeg", image.stdout)
            else:
                self.send_data(404, "image/jpeg", b"")
            return
        if path == "/api/songs":
            self.mediactl_json(["songs-json"])
            return

        if path == "/api/song/playlists":
            identifier = query.get("id", [""])[0]
            if not valid_song_identifier(identifier):
                self.send_json(400, {"ok": False, "error": "Invalid song ID"})
                return
            self.mediactl_json(["song-playlists-json", identifier])
            return

        if path == "/api/playlists":
            self.mediactl_json(
                ["playlists-json"]
            )
            return

        if path == "/api/playlist":
            name = query.get(
                "name",
                [""],
            )[0].strip()

            if not name:
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error": "Missing playlist name"
                    }
                )
                return

            self.mediactl_json(
                [
                    "playlist-songs-json",
                    name
                ]
            )
            return

        self.send_json(
            404,
            {
                "ok": False,
                "error": "Not found"
            }
        )

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path



        if path == "/api/music/upload-session":
            try:
                payload = self.read_json_body()
                playlists = payload.get("playlists", [])
                if not isinstance(playlists, list) or not all(isinstance(v, str) and v.strip() for v in playlists):
                    raise ValueError("Invalid playlist selection")
                identifier = _new_upload_session(merge_playlist_names(playlists))
                self.send_json(200, {"ok": True, "sessionID": identifier})
            except (ValueError, json.JSONDecodeError) as error:
                self.send_json(400, {"ok": False, "error": str(error)})
            return
        if path == "/api/music/upload-file":
            parsed_query = parse_qs(parsed.query)
            identifier = parsed_query.get("session", [""])[0]
            session = _get_upload_session(identifier)
            if session is None:
                self.send_json(404, {"ok": False, "error": "Upload session not found"})
                return
            staging = None
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_UPLOAD_BYTES:
                    raise ValueError("Invalid upload size")
                form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={
                    "REQUEST_METHOD":"POST", "CONTENT_TYPE":self.headers.get("Content-Type", "")
                }, keep_blank_values=True)
                field = form["file"]
                original = Path(field.filename or "upload.m4a").name
                extension = Path(original).suffix.lower()
                if extension not in ALLOWED_AUDIO_EXTENSIONS:
                    raise ValueError("Unsupported audio file: " + original)
                MUSIC_UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
                staging = MUSIC_UPLOAD_DIRECTORY / (str(uuid.uuid4()) + extension)
                with staging.open("wb") as output:
                    shutil.copyfileobj(field.file, output)
                with MUSIC_UPLOAD_SESSIONS_LOCK:
                    current = MUSIC_UPLOAD_SESSIONS.get(identifier)
                    if current is None: raise ValueError("Upload session expired")
                    current["items"].append({"filename": original, "staging": staging})
                self.send_json(200, {"ok": True, "filename": original})
                staging = None
            except (KeyError, TypeError, ValueError, OSError) as error:
                self.send_json(400, {"ok": False, "error": str(error)})
            finally:
                if staging is not None:
                    try: staging.unlink()
                    except OSError: pass
            return
        if path == "/api/music/upload-commit":
            try:
                payload = self.read_json_body()
                session = _pop_upload_session(str(payload.get("sessionID") or ""))
                if not session or not session["items"]:
                    raise ValueError("Upload session is empty or expired")
                identifier = str(uuid.uuid4())
                _set_import_job(identifier, status="queued", completed=0, total=len(session["items"]))
                threading.Thread(target=process_import_batch_job,
                    args=(identifier, session["items"], session["playlists"], session["failed"]),
                    daemon=True, name="music-import-" + identifier[:8]).start()
                self.send_json(202, {"ok": True, "jobID": identifier, "total": len(session["items"])})
            except (ValueError, json.JSONDecodeError) as error:
                self.send_json(400, {"ok": False, "error": str(error)})
            return
        if path == "/api/songs/batch":
            try:
                payload = self.read_json_body()
                identifiers = payload.get("ids", [])
                action = payload.get("action", "")
                playlist = str(payload.get("playlist") or "").strip()
                if (not isinstance(identifiers, list) or not identifiers
                        or not all(valid_song_identifier(str(value)) for value in identifiers)
                        or action not in {"playlist-remove", "library-remove"}
                        or (action == "playlist-remove" and not playlist)):
                    raise ValueError("Invalid batch song request")
                results = []
                for value in identifiers:
                    song_id = str(value)
                    try:
                        if action == "playlist-remove":
                            result = execute(["song-remove-from-playlist", song_id, playlist])
                            if result.returncode != 0:
                                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Playlist removal failed")
                        else:
                            remove_song_from_library(song_id)
                        results.append({"id": song_id, "ok": True})
                    except Exception as error:
                        results.append({"id": song_id, "ok": False, "error": str(error)})
                succeeded = sum(1 for item in results if item["ok"])
                self.send_json(200, {"ok": True, "results": results, "succeeded": succeeded, "failed": len(results)-succeeded, "message": f"Completed {succeeded} of {len(results)} song operations"})
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                self.send_json(400, {"ok": False, "error": str(error)})
            return

        if path == "/api/music/import/decision":
            try:
                payload = self.read_json_body()
                job_id = str(payload.get("jobID") or "")
                decisions = payload.get("decisions", {})
                if not job_id or not isinstance(decisions, dict):
                    raise ValueError("Invalid duplicate decision payload")
                with MUSIC_IMPORT_JOBS_LOCK:
                    job = MUSIC_IMPORT_JOBS.get(job_id)
                    if not isinstance(job, dict) or job.get("status") != "awaiting-duplicates":
                        raise ValueError("Import job is not awaiting duplicate decisions")
                    job["decisions"] = decisions
                    job["status"] = "duplicate-decisions-received"
                self.send_json(200, {"ok": True, "message": "Duplicate choices saved"})
            except (ValueError, json.JSONDecodeError) as error:
                self.send_json(400, {"ok": False, "error": str(error)})
            return

        if path == "/api/sonobus/restart":
            try:
                active = str(routing_state().get("activePreset") or "local")
                if active in SONOBUS_PRESETS and SONOBUS_PRESETS[active]["receive"]:
                    apply_routing_preset(active)
                else:
                    restart_sonobus()
                self.send_json(200, {"ok": True, "message": "SonoBus restarted with current settings"})
            except Exception as error:
                self.send_json(500, {"ok": False, "error": str(error)})
            return
        if path.startswith("/api/sonobus/"):
            try:
                payload = self.read_json_body()
                with SONOBUS_LOCK:
                    store = sonobus_profiles()
                    profiles = store["profiles"]
                    selected = store.get("selected", "default")
                    if path == "/api/sonobus/profile/save":
                        name = str(payload.get("name") or "").strip()
                        group = str(payload.get("group") or "").strip()
                        username = str(payload.get("username") or "iPad4817").strip()
                        if not name or not group:
                            raise ValueError("Profile name and group are required")
                        identifier = str(uuid.uuid4())
                        profiles[identifier] = {
                            "name": name,
                            "username": username,
                            "group": group,
                            "password": str(payload.get("password") or ""),
                        }
                        store["selected"] = identifier
                        _atomic_json(SONOBUS_PROFILES, store)
                        message = "Default group profile saved"
                    elif path == "/api/sonobus/profile/select":
                        identifier = str(payload.get("id") or "")
                        if identifier not in profiles:
                            raise ValueError("Unknown group profile")
                        store["selected"] = identifier
                        _atomic_json(SONOBUS_PROFILES, store)
                        message = "Group profile selected"
                    elif path == "/api/sonobus/profile/delete":
                        identifier = str(payload.get("id") or "")
                        if identifier == "default":
                            raise ValueError("The default profile cannot be deleted")
                        profiles.pop(identifier, None)
                        if store.get("selected") == identifier:
                            store["selected"] = "default"
                        _atomic_json(SONOBUS_PROFILES, store)
                        message = "Group profile deleted"
                    elif path == "/api/sonobus/preset":
                        preset_name = str(payload.get("preset") or "")
                        apply_routing_preset(preset_name)
                        message = f"{preset_name.title()} routing applied"
                    else:
                        raise ValueError("Unknown SonoBus action")
                self.send_json(200, {"ok": True, "message": message, "state": sonobus_state()})
            except (ValueError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
                self.send_json(400, {"ok": False, "error": str(error)})
            return

        if path in {
            "/api/system/play",
            "/api/system/pause",
            "/api/system/toggle",
            "/api/system/next",
            "/api/system/previous",
        }:
            command = path.rsplit("/", 1)[-1]
            result = execute(["system-" + command])
            self.send_json(200 if result.returncode == 0 else 500, {
                "ok": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "error": "" if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip() or "System transport command failed"),
            })
            return
        if path == "/api/system/seek":
            try:
                payload = self.read_json_body()
                seconds = float(payload["seconds"])
                if not math.isfinite(seconds) or seconds < 0:
                    raise ValueError
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.send_json(400, {"ok": False, "error": "Invalid system playback position"})
                return
            result = execute(["system-seek", str(seconds)])
            self.send_json(200 if result.returncode == 0 else 500, {
                "ok": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "error": "" if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip() or "System seek failed"),
            })
            return
        if path == "/api/playlist/rename":
            try:
                payload = self.read_json_body()
                old_name = str(payload.get("oldName") or "").strip()
                new_name = str(payload.get("newName") or "").strip()
                if not old_name or not new_name:
                    raise ValueError("Old and new playlist names are required")
                if old_name == new_name:
                    self.send_json(200, {
                        "ok": True,
                        "oldName": old_name,
                        "name": old_name,
                        "changed": False,
                        "message": "The playlist name is unchanged",
                    })
                    return
                result = execute(["playlist-rename", old_name, new_name], timeout=75)
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Playlist rename failed")
                response = json.loads(result.stdout)
                if not isinstance(response, dict):
                    raise RuntimeError("Invalid playlist rename response")
                response["ok"] = True
                response["message"] = (
                    'Renamed "' + old_name + '" to "' + str(response.get("name") or new_name) + '".'
                )
                self.send_json(200, response)
            except (ValueError, RuntimeError, json.JSONDecodeError) as error:
                self.send_json(400, {"ok": False, "error": str(error)})
            return

        if path == "/api/playlist/create":
            try:
                payload = self.read_json_body()
                name = payload["name"]

                if (
                    not isinstance(name, str)
                    or not name.strip()
                ):
                    raise ValueError

                name = name.strip()

            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error":
                            "Invalid playlist name",
                    },
                )
                return

            self.mediactl_json([
                "playlist-create",
                name,
            ])
            return

        if path == "/api/song/play":
            try:
                payload = self.read_json_body()
                identifier = payload["id"]
                if not valid_song_identifier(identifier):
                    raise ValueError
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.send_json(400, {"ok": False, "error": "Invalid song ID"})
                return
            self.mediactl_json(["song-play", identifier])
            return

        if path == "/api/song/playlist":
            try:
                payload = self.read_json_body()
                identifier = payload["id"]
                playlist = payload["playlist"].strip()
                included = payload["included"]
                if not valid_song_identifier(identifier) or not playlist or not isinstance(included, bool):
                    raise ValueError
            except (KeyError, AttributeError, TypeError, ValueError, json.JSONDecodeError):
                self.send_json(400, {"ok": False, "error": "Invalid playlist membership request"})
                return
            command = "song-add-to-playlist" if included else "song-remove-from-playlist"
            self.mediactl_json([command, identifier, playlist])
            return

        if path == "/api/music/import/prepare":
            try:
                # Start the proven foreground bridge lifecycle before the
                # browser uploads a large multipart body.
                restart_filza()
                self.send_json(200, {"ok": True, "message": "Filza ready"})
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
                self.send_json(500, {"ok": False, "error": str(error)})
            return
        if path == "/api/music/import":
            staged_paths = []
            try:
                prune_pending_duplicates()
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_UPLOAD_BYTES:
                    raise ValueError("Invalid upload size")
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        "REQUEST_METHOD": "POST",
                        "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    },
                    keep_blank_values=True,
                )
                playlists = json.loads(form.getfirst("playlists", "[]"))
                if not isinstance(playlists, list) or not all(
                    isinstance(value, str) and value.strip() for value in playlists
                ):
                    raise ValueError("Invalid playlist selection")
                playlists = merge_playlist_names(playlists)
                fields = form["files"] if "files" in form else []
                if not isinstance(fields, list):
                    fields = [fields]
                if not fields:
                    raise ValueError("No files uploaded")
                MUSIC_UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
                staged_items = []
                staging_failures = []
                for field in fields:
                    original = Path(field.filename or "upload.m4a").name
                    try:
                        extension = Path(original).suffix.lower()
                        if extension not in ALLOWED_AUDIO_EXTENSIONS:
                            raise ValueError("Unsupported audio file: " + original)
                        staging = MUSIC_UPLOAD_DIRECTORY / (str(uuid.uuid4()) + extension)
                        with staging.open("wb") as output:
                            shutil.copyfileobj(field.file, output)
                        staged_paths.append(staging)
                        staged_items.append({"filename": original, "staging": staging})
                    except Exception as error:
                        staging_failures.append({"filename": original, "error": str(error)})
                if not staged_items:
                    self.send_json(200, {"ok": True, "imported": [], "duplicates": [], "failed": staging_failures})
                    return
                identifier = str(uuid.uuid4())
                _set_import_job(identifier, status="queued", completed=0, total=len(staged_items))
                threading.Thread(
                    target=process_import_batch_job,
                    args=(identifier, staged_items, playlists, staging_failures),
                    daemon=True,
                    name="music-import-" + identifier[:8],
                ).start()
                self.send_json(202, {"ok": True, "jobID": identifier, "status": "queued", "total": len(staged_items)})
                staged_paths = []
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as error:
                self.send_json(400, {"ok": False, "error": str(error)})
            finally:
                for staging in staged_paths:
                    try:
                        staging.unlink()
                    except OSError:
                        pass
            return
        if path == "/api/music/duplicate-resolve":
            try:
                prune_pending_duplicates()

                payload = self.read_json_body()
                token = payload["token"]
                action = payload["action"]

                if (
                    not isinstance(token, str)
                    or not token
                    or action not in {
                        "replace",
                        "remove-upload",
                    }
                ):
                    raise ValueError(
                        "Invalid duplicate decision"
                    )

                pending = get_pending_duplicate(
                    token
                )

                new_identifier = str(
                    pending["new"]["id"]
                )
                existing_identifier = str(
                    pending["existing"]["id"]
                )

                if (
                    not valid_song_identifier(
                        new_identifier
                    )
                    or not valid_song_identifier(
                        existing_identifier
                    )
                ):
                    raise ValueError(
                        "Invalid duplicate song ID"
                    )

                if action == "replace":
                    # Configure the replacement completely before
                    # removing the existing library item.
                    add_song_to_playlists(
                        new_identifier,
                        pending["playlists"],
                    )

                    remove_song_from_library(
                        existing_identifier
                    )

                    message = (
                        "Existing song replaced"
                    )

                else:
                    remove_song_from_library(
                        new_identifier
                    )

                    message = (
                        "Uploaded duplicate removed"
                    )

                # The token remains retryable until every required
                # library operation has succeeded.
                complete_pending_duplicate(
                    token
                )

                self.send_json(
                    200,
                    {
                        "ok": True,
                        "action": action,
                        "message": message,
                        "filename":
                            pending.get(
                                "filename",
                                "",
                            ),
                    },
                )

            except KeyError:
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error":
                            "Duplicate decision expired",
                    },
                )

            except (
                TypeError,
                ValueError,
                json.JSONDecodeError,
                OSError,
                RuntimeError,
                TimeoutError,
            ) as error:
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error": str(error),
                    },
                )

            return

        if path == "/api/volume":
            try:
                payload = self.read_json_body()
                percent = float(payload["percent"])

                if (
                    not math.isfinite(percent)
                    or percent < 0
                    or percent > 100
                ):
                    raise ValueError
            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error": "Invalid volume",
                    },
                )
                return

            result = execute(
                ["volume", str(percent / 100.0)]
            )
            if result.returncode != 0:
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error": (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "Volume change failed"
                        ),
                    },
                )
                return

            try:
                response = json.loads(result.stdout)
            except json.JSONDecodeError:
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error": "Invalid volume response",
                    },
                )
                return

            volume_value = (
                response.get("volume")
                if isinstance(response, dict)
                else None
            )

            percent_value = (
                response.get("percent")
                if isinstance(response, dict)
                else None
            )

            if (
                not isinstance(response, dict)
                or isinstance(volume_value, bool)
                or not isinstance(
                    volume_value,
                    (int, float),
                )
                or not math.isfinite(
                    float(volume_value)
                )
                or isinstance(percent_value, bool)
                or not isinstance(
                    percent_value,
                    int,
                )
            ):
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error":
                            "Invalid volume response schema",
                    },
                )
                return

            response["ok"] = True
            self.send_json(200, response)
            return

        if path == "/api/seek":
            try:
                payload = self.read_json_body()

                seconds = float(
                    payload["seconds"]
                )

                if (
                    not math.isfinite(seconds)
                    or seconds < 0
                ):
                    raise ValueError

            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error":
                            "Invalid playback position",
                    },
                )
                return

            result = execute(
                [
                    "seek",
                    str(seconds),
                ]
            )

            succeeded = (
                result.returncode == 0
            )

            self.send_json(
                200 if succeeded else 500,
                {
                    "ok":
                        succeeded,

                    "stdout":
                        result.stdout.strip(),

                    "error": (
                        ""
                        if succeeded
                        else (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "Seek failed"
                        )
                    ),
                },
            )
            return

        if path == "/api/playlist/play":
            try:
                payload = self.read_json_body()

                playlist = payload["playlist"]

                if (
                    not isinstance(playlist, str)
                    or not playlist.strip()
                ):
                    raise ValueError

                playlist = playlist.strip()

            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error":
                            "Invalid playlist play request",
                    },
                )
                return

            result = execute(
                [
                    "playlist-play",
                    playlist,
                ]
            )

            succeeded = (
                result.returncode == 0
            )

            self.send_json(
                200 if succeeded else 500,
                {
                    "ok":
                        succeeded,

                    "message": (
                        "Playing " + playlist
                        if succeeded
                        else ""
                    ),

                    "stdout":
                        result.stdout.strip(),

                    "error": (
                        ""
                        if succeeded
                        else (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "Playlist play failed"
                        )
                    ),
                },
            )
            return

        if path == "/api/shuffle/toggle":
            self.mediactl_json(["shuffle-toggle"])
            return

        if path == "/api/repeat/cycle":
            self.mediactl_json(
                ["repeat-cycle"]
            )
            return

        if path in TRANSPORT_COMMANDS:
            result = execute(
                TRANSPORT_COMMANDS[path]
            )

            self.send_json(
                200 if result.returncode == 0 else 500,
                {
                    "ok": result.returncode == 0,
                    "stdout": result.stdout.strip(),
                    "error": (
                        ""
                        if result.returncode == 0
                        else (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "Transport command failed"
                        )
                    ),
                }
            )
            return

        if path == "/api/airplay/connect-device":
            try:
                payload = self.read_json_body()
                uid = payload["uid"]
                name = payload["name"]

                if (
                    not isinstance(uid, str)
                    or not isinstance(name, str)
                    or not uid.strip()
                    or not name.strip()
                ):
                    raise ValueError

                uid = uid.strip()
                name = name.strip()

            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error":
                            "Invalid AirPlay device"
                    }
                )
                return

            result = execute(
                [
                    "airplay-connect",
                    uid,
                    name
                ]
            )

            succeeded = (
                result.returncode == 0
            )

            self.send_json(
                200 if succeeded else 500,
                {
                    "ok": succeeded,
                    "message": (
                        "Connected to " + name
                        if succeeded
                        else ""
                    ),
                    "stdout":
                        result.stdout.strip(),
                    "error": (
                        ""
                        if succeeded
                        else (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "AirPlay connection failed"
                        )
                    )
                }
            )
            return

        if path == "/api/airplay/default":
            try:
                payload = self.read_json_body()
                uid = payload["uid"]
                name = payload["name"]

                if (
                    not isinstance(uid, str)
                    or not isinstance(name, str)
                    or not uid.strip()
                    or not name.strip()
                ):
                    raise ValueError

                uid = uid.strip()
                name = name.strip()

            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error":
                            "Invalid AirPlay default"
                    }
                )
                return

            result = execute(
                [
                    "airplay-set-default",
                    uid,
                    name
                ]
            )

            succeeded = (
                result.returncode == 0
            )

            self.send_json(
                200 if succeeded else 500,
                {
                    "ok": succeeded,
                    "message": (
                        "Default set to " + name
                        if succeeded
                        else ""
                    ),
                    "stdout":
                        result.stdout.strip(),
                    "error": (
                        ""
                        if succeeded
                        else (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "Could not save default"
                        )
                    )
                }
            )
            return

        if path == "/api/airplay/disconnect":
            result = execute(
                ["airplay-disconnect"]
            )
            succeeded = (
                result.returncode == 0
            )
            self.send_json(
                200 if succeeded else 500,
                {
                    "ok": succeeded,
                    "message": (
                        "AirPlay disconnected"
                        if succeeded
                        else ""
                    ),
                    "stdout": result.stdout.strip(),
                    "error": (
                        ""
                        if succeeded
                        else (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "AirPlay disconnect failed"
                        )
                    ),
                },
            )
            return
        if path == "/api/airplay/connect":
            result = execute(
                ["airplay-connect-default"]
            )

            succeeded = (
                result.returncode == 0
            )

            self.send_json(
                200 if succeeded else 500,
                {
                    "ok": succeeded,
                    "message": (
                        "Connected to default AirPlay device"
                        if succeeded
                        else ""
                    ),
                    "stdout":
                        result.stdout.strip(),
                    "error": (
                        ""
                        if succeeded
                        else (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "AirPlay connection failed"
                        )
                    )
                }
            )
            return

        if path == "/api/device/home":
            result = execute(
                ["wake-screen"]
            )
            succeeded = result.returncode == 0

            self.send_json(
                200 if succeeded else 500,
                {
                    "ok": succeeded,
                    "message": (
                        "iPad awakened"
                        if succeeded
                        else ""
                    ),
                    "stdout": result.stdout.strip(),
                    "error": (
                        ""
                        if succeeded
                        else (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "Could not wake iPad"
                        )
                    ),
                },
            )
            return

        if path == "/api/music/restart":
            result = execute(
                ["restart-music"]
            )

            succeeded = (
                result.returncode == 0
            )

            self.send_json(
                200 if succeeded else 500,
                {
                    "ok": succeeded,
                    "message": (
                        "Music restarted"
                        if succeeded
                        else ""
                    ),
                    "stdout":
                        result.stdout.strip(),
                    "error": (
                        ""
                        if succeeded
                        else (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "Music restart failed"
                        )
                    )
                }
            )
            return

        if path == "/api/shuffle":
            try:
                payload = self.read_json_body()
                playlist = payload["playlist"]

                if (
                    not isinstance(playlist, str)
                    or not playlist.strip()
                ):
                    raise ValueError

                playlist = playlist.strip()

            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error": "Invalid shuffle request"
                    }
                )
                return

            result = execute(
                [
                    "playlist",
                    playlist
                ]
            )

            self.send_json(
                200 if result.returncode == 0 else 500,
                {
                    "ok": result.returncode == 0,
                    "stdout": result.stdout.strip(),
                    "error": result.stderr.strip()
                }
            )
            return

        if path == "/api/song":
            try:
                payload = self.read_json_body()
                playlist = payload["playlist"]
                identifier = payload["id"]

                if (
                    not isinstance(playlist, str)
                    or not playlist.strip()
                    or not isinstance(identifier, str)
                    or not identifier.isdecimal()
                    or int(identifier) == 0
                ):
                    raise ValueError

                playlist = playlist.strip()

            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error": "Invalid song request"
                    }
                )
                return

            result = execute(
                [
                    "song",
                    identifier,
                    playlist
                ]
            )

            self.send_json(
                200 if result.returncode == 0 else 500,
                {
                    "ok": result.returncode == 0,
                    "stdout": result.stdout.strip(),
                    "error": result.stderr.strip()
                }
            )
            return

        self.send_json(
            404,
            {
                "ok": False,
                "error": "Unknown command"
            }
        )


    def do_DELETE(self):
        path = urlparse(self.path).path

        if path == "/api/playlist/remove":
            try:
                payload = self.read_json_body()
                name = payload["name"]

                if (
                    not isinstance(name, str)
                    or not name.strip()
                ):
                    raise ValueError

                name = name.strip()

            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error":
                            "Invalid playlist name",
                    },
                )
                return

            result = execute(
                [
                    "playlist-remove",
                    name,
                ],
                timeout=40,
            )

            if result.returncode != 0:
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error": (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or
                            "Playlist removal failed"
                        ),
                    },
                )
                return

            try:
                response = json.loads(
                    result.stdout
                )
            except json.JSONDecodeError:
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error":
                            "Invalid playlist removal response",
                    },
                )
                return

            if not isinstance(response, dict):
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error":
                            "Invalid playlist removal response",
                    },
                )
                return

            response["ok"] = True
            self.send_json(
                200,
                response,
            )
            return

        if path != "/api/song/library":
            self.send_json(
                404,
                {
                    "ok": False,
                    "error": "Not found",
                },
            )
            return

        try:
            payload = self.read_json_body()
            identifier = payload["id"]
            if not valid_song_identifier(identifier):
                raise ValueError("Invalid song ID")

            response = remove_song_from_library(identifier)
            response["ok"] = True
            self.send_json(200, response)
        except Exception as error:
            self.send_json(400, {"ok": False, "error": str(error)})

    def log_message(self, format, *args):
        pass


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    restore_safe_routing()
    load_pending_duplicates()
    prune_pending_duplicates()

    server = Server(
        ("0.0.0.0", PORT),
        Handler,
    )

    print(
        f"Web remote listening on port {PORT}",
        flush=True,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
