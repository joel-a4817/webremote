#!/var/jb/usr/bin/python3
import cgi
import json
import math
import os
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


TRANSPORT_COMMANDS = {
    "/api/play": ["play"],
    "/api/pause": ["pause"],
    "/api/toggle": ["toggle"],
    "/api/next": ["next"],
    "/api/previous": ["previous"],
}

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">

<meta
  name="viewport"
  content="width=device-width,initial-scale=1,viewport-fit=cover"
>

<meta name="theme-color" content="#090a0f">
<meta name="apple-mobile-web-app-capable" content="yes">

<meta
  name="apple-mobile-web-app-status-bar-style"
  content="black-translucent"
>

<title>iPad Music Remote</title>

<style>
:root {
  color-scheme: dark;
  font-family:
    -apple-system,
    BlinkMacSystemFont,
    "SF Pro Display",
    sans-serif;
}

* {
  box-sizing: border-box;
  -webkit-tap-highlight-color: transparent;
}

html {
  width: 100%;
  max-width: 100%;
  overflow-x: hidden;
  overflow-y: scroll;
  overscroll-behavior-x: none;
  scrollbar-color:
    rgba(255, 255, 255, .34)
    rgba(255, 255, 255, .07);
  scrollbar-width: thin;
}

::-webkit-scrollbar {
  width: 8px;
}

::-webkit-scrollbar-track {
  background:
    rgba(255, 255, 255, .07);
}

::-webkit-scrollbar-thumb {
  border: 2px solid transparent;
  border-radius: 999px;
  background:
    rgba(255, 255, 255, .34);
  background-clip:
    padding-box;
}

::-webkit-scrollbar-thumb:active {
  background:
    rgba(255, 255, 255, .55);
  background-clip:
    padding-box;
}

body {
  width: 100%;
  max-width: 100%;
  margin: 0;
  overflow-x: hidden;
  overscroll-behavior-x: none;
  touch-action: pan-y;
  min-height: 100svh;

  padding:
    max(22px, env(safe-area-inset-top))
    18px
    max(30px, env(safe-area-inset-bottom));

  color: white;

  background:
    radial-gradient(
      circle at top,
      #44266b 0,
      #171521 42%,
      #07080b 100%
    );
}

main {
  width: min(100%, 480px);
  max-width: 100%;
  margin: 0 auto;
  overflow-x: hidden;
}

.hidden {
  display: none !important;
}

h1 {
  margin: 6px 0 20px;
  font-size: 29px;
  text-align: center;
}

.now-playing {
  min-height: 114px;
  margin-bottom: 23px;
  padding: 20px;

  border-radius: 24px;

  background: rgba(255, 255, 255, .11);

  box-shadow:
    inset 0 1px rgba(255, 255, 255, .18),
    0 14px 38px rgba(0, 0, 0, .28);

  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.now-label {
  margin-bottom: 8px;

  color: #aaa7b7;

  font-size: 12px;
  font-weight: 750;
  letter-spacing: .11em;
  text-transform: uppercase;
}

#current-title {
  font-size: 22px;
  font-weight: 750;
  line-height: 1.25;
}

#current-details {
  margin-top: 6px;

  color: #c2becb;

  font-size: 15px;
  line-height: 1.35;
}

.playback-progress {
  margin-top: 16px;
}

#playback-seek {
  --seek-progress: 0%;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;

  display: block;
  width: 100%;
  height: 26px;
  margin: 0;
  padding: 0;
  border: 0;
  box-shadow: none;
  background: transparent;
  appearance: none;
  -webkit-appearance: none;
}

#playback-seek:disabled {
  opacity: .45;
}

#playback-seek::-webkit-slider-runnable-track {
  height: 5px;
  border-radius: 999px;
  background:
    linear-gradient(
      to right,
      #ffffff 0%,
      #ffffff var(--seek-progress),
      rgba(255, 255, 255, .22)
        var(--seek-progress),
      rgba(255, 255, 255, .22) 100%
    );
}

#playback-seek::-webkit-slider-thumb {
  width: 17px;
  height: 17px;
  margin-top: -6px;
  border: 0;
  border-radius: 50%;
  background: white;
  box-shadow:
    0 2px 8px rgba(0, 0, 0, .38);
  appearance: none;
  -webkit-appearance: none;
}

.playback-times {
  display: flex;
  justify-content: space-between;
  margin-top: 1px;
  color: #aaa7b7;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.volume-control {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, .10);
}

.volume-slider-row {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) 18px;
  gap: 5px;
  align-items: center;
  width: calc(100% + 22px);
  margin-left: -11px;
}

.volume-icon {
  color: #d6d3de;
  font-size: 17px;
  line-height: 1;
  text-align: center;
  pointer-events: none;
}

#volume-slider {
  --volume-progress: 0%;
  display: block;
  width: 100%;
  min-width: 0;
  height: 44px;
  margin: 0;
  padding: 0;
  border: 0;
  box-shadow: none;
  background: transparent;
  appearance: none;
  -webkit-appearance: none;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}

#volume-slider::-webkit-slider-runnable-track {
  height: 7px;
  border-radius: 999px;
  background: linear-gradient(
    to right,
    #ffffff 0%,
    #ffffff var(--volume-progress),
    rgba(255, 255, 255, .22) var(--volume-progress),
    rgba(255, 255, 255, .22) 100%
  );
}

#volume-slider::-webkit-slider-thumb {
  width: 24px;
  height: 24px;
  margin-top: -9px;
  border: 0;
  border-radius: 50%;
  background: white;
  box-shadow: 0 2px 9px rgba(0, 0, 0, .42);
  appearance: none;
  -webkit-appearance: none;
}

#volume-slider:disabled {
  opacity: .42;
}


.controls {
  display: grid;
  grid-template-columns: 1fr 1.25fr 1fr;
  gap: 13px;
  align-items: center;
}

button {
  width: 100%;
  border: 0;

  color: white;
  background: rgba(255, 255, 255, .13);

  box-shadow:
    inset 0 1px rgba(255, 255, 255, .20),
    0 10px 28px rgba(0, 0, 0, .28);

  font: inherit;
  cursor: pointer;
}

button:active {
  transform: scale(.96);
  background: rgba(255, 255, 255, .23);
}

.media-icon {
  width: 38px;
  height: 38px;
  display: block;
  margin: auto;
  overflow: visible;
  fill: none;
  stroke: white;
  stroke-width: 2.15;
  stroke-linecap: round;
  stroke-linejoin: round;
  pointer-events: none;
}

.media-icon .icon-fill {
  fill: white;
  stroke: white;
}

#toggle .media-icon {
  width: 45px;
  height: 45px;
}

.transport {
  min-height: 82px;
  border-radius: 999px;
  font-size: 34px;
  font-family:
    "Helvetica Neue",
    Arial,
    sans-serif;
  font-variant-emoji: text;
}

#toggle {
  min-height: 108px;
  font-size: 45px;
  background: #7b5cff;
}

.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin: 32px 3px 12px; }
.section-heading .section-title { margin: 0; }
.section-subtitle { margin-top: 4px; color: #85818f; font-size: 13px; font-weight: 550; line-height: 1.35; }
.section-title {
  margin: 30px 3px 12px;

  color: #aaa6b5;

  font-size: 13px;
  font-weight: 750;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.list {
  display: grid;
  gap: 11px;
}

.playlist-row {
  display: grid;
  grid-template-columns:
    minmax(0, 1fr) 72px 72px;
  gap: 9px;
}

.playlist-button,
.song-button {
  min-height: 68px;
  padding: 13px 17px;

  border-radius: 19px;

  text-align: left;
  background: rgba(255, 255, 255, .10);
}

.playlist-button {
  display: block;
}

.playlist-name,
.song-title {
  display: block;

  font-size: 17px;
  font-weight: 700;
  line-height: 1.3;
}

.playlist-count,
.song-artist {
  display: block;
  margin-top: 4px;

  color: #aaa7b2;

  font-size: 13px;
  line-height: 1.35;
}

.header-row {
  display: grid;
  grid-template-columns: 76px 1fr 76px;
  align-items: center;

  margin-bottom: 18px;
}

.header-row h1 {
  overflow: hidden;
  margin: 0;

  font-size: 23px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.back {
  min-height: 44px;
  border-radius: 15px;

  font-size: 15px;
  font-weight: 700;
}

.system-media-card {
  position: relative;
  overflow: hidden;
  padding: 19px;
  border: 1px solid rgba(255, 255, 255, .11);
  border-radius: 24px;
  background: linear-gradient(145deg, rgba(57, 113, 204, .20), rgba(255, 255, 255, .07));
  box-shadow: inset 0 1px rgba(255, 255, 255, .17), 0 14px 34px rgba(0, 0, 0, .24);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}
.system-media-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.system-media-copy { min-width: 0; }
.system-media-badge { flex: 0 0 auto; padding: 5px 9px; border: 1px solid rgba(143, 213, 255, .22); border-radius: 999px; color: #bce8ff; background: rgba(45, 132, 210, .17); font-size: 11px; font-weight: 750; letter-spacing: .06em; text-transform: uppercase; }
.system-media-title { overflow: hidden; font-size: 19px; font-weight: 750; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
.system-media-details { min-height: 18px; margin-top: 5px; overflow: hidden; color: #bbb8c5; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.system-media-controls { display: grid; grid-template-columns: 1fr 1.25fr 1fr; gap: 11px; align-items: center; margin-top: 17px; }
.system-transport { display: grid; place-items: center; min-height: 68px; padding: 0; border-radius: 999px; background: rgba(255, 255, 255, .12); }
.system-transport .media-icon { width: 31px; height: 31px; }
#system-toggle { min-height: 82px; background: linear-gradient(145deg, #518fe9, #5262d8); }
#system-toggle .media-icon { width: 39px; height: 39px; }
.system-progress { margin-top: 13px; }
#system-playback-seek { --seek-progress: 0%; display: block; width: 100%; height: 28px; margin: 0; padding: 0; border: 0; box-shadow: none; background: transparent; appearance: none; -webkit-appearance: none; touch-action: none; }
#system-playback-seek::-webkit-slider-runnable-track { height: 5px; border-radius: 999px; background: linear-gradient(to right, #fff 0%, #fff var(--seek-progress), rgba(255,255,255,.22) var(--seek-progress), rgba(255,255,255,.22) 100%); }
#system-playback-seek::-webkit-slider-thumb { width: 18px; height: 18px; margin-top: -6.5px; border: 0; border-radius: 50%; background: white; box-shadow: 0 2px 8px rgba(0,0,0,.38); appearance: none; -webkit-appearance: none; }
#system-playback-seek:disabled { opacity: .42; }
button:focus-visible, input:focus-visible { outline: 3px solid rgba(143, 213, 255, .82); outline-offset: 3px; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition-duration: .01ms !important; animation-duration: .01ms !important; } }
.system-controls {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 11px;
  margin-top: 0;
}

.system-button {
  min-height: 58px;
  padding: 12px 14px;

  border-radius: 19px;

  font-size: 15px;
  font-weight: 750;
  line-height: 1.25;
}

#airplay-devices {
  background:
    linear-gradient(
      135deg,
      #27a9a1,
      #3971cc
    );
}

.airplay-list {
  display: grid;
  gap: 12px;
}

.airplay-device {
  padding: 15px;
  border-radius: 19px;
  background: rgba(255, 255, 255, .10);
  box-shadow:
    inset 0 1px rgba(255, 255, 255, .17),
    0 10px 28px rgba(0, 0, 0, .25);
}

.airplay-device-name {
  font-size: 17px;
  font-weight: 750;
}

.airplay-device-uid {
  margin-top: 5px;
  overflow-wrap: anywhere;
  color: #aaa7b2;
  font-size: 12px;
}

.airplay-device-default {
  margin-top: 7px;
  color: #8fd5ff;
  font-size: 13px;
  font-weight: 750;
}

.airplay-device-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
  margin-top: 13px;
}

.airplay-device-actions button {
  min-height: 48px;
  padding: 10px;
  border-radius: 15px;
  font-size: 14px;
  font-weight: 750;
}

.airplay-connect-button {
  background:
    linear-gradient(
      135deg,
      #2f8cff,
      #765cff
    );
}

.airplay-default-button {
  background:
    linear-gradient(
      135deg,
      #3a9e72,
      #277a8d
    );
}

#connect-airplay {
  background:
    linear-gradient(
      135deg,
      #2f8cff,
      #765cff
    );
}

#disconnect-airplay {
  background:
    linear-gradient(
      135deg,
      #687080,
      #343846
    );
}

#restart-music {
  background:
    linear-gradient(
      135deg,
      #ee6a36,
      #d83e63
    );
}

