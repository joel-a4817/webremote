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
MUSIC_UPLOAD_DIRECTORY = Path('/var/mobile/Media/MusicUploads')
MUSIC_IMPORT_REQUEST = Path('/var/mobile/MediaCtlMusicImport-request.plist')
MUSIC_IMPORT_RESPONSE = Path('/var/mobile/MediaCtlMusicImport-response.plist')
ALLOWED_AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.aac', '.alac', '.wav'}
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
PENDING_DUPLICATES = {}
PENDING_DUPLICATE_TTL_SECONDS = 30 * 60
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

.volume-lock-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-top: 4px;
}

.volume-lock-label {
  font-size: 14px;
  font-weight: 700;
}

.volume-switch {
  position: relative;
  width: 52px;
  height: 30px;
  flex: 0 0 52px;
  touch-action: manipulation;
}

.volume-switch input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}

.volume-switch-track {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: rgba(255, 255, 255, .20);
  transition: background .18s ease;
}

.volume-switch-track::after {
  content: "";
  position: absolute;
  top: 3px;
  left: 3px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: white;
  box-shadow: 0 2px 7px rgba(0, 0, 0, .34);
  transition: transform .18s ease;
}

.volume-switch input:checked + .volume-switch-track {
  background: #7b5cff;
}

.volume-switch input:checked + .volume-switch-track::after {
  transform: translateX(22px);
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

.system-controls {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 11px;
  margin-top: 15px;
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
  margin-top: 24px;
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

</style>
</head>

<body>
<main>
  <section id="main-screen">
    <h1>iPad Music</h1>
    <div id="upload-complete-panel" class="upload-complete-panel hidden" aria-live="polite"></div>

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
            step="1"
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
        <div class="volume-lock-row">
          <span class="volume-lock-label">
            Set 100% when Play is pressed
          </span>

          <label class="volume-switch">
            <input
              id="volume-lock"
              type="checkbox"
              aria-label="Set volume to 100 percent when Play is pressed"
            >
            <span class="volume-switch-track"></span>
          </label>
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
      <button
        id="home-device"
        class="system-button"
        type="button"
      >
        Wake iPad
      </button>
    </div>


    <div class="library-launchers">
      <button id="open-all-songs" type="button">All Songs</button>
      <button id="open-upload" type="button">Upload Music</button>
    </div>

    <div class="section-title">Playlists</div>

    <div
      id="playlist-list"
      class="list"
    ></div>
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
const volumeLock =
  document.querySelector(
    "#volume-lock"
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
    volumeLock.checked = Boolean(result.locked);
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

volumeLock.addEventListener(
  "change",
  async () => {
    const requested = volumeLock.checked;
    volumeLock.disabled = true;

    try {
      const result = await readJSON(
        "/api/volume-lock",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            locked: requested
          })
        }
      );

      volumeLock.checked = Boolean(result.locked);
      setStatus(
        result.locked
          ? "100% on Play enabled"
          : "100% on Play disabled"
      );
    } catch (error) {
      volumeLock.checked = !requested;
      setStatus(error.message);
    } finally {
      volumeLock.disabled = false;
    }
  }
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

function refreshActualVolumeAfterPlayback() {
  /*
   * Never assume that the requested playback action changed volume.
   * Re-read the volume published by the iPad and let loadVolumeState()
   * update the slider only from that authoritative result.
   */
  for (const delay of [
    0,
    150,
    350,
    700,
    1200
  ]) {
    setTimeout(
      loadVolumeState,
      delay
    );
  }
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

    if (
      command === "play"
      || command === "toggle"
    ) {
      refreshActualVolumeAfterPlayback();
    }

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
  for (const section of [mainScreen, playlistScreen, airPlayScreen, allSongsScreen, uploadScreen, songManageScreen]) {
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
  if (!selectedUploadFiles.length) { setStatus('Choose at least one audio file'); return; }
  const playlists = [...uploadPlaylistChecks.querySelectorAll('input:checked')].map(input => input.value);
  const data = new FormData();
  for (const file of selectedUploadFiles) data.append('files', file, file.name);
  data.append('playlists', JSON.stringify(playlists));
  try {
    setStatus('Importing music…');
    const result = await readJSON('/api/music/import', {method:'POST', body:data});

    for (const duplicate of (result.duplicates || [])) {
      const uploaded = duplicate.uploaded || {};
      const existing = duplicate.existing || {};
      const label = [uploaded.title, uploaded.artist].filter(Boolean).join(' by ');
      const replace = confirm(
        'Duplicate detected: ' + (label || 'same title and artist')
        + '\n\nOK: replace the existing song'
        + '\nCancel: remove this upload'
      );
      await readJSON('/api/music/duplicate-resolve', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          token: duplicate.token,
          action: replace ? 'replace' : 'remove-upload'
        })
      });
    }

    const count = result.imported.length + (result.duplicates || []).length;
    const message = count === 1
      ? 'Music upload complete: 1 song processed.'
      : 'Music upload complete: ' + count + ' songs processed.';

    selectedUploadFiles = [];
    musicFiles.value = '';
    renderSelectedUploadFiles();
    await loadPlaylists();

    uploadCompletePanel.textContent = message;
    uploadCompletePanel.classList.remove('hidden');
    showOnly(mainScreen);
    window.scrollTo({top: 0, behavior: 'smooth'});
    setStatus(message);

    setTimeout(() => {
      if (uploadCompletePanel.textContent === message) {
        uploadCompletePanel.classList.add('hidden');
        uploadCompletePanel.textContent = '';
      }
    }, 8000);
  } catch (error) { setStatus(error.message); }
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