#home-device {
  grid-column: 1 / -1;

  background:
    linear-gradient(
      135deg,
      #343746,
      #181a22
    );
}

.system-button:disabled {
  opacity: .55;
  cursor: default;
  transform: none;
}

#status {
  min-height: 24px;
  margin-top: 17px;

  color: #aaa7b2;

  text-align: center;
  font-size: 14px;
}


/* Playlist and queue-control styles. */
.playlist-play-button,
.shuffle-button {
  width: 72px;
  min-width: 72px;
  min-height: 68px;
  padding: 8px 5px;
  border-radius: 19px;
  -webkit-appearance: none;
  appearance: none;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif !important;
  font-size: 13px !important;
  font-style: normal !important;
  font-weight: 750 !important;
  line-height: 1.15 !important;
  letter-spacing: normal !important;
  text-align: center;
  text-transform: none !important;
  white-space: nowrap;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}

.playlist-play-button {
  background: rgba(255, 255, 255, .16);
}

.shuffle-button {
  background:
    linear-gradient(
      135deg,
      #fa2d55,
      #8b5cff
    );
}

.queue-mode-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 9px;
  margin-top: 10px;
}

#repeat-mode,
#shuffle-queue {
  width: 100%;
  min-width: 0;
  min-height: 42px;
  padding: 9px 8px;
  border-radius: 14px;
  -webkit-appearance: none;
  appearance: none;
  color: #d9d6e2;
  background: rgba(255, 255, 255, .14);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif !important;
  font-size: 13px !important;
  font-style: normal !important;
  font-weight: 750 !important;
  line-height: 1.2 !important;
  letter-spacing: normal !important;
  text-align: center;
  text-transform: none !important;
  white-space: nowrap;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}

#repeat-mode.repeat-active,
#shuffle-queue.shuffle-active {
  color: white;
  background: #7b5cff;
}

#repeat-mode.control-busy,
#shuffle-queue.control-busy {
  opacity: .72;
  pointer-events: none;
}


/* Song search controls. */
.search-box {
  width: 100%;
  min-height: 46px;
  padding: 10px 14px;
  border: 1px solid rgba(255, 255, 255, .16);
  border-radius: 15px;
  outline: none;
  color: white;
  background: rgba(255, 255, 255, .10);
  font: inherit;
  font-size: 15px;
  -webkit-appearance: none;
  appearance: none;
}

.search-box::placeholder {
  color: #aaa7b2;
}

.search-box:focus {
  border-color: rgba(123, 92, 255, .85);
  box-shadow: 0 0 0 3px rgba(123, 92, 255, .18);
}

.search-results {
  display: grid;
  gap: 9px;
  margin-top: 10px;
}

.search-message {
  padding: 10px 3px;
  color: #aaa7b2;
  font-size: 13px;
  line-height: 1.4;
}


.library-launchers {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 11px;
  margin-top: 0;
}
.library-launchers button,
.upload-submit {
  min-height: 56px;
  border-radius: 18px;
  font-weight: 750;
}
#open-all-songs { background: linear-gradient(135deg, #7b5cff, #3d73dc); }
#open-upload { background: linear-gradient(135deg, #14a078, #277a8d); }
.song-management-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 52px;
  gap: 9px;
}
.playlist-song-row {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 9px;
  align-items: stretch;
}

.playlist-song-membership {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 68px;
  border-radius: 19px;
  background: rgba(255,255,255,.10);
}

.playlist-song-membership input {
  width: 24px;
  height: 24px;
  margin: 0;
  accent-color: #7b5cff;
}
.song-menu-button {
  min-height: 68px;
  border-radius: 19px;
  font-size: 24px;
}
.upload-card, .membership-card {
  padding: 18px;
  border-radius: 21px;
  background: rgba(255,255,255,.10);
}
.upload-card input[type=file] {
  width: 100%;
  margin-bottom: 14px;
  color: white;
}
.upload-file-list {
  display: grid;
  gap: 8px;
  margin: 0 0 14px;
}
.upload-file-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 34px;
  gap: 8px;
  align-items: center;
  min-height: 42px;
  padding: 7px 7px 7px 12px;
  border-radius: 13px;
  background: rgba(255,255,255,.08);
}
.upload-file-name {
  overflow: hidden;
  color: #e8e5ee;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;
  font-size: 15px;
  font-style: normal;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: normal;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.upload-file-remove {
  width: 34px;
  min-height: 34px;
  padding: 0;
  border-radius: 999px;
  color: white;
  background: rgba(255,255,255,.14);
  font-size: 19px;
  font-weight: 700;
  line-height: 1;
}
.upload-file-remove:active {
  background: rgba(216,62,99,.72);
}
.playlist-checks { display: grid; gap: 9px; margin: 12px 0; }
.playlist-check {
  display: flex;
  gap: 10px;
  align-items: center;
  min-height: 44px;
  padding: 9px 12px;
  border-radius: 14px;
  background: rgba(255,255,255,.08);
}
.destructive {
  margin-top: 16px;
  min-height: 52px;
  border-radius: 16px;
  background: linear-gradient(135deg, #d83e63, #98233d);
  font-weight: 750;
}
.upload-complete-panel {
  margin: 0 0 18px;
  padding: 15px 17px;
  border: 1px solid rgba(112, 235, 177, .30);
  border-radius: 18px;
  color: #eafff3;
  background: rgba(27, 132, 91, .24);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;
  font-size: 15px;
  font-style: normal;
  font-weight: 700;
  line-height: 1.35;
  letter-spacing: normal;
  text-align: center;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}


.playlist-management-bar {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
  margin-bottom: 12px;
}

.playlist-management-button {
  min-height: 46px;
  padding: 10px 12px;
  border-radius: 15px;
  font-size: 14px;
  font-weight: 750;
}

#playlist-add-songs {
  background:
    linear-gradient(
      135deg,
      #2f8cff,
      #765cff
    );
}

#playlist-remove {
  background:
    linear-gradient(
      135deg,
      #8e3447,
      #5e2737
    );
}

#create-playlist {
  margin: 0 0 12px;
  background:
    linear-gradient(
      135deg,
      #3a9e72,
      #277a8d
    );
}

.playlist-candidate-row {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 11px;
  align-items: center;
  min-height: 62px;
  padding: 10px 14px;
  border-radius: 17px;
  background: rgba(255, 255, 255, .10);
}

.playlist-candidate-row input {
  width: 22px;
  height: 22px;
  margin: 0;
}

.playlist-candidate-details {
  min-width: 0;
}

.playlist-candidate-title {
  display: block;
  font-size: 16px;
  font-weight: 750;
  line-height: 1.3;
}

.playlist-candidate-artist {
  display: block;
  margin-top: 3px;
  color: #aaa7b2;
  font-size: 12px;
  line-height: 1.35;
}

#playlist-add-selected {
  min-height: 52px;
  margin: 0 0 12px;
  padding: 11px 14px;
  border-radius: 17px;
  background: #7b5cff;
  font-size: 15px;
  font-weight: 750;
}


.sonobus-card{margin:18px 0;padding:18px;border:1px solid #ffffff24;border-radius:24px;background:linear-gradient(145deg,#ffffff18,#ffffff0a);box-shadow:inset 0 1px #ffffff24,0 18px 45px #0004}.sonobus-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.sonobus-head h2{margin:3px 0 12px;font-size:21px}.sonobus-kicker,.sonobus-section-label{font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#bdb7cb}.sonobus-section-label{margin:17px 2px 8px}.sonobus-grid{display:grid;gap:10px}.sonobus-grid.three{grid-template-columns:repeat(3,1fr)}.sonobus-grid.four{grid-template-columns:repeat(4,minmax(0,1fr))}.sonobus-grid.two{grid-template-columns:repeat(2,1fr)}.sonobus-grid button,.sonobus-form button,.sonobus-close{min-height:50px;border-radius:16px;background:#ffffff18;border:1px solid #ffffff14;color:#fff;font-weight:750}.sonobus-grid button.active{background:linear-gradient(135deg,#3f8eff,#865dff);box-shadow:0 9px 24px #503dd05c}.sonobus-manage{margin-top:18px}.sonobus-note{color:#b9b4c5;font-size:12px;margin:12px 2px 0}.sonobus-form{display:grid;gap:10px;margin-top:12px}.sonobus-form input{width:100%;min-height:48px;border:1px solid #ffffff1f;border-radius:14px;padding:0 14px;background:#0e1018;color:#fff}.sonobus-profile{display:flex;align-items:center;gap:10px;padding:11px 0;border-bottom:1px solid #ffffff12}.sonobus-profile-main{flex:1}.sonobus-profile-name{font-weight:800}.sonobus-profile-meta{font-size:12px;color:#b9b4c5}.sonobus-profile button{min-height:38px;padding:0 12px;border-radius:12px;background:#ffffff17;color:#fff}.sonobus-profile.selected{color:#a9d4ff}#sonobus-state-badge{padding:7px 10px;border-radius:999px;background:#ffffff16;font-size:12px;color:#c9c5d2}

#restart-sonobus.is-restarting {
  position: relative;
  color: transparent;
  pointer-events: none;
}
#restart-sonobus.is-restarting::after {
  content: "Restarting SonoBus…";
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #fff;
}
#sonobus-state-badge.is-restarting {
  border-color: rgba(255, 190, 92, 0.52);
  background: rgba(255, 159, 10, 0.16);
  color: #ffd39a;
}
</style>
</head>

<body>
<main>
  <section id="main-screen">
    <h1>iPad Music Remote</h1>
    <div id="upload-complete-panel" class="upload-complete-panel hidden" aria-live="polite"></div>

    <div class="section-heading"><div><div class="section-title">Apple Music</div><div class="section-subtitle">Library playback, queue modes and volume</div></div></div>
    <div class="now-playing">
      <div class="now-label">Now Playing</div>
      <div id="current-title">Loading…</div>
      <div id="current-details"></div>

      <div class="playback-progress">
        <input
          id="playback-seek"
          type="range"
          min="0"
          max="0"
          step="0.1"
          value="0"
          disabled
          aria-label="Playback position"
        >

        <div class="playback-times">
          <span id="playback-elapsed">0:00</span>
          <span id="playback-duration">0:00</span>
        </div>
      </div>

      <div class="volume-control">
        <div class="volume-slider-row">
          <span
            class="volume-icon"
            aria-hidden="true"
          >🔈</span>

          <input
            id="volume-slider"
            type="range"
            min="0"
            max="100"
            step="6.25"
            value="0"
            aria-label="iPad volume"
          >

          <span
            class="volume-icon"
            aria-hidden="true"
          >🔊</span>
        </div>


        <div class="queue-mode-controls">
          <button
            id="repeat-mode"
            type="button"
            aria-label="Repeat mode off"
          >
            Repeat Off
          </button>

          <button
            id="shuffle-queue"
            type="button"
            aria-label="Queue shuffle off"
          >
            Shuffle Off
          </button>
        </div>
      </div>
    </div>

    <div class="controls">
      <button
        class="transport"
        type="button"
        data-command="previous"
        aria-label="Previous track"
      >
        <svg
          class="media-icon"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path d="M6 5v14"></path>
          <path d="M18 6.5 8.5 12 18 17.5z"></path>
        </svg>
      </button>

      <button
        class="transport"
        id="toggle"
        type="button"
        data-command="toggle"
        aria-label="Play or pause"
      >
        <svg
          class="media-icon"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path class="icon-fill" d="M8 5.5 19 12 8 18.5z"></path>
        </svg>
      </button>

      <button
        class="transport"
        type="button"
        data-command="next"
        aria-label="Next track"
      >
        <svg
          class="media-icon"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path d="M18 5v14"></path>
          <path d="M6 6.5 15.5 12 6 17.5z"></path>
        </svg>
      </button>
    </div>

    <div class="section-heading"><div><div class="section-title">System Media</div><div class="section-subtitle">Control the active Control Centre media session</div></div></div>
    <div class="system-media-card">
      <div class="system-media-heading"><div class="system-media-copy"><div id="system-current-title" class="system-media-title">Loading…</div><div id="system-current-details" class="system-media-details"></div></div><span class="system-media-badge">System</span></div>
      <div class="system-media-controls">
        <button class="system-transport" type="button" data-system-command="previous" aria-label="Previous system track"><svg class="media-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5v14"></path><path d="M18 6.5 8.5 12 18 17.5z"></path></svg></button>
        <button class="system-transport" id="system-toggle" type="button" data-system-command="toggle" aria-label="Play system media"><svg class="media-icon" viewBox="0 0 24 24" aria-hidden="true"><path class="icon-fill" d="M8 5.5 19 12 8 18.5z"></path></svg></button>
        <button class="system-transport" type="button" data-system-command="next" aria-label="Next system track"><svg class="media-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 5v14"></path><path d="M6 6.5 15.5 12 6 17.5z"></path></svg></button>
      </div>
      <div class="system-progress"><input id="system-playback-seek" type="range" min="0" max="0" step="0.1" value="0" disabled aria-label="System playback position"><div class="playback-times"><span id="system-playback-elapsed">0:00</span><span id="system-playback-duration">0:00</span></div></div>
    </div>
    <div class="section-heading"><div><div class="section-title">Music Library</div><div class="section-subtitle">Browse songs or import new music</div></div></div>
    <div class="library-launchers">
      <button id="open-all-songs" type="button">All Songs</button>
      <button id="open-upload" type="button">Upload Music</button>
    </div>

    <div class="section-heading"><div><div class="section-title">Playlists</div><div class="section-subtitle">Play, shuffle and manage your collections</div></div></div>
    <button
      id="create-playlist"
      class="playlist-management-button"
      type="button"
    >
      New Playlist
    </button>

    <div
      id="playlist-list"
      class="list"
    ></div>
    <div class="section-heading"><div><div class="section-title">AirPlay &amp; Device</div><div class="section-subtitle">Choose an output, restart Music or wake the iPad</div></div></div>
    <div class="system-controls">

      <button
        id="connect-airplay"
        class="system-button"
        type="button"
      >
        Connect AirPlay
      </button>

      <button
        id="airplay-devices"
        class="system-button"
        type="button"
      >
        AirPlay Devices
      </button>

      <button
        id="restart-music"
        class="system-button"
        type="button"
      >
        Restart Music
      </button>

      <button
        id="disconnect-airplay"
        class="system-button"
        type="button"
      >
        Disconnect AirPlay
      </button>
      <button id="restart-sonobus" class="system-button" type="button">Restart SonoBus</button>
      <button
        id="home-device"
        class="system-button"
        type="button"
      >
        Wake iPad
      </button>
    </div>


    <section id="sonobus-home" class="sonobus-card">
      <div class="sonobus-head"><div><div class="sonobus-kicker">SonoBus & Home Routing</div><h2>Audio destinations</h2></div><span id="sonobus-state-badge">Loading</span></div>
      <div class="sonobus-section-label">Playing from iPad</div>
      <div class="sonobus-grid four">
        <button data-sonobus-preset="ipad-local">iPad</button><button data-sonobus-preset="ipad-laptop">Laptop</button><button data-sonobus-preset="ipad-both">Both</button><button data-sonobus-preset="ipad-external">External</button>
      </div>
      <div class="sonobus-section-label">Playing from laptop</div>
      <div class="sonobus-grid four">
        <button data-sonobus-preset="laptop-ipad">iPad</button><button data-sonobus-preset="laptop-local">Laptop</button><button data-sonobus-preset="laptop-both">Both</button><button data-sonobus-preset="laptop-external">External</button>
      </div>
      <div class="sonobus-grid sonobus-manage">
        <button id="sonobus-groups-open">Group Profiles</button>
      </div>
    </section>
    <section id="sonobus-groups" class="sonobus-card hidden">
      <div class="sonobus-head"><h2>Group Profiles</h2><button class="sonobus-close" data-sonobus-close>Done</button></div>
      <div id="sonobus-profile-list"></div>
      <div class="sonobus-form">
        <input id="sonobus-profile-name" placeholder="Profile name"><input id="sonobus-username" placeholder="Username" value="iPad4817">
        <input id="sonobus-group" placeholder="Group name"><input id="sonobus-password" type="password" autocomplete="new-password" placeholder="Password, if required">
        <button id="sonobus-profile-save">Save profile</button>
      </div>
    </section>

  </section>

  <section
    id="playlist-screen"
    class="hidden"
  >
    <div class="header-row">
      <button
        id="back"
        class="back"
        type="button"
      >
        Back
      </button>

      <h1 id="playlist-title">
        Playlist
      </h1>

      <div></div>
    </div>


    <div class="playlist-management-bar">
      <button
        id="playlist-add-songs"
        class="playlist-management-button"
        type="button"
      >
        Add Songs
      </button>

      <button
        id="playlist-remove"
        class="playlist-management-button"
        type="button"
      >
        Remove Playlist
      </button>
    </div>

    <input
      id="playlist-song-search"
      class="search-box"
      type="search"
      inputmode="search"
      autocomplete="off"
      placeholder="Search this playlist"
      aria-label="Search songs in this playlist"
    >

    <div
      id="playlist-search-message"
      class="search-message hidden"
      aria-live="polite"
    ></div>

    <div
      id="song-list"
      class="list"
    ></div>
  </section>


  <section id="all-songs-screen" class="hidden">
    <div class="header-row">
      <button id="all-songs-back" class="back" type="button">Back</button>
      <h1>All Songs</h1><div></div>
    </div>
    <input id="global-song-search" class="search-box" type="search"
      inputmode="search" autocomplete="off" placeholder="Search all songs"
      aria-label="Search all songs">
    <div id="global-song-results" class="search-results" aria-live="polite"></div>
    <div id="all-song-list" class="list"></div>
  </section>

  <section id="upload-screen" class="hidden">
    <div class="header-row">
      <button id="upload-back" class="back" type="button">Back</button>
      <h1>Upload Music</h1><div></div>
    </div>
    <div class="upload-card">
      <input id="music-files" type="file" multiple
        accept="audio/mp4,audio/m4a,audio/mpeg,audio/aac,audio/wav,.m4a,.mp3,.aac,.alac,.wav">
      <div id="upload-file-list" class="upload-file-list" aria-live="polite"></div>
      <div class="playlist-checks" id="upload-playlist-checks"></div>
      <button id="upload-submit" class="upload-submit" type="button">Import Selected Files</button>
    </div>
  </section>

  <section id="song-manage-screen" class="hidden">
    <div class="header-row">
      <button id="song-manage-back" class="back" type="button">Back</button>
      <h1 id="song-manage-title">Song</h1><div></div>
    </div>
    <div class="membership-card">
      <div id="song-manage-details" class="song-artist"></div>
      <div id="song-playlist-checks" class="playlist-checks"></div>
      <button id="remove-from-library" class="destructive" type="button">Remove from Library</button>
    </div>
  </section>

  <section
    id="airplay-screen"
    class="hidden"
  >
    <div class="header-row">
      <button
        id="airplay-back"
        class="back"
        type="button"
      >
        Back
      </button>

      <h1>
        AirPlay Devices
      </h1>

      <div></div>
    </div>

    <div
      id="airplay-list"
      class="airplay-list"
    ></div>
  </section>


  <section
    id="playlist-add-screen"
    class="hidden"
  >
    <div class="header-row">
      <button
        id="playlist-add-back"
        class="back"
        type="button"
      >
        Back
      </button>

      <h1 id="playlist-add-title">
        Add Songs
      </h1>

      <div></div>
    </div>

    <input
      id="playlist-add-search"
      class="search-box"
      type="search"
      inputmode="search"
      autocomplete="off"
      placeholder="Search available songs"
      aria-label="Search songs not in this playlist"
    >

    <div
      id="playlist-add-list"
      class="list"
    ></div>

    <button
      id="playlist-add-selected"
      type="button"
    >
      Add Selected Songs
    </button>
  </section>

  
<div id="status"></div>
</main>

<script>
const mainScreen =
  document.querySelector("#main-screen");

const playlistScreen =
  document.querySelector("#playlist-screen");

const playlistList =
  document.querySelector("#playlist-list");

const songList =
  document.querySelector("#song-list");

const playlistTitle =
  document.querySelector("#playlist-title");

const statusBox =
  document.querySelector("#status");

const uploadCompletePanel =
  document.querySelector("#upload-complete-panel");

const currentTitle =
  document.querySelector("#current-title");

const currentDetails =
  document.querySelector("#current-details");
const playbackSeek =
  document.querySelector(
    "#playback-seek"
  );

const playbackElapsed =
  document.querySelector(
    "#playback-elapsed"
  );

const playbackDuration =
  document.querySelector(
    "#playback-duration"
  );
const volumeSlider =
  document.querySelector(
    "#volume-slider"
  );
const repeatModeButton =
  document.querySelector(
    "#repeat-mode"
  );
const shuffleQueueButton =
  document.querySelector(
    "#shuffle-queue"
  );

const toggleButton =
  document.querySelector("#toggle");
const systemCurrentTitle = document.querySelector("#system-current-title");
const systemCurrentDetails = document.querySelector("#system-current-details");
const systemToggleButton = document.querySelector("#system-toggle");
const systemPlaybackSeek = document.querySelector("#system-playback-seek");
const systemPlaybackElapsed = document.querySelector("#system-playback-elapsed");
const systemPlaybackDuration = document.querySelector("#system-playback-duration");

const connectAirPlayButton =
  document.querySelector(
    "#connect-airplay"
  );

const airPlayDevicesButton =
  document.querySelector(
    "#airplay-devices"
  );

const airPlayScreen =
  document.querySelector(
    "#airplay-screen"
  );

const airPlayList =
  document.querySelector(
    "#airplay-list"
  );

const airPlayBackButton =
  document.querySelector(
    "#airplay-back"
  );

const restartMusicButton =
  document.querySelector(
    "#restart-music"
  );

const disconnectAirPlayButton =
  document.querySelector(
    "#disconnect-airplay"
  );
const homeDeviceButton =
  document.querySelector(
    "#home-device"
  );

const globalSongSearch =
  document.querySelector("#global-song-search");
const globalSongResults =
  document.querySelector("#global-song-results");
const playlistSongSearch =
  document.querySelector("#playlist-song-search");
const playlistSearchMessage =
  document.querySelector("#playlist-search-message");

let allPlaylists = [];
let currentPlaylistName = "";
let playlistAddCandidates = [];

function normalizeSearchText(value) {
  return String(value || "")
    .normalize("NFKD")
    .toLocaleLowerCase();
}


function filterCurrentPlaylistSongs() {
  const query = normalizeSearchText(
    playlistSongSearch.value.trim()
  );
  let visible = 0;

  for (const row of songList.querySelectorAll(
    ".playlist-song-row"
  )) {
    const button =
      row.querySelector(".song-button");

    const show = !query
      || normalizeSearchText(
          button?.textContent
        ).includes(query);

    row.classList.toggle(
      "hidden",
      !show
    );

    if (show) {
      visible += 1;
    }
  }

  playlistSearchMessage.classList.toggle(
    "hidden",
    visible !== 0 || !query
  );
  playlistSearchMessage.textContent =
    visible === 0 && query
      ? "No matching songs in this playlist"
      : "";
}


playlistSongSearch.addEventListener(
  "input",
  filterCurrentPlaylistSongs
);

const ICONS = {
  play: `
    <svg
      class="media-icon"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        class="icon-fill"
        d="M8 5.5 19 12 8 18.5z"
      ></path>
    </svg>
  `,

  pause: `
    <svg
      class="media-icon"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <rect
        class="icon-fill"
        x="7"
        y="5.5"
        width="3.5"
        height="13"
        rx="1"
      ></rect>

      <rect
        class="icon-fill"
        x="13.5"
        y="5.5"
        width="3.5"
        height="13"
        rx="1"
      ></rect>
    </svg>
  `
};

let seekInteractionActive = false;
let liveSeekTimer = null;
let liveSeekInFlight = false;
let pendingLiveSeek = null;