loadPlaylists();
updateNowPlaying();
loadVolumeState();
loadRepeatMode();
loadShuffleMode();

setInterval(
  updateNowPlaying,
  2000
);
setInterval(
  loadRepeatMode,
  2000
);
setInterval(
  loadShuffleMode,
  2000
);
setInterval(
  loadVolumeState,
  500
);
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
    return isinstance(value, str) and value.isdecimal() and int(value) != 0


def prune_pending_duplicates():
    cutoff = (
        time.time()
        - PENDING_DUPLICATE_TTL_SECONDS
    )

    with PENDING_DUPLICATES_LOCK:
        expired = [
            token
            for token, pending
            in PENDING_DUPLICATES.items()
            if pending.get("created", 0) < cutoff
        ]

        for token in expired:
            PENDING_DUPLICATES.pop(
                token,
                None,
            )


def normalized_metadata_text(value):
    return " ".join(
        unicodedata.normalize("NFKC", str(value or ""))
        .casefold()
        .split()
    )


def song_duplicate_key(song):
    title = normalized_metadata_text(song.get("title"))
    artist = normalized_metadata_text(song.get("artist"))
    if not title or not artist:
        return None
    return title, artist


def mediactl_object(arguments, timeout=15):
    result = execute(arguments, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "mediactl failed"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("mediactl returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeError("mediactl returned invalid data")
    return payload


def library_songs():
    payload = mediactl_object(["songs-json"])
    songs = payload.get("songs", [])
    return songs if isinstance(songs, list) else []


def add_song_to_playlists(identifier, playlists):
    for playlist in playlists:
        result = execute([
            "song-add-to-playlist",
            identifier,
            playlist,
        ])
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or "Could not add song to " + playlist
            )


def remove_song_from_library(identifier):
    if not valid_song_identifier(str(identifier)):
        raise ValueError("Invalid song ID")

    result = execute(
        ["song-remove-from-library", str(identifier)],
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "Apple Music library removal failed"
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "mediactl returned invalid removal data"
        ) from error

    if not isinstance(payload, dict):
        raise RuntimeError(
            "mediactl returned invalid removal data"
        )

    return payload


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
                    isinstance(value, str) and value.strip()
                    for value in playlists
                ):
                    raise ValueError("Invalid playlist selection")
                playlists = [value.strip() for value in playlists]

                fields = form["files"] if "files" in form else []
                if not isinstance(fields, list):
                    fields = [fields]
                if not fields:
                    raise ValueError("No files uploaded")

                existing_songs = library_songs()
                existing_by_key = {}
                for song in existing_songs:
                    key = song_duplicate_key(song)
                    if key is not None:
                        existing_by_key.setdefault(key, []).append(song)

                MUSIC_UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
                imported = []
                duplicates = []

                for field in fields:
                    original = Path(field.filename or "upload.m4a").name
                    extension = Path(original).suffix.lower()
                    if extension not in ALLOWED_AUDIO_EXTENSIONS:
                        raise ValueError("Unsupported audio file: " + original)

                    staging = MUSIC_UPLOAD_DIRECTORY / (str(uuid.uuid4()) + extension)
                    staged_paths.append(staging)
                    with staging.open("wb") as output:
                        shutil.copyfileobj(field.file, output)

                    response = bridge_request({
                        "action": "import",
                        "sourcePath": str(staging),
                        "title": Path(original).stem,
                    })
                    if not staging.exists():
                        staged_paths.remove(staging)

                    identifier = str(response.get("persistentID", ""))
                    refreshed = library_songs()
                    imported_song = next(
                        (song for song in refreshed if str(song.get("id", "")) == identifier),
                        None,
                    )
                    if imported_song is None:
                        raise RuntimeError("Imported song was not returned by the Music library")

                    key = song_duplicate_key(imported_song)
                    matches = existing_by_key.get(key, []) if key is not None else []
                    if matches:
                        token = str(uuid.uuid4())
                        existing = matches[0]
                        with PENDING_DUPLICATES_LOCK:
                            PENDING_DUPLICATES[token] = {
                                "new": imported_song,
                                "existing": existing,
                                "playlists": playlists,
                                "created": time.time(),
                            }
                        duplicates.append({
                            "token": token,
                            "uploaded": imported_song,
                            "existing": existing,
                        })
                    else:
                        add_song_to_playlists(identifier, playlists)
                        imported.append(response)
                        if key is not None:
                            existing_by_key.setdefault(key, []).append(imported_song)

                self.send_json(200, {
                    "ok": True,
                    "imported": imported,
                    "duplicates": duplicates,
                })
            except Exception as error:
                for staging in staged_paths:
                    try:
                        staging.unlink()
                    except FileNotFoundError:
                        pass
                self.send_json(400, {"ok": False, "error": str(error)})
            return

        if path == "/api/music/duplicate-resolve":
            try:
                prune_pending_duplicates()
                payload = self.read_json_body()
                token = payload["token"]
                action = payload["action"]
                if not isinstance(token, str) or action not in {"replace", "remove-upload"}:
                    raise ValueError
                with PENDING_DUPLICATES_LOCK:
                    pending = PENDING_DUPLICATES.pop(token)

                new_identifier = str(pending["new"]["id"])
                existing_identifier = str(pending["existing"]["id"])

                if action == "replace":
                    remove_song_from_library(existing_identifier)
                    add_song_to_playlists(
                        new_identifier,
                        pending["playlists"],
                    )
                    message = "Existing song replaced"
                else:
                    remove_song_from_library(new_identifier)
                    message = "Uploaded duplicate removed"

                self.send_json(200, {
                    "ok": True,
                    "action": action,
                    "message": message,
                })
            except KeyError:
                self.send_json(400, {"ok": False, "error": "Duplicate decision expired"})
            except Exception as error:
                self.send_json(400, {"ok": False, "error": str(error)})
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
                or not isinstance(
                    response.get("locked"),
                    bool,
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

        if path == "/api/volume-lock":
            try:
                payload = self.read_json_body()
                locked = payload["locked"]
                if not isinstance(locked, bool):
                    raise TypeError
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
                        "error": "Invalid volume lock",
                    },
                )
                return

            result = execute(
                [
                    "volume-lock",
                    "on" if locked else "off",
                ]
            )
            if result.returncode != 0:
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error": (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "Volume lock change failed"
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
                        "error": "Invalid volume lock response",
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
                or not isinstance(
                    response.get("locked"),
                    bool,
                )
            ):
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error":
                            "Invalid volume-lock response schema",
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
        if path != "/api/song/library":
            self.send_json(404, {"ok": False, "error": "Not found"})
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