function formatPlaybackTime(value) {
  const totalSeconds =
    Number.isFinite(Number(value))
      ? Math.max(
          0,
          Math.floor(Number(value))
        )
      : 0;

  const hours =
    Math.floor(totalSeconds / 3600);

  const minutes =
    Math.floor(
      (totalSeconds % 3600) / 60
    );

  const seconds =
    totalSeconds % 60;

  if (hours > 0) {
    return (
      hours
      + ":"
      + String(minutes).padStart(2, "0")
      + ":"
      + String(seconds).padStart(2, "0")
    );
  }

  return (
    minutes
    + ":"
    + String(seconds).padStart(2, "0")
  );
}


function updateSeekDisplay(
  currentTime,
  duration
) {
  const safeDuration =
    Number.isFinite(Number(duration))
      ? Math.max(0, Number(duration))
      : 0;

  const safeCurrentTime =
    Number.isFinite(Number(currentTime))
      ? Math.max(
          0,
          Math.min(
            Number(currentTime),
            safeDuration > 0
              ? safeDuration
              : Number(currentTime)
          )
        )
      : 0;

  if (!seekInteractionActive) {
    playbackSeek.max =
      String(safeDuration);

    playbackSeek.value =
      String(safeCurrentTime);
  }

  const displayedTime =
    seekInteractionActive
      ? Number(playbackSeek.value)
      : safeCurrentTime;

  const progress =
    safeDuration > 0
      ? (
          displayedTime
          / safeDuration
          * 100
        )
      : 0;

  playbackSeek.style.setProperty(
    "--seek-progress",
    progress + "%"
  );

  playbackElapsed.textContent =
    formatPlaybackTime(displayedTime);

  playbackDuration.textContent =
    formatPlaybackTime(safeDuration);

  playbackSeek.disabled =
    safeDuration <= 0;
}


async function sendLiveSeek(
  seconds
) {
  if (liveSeekInFlight) {
    pendingLiveSeek = seconds;
    return;
  }

  liveSeekInFlight = true;

  try {
    await readJSON(
      "/api/seek",
      {
        method: "POST",
        headers: {
          "Content-Type":
            "application/json"
        },
        body: JSON.stringify({
          seconds: seconds
        })
      }
    );

  } catch (error) {
    setStatus(error.message);

  } finally {
    liveSeekInFlight = false;

    if (pendingLiveSeek !== null) {
      const nextSeek =
        pendingLiveSeek;

      pendingLiveSeek = null;

      sendLiveSeek(nextSeek);
    }
  }
}


function scheduleLiveSeek() {
  const seconds =
    Number(playbackSeek.value);

  if (liveSeekTimer !== null) {
    clearTimeout(liveSeekTimer);
  }

  liveSeekTimer = setTimeout(
    () => {
      liveSeekTimer = null;
      sendLiveSeek(seconds);
    },
    120
  );
}


async function commitPlaybackSeek() {
  const seconds =
    Number(playbackSeek.value);

  if (liveSeekTimer !== null) {
    clearTimeout(liveSeekTimer);
    liveSeekTimer = null;
  }

  pendingLiveSeek = null;

  try {
    await readJSON(
      "/api/seek",
      {
        method: "POST",
        headers: {
          "Content-Type":
            "application/json"
        },
        body: JSON.stringify({
          seconds: seconds
        })
      }
    );

  } catch (error) {
    setStatus(error.message);

  } finally {
    seekInteractionActive = false;

    setTimeout(
      updateNowPlaying,
      150
    );
  }
}


playbackSeek.addEventListener(
  "pointerdown",
  () => {
    seekInteractionActive = true;
  }
);


playbackSeek.addEventListener(
  "touchstart",
  () => {
    seekInteractionActive = true;
  },
  {
    passive: true
  }
);


playbackSeek.addEventListener(
  "input",
  () => {
    seekInteractionActive = true;

    updateSeekDisplay(
      Number(playbackSeek.value),
      Number(playbackSeek.max)
    );

    scheduleLiveSeek();
  }
);


playbackSeek.addEventListener(
  "change",
  commitPlaybackSeek
);


let volumeTimer = null;
let volumeWriteInFlight = false;
let pendingVolumeWrite = null;
let volumeDragActive = false;
let volumePollAbortController = null;
let lastQueuedVolumeSent = null;

function clampVolume(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? Math.max(0, Math.min(100, numeric))
    : 0;
}

function drawVolume(value) {
  const percent = clampVolume(value);
  volumeSlider.value = String(percent);
  volumeSlider.style.setProperty(
    "--volume-progress",
    percent + "%"
  );
}

function reportedIPadVolume(result) {
  /*
   * The normalized 0..1 system-volume value is the source of truth.
   * percent is used only as a compatibility fallback.
   */
  const normalized = Number(result.volume);

  if (Number.isFinite(normalized)) {
    return clampVolume(normalized * 100);
  }

  return clampVolume(result.percent);
}

async function loadVolumeState() {
  if (
    volumeDragActive
    || volumeWriteInFlight
    || pendingVolumeWrite !== null
  ) {
    return;
  }

  if (volumePollAbortController !== null) {
    volumePollAbortController.abort();
  }

  const controller = new AbortController();
  volumePollAbortController = controller;

  try {
    const result = await readJSON(
      "/api/volume?time=" + Date.now(),
      {
        signal: controller.signal
      }
    );

    if (
      controller.signal.aborted
      || volumeDragActive
      || volumeWriteInFlight
      || pendingVolumeWrite !== null
    ) {
      return;
    }

    drawVolume(
      reportedIPadVolume(result)
    );
    volumeSlider.disabled = false;
  } catch (error) {
    if (error.name !== "AbortError") {
      setStatus(error.message);
    }
  } finally {
    if (volumePollAbortController === controller) {
      volumePollAbortController = null;
    }
  }
}

async function sendVolume(value) {
  const requested = clampVolume(value);

  if (volumeWriteInFlight) {
    pendingVolumeWrite = requested;
    return;
  }

  if (volumePollAbortController !== null) {
    volumePollAbortController.abort();
    volumePollAbortController = null;
  }

  volumeWriteInFlight = true;

  try {
    await readJSON(
      "/api/volume",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          percent: requested
        })
      }
    );
  } catch (error) {
    setStatus(error.message);
  } finally {
    volumeWriteInFlight = false;

    if (pendingVolumeWrite !== null) {
      const next = pendingVolumeWrite;
      pendingVolumeWrite = null;
      sendVolume(next);
      return;
    }

    /* The next draw comes only from a fresh iPad volume read. */
    setTimeout(loadVolumeState, 180);
  }
}

function queueVolume() {
  const requested = clampVolume(
    volumeSlider.value
  );

  /* Native slider feedback is allowed only while the user interacts. */
  drawVolume(requested);

  if (volumeTimer !== null) {
    clearTimeout(volumeTimer);
  }

  volumeTimer = setTimeout(
    () => {
      volumeTimer = null;
      lastQueuedVolumeSent = requested;
      sendVolume(requested);
    },
    90
  );
}

function beginVolumeDrag() {
  if (volumePollAbortController !== null) {
    volumePollAbortController.abort();
    volumePollAbortController = null;
  }

  volumeDragActive = true;
}

function finishVolumeDrag() {
  if (!volumeDragActive) {
    return;
  }

  volumeDragActive = false;

  if (volumeTimer !== null) {
    clearTimeout(volumeTimer);
    volumeTimer = null;
  }

  const finalValue = clampVolume(
    volumeSlider.value
  );

  if (lastQueuedVolumeSent !== finalValue) {
    sendVolume(finalValue);
  }

  lastQueuedVolumeSent = null;
}

volumeSlider.addEventListener(
  "pointerdown",
  beginVolumeDrag
);
volumeSlider.addEventListener(
  "touchstart",
  beginVolumeDrag,
  { passive: true }
);
volumeSlider.addEventListener(
  "input",
  queueVolume
);
volumeSlider.addEventListener(
  "change",
  finishVolumeDrag
);
volumeSlider.addEventListener(
  "pointerup",
  finishVolumeDrag
);
volumeSlider.addEventListener(
  "touchend",
  finishVolumeDrag
);

function renderShuffleMode(enabled) {
  const active = Boolean(enabled);
  shuffleQueueButton.classList.toggle(
    "shuffle-active",
    active
  );
  shuffleQueueButton.textContent =
    active ? "Shuffle On" : "Shuffle Off";
  shuffleQueueButton.setAttribute(
    "aria-label",
    active ? "Queue shuffle on" : "Queue shuffle off"
  );
}

let shuffleReadInFlight = false;

async function loadShuffleMode() {
  if (shuffleReadInFlight) {
    return;
  }

  shuffleReadInFlight = true;

  try {
    const result = await readJSON(
      "/api/shuffle?time=" + Date.now()
    );
    renderShuffleMode(result.enabled);
  } catch (error) {
    setStatus(error.message);
  } finally {
    shuffleReadInFlight = false;
  }
}

let shuffleToggleInFlight = false;

shuffleQueueButton.addEventListener(
  "click",
  async () => {
    if (shuffleToggleInFlight) {
      return;
    }

    shuffleToggleInFlight = true;
    shuffleQueueButton.classList.add("control-busy");
    shuffleQueueButton.setAttribute("aria-busy", "true");

    try {
      const result = await readJSON(
        "/api/shuffle/toggle",
        { method: "POST" }
      );
      renderShuffleMode(result.enabled);
      setTimeout(loadShuffleMode, 300);
    } catch (error) {
      setStatus(error.message);
    } finally {
      shuffleToggleInFlight = false;
      shuffleQueueButton.classList.remove("control-busy");
      shuffleQueueButton.removeAttribute("aria-busy");
    }
  }
);

function renderRepeatMode(mode) {
  const normalized =
    mode === "all" || mode === "one"
      ? mode
      : "off";

  repeatModeButton.dataset.mode = normalized;
  repeatModeButton.classList.toggle(
    "repeat-active",
    normalized !== "off"
  );

  if (normalized === "all") {
    repeatModeButton.textContent = "Repeat All";
    repeatModeButton.setAttribute(
      "aria-label",
      "Repeat all enabled"
    );
    return;
  }

  if (normalized === "one") {
    repeatModeButton.textContent = "Repeat 1";
    repeatModeButton.setAttribute(
      "aria-label",
      "Repeat one enabled"
    );
    return;
  }

  repeatModeButton.textContent = "Repeat Off";
  repeatModeButton.setAttribute(
    "aria-label",
    "Repeat mode off"
  );
}


let repeatReadInFlight = false;

async function loadRepeatMode() {
  if (repeatReadInFlight) {
    return;
  }

  repeatReadInFlight = true;

  try {
    const result = await readJSON(
      "/api/repeat?time=" + Date.now()
    );
    renderRepeatMode(result.mode);
  } catch (error) {
    setStatus(error.message);
  } finally {
    repeatReadInFlight = false;
  }
}


let repeatToggleInFlight = false;

repeatModeButton.addEventListener(
  "click",
  async () => {
    if (repeatToggleInFlight) {
      return;
    }

    repeatToggleInFlight = true;
    repeatModeButton.classList.add("control-busy");
    repeatModeButton.setAttribute("aria-busy", "true");

    try {
      const result = await readJSON(
        "/api/repeat/cycle",
        { method: "POST" }
      );
      renderRepeatMode(result.mode);
      setTimeout(loadRepeatMode, 200);
    } catch (error) {
      setStatus(error.message);
    } finally {
      repeatToggleInFlight = false;
      repeatModeButton.classList.remove("control-busy");
      repeatModeButton.removeAttribute("aria-busy");
    }
  }
);

function setToggleState(isPlaying) {
  toggleButton.innerHTML =
    isPlaying
      ? ICONS.pause
      : ICONS.play;

  toggleButton.setAttribute(
    "aria-label",
    isPlaying ? "Pause" : "Play"
  );
}

let statusTimer = null;

function setStatus(text) {
  statusBox.textContent = text;

  if (statusTimer !== null) {
    clearTimeout(statusTimer);
  }

  if (text) {
    statusTimer = setTimeout(() => {
      if (statusBox.textContent === text) {
        statusBox.textContent = "";
      }
    }, 2400);
  }
}

async function readJSON(url, options = {}) {
  const response = await fetch(url, {
    cache: "no-store",
    ...options
  });

  let result;

  try {
    result = await response.json();
  } catch {
    throw new Error("Server returned invalid data");
  }

  if (!response.ok || result.ok === false) {
    throw new Error(
      result.error || "Request failed"
    );
  }

  return result;
}

let nowPlayingReadInFlight = false;

async function updateNowPlaying() {
  if (nowPlayingReadInFlight) {
    return;
  }

  nowPlayingReadInFlight = true;

  try {
    const data =
      await readJSON("/api/now-playing");

    if (!data.available) {
      currentTitle.textContent =
        "Nothing playing";

      currentDetails.textContent = "";

      setToggleState(false);
      updateSeekDisplay(0, 0);

      return;
    }

    setToggleState(data.playing);

    currentTitle.textContent =
      data.title || "Unknown title";

    const details = [
      data.artist,
      data.album
    ].filter(Boolean);

    currentDetails.textContent =
      details.join(" • ");
    updateSeekDisplay(
      Number(data.currentTime || 0),
      Number(data.duration || 0)
    );

  } catch {
    currentTitle.textContent =
      "Now Playing unavailable";

    currentDetails.textContent = "";

    setToggleState(false);
    updateSeekDisplay(0, 0);
  } finally {
    nowPlayingReadInFlight = false;
  }
}

let systemSeekActive = false;
let systemSeekTimer = null;
function drawSystemSeek(currentTime, duration) {
  const total = Number.isFinite(Number(duration)) ? Math.max(0, Number(duration)) : 0;
  const position = Number.isFinite(Number(currentTime)) ? Math.max(0, Math.min(Number(currentTime), total > 0 ? total : Number(currentTime))) : 0;
  if (!systemSeekActive) {
    systemPlaybackSeek.max = String(total);
    systemPlaybackSeek.value = String(position);
  }
  const shown = systemSeekActive ? Number(systemPlaybackSeek.value) : position;
  systemPlaybackSeek.style.setProperty("--seek-progress", (total > 0 ? shown / total * 100 : 0) + "%");
  systemPlaybackElapsed.textContent = formatPlaybackTime(shown);
  systemPlaybackDuration.textContent = formatPlaybackTime(total);
  systemPlaybackSeek.disabled = total <= 0;
}
function setSystemToggleState(isPlaying) {
  systemToggleButton.innerHTML = isPlaying ? ICONS.pause : ICONS.play;
  systemToggleButton.setAttribute("aria-label", isPlaying ? "Pause system media" : "Play system media");
}
async function updateSystemNowPlaying() {
  try {
    const data = await readJSON("/api/system/now-playing");
    setSystemToggleState(Boolean(data.playing));
    if (!data.available) {
      systemCurrentTitle.textContent = "Nothing playing";
      systemCurrentDetails.textContent = "";
      drawSystemSeek(0, 0);
      return;
    }
    systemCurrentTitle.textContent = data.title || "Unknown title";
    systemCurrentDetails.textContent = [data.artist, data.album].filter(Boolean).join(" • ");
    drawSystemSeek(data.currentTime, data.duration);
  } catch {
    setSystemToggleState(false);
    systemCurrentTitle.textContent = "System Now Playing unavailable";
    systemCurrentDetails.textContent = "";
    drawSystemSeek(0, 0);
  }
}
async function sendSystemCommand(command) {
  try {
    await readJSON("/api/system/" + command, {method: "POST"});
    setStatus("System command sent");
    setTimeout(updateSystemNowPlaying, 200);
  } catch (error) { setStatus(error.message); }
}
async function sendSystemSeek() {
  if (systemSeekTimer !== null) clearTimeout(systemSeekTimer);
  systemSeekTimer = null;
  try {
    await readJSON("/api/system/seek", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({seconds: Number(systemPlaybackSeek.value)})
    });
  } catch (error) { setStatus(error.message); }
  finally { systemSeekActive = false; setTimeout(updateSystemNowPlaying, 150); }
}
systemPlaybackSeek.addEventListener("pointerdown", () => { systemSeekActive = true; });
systemPlaybackSeek.addEventListener("touchstart", () => { systemSeekActive = true; }, {passive: true});
systemPlaybackSeek.addEventListener("input", () => {
  systemSeekActive = true;
  drawSystemSeek(systemPlaybackSeek.value, systemPlaybackSeek.max);
  if (systemSeekTimer !== null) clearTimeout(systemSeekTimer);
  systemSeekTimer = setTimeout(sendSystemSeek, 120);
});
systemPlaybackSeek.addEventListener("change", sendSystemSeek);
for (const button of document.querySelectorAll("[data-system-command]")) {
  button.addEventListener("click", () => sendSystemCommand(button.dataset.systemCommand));
}

async function sendTransport(command) {
  try {
    await readJSON(
      "/api/" + command,
      {
        method: "POST"
      }
    );

    setStatus("Done");

    setTimeout(
      updateNowPlaying,
      250
    );


  } catch (error) {
    setStatus(error.message);
  }
}

async function runSystemAction(
  button,
  endpoint,
  workingLabel,
  successLabel
) {
  if (button.disabled) {
    return;
  }

  const normalLabel =
    button.textContent;

  button.disabled = true;
  button.textContent = workingLabel;

  try {
    const result =
      await readJSON(
        endpoint,
        {
          method: "POST"
        }
      );

    setStatus(
      result.message || successLabel
    );

    setTimeout(
      updateNowPlaying,
      700
    );

  } catch (error) {
    setStatus(error.message);

  } finally {
    button.disabled = false;
    button.textContent =
      normalLabel;
  }
}

async function connectAirPlayDevice(
  device
) {
  try {
    const result =
      await readJSON(
        "/api/airplay/connect-device",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json"
          },
          body: JSON.stringify({
            uid: device.uid,
            name: device.name
          })
        }
      );

    setStatus(
      result.message
      || "Connected to "
      + device.name
    );

  } catch (error) {
    setStatus(
      error.message
    );
  }
}


async function setDefaultAirPlayDevice(
  device
) {
  try {
    const result =
      await readJSON(
        "/api/airplay/default",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json"
          },
          body: JSON.stringify({
            uid: device.uid,
            name: device.name
          })
        }
      );

    setStatus(
      result.message
      || "Default set to "
      + device.name
    );

    await loadAirPlayDevices();

  } catch (error) {
    setStatus(
      error.message
    );
  }
}


async function loadAirPlayDevices() {
  airPlayList.innerHTML = "";

  try {
    const result =
      await readJSON(
        "/api/airplay/devices"
      );

    const devices =
      Array.isArray(result.devices)
        ? result.devices
        : [];

    if (
      devices.length === 0
    ) {
      airPlayList.textContent =
        "No external AirPlay devices are "
        + "currently exposed by Music. "
        + "Open Music's AirPlay picker once "
        + "to refresh the list.";

      return;
    }

    for (
      const device
      of devices
    ) {
      const card =
        document.createElement("div");

      card.className =
        "airplay-device";

      const name =
        document.createElement("div");

      name.className =
        "airplay-device-name";

      name.textContent =
        device.name;

      const uid =
        document.createElement("div");

      uid.className =
        "airplay-device-uid";

      uid.textContent =
        device.uid;

      card.append(
        name,
        uid
      );

      if (device.default) {
        const defaultLabel =
          document.createElement("div");

        defaultLabel.className =
          "airplay-device-default";

        defaultLabel.textContent =
          "Default";

        card.appendChild(
          defaultLabel
        );
      }

      const actions =
        document.createElement("div");

      actions.className =
        "airplay-device-actions";

      const connectButton =
        document.createElement("button");

      connectButton.className =
        "airplay-connect-button";
      connectButton.type = "button";

      connectButton.textContent =
        "Connect";

      connectButton.addEventListener(
        "click",
        () => {
          connectAirPlayDevice(
            device
          );
        }
      );

      const defaultButton =
        document.createElement("button");

      defaultButton.className =
        "airplay-default-button";
      defaultButton.type = "button";

      defaultButton.textContent =
        device.default
          ? "Default"
          : "Set Default";

      defaultButton.disabled =
        Boolean(device.default);

      defaultButton.addEventListener(
        "click",
        () => {
          setDefaultAirPlayDevice(
            device
          );
        }
      );

      actions.append(
        connectButton,
        defaultButton
      );

      card.appendChild(
        actions
      );

      airPlayList.appendChild(
        card
      );
    }

  } catch (error) {
    setStatus(
      error.message
    );
  }
}


async function playPlaylistOrdered(name) {
  try {
    await readJSON(
      "/api/playlist/play",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          playlist: name
        })
      }
    );
    setStatus("Playing " + name);
    setTimeout(updateNowPlaying, 400);
  } catch (error) {
    setStatus(error.message);
  }
}

async function shufflePlaylist(name) {
  try {
    await readJSON(
      "/api/shuffle",
      {
        method: "POST",
        headers: {
          "Content-Type":
            "application/json"
        },
        body: JSON.stringify({
          playlist: name
        })
      }
    );

    setStatus(
      "Shuffling " + name
    );

    setTimeout(
      updateNowPlaying,
      400
    );

  } catch (error) {
    setStatus(error.message);
  }
}

async function loadPlaylists() {
  playlistList.innerHTML = "";
  allPlaylists = [];

  try {
    const data =
      await readJSON("/api/playlists");

    allPlaylists = Array.isArray(data.playlists)
      ? data.playlists
      : [];

    if (allPlaylists.length === 0) {
      playlistList.textContent =
        "No playlists available";

      return;
    }

    for (const playlist of allPlaylists) {
      const row =
        document.createElement("div");

      row.className = "playlist-row";

      const openButton =
        document.createElement("button");

      openButton.className =
        "playlist-button";
      openButton.type = "button";

      const name =
        document.createElement("span");

      name.className =
        "playlist-name";

      name.textContent =
        playlist.name;

      const count =
        document.createElement("span");

      count.className =
        "playlist-count";

      count.textContent =
        playlist.count +
        (
          playlist.count === 1
            ? " song"
            : " songs"
        );

      openButton.append(
        name,
        count
      );

      openButton.addEventListener(
        "click",
        () => {
          openPlaylist(playlist.name);
        }
      );

      const plainPlayButton =
        document.createElement("button");
      plainPlayButton.className =
        "playlist-play-button";
      plainPlayButton.type = "button";
      plainPlayButton.textContent = "Play";
      plainPlayButton.setAttribute(
        "aria-label",
        "Play " + playlist.name
      );
      plainPlayButton.addEventListener(
        "click",
        () => {
          playPlaylistOrdered(playlist.name);
        }
      );
      const shuffleButton =
        document.createElement("button");

      shuffleButton.className =
        "shuffle-button";
      shuffleButton.type = "button";

      shuffleButton.textContent = "Shuffle";

      shuffleButton.setAttribute(
        "aria-label",
        "Shuffle " + playlist.name
      );

      shuffleButton.addEventListener(
        "click",
        () => {
          shufflePlaylist(playlist.name);
        }
      );

      row.append(
        openButton,
        plainPlayButton,
        shuffleButton
      );

      playlistList.appendChild(row);
    }

  } catch (error) {
    setStatus(error.message);
  }
}

async function openPlaylist(name) {
  songList.innerHTML = "";
  playlistSongSearch.value = "";
  playlistSearchMessage.textContent = "";
  playlistSearchMessage.classList.add("hidden");

  currentPlaylistName = name;
  playlistTitle.textContent = name;

  mainScreen.classList.add("hidden");
  playlistScreen.classList.remove("hidden");

  setStatus("Loading playlist…");

  try {
    const data =
      await readJSON(
        "/api/playlist?name=" +
        encodeURIComponent(name)
      );

    statusBox.textContent = "";

    const songs =
      Array.isArray(data.songs)
        ? data.songs
        : [];

    if (songs.length === 0) {
      songList.textContent =
        "This playlist has no available songs";

      return;
    }

    for (const song of songs) {
      const row =
        document.createElement("div");

      row.className =
        "playlist-song-row";

      const membership =
        document.createElement("label");

      membership.className =
        "playlist-song-membership";

      const checkbox =
        document.createElement("input");

      checkbox.type = "checkbox";
      checkbox.checked = true;

      checkbox.setAttribute(
        "aria-label",
        "Keep "
        + (song.title || "song")
        + " in "
        + name
      );

      checkbox.addEventListener(
        "change",
        async () => {
          if (checkbox.checked) {
            return;
          }

          checkbox.disabled = true;

          try {
            await readJSON(
              "/api/song/playlist",
              {
                method: "POST",
                headers: {
                  "Content-Type":
                    "application/json"
                },
                body: JSON.stringify({
                  id: song.id,
                  playlist: name,
                  included: false
                })
              }
            );

            row.remove();

            if (
              songList.querySelectorAll(
                ".playlist-song-row"
              ).length === 0
            ) {
              songList.textContent =
                "This playlist has no available songs";
            }

            setStatus(
              "Removed from " + name
            );

            await loadPlaylists();

          } catch (error) {
            checkbox.checked = true;
            checkbox.disabled = false;
            setStatus(error.message);
          }
        }
      );

      membership.appendChild(
        checkbox
      );

      const button =
        document.createElement("button");

      button.className =
        "song-button";

      button.type = "button";

      const title =
        document.createElement("span");

      title.className =
        "song-title";

      title.textContent =
        song.title || "Unknown title";

      const artist =
        document.createElement("span");

      artist.className =
        "song-artist";

      artist.textContent = [
        song.artist,
        song.album
      ].filter(Boolean).join(" • ");

      button.append(
        title,
        artist
      );

      button.addEventListener(
        "click",
        async () => {
          try {
            await readJSON(
              "/api/song",
              {
                method: "POST",
                headers: {
                  "Content-Type":
                    "application/json"
                },
                body: JSON.stringify({
                  playlist: name,
                  id: song.id
                })
              }
            );

            setStatus(
              "Playing "
              + (
                song.title
                || "selected song"
              )
            );

            setTimeout(
              updateNowPlaying,
              350
            );

          } catch (error) {
            setStatus(error.message);
          }
        }
      );

      row.append(
        membership,
        button
      );

      songList.appendChild(row);
    }

  } catch (error) {
    setStatus(error.message);
  }
}

document
  .querySelector("#back")
  .addEventListener(
    "click",
    () => {
      playlistScreen
        .classList
        .add("hidden");

      mainScreen
        .classList
        .remove("hidden");

      updateNowPlaying();
    }
  );

for (
  const button
  of document.querySelectorAll(
    "[data-command]"
  )
) {
  button.addEventListener(
    "click",
    () => {
      sendTransport(
        button.dataset.command
      );
    }
  );
}

airPlayDevicesButton.addEventListener(
  "click",
  () => {
    mainScreen.classList.add(
      "hidden"
    );

    playlistScreen.classList.add(
      "hidden"
    );

    airPlayScreen.classList.remove(
      "hidden"
    );

    loadAirPlayDevices();
  }
);

airPlayBackButton.addEventListener(
  "click",
  () => {
    airPlayScreen.classList.add(
      "hidden"
    );

    mainScreen.classList.remove(
      "hidden"
    );

    updateNowPlaying();
  }
);

connectAirPlayButton.addEventListener(
  "click",
  () => {
    runSystemAction(
      connectAirPlayButton,
      "/api/airplay/connect",
      "Connecting…",
      "Connected to default AirPlay device"
    );
  }
);

disconnectAirPlayButton.addEventListener(
  "click",
  () => {
    runSystemAction(
      disconnectAirPlayButton,
      "/api/airplay/disconnect",
      "Disconnecting…",
      "AirPlay disconnected"
    );
  }
);
restartMusicButton.addEventListener(
  "click",
  () => {
    runSystemAction(
      restartMusicButton,
      "/api/music/restart",
      "Restarting…",
      "Music restarted"
    );
  }
);

homeDeviceButton.addEventListener(
  "click",
  () => {
    runSystemAction(
      homeDeviceButton,
      "/api/device/home",
      "Waking…",
      "iPad awakened"
    );
  }
);


const allSongsScreen = document.querySelector('#all-songs-screen');
const uploadScreen = document.querySelector('#upload-screen');
const songManageScreen = document.querySelector('#song-manage-screen');
const allSongList = document.querySelector('#all-song-list');
const uploadPlaylistChecks = document.querySelector('#upload-playlist-checks');
const songPlaylistChecks = document.querySelector('#song-playlist-checks');
const musicFiles = document.querySelector('#music-files');
const uploadFileList = document.querySelector('#upload-file-list');
let selectedUploadFiles = [];
let allSongs = [];
let selectedManagedSong = null;

function uploadFileKey(file) {
  return [file.name, file.size, file.lastModified].join('::');
}

function renderSelectedUploadFiles() {
  uploadFileList.innerHTML = '';

  for (const file of selectedUploadFiles) {
    const row = document.createElement('div');
    row.className = 'upload-file-row';

    const name = document.createElement('div');
    name.className = 'upload-file-name';
    name.textContent = file.name;
    name.title = file.name;

    const remove = document.createElement('button');
    remove.className = 'upload-file-remove';
    remove.type = 'button';
    remove.textContent = '×';
    remove.setAttribute('aria-label', 'Remove ' + file.name + ' from upload');
    remove.addEventListener('click', () => {
      const key = uploadFileKey(file);
      selectedUploadFiles = selectedUploadFiles.filter(
        candidate => uploadFileKey(candidate) !== key
      );
      renderSelectedUploadFiles();
    });

    row.append(name, remove);
    uploadFileList.appendChild(row);
  }
}

musicFiles.addEventListener('change', () => {
  const known = new Set(selectedUploadFiles.map(uploadFileKey));
  for (const file of musicFiles.files) {
    const key = uploadFileKey(file);
    if (!known.has(key)) {
      known.add(key);
      selectedUploadFiles.push(file);
    }
  }
  musicFiles.value = '';
  renderSelectedUploadFiles();
});

function showOnly(screen) {
  for (const section of [
    mainScreen,
    playlistScreen,
    airPlayScreen,
    allSongsScreen,
    uploadScreen,
    songManageScreen,
    playlistAddScreen
  ]) {
    section.classList.toggle('hidden', section !== screen);
  }
}

function createSongManagementRow(song) {
  const row = document.createElement('div');
  row.className = 'song-management-row';
  const play = document.createElement('button');
  play.className = 'song-button';
  play.type = 'button';
  play.innerHTML = '<span class="song-title"></span><span class="song-artist"></span>';
  play.querySelector('.song-title').textContent = song.title || 'Unknown title';
  play.querySelector('.song-artist').textContent = [song.artist, song.album].filter(Boolean).join(' • ');
  play.addEventListener('click', async () => {
    try {
      await readJSON('/api/song/play', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id:song.id})});
      setStatus('Playing ' + (song.title || 'selected song'));
      setTimeout(updateNowPlaying, 350);
    } catch (error) { setStatus(error.message); }
  });
  const menu = document.createElement('button');
  menu.className = 'song-menu-button';
  menu.type = 'button';
  menu.textContent = '⋯';
  menu.setAttribute('aria-label', 'Manage ' + (song.title || 'song'));
  menu.addEventListener('click', () => openSongManager(song));
  row.append(play, menu);
  return row;
}

function renderAllSongs() {
  const query = normalizeSearchText(globalSongSearch.value.trim());
  allSongList.innerHTML = '';
  const matches = allSongs.filter(song => normalizeSearchText([song.title, song.artist, song.album].filter(Boolean).join(' ')).includes(query));
  globalSongResults.textContent = matches.length ? '' : 'No matching songs';
  for (const song of matches) allSongList.appendChild(createSongManagementRow(song));
}

async function loadAllSongs() {
  const response = await readJSON('/api/songs');
  allSongs = Array.isArray(response.songs) ? response.songs : [];
  renderAllSongs();
}

globalSongSearch.addEventListener('input', renderAllSongs);

document.querySelector('#open-all-songs').addEventListener('click', async () => {
  showOnly(allSongsScreen);
  try { await loadAllSongs(); } catch (error) { setStatus(error.message); }
});
document.querySelector('#all-songs-back').addEventListener('click', () => showOnly(mainScreen));

document.querySelector('#open-upload').addEventListener('click', () => {
  showOnly(uploadScreen);
  uploadPlaylistChecks.innerHTML = '';
  for (const playlist of allPlaylists) {
    const label = document.createElement('label');
    label.className = 'playlist-check';
    label.innerHTML = '<input type="checkbox"><span></span>';
    label.querySelector('input').value = playlist.name;
    label.querySelector('span').textContent = playlist.name;
    uploadPlaylistChecks.appendChild(label);
  }
});
document.querySelector('#upload-back').addEventListener('click', () => showOnly(mainScreen));

document.querySelector('#upload-submit').addEventListener('click', async () => {
  if (!selectedUploadFiles.length) {
    setStatus('Choose at least one audio file');
    return;
  }

  const submitButton =
    document.querySelector('#upload-submit');

  const playlists = [
    ...uploadPlaylistChecks.querySelectorAll(
      'input:checked'
    )
  ].map(input => input.value);

  const data = new FormData();

  for (const file of selectedUploadFiles) {
    data.append(
      'files',
      file,
      file.name
    );
  }

  data.append(
    'playlists',
    JSON.stringify(playlists)
  );

  submitButton.disabled = true;
  submitButton.textContent = 'Importing…';

  try {
    setStatus('Importing music…');

    const result = await readJSON(
      '/api/music/import',
      {
        method: 'POST',
        body: data
      }
    );

    const imported =
      Array.isArray(result.imported)
        ? result.imported
        : [];

    const duplicates =
      Array.isArray(result.duplicates)
        ? result.duplicates
        : [];

    const failed =
      Array.isArray(result.failed)
        ? [...result.failed]
        : [];

    const resolved = [];

    for (const duplicate of duplicates) {
      const uploaded =
        duplicate.uploaded || {};

      const label = [
        uploaded.title,
        uploaded.artist
      ].filter(Boolean).join(' by ');

      const replace = confirm(
        'Duplicate detected: '
        + (
          label
          || duplicate.filename
          || 'same title and artist'
        )
        + '\n\nOK: replace the existing song'
        + '\nCancel: remove this upload'
      );

      try {
        const resolution = await readJSON(
          '/api/music/duplicate-resolve',
          {
            method: 'POST',
            headers: {
              'Content-Type':
                'application/json'
            },
            body: JSON.stringify({
              token: duplicate.token,
              action:
                replace
                  ? 'replace'
                  : 'remove-upload'
            })
          }
        );

        resolved.push(resolution);

      } catch (error) {
        failed.push({
          filename:
            duplicate.filename
            || label
            || 'Duplicate',
          error: error.message
        });
      }
    }

    const completedCount =
      imported.length
      + resolved.length;

    const failedCount =
      failed.length;

    let message =
      completedCount === 1
        ? 'Music upload complete: 1 song processed.'
        : (
            'Music upload complete: '
            + completedCount
            + ' songs processed.'
          );

    if (failedCount > 0) {
      message += (
        ' '
        + failedCount
        + (
            failedCount === 1
              ? ' file needs attention.'
              : ' files need attention.'
          )
      );
    }

    const failedNames = new Set(
      failed
        .map(item => item.filename)
        .filter(Boolean)
    );

    selectedUploadFiles =
      selectedUploadFiles.filter(
        file => failedNames.has(file.name)
      );

    musicFiles.value = '';
    renderSelectedUploadFiles();

    await loadPlaylists();

    uploadCompletePanel.textContent =
      message;

    uploadCompletePanel.classList.remove(
      'hidden'
    );

    showOnly(mainScreen);

    window.scrollTo({
      top: 0,
      behavior: 'smooth'
    });

    setStatus(message);

    setTimeout(() => {
      if (
        uploadCompletePanel.textContent
        === message
      ) {
        uploadCompletePanel.classList.add(
          'hidden'
        );
        uploadCompletePanel.textContent = '';
      }
    }, 8000);

  } catch (error) {
    setStatus(error.message);

  } finally {
    submitButton.disabled = false;
    submitButton.textContent =
      'Import Selected Files';
  }
});

async function openSongManager(song) {
  selectedManagedSong = song;
  document.querySelector('#song-manage-title').textContent = song.title || 'Song';
  document.querySelector('#song-manage-details').textContent = [song.artist, song.album].filter(Boolean).join(' • ');
  songPlaylistChecks.innerHTML = 'Loading…';
  showOnly(songManageScreen);
  try {
    const response = await readJSON('/api/song/playlists?id=' + encodeURIComponent(song.id));
    songPlaylistChecks.innerHTML = '';
    for (const playlist of response.playlists || []) {
      const label = document.createElement('label');
      label.className = 'playlist-check';
      label.innerHTML = '<input type="checkbox"><span></span>';
      const input = label.querySelector('input');
      input.checked = Boolean(playlist.included);
      label.querySelector('span').textContent = playlist.name;
      input.addEventListener('change', async () => {
        input.disabled = true;
        try {
          await readJSON('/api/song/playlist', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id:song.id, playlist:playlist.name, included:input.checked})});
        } catch (error) { input.checked = !input.checked; setStatus(error.message); }
        finally { input.disabled = false; }
      });
      songPlaylistChecks.appendChild(label);
    }
  } catch (error) { songPlaylistChecks.textContent = error.message; }
}

document.querySelector('#song-manage-back').addEventListener('click', () => showOnly(allSongsScreen));
document.querySelector('#remove-from-library').addEventListener('click', async () => {
  if (!selectedManagedSong) return;
  if (!confirm('Remove "' + (selectedManagedSong.title || 'this song') + '" from your Apple Music library?')) return;

  const button = document.querySelector('#remove-from-library');
  button.disabled = true;
  button.textContent = 'Removing…';

  try {
    await readJSON('/api/song/library', {
      method: 'DELETE',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id:selectedManagedSong.id})
    });
    setStatus('Removed from Apple Music');
    selectedManagedSong = null;
    showOnly(allSongsScreen);
    await loadAllSongs();
    await loadPlaylists();
  } catch (error) {
    setStatus(error.message);
  } finally {
    button.disabled = false;
    button.textContent = 'Remove from Library';
  }
});


const playlistAddScreen =
  document.querySelector(
    "#playlist-add-screen"
  );

const playlistAddList =
  document.querySelector(
    "#playlist-add-list"
  );

const playlistAddSearch =
  document.querySelector(
    "#playlist-add-search"
  );

const playlistAddSelectedButton =
  document.querySelector(
    "#playlist-add-selected"
  );

playlistAddSearch.parentNode.insertBefore(
  playlistAddSelectedButton,
  playlistAddSearch
);

function renderPlaylistAddCandidates() {
  const query = normalizeSearchText(
    playlistAddSearch.value.trim()
  );

  playlistAddList.innerHTML = "";

  const matches =
    playlistAddCandidates.filter(
      song =>
        normalizeSearchText([
          song.title,
          song.artist,
          song.album
        ].filter(Boolean).join(" "))
          .includes(query)
    );

  if (matches.length === 0) {
    playlistAddList.textContent =
      query
        ? "No matching songs"
        : "Every library song is already in this playlist";
    return;
  }

  for (const song of matches) {
    const label =
      document.createElement("label");

    label.className =
      "playlist-candidate-row";

    const input =
      document.createElement("input");

    input.type = "checkbox";
    input.value = song.id;

    const details =
      document.createElement("span");

    details.className =
      "playlist-candidate-details";

    const title =
      document.createElement("span");

    title.className =
      "playlist-candidate-title";

    title.textContent =
      song.title || "Unknown title";

    const artist =
      document.createElement("span");

    artist.className =
      "playlist-candidate-artist";

    artist.textContent = [
      song.artist,
      song.album
    ].filter(Boolean).join(" • ");

    details.append(
      title,
      artist
    );

    label.append(
      input,
      details
    );

    playlistAddList.appendChild(label);
  }
}

async function openPlaylistAddSongs() {
  if (!currentPlaylistName) {
    return;
  }

  playlistAddSearch.value = "";
  playlistAddList.textContent = "Loading…";

  document.querySelector(
    "#playlist-add-title"
  ).textContent =
    "Add to " + currentPlaylistName;

  showOnly(playlistAddScreen);

  try {
    const [libraryResult, playlistResult] =
      await Promise.all([
        readJSON("/api/songs"),
        readJSON(
          "/api/playlist?name="
          + encodeURIComponent(
              currentPlaylistName
            )
        )
      ]);

    const librarySongs =
      Array.isArray(libraryResult.songs)
        ? libraryResult.songs
        : [];

    const playlistSongs =
      Array.isArray(playlistResult.songs)
        ? playlistResult.songs
        : [];

    const existingIDs =
      new Set(
        playlistSongs.map(
          song => String(song.id)
        )
      );

    playlistAddCandidates =
      librarySongs.filter(
        song =>
          !existingIDs.has(
            String(song.id)
          )
      );

    renderPlaylistAddCandidates();

  } catch (error) {
    playlistAddList.textContent =
      error.message;
  }
}

playlistAddSearch.addEventListener(
  "input",
  renderPlaylistAddCandidates
);

document.querySelector(
  "#playlist-add-songs"
).addEventListener(
  "click",
  openPlaylistAddSongs
);

document.querySelector(
  "#playlist-add-back"
).addEventListener(
  "click",
  () => showOnly(playlistScreen)
);

playlistAddSelectedButton.addEventListener(
  "click",
  async () => {
    const button =
      playlistAddSelectedButton;

    const identifiers = [
      ...playlistAddList.querySelectorAll(
        'input[type="checkbox"]:checked'
      )
    ].map(input => input.value);

    if (identifiers.length === 0) {
      setStatus("Select at least one song");
      return;
    }

    const playlistName =
      currentPlaylistName;

    button.disabled = true;
    button.textContent = "Adding…";

    const failed = [];

    try {
      for (const identifier of identifiers) {
        try {
          await readJSON(
            "/api/song/playlist",
            {
              method: "POST",
              headers: {
                "Content-Type":
                  "application/json"
              },
              body: JSON.stringify({
                id: identifier,
                playlist: playlistName,
                included: true
              })
            }
          );
        } catch (error) {
          failed.push(
            error.message
          );
        }
      }

      playlistAddCandidates = [];
      playlistAddSearch.value = "";
      playlistAddList.innerHTML = "";

      /*
       * Close every other application screen before reloading
       * the playlist. This prevents playlist-add-screen from
       * remaining visible underneath playlist-screen.
       */
      showOnly(playlistScreen);

      await openPlaylist(
        playlistName
      );

      window.scrollTo({
        top: 0,
        behavior: "smooth"
      });

      if (failed.length > 0) {
        setStatus(
          failed.length
          + (
              failed.length === 1
                ? " song addition failed"
                : " song additions failed"
            )
        );
      } else {
        setStatus(
          identifiers.length === 1
            ? "Added 1 song"
            : (
                "Added "
                + identifiers.length
                + " songs"
              )
        );
      }

    } catch (error) {
      /*
       * Keep the selection screen available only when an
       * unexpected outer failure prevents playlist reload.
       */
      showOnly(
        playlistAddScreen
      );

      setStatus(
        error.message
      );

    } finally {
      button.disabled = false;
      button.textContent =
        "Add Selected Songs";
    }
  }
);

document.querySelector(
  "#create-playlist"
).addEventListener(
  "click",
  async () => {
    const requested =
      prompt("New playlist name");

    if (requested === null) {
      return;
    }

    const name = requested.trim();

    if (!name) {
      setStatus(
        "Enter a playlist name"
      );
      return;
    }

    try {
      await readJSON(
        "/api/playlist/create",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json"
          },
          body: JSON.stringify({
            name: name
          })
        }
      );

      await loadPlaylists();
      setStatus(
        'Created playlist "' + name + '"'
      );

    } catch (error) {
      setStatus(error.message);
    }
  }
);

document.querySelector(
  "#playlist-remove"
).addEventListener(
  "click",
  async () => {
    if (!currentPlaylistName) {
      return;
    }

    if (
      !confirm(
        'Remove playlist "'
        + currentPlaylistName
        + '"?\n\n'
        + "Songs will remain in your Apple Music library."
      )
    ) {
      return;
    }

    const name = currentPlaylistName;
    const button =
      document.querySelector(
        "#playlist-remove"
      );

    button.disabled = true;
    button.textContent = "Removing…";

    try {
      await readJSON(
        "/api/playlist/remove",
        {
          method: "DELETE",
          headers: {
            "Content-Type":
              "application/json"
          },
          body: JSON.stringify({
            name: name
          })
        }
      );

      currentPlaylistName = "";
      await loadPlaylists();
      showOnly(mainScreen);

      setStatus(
        'Removed playlist "'
        + name
        + '". Songs were kept.'
      );

    } catch (error) {
      setStatus(error.message);

    } finally {
      button.disabled = false;
      button.textContent =
        "Remove Playlist";
    }
  }
);

let ipadStateTimer = null;
let routeStateTimer = null;
let pageRefreshGeneration = 0;
async function refreshIPadState(){
  if(document.hidden)return;
  await Promise.allSettled([updateNowPlaying(),updateSystemNowPlaying(),loadVolumeState(),loadRepeatMode(),loadShuffleMode()]);
}
function scheduleIPadStatePoll(generation){
  clearTimeout(ipadStateTimer);
  if(document.hidden||generation!==pageRefreshGeneration)return;
  ipadStateTimer=setTimeout(async()=>{await refreshIPadState();scheduleIPadStatePoll(generation)},1500);
}

const sonobusUI={state:null,busy:false};
async function sonobusJSON(url,options){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),8000);try{const response=await fetch(url,{cache:'no-store',signal:controller.signal,...(options||{})});const data=await response.json();if(!response.ok||data.ok===false)throw new Error(data.error||'SonoBus request failed');return data}finally{clearTimeout(timer)}}
function sonobusRender(state){sonobusUI.state=state;document.querySelectorAll('[data-sonobus-preset]').forEach(button=>{const selected=button.dataset.sonobusPreset===state.activePreset;button.classList.toggle('active',selected);button.setAttribute('aria-pressed',String(selected))});const badge=document.querySelector('#sonobus-state-badge');if(badge){const sono=state.sonobusRunning?((state.group||'SonoBus')+' · Running'):'SonoBus stopped';const air=state.airplayAvailable?(state.airplayConnected?('AirPlay '+(state.airplayName||'connected')):'AirPlay off'):'AirPlay unknown';badge.textContent=sono+' · '+air}const list=document.querySelector('#sonobus-profile-list');if(list){list.innerHTML='';Object.entries(state.profiles||{}).forEach(([id,profile])=>{const row=document.createElement('div');row.className='sonobus-profile'+(id===state.selectedProfile?' selected':'');row.innerHTML='<div class="sonobus-profile-main"><div class="sonobus-profile-name"></div><div class="sonobus-profile-meta"></div></div><button data-use>Use</button><button data-delete>Delete</button>';row.querySelector('.sonobus-profile-name').textContent=profile.name||id;row.querySelector('.sonobus-profile-meta').textContent=(profile.username||'')+' · '+(profile.group||'');row.querySelector('[data-use]').onclick=()=>sonobusPost('/api/sonobus/profile/select',{id});row.querySelector('[data-delete]').onclick=()=>sonobusPost('/api/sonobus/profile/delete',{id});list.appendChild(row)})}}
async function sonobusRefresh(){if(sonobusUI.busy||document.hidden)return;try{sonobusRender(await sonobusJSON('/api/sonobus/state'))}catch(error){setStatus(error.name==='AbortError'?'Route status timed out':error.message)}}
async function sonobusPost(url,payload){if(sonobusUI.busy)return;sonobusUI.busy=true;try{const data=await sonobusJSON(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload||{})});if(data.state)sonobusRender(data.state);setStatus(data.message||'Routing updated')}catch(error){setStatus(error.message)}finally{sonobusUI.busy=false;sonobusRefresh()}}
document.querySelectorAll('[data-sonobus-preset]').forEach(button=>button.onclick=async()=>{
  if(sonobusUI.busy)return;
  const preset=button.dataset.sonobusPreset;
  document.querySelectorAll('[data-sonobus-preset]').forEach(item=>{
    item.classList.toggle('active',item===button);
    item.disabled=true;
  });
  button.setAttribute('aria-pressed','true');
  setStatus('Applying '+button.textContent.trim()+' destination…');
  try{
    await sonobusPost('/api/sonobus/preset',{preset});
  }finally{
    document.querySelectorAll('[data-sonobus-preset]').forEach(item=>{
      item.disabled=false;
      item.setAttribute('aria-pressed',String(item.classList.contains('active')));
    });
  }
});
const restartSonoBusButton=document.querySelector('#restart-sonobus');
async function restartSonoBusWithFeedback(){
  if(!restartSonoBusButton||sonobusUI.busy)return;
  const badge=document.querySelector('#sonobus-state-badge');
  const previousBadge=badge?badge.textContent:'';
  sonobusUI.busy=true;
  restartSonoBusButton.disabled=true;
  restartSonoBusButton.classList.add('is-restarting');
  restartSonoBusButton.setAttribute('aria-busy','true');
  if(badge){badge.textContent='Restarting SonoBus…';badge.classList.add('is-restarting')}
  setStatus('Restarting SonoBus…');
  try{
    const data=await sonobusJSON('/api/sonobus/restart',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    let state=null;
    for(let attempt=0;attempt<10;attempt+=1){
      await new Promise(resolve=>setTimeout(resolve,500));
      try{
        state=await sonobusJSON('/api/sonobus/state');
        if(state.sonobusRunning)break;
      }catch(_error){}
    }
    if(state)sonobusRender(state);
    setStatus(state&&state.sonobusRunning?'SonoBus restarted':'SonoBus restart sent');
  }catch(error){
    if(badge)badge.textContent=previousBadge||'SonoBus stopped';
    setStatus(error.message);
  }finally{
    restartSonoBusButton.disabled=false;
    restartSonoBusButton.classList.remove('is-restarting');
    restartSonoBusButton.removeAttribute('aria-busy');
    if(badge)badge.classList.remove('is-restarting');
    sonobusUI.busy=false;
    sonobusRefresh();
  }
}
if(restartSonoBusButton)restartSonoBusButton.addEventListener('click',restartSonoBusWithFeedback);
document.querySelector('#sonobus-groups-open').onclick=()=>document.querySelector('#sonobus-groups').classList.remove('hidden');
document.querySelectorAll('[data-sonobus-close]').forEach(button=>button.onclick=()=>button.closest('section').classList.add('hidden'));
document.querySelector('#sonobus-profile-save').onclick=()=>sonobusPost('/api/sonobus/profile/save',{name:document.querySelector('#sonobus-profile-name').value.trim(),username:document.querySelector('#sonobus-username').value.trim(),group:document.querySelector('#sonobus-group').value.trim(),password:document.querySelector('#sonobus-password').value});
async function refreshVisiblePage(){if(document.hidden)return;await Promise.allSettled([refreshIPadState(),sonobusRefresh()])}
function scheduleRouteStatePoll(generation){clearTimeout(routeStateTimer);if(document.hidden||generation!==pageRefreshGeneration)return;routeStateTimer=setTimeout(async()=>{await sonobusRefresh();scheduleRouteStatePoll(generation)},2500)}
function startVisiblePolling(){pageRefreshGeneration+=1;const generation=pageRefreshGeneration;refreshVisiblePage();scheduleIPadStatePoll(generation);scheduleRouteStatePoll(generation)}
document.addEventListener('visibilitychange',()=>{if(document.hidden){pageRefreshGeneration+=1;clearTimeout(ipadStateTimer);clearTimeout(routeStateTimer);return}loadPlaylists();startVisiblePolling()});
loadPlaylists();startVisiblePolling();
</script>
</body>
</html>
"""


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

        # Allow Filza and the injected bridge observer to initialize.
        time.sleep(2.0)
        return

    raise RuntimeError("uiopen was not found")


def bridge_request(payload, timeout=20):
    # Serialize Filza import requests.
    with FILZA_IMPORT_LOCK:
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

        restart_filza()

        trigger = execute(["music-import-trigger"], timeout=5)
        if trigger.returncode != 0:
            raise RuntimeError(
                trigger.stderr.strip()
                or trigger.stdout.strip()
                or "Could not trigger the Filza music bridge"
            )

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
                raise RuntimeError(
                    response.get("error")
                    or "Filza music operation failed"
                )
            return response

        # Never leave the web request stuck if Filza exits during an operation.
        raise TimeoutError(
            "Filza did not complete the music operation; it may have exited"
        )


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


def song_duplicate_key(song):
    title = normalized_metadata_text(
        song.get("title")
    )
    artist = normalized_metadata_text(
        song.get("artist")
    )

    if not title or not artist:
        return None

    return title, artist


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

    saved_preset = routing_state().get("activePreset", "")
    active_preset = (
        saved_preset if saved_preset in SONOBUS_PRESETS else ""
    )
    # The badge reflects the successfully applied destination command.
    # The live state reader reports Speaker from this server process even
    # while Music is connected, so it must not overwrite the route result.
    airplay_connected = bool(
        active_preset
        and SONOBUS_PRESETS[active_preset]["airplay"]
    )
    payload["airplayAvailable"] = True
    payload["airplayConnected"] = airplay_connected
    payload["airplayName"] = "rt4817" if airplay_connected else ""
    payload["airplayUID"] = (
        "07b32858-19ad-447c-898c-13d7f0ea07fe"
        if airplay_connected
        else ""
    )
    payload["activePreset"] = active_preset
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


SONOBUS_PRESETS = {
    # Every iPad-source route sends to the laptop through the saved
    # default AirPlay receiver so audio always passes through convolution.
    "ipad-local": {"airplay": True, "receive": True},
    "ipad-laptop": {"airplay": True, "receive": False},
    "ipad-both": {"airplay": True, "receive": True},
    "ipad-external": {"airplay": True, "receive": False},
    "laptop-ipad": {"airplay": False, "receive": True},
    "laptop-local": {"airplay": False, "receive": False},
    "laptop-both": {"airplay": False, "receive": True},
    "laptop-external": {"airplay": False, "receive": False},
}


def routing_state():
    try:
        value = json.loads(ROUTING_STATE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def save_routing_state(name):
    _atomic_json(ROUTING_STATE, {"activePreset": name})


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
                PAGE.encode("utf-8")
            )
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



        if path == "/api/sonobus/restart":
            try:
                restart_sonobus()
                self.send_json(200, {"ok": True, "message": "SonoBus restarted"})
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
                        if preset_name not in SONOBUS_PRESETS:
                            raise ValueError("Unknown routing preset")
                        preset = SONOBUS_PRESETS[preset_name]
                        profile = profiles[selected]
                        running = sonobus_running()
                        if preset["receive"] and not running:
                            apply_sonobus(profile, {"sendMuted": True, "receiveMuted": False, "inputMuted": True, "monitorSolo": False}, password=str(profile.get("password") or ""))
                        elif not preset["receive"] and running:
                            stop_sonobus()
                        if preset["airplay"]:
                            # All iPad-source presets use the same proven
                            # standalone AirPlay flow: clear the current route,
                            # then connect the saved default receiver.
                            disconnect_result = execute(["airplay-disconnect"])
                            if disconnect_result.returncode != 0:
                                raise RuntimeError(
                                    disconnect_result.stderr.strip()
                                    or disconnect_result.stdout.strip()
                                    or "AirPlay disconnect failed"
                                )
                            time.sleep(0.35)
                            result = execute(["airplay-connect-default"])
                        else:
                            result = execute(["airplay-disconnect"])
                        if result.returncode != 0:
                            raise RuntimeError(
                                result.stderr.strip()
                                or result.stdout.strip()
                                or "AirPlay routing failed"
                            )
                        save_routing_state(preset_name)
                        message = "Routing preset applied"
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

        if path == "/api/music/import":
            staged_paths = []

            try:
                prune_pending_duplicates()

                content_length = int(
                    self.headers.get(
                        "Content-Length",
                        "0",
                    )
                )

                if (
                    content_length <= 0
                    or content_length
                    > MAX_UPLOAD_BYTES
                ):
                    raise ValueError(
                        "Invalid upload size"
                    )

                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        "REQUEST_METHOD": "POST",
                        "CONTENT_TYPE":
                            self.headers.get(
                                "Content-Type",
                                "",
                            ),
                    },
                    keep_blank_values=True,
                )

                playlists = json.loads(
                    form.getfirst(
                        "playlists",
                        "[]",
                    )
                )

                if (
                    not isinstance(playlists, list)
                    or not all(
                        isinstance(value, str)
                        and value.strip()
                        for value in playlists
                    )
                ):
                    raise ValueError(
                        "Invalid playlist selection"
                    )

                playlists = merge_playlist_names(
                    playlists
                )

                fields = (
                    form["files"]
                    if "files" in form
                    else []
                )

                if not isinstance(fields, list):
                    fields = [fields]

                if not fields:
                    raise ValueError(
                        "No files uploaded"
                    )

                existing_songs = library_songs()
                existing_by_key = {}

                for song in existing_songs:
                    key = song_duplicate_key(song)

                    if key is not None:
                        existing_by_key.setdefault(
                            key,
                            [],
                        ).append(song)

                MUSIC_UPLOAD_DIRECTORY.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                imported = []
                duplicates = []
                failed = []

                for field in fields:
                    original = Path(
                        field.filename
                        or "upload.m4a"
                    ).name

                    staging = None

                    try:
                        extension = (
                            Path(original)
                            .suffix
                            .lower()
                        )

                        if (
                            extension
                            not in
                            ALLOWED_AUDIO_EXTENSIONS
                        ):
                            raise ValueError(
                                "Unsupported audio file: "
                                + original
                            )

                        staging = (
                            MUSIC_UPLOAD_DIRECTORY
                            / (
                                str(uuid.uuid4())
                                + extension
                            )
                        )

                        staged_paths.append(staging)

                        with staging.open("wb") as output:
                            shutil.copyfileobj(
                                field.file,
                                output,
                            )

                        response = bridge_request({
                            "action": "import",
                            "sourcePath":
                                str(staging),
                            "title":
                                Path(original).stem,
                        })

                        if not staging.exists():
                            staged_paths.remove(
                                staging
                            )

                        identifier = str(
                            response.get(
                                "persistentID",
                                "",
                            )
                        )

                        if not valid_song_identifier(
                            identifier
                        ):
                            raise RuntimeError(
                                "Import returned "
                                "an invalid song ID"
                            )

                        imported_song = (
                            wait_for_library_song(
                                identifier
                            )
                        )

                        key = song_duplicate_key(
                            imported_song
                        )

                        matches = (
                            existing_by_key.get(
                                key,
                                [],
                            )
                            if key is not None
                            else []
                        )

                        if matches:
                            existing = matches[0]

                            existing_identifier = str(
                                existing.get(
                                    "id",
                                    "",
                                )
                            )

                            memberships = (
                                song_playlist_names(
                                    existing_identifier
                                )
                            )

                            target_playlists = (
                                merge_playlist_names(
                                    memberships,
                                    playlists,
                                )
                            )

                            token = str(
                                uuid.uuid4()
                            )

                            store_pending_duplicate(
                                token,
                                {
                                    "new":
                                        imported_song,
                                    "existing":
                                        existing,
                                    "playlists":
                                        target_playlists,
                                    "created":
                                        time.time(),
                                    "filename":
                                        original,
                                },
                            )

                            duplicates.append({
                                "token": token,
                                "filename": original,
                                "uploaded":
                                    imported_song,
                                "existing":
                                    existing,
                                "playlists":
                                    target_playlists,
                            })

                        else:
                            add_song_to_playlists(
                                identifier,
                                playlists,
                            )

                            imported.append({
                                "filename": original,
                                "song":
                                    imported_song,
                                "import":
                                    response,
                            })

                            if key is not None:
                                existing_by_key.setdefault(
                                    key,
                                    [],
                                ).append(
                                    imported_song
                                )

                    except Exception as error:
                        failed.append({
                            "filename": original,
                            "error": str(error),
                        })

                    finally:
                        if (
                            staging is not None
                            and staging.exists()
                        ):
                            try:
                                staging.unlink()
                            except OSError:
                                pass

                            if staging in staged_paths:
                                staged_paths.remove(
                                    staging
                                )

                self.send_json(
                    200,
                    {
                        "ok": True,
                        "imported": imported,
                        "duplicates": duplicates,
                        "failed": failed,
                    },
                )

            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
                OSError,
                RuntimeError,
                TimeoutError,
            ) as error:
                for staging in staged_paths:
                    try:
                        staging.unlink()
                    except OSError:
                        pass

                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error": str(error),
                    },
                )

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
