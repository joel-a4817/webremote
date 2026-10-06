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

PAGE='<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n\n<meta\n  name="viewport"\n  content="width=device-width,initial-scale=1,viewport-fit=cover"\n>\n\n<meta name="theme-color" content="#090a0f">\n<meta name="apple-mobile-web-app-capable" content="yes">\n\n<meta\n  name="apple-mobile-web-app-status-bar-style"\n  content="black-translucent"\n>\n\n<title>iPad Music Remote</title>\n\n<style>\n:root {\n  color-scheme: dark;\n  font-family:\n    -apple-system,\n    BlinkMacSystemFont,\n    "SF Pro Display",\n    sans-serif;\n}\n\n* {\n  box-sizing: border-box;\n  -webkit-tap-highlight-color: transparent;\n}\n\nhtml {\n  width: 100%;\n  max-width: 100%;\n  overflow-x: hidden;\n  overflow-y: scroll;\n  overscroll-behavior-x: none;\n  scrollbar-color:\n    rgba(255, 255, 255, .34)\n    rgba(255, 255, 255, .07);\n  scrollbar-width: thin;\n}\n\n::-webkit-scrollbar {\n  width: 8px;\n}\n\n::-webkit-scrollbar-track {\n  background:\n    rgba(255, 255, 255, .07);\n}\n\n::-webkit-scrollbar-thumb {\n  border: 2px solid transparent;\n  border-radius: 999px;\n  background:\n    rgba(255, 255, 255, .34);\n  background-clip:\n    padding-box;\n}\n\n::-webkit-scrollbar-thumb:active {\n  background:\n    rgba(255, 255, 255, .55);\n  background-clip:\n    padding-box;\n}\n\nbody {\n  width: 100%;\n  max-width: 100%;\n  margin: 0;\n  overflow-x: hidden;\n  overscroll-behavior-x: none;\n  touch-action: pan-y;\n  min-height: 100svh;\n\n  padding:\n    max(22px, env(safe-area-inset-top))\n    18px\n    max(30px, env(safe-area-inset-bottom));\n\n  color: white;\n\n  background:\n    radial-gradient(\n      circle at top,\n      #44266b 0,\n      #171521 42%,\n      #07080b 100%\n    );\n}\n\nmain {\n  width: min(100%, 480px);\n  max-width: 100%;\n  margin: 0 auto;\n  overflow-x: hidden;\n}\n\n.hidden {\n  display: none !important;\n}\n\nh1 {\n  margin: 6px 0 20px;\n  font-size: 29px;\n  text-align: center;\n}\n\n.now-playing {\n  min-height: 114px;\n  margin-bottom: 23px;\n  padding: 20px;\n\n  border-radius: 24px;\n\n  background: rgba(255, 255, 255, .11);\n\n  box-shadow:\n    inset 0 1px rgba(255, 255, 255, .18),\n    0 14px 38px rgba(0, 0, 0, .28);\n\n  backdrop-filter: blur(20px);\n  -webkit-backdrop-filter: blur(20px);\n}\n\n.now-label {\n  margin-bottom: 8px;\n\n  color: #aaa7b7;\n\n  font-size: 12px;\n  font-weight: 750;\n  letter-spacing: .11em;\n  text-transform: uppercase;\n}\n\n/* Artwork is confined to the Apple Music card. */\n.apple-now-playing-header { display:flex; align-items:center; gap:14px; min-width:0; }\n.apple-now-playing-copy { flex:1; min-width:0; }\n#apple-now-playing-artwork { flex:0 0 72px; width:72px; height:72px; border-radius:15px; font-size:32px; }\n#current-title {\n  font-size: 22px;\n  font-weight: 750;\n  line-height: 1.25;\n}\n\n#current-details {\n  margin-top: 6px;\n\n  color: #c2becb;\n\n  font-size: 15px;\n  line-height: 1.35;\n}\n\n.playback-progress {\n  margin-top: 16px;\n}\n\n#playback-seek {\n  --seek-progress: 0%;\n  touch-action: none;\n  user-select: none;\n  -webkit-user-select: none;\n\n  display: block;\n  width: 100%;\n  height: 26px;\n  margin: 0;\n  padding: 0;\n  border: 0;\n  box-shadow: none;\n  background: transparent;\n  appearance: none;\n  -webkit-appearance: none;\n}\n\n#playback-seek:disabled {\n  opacity: .45;\n}\n\n#playback-seek::-webkit-slider-runnable-track {\n  height: 5px;\n  border-radius: 999px;\n  background:\n    linear-gradient(\n      to right,\n      #ffffff 0%,\n      #ffffff var(--seek-progress),\n      rgba(255, 255, 255, .22)\n        var(--seek-progress),\n      rgba(255, 255, 255, .22) 100%\n    );\n}\n\n#playback-seek::-webkit-slider-thumb {\n  width: 17px;\n  height: 17px;\n  margin-top: -6px;\n  border: 0;\n  border-radius: 50%;\n  background: white;\n  box-shadow:\n    0 2px 8px rgba(0, 0, 0, .38);\n  appearance: none;\n  -webkit-appearance: none;\n}\n\n.playback-times {\n  display: flex;\n  justify-content: space-between;\n  margin-top: 1px;\n  color: #aaa7b7;\n  font-size: 12px;\n  font-variant-numeric: tabular-nums;\n}\n\n.volume-control {\n  margin-top: 16px;\n  padding-top: 14px;\n  border-top: 1px solid rgba(255, 255, 255, .10);\n}\n\n.volume-slider-row {\n  display: grid;\n  grid-template-columns: 18px minmax(0, 1fr) 18px;\n  gap: 5px;\n  align-items: center;\n  width: calc(100% + 22px);\n  margin-left: -11px;\n}\n\n.volume-icon {\n  color: #d6d3de;\n  font-size: 17px;\n  line-height: 1;\n  text-align: center;\n  pointer-events: none;\n}\n\n:is(#volume-slider, #system-volume-slider) {\n  --volume-progress: 0%;\n  display: block;\n  width: 100%;\n  min-width: 0;\n  height: 44px;\n  margin: 0;\n  padding: 0;\n  border: 0;\n  box-shadow: none;\n  background: transparent;\n  appearance: none;\n  -webkit-appearance: none;\n  touch-action: none;\n  user-select: none;\n  -webkit-user-select: none;\n}\n\n:is(#volume-slider, #system-volume-slider)::-webkit-slider-runnable-track {\n  height: 7px;\n  border-radius: 999px;\n  background: linear-gradient(\n    to right,\n    #ffffff 0%,\n    #ffffff var(--volume-progress),\n    rgba(255, 255, 255, .22) var(--volume-progress),\n    rgba(255, 255, 255, .22) 100%\n  );\n}\n\n:is(#volume-slider, #system-volume-slider)::-webkit-slider-thumb {\n  width: 24px;\n  height: 24px;\n  margin-top: -9px;\n  border: 0;\n  border-radius: 50%;\n  background: white;\n  box-shadow: 0 2px 9px rgba(0, 0, 0, .42);\n  appearance: none;\n  -webkit-appearance: none;\n}\n\n:is(#volume-slider, #system-volume-slider):disabled {\n  opacity: .42;\n}\n\n\n.controls {\n  display: grid;\n  grid-template-columns: 1fr 1.25fr 1fr;\n  gap: 13px;\n  align-items: center;\n}\n\nbutton {\n  width: 100%;\n  border: 0;\n\n  color: white;\n  background: rgba(255, 255, 255, .13);\n\n  box-shadow:\n    inset 0 1px rgba(255, 255, 255, .20),\n    0 10px 28px rgba(0, 0, 0, .28);\n\n  font: inherit;\n  cursor: pointer;\n}\n\nbutton:active {\n  transform: scale(.96);\n  background: rgba(255, 255, 255, .23);\n}\n\n.media-icon {\n  width: 38px;\n  height: 38px;\n  display: block;\n  margin: auto;\n  overflow: visible;\n  fill: none;\n  stroke: white;\n  stroke-width: 2.15;\n  stroke-linecap: round;\n  stroke-linejoin: round;\n  pointer-events: none;\n}\n\n.media-icon .icon-fill {\n  fill: white;\n  stroke: white;\n}\n\n#toggle .media-icon {\n  width: 45px;\n  height: 45px;\n}\n\n.transport {\n  min-height: 82px;\n  border-radius: 999px;\n  font-size: 34px;\n  font-family:\n    "Helvetica Neue",\n    Arial,\n    sans-serif;\n  font-variant-emoji: text;\n}\n\n#toggle {\n  min-height: 108px;\n  font-size: 45px;\n  background: #7b5cff;\n}\n\n.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin: 32px 3px 12px; }\n.section-heading .section-title { margin: 0; }\n.section-subtitle { margin-top: 4px; color: #85818f; font-size: 13px; font-weight: 550; line-height: 1.35; }\n.section-title {\n  margin: 30px 3px 12px;\n\n  color: #aaa6b5;\n\n  font-size: 13px;\n  font-weight: 750;\n  letter-spacing: .08em;\n  text-transform: uppercase;\n}\n\n.list {\n  display: grid;\n  gap: 11px;\n}\n\n.playlist-row { position: relative; min-width: 0; }\n.playlist-row .playlist-button { width: 100%; min-height: 80px; padding-right: 122px; }\n.playlist-row .playlist-copy { min-width: 0; overflow-wrap: anywhere; }\n.playlist-row .playlist-play-button,\n.playlist-row .shuffle-button {\n  position: absolute;\n  z-index: 1;\n  top: 50%;\n  display: grid;\n  place-items: center;\n  width: 44px;\n  min-width: 44px;\n  height: 44px;\n  min-height: 44px;\n  padding: 0;\n  border: 1px solid rgba(255, 255, 255, .14);\n  border-radius: 14px;\n  transform: translateY(-50%);\n  -webkit-appearance: none;\n  appearance: none;\n}\n.playlist-row .playlist-play-button { right: 64px; background: rgba(255, 255, 255, .17); }\n.playlist-row .shuffle-button { right: 12px; background: linear-gradient(135deg, #fa2d55, #8b5cff); }\n.playlist-row .playlist-play-button:active,\n.playlist-row .shuffle-button:active { transform: translateY(-50%) scale(.96); }\n.playlist-action-icon {\n  display: block;\n  width: 22px;\n  height: 22px;\n  fill: none;\n  stroke: currentColor;\n  stroke-width: 2;\n  stroke-linecap: round;\n  stroke-linejoin: round;\n  pointer-events: none;\n}\n.playlist-action-icon .play-glyph { fill: currentColor; stroke: none; }\n\n.playlist-button,\n.song-button {\n  min-height: 68px;\n  padding: 13px 17px;\n\n  border-radius: 19px;\n\n  text-align: left;\n  background: rgba(255, 255, 255, .10);\n}\n\n.playlist-button {\n  display: block;\n}\n\n.playlist-name,\n.song-title {\n  display: block;\n\n  font-size: 17px;\n  font-weight: 700;\n  line-height: 1.3;\n}\n\n.playlist-count,\n.song-artist {\n  display: block;\n  margin-top: 4px;\n\n  color: #aaa7b2;\n\n  font-size: 13px;\n  line-height: 1.35;\n}\n\n.header-row {\n  display: grid;\n  grid-template-columns: 76px 1fr 76px;\n  align-items: center;\n\n  margin-bottom: 18px;\n}\n\n.header-row h1 {\n  overflow: hidden;\n  margin: 0;\n\n  font-size: 23px;\n  text-overflow: ellipsis;\n  white-space: nowrap;\n}\n\n.back {\n  min-height: 44px;\n  border-radius: 15px;\n\n  font-size: 15px;\n  font-weight: 700;\n}\n\n.system-media-card {\n  position: relative;\n  overflow: hidden;\n  padding: 19px;\n  border: 1px solid rgba(255, 255, 255, .11);\n  border-radius: 24px;\n  background: linear-gradient(145deg, rgba(57, 113, 204, .20), rgba(255, 255, 255, .07));\n  box-shadow: inset 0 1px rgba(255, 255, 255, .17), 0 14px 34px rgba(0, 0, 0, .24);\n  backdrop-filter: blur(20px);\n  -webkit-backdrop-filter: blur(20px);\n}\n.system-media-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }\n.system-media-copy { min-width: 0; }\n.system-media-badge { flex: 0 0 auto; padding: 5px 9px; border: 1px solid rgba(143, 213, 255, .22); border-radius: 999px; color: #bce8ff; background: rgba(45, 132, 210, .17); font-size: 11px; font-weight: 750; letter-spacing: .06em; text-transform: uppercase; }\n.system-media-title { overflow: hidden; font-size: 19px; font-weight: 750; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }\n.system-media-details { min-height: 18px; margin-top: 5px; overflow: hidden; color: #bbb8c5; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }\n.system-media-controls { display: grid; grid-template-columns: 1fr 1.25fr 1fr; gap: 11px; align-items: center; margin-top: 17px; }\n.system-transport { display: grid; place-items: center; min-height: 68px; padding: 0; border-radius: 999px; background: rgba(255, 255, 255, .12); }\n.system-transport .media-icon { width: 31px; height: 31px; }\n#system-toggle { min-height: 82px; background: linear-gradient(145deg, #518fe9, #5262d8); }\n#system-toggle .media-icon { width: 39px; height: 39px; }\n.system-progress { margin-top: 13px; }\n#system-playback-seek { --seek-progress: 0%; display: block; width: 100%; height: 28px; margin: 0; padding: 0; border: 0; box-shadow: none; background: transparent; appearance: none; -webkit-appearance: none; touch-action: none; }\n#system-playback-seek::-webkit-slider-runnable-track { height: 5px; border-radius: 999px; background: linear-gradient(to right, #fff 0%, #fff var(--seek-progress), rgba(255,255,255,.22) var(--seek-progress), rgba(255,255,255,.22) 100%); }\n#system-playback-seek::-webkit-slider-thumb { width: 18px; height: 18px; margin-top: -6.5px; border: 0; border-radius: 50%; background: white; box-shadow: 0 2px 8px rgba(0,0,0,.38); appearance: none; -webkit-appearance: none; }\n#system-playback-seek:disabled { opacity: .42; }\nbutton:focus-visible, input:focus-visible { outline: 3px solid rgba(143, 213, 255, .82); outline-offset: 3px; }\n@media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition-duration: .01ms !important; animation-duration: .01ms !important; } }\n.system-controls {\n  display: grid;\n  grid-template-columns: repeat(3, minmax(0, 1fr));\n  gap: 11px;\n  margin-top: 0;\n}\n\n.system-button {\n  min-height: 58px;\n  padding: 12px 14px;\n\n  border-radius: 19px;\n\n  font-size: 15px;\n  font-weight: 750;\n  line-height: 1.25;\n}\n\n#airplay-devices {\n  background:\n    linear-gradient(\n      135deg,\n      #27a9a1,\n      #3971cc\n    );\n}\n\n.airplay-list {\n  display: grid;\n  gap: 12px;\n}\n\n.airplay-device {\n  padding: 15px;\n  border-radius: 19px;\n  background: rgba(255, 255, 255, .10);\n  box-shadow:\n    inset 0 1px rgba(255, 255, 255, .17),\n    0 10px 28px rgba(0, 0, 0, .25);\n}\n\n.airplay-device-name {\n  font-size: 17px;\n  font-weight: 750;\n}\n\n.airplay-device-uid {\n  margin-top: 5px;\n  overflow-wrap: anywhere;\n  color: #aaa7b2;\n  font-size: 12px;\n}\n\n.airplay-device-default {\n  margin-top: 7px;\n  color: #8fd5ff;\n  font-size: 13px;\n  font-weight: 750;\n}\n\n.airplay-device-actions {\n  display: grid;\n  grid-template-columns: 1fr 1fr;\n  gap: 9px;\n  margin-top: 13px;\n}\n\n.airplay-device-actions button {\n  min-height: 48px;\n  padding: 10px;\n  border-radius: 15px;\n  font-size: 14px;\n  font-weight: 750;\n}\n\n.airplay-connect-button {\n  background:\n    linear-gradient(\n      135deg,\n      #2f8cff,\n      #765cff\n    );\n}\n\n.airplay-default-button {\n  background:\n    linear-gradient(\n      135deg,\n      #3a9e72,\n      #277a8d\n    );\n}\n\n#connect-airplay {\n  background:\n    linear-gradient(\n      135deg,\n      #2f8cff,\n      #765cff\n    );\n}\n\n#disconnect-airplay {\n  background:\n    linear-gradient(\n      135deg,\n      #687080,\n      #343846\n    );\n}\n\n#restart-music {\n  background:\n    linear-gradient(\n      135deg,\n      #ee6a36,\n      #d83e63\n    );\n}\n\n#home-device {\n\n  background:\n    linear-gradient(\n      135deg,\n      #343746,\n      #181a22\n    );\n}\n\n.system-button:disabled {\n  opacity: .55;\n  cursor: default;\n  transform: none;\n}\n\n#status {\n  min-height: 24px;\n  margin-top: 17px;\n\n  color: #aaa7b2;\n\n  text-align: center;\n  font-size: 14px;\n}\n\n\n/* Playlist and queue-control styles. */\n.queue-mode-controls {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);\n  gap: 9px;\n  margin-top: 10px;\n}\n\n#repeat-mode,\n#shuffle-queue {\n  width: 100%;\n  min-width: 0;\n  min-height: 42px;\n  padding: 9px 8px;\n  border-radius: 14px;\n  -webkit-appearance: none;\n  appearance: none;\n  color: #d9d6e2;\n  background: rgba(255, 255, 255, .14);\n  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif !important;\n  font-size: 13px !important;\n  font-style: normal !important;\n  font-weight: 750 !important;\n  line-height: 1.2 !important;\n  letter-spacing: normal !important;\n  text-align: center;\n  text-transform: none !important;\n  white-space: nowrap;\n  -webkit-text-size-adjust: 100%;\n  text-size-adjust: 100%;\n}\n\n#repeat-mode.repeat-active,\n#shuffle-queue.shuffle-active {\n  color: white;\n  background: #7b5cff;\n}\n\n#repeat-mode.control-busy,\n#shuffle-queue.control-busy {\n  opacity: .72;\n  pointer-events: none;\n}\n\n\n/* Song search controls. */\n.search-box {\n  width: 100%;\n  min-height: 46px;\n  padding: 10px 14px;\n  border: 1px solid rgba(255, 255, 255, .16);\n  border-radius: 15px;\n  outline: none;\n  color: white;\n  background: rgba(255, 255, 255, .10);\n  font: inherit;\n  font-size: 15px;\n  -webkit-appearance: none;\n  appearance: none;\n}\n\n.search-box::placeholder {\n  color: #aaa7b2;\n}\n\n.search-box:focus {\n  border-color: rgba(123, 92, 255, .85);\n  box-shadow: 0 0 0 3px rgba(123, 92, 255, .18);\n}\n\n.search-results {\n  display: grid;\n  gap: 9px;\n  margin-top: 10px;\n}\n\n.search-message {\n  padding: 10px 3px;\n  color: #aaa7b2;\n  font-size: 13px;\n  line-height: 1.4;\n}\n\n\n.library-launchers {\n  display: grid;\n  grid-template-columns: 1fr 1fr;\n  gap: 11px;\n  margin-top: 0;\n}\n.library-launchers button,\n.upload-submit {\n  min-height: 56px;\n  border-radius: 18px;\n  font-weight: 750;\n}\n#open-all-songs { background: linear-gradient(135deg, #7b5cff, #3d73dc); }\n#open-upload { background: linear-gradient(135deg, #14a078, #277a8d); }\n.song-management-row {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr) 52px;\n  gap: 9px;\n}\n.playlist-song-row {\n  display: grid;\n  grid-template-columns: 48px minmax(0, 1fr);\n  gap: 9px;\n  align-items: stretch;\n}\n\n.playlist-song-membership {\n  display: flex;\n  align-items: center;\n  justify-content: center;\n  min-height: 68px;\n  border-radius: 19px;\n  background: rgba(255,255,255,.10);\n}\n\n.playlist-song-membership input {\n  width: 24px;\n  height: 24px;\n  margin: 0;\n  accent-color: #7b5cff;\n}\n.song-menu-button {\n  min-height: 68px;\n  border-radius: 19px;\n  font-size: 24px;\n}\n.upload-card, .membership-card {\n  padding: 18px;\n  border-radius: 21px;\n  background: rgba(255,255,255,.10);\n}\n.upload-card input[type=file] {\n  width: 100%;\n  margin-bottom: 14px;\n  color: white;\n}\n.upload-file-list {\n  display: grid;\n  gap: 8px;\n  margin: 0 0 14px;\n}\n.upload-file-row {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr) 34px;\n  gap: 8px;\n  align-items: center;\n  min-height: 42px;\n  padding: 7px 7px 7px 12px;\n  border-radius: 13px;\n  background: rgba(255,255,255,.08);\n}\n.upload-file-name {\n  overflow: hidden;\n  color: #e8e5ee;\n  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;\n  font-size: 15px;\n  font-style: normal;\n  font-weight: 700;\n  line-height: 1.3;\n  letter-spacing: normal;\n  -webkit-text-size-adjust: 100%;\n  text-size-adjust: 100%;\n  text-overflow: ellipsis;\n  white-space: nowrap;\n}\n.upload-file-remove {\n  width: 34px;\n  min-height: 34px;\n  padding: 0;\n  border-radius: 999px;\n  color: white;\n  background: rgba(255,255,255,.14);\n  font-size: 19px;\n  font-weight: 700;\n  line-height: 1;\n}\n.upload-file-remove:active {\n  background: rgba(216,62,99,.72);\n}\n.playlist-checks { display: grid; gap: 9px; margin: 12px 0; }\n.playlist-check {\n  display: flex;\n  gap: 10px;\n  align-items: center;\n  min-height: 44px;\n  padding: 9px 12px;\n  border-radius: 14px;\n  background: rgba(255,255,255,.08);\n}\n.destructive {\n  margin-top: 16px;\n  min-height: 52px;\n  border-radius: 16px;\n  background: linear-gradient(135deg, #d83e63, #98233d);\n  font-weight: 750;\n}\n.upload-complete-panel {\n  margin: 0 0 18px;\n  padding: 15px 17px;\n  border: 1px solid rgba(112, 235, 177, .30);\n  border-radius: 18px;\n  color: #eafff3;\n  background: rgba(27, 132, 91, .24);\n  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;\n  font-size: 15px;\n  font-style: normal;\n  font-weight: 700;\n  line-height: 1.35;\n  letter-spacing: normal;\n  text-align: center;\n  -webkit-text-size-adjust: 100%;\n  text-size-adjust: 100%;\n}\n\n\n.playlist-management-bar {\n  display: grid;\n  grid-template-columns: repeat(3, minmax(0, 1fr));\n  gap: 9px;\n  margin-bottom: 12px;\n}\n\n.playlist-management-button {\n  min-height: 46px;\n  padding: 10px 12px;\n  border-radius: 15px;\n  font-size: 14px;\n  font-weight: 750;\n}\n\n#playlist-add-songs {\n  background:\n    linear-gradient(\n      135deg,\n      #2f8cff,\n      #765cff\n    );\n}\n\n#playlist-rename {\n  background: linear-gradient(135deg, #7b5cff, #3d73dc);\n}\n\n#playlist-remove {\n  background:\n    linear-gradient(\n      135deg,\n      #8e3447,\n      #5e2737\n    );\n}\n\n#create-playlist {\n  margin: 0 0 12px;\n  background:\n    linear-gradient(\n      135deg,\n      #3a9e72,\n      #277a8d\n    );\n}\n\n.playlist-candidate-row {\n  display: grid;\n  grid-template-columns: 30px minmax(0, 1fr);\n  gap: 11px;\n  align-items: center;\n  min-height: 62px;\n  padding: 10px 14px;\n  border-radius: 17px;\n  background: rgba(255, 255, 255, .10);\n}\n\n.playlist-candidate-row input {\n  width: 22px;\n  height: 22px;\n  margin: 0;\n}\n\n.playlist-candidate-details {\n  min-width: 0;\n}\n\n.playlist-candidate-title {\n  display: block;\n  font-size: 16px;\n  font-weight: 750;\n  line-height: 1.3;\n}\n\n.playlist-candidate-artist {\n  display: block;\n  margin-top: 3px;\n  color: #aaa7b2;\n  font-size: 12px;\n  line-height: 1.35;\n}\n\n#playlist-add-selected {\n  min-height: 52px;\n  margin: 0 0 12px;\n  padding: 11px 14px;\n  border-radius: 17px;\n  background: #7b5cff;\n  font-size: 15px;\n  font-weight: 750;\n}\n\n\n.sonobus-card{margin:18px 0;padding:18px;border:1px solid #ffffff24;border-radius:24px;background:linear-gradient(145deg,#ffffff18,#ffffff0a);box-shadow:inset 0 1px #ffffff24,0 18px 45px #0004}.sonobus-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.sonobus-head h2{margin:3px 0 12px;font-size:21px}.sonobus-kicker,.sonobus-section-label{font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#bdb7cb}.sonobus-section-label{margin:17px 2px 8px}.sonobus-grid{display:grid;gap:10px}.sonobus-grid.three{grid-template-columns:repeat(3,1fr)}.sonobus-grid.four{grid-template-columns:repeat(4,minmax(0,1fr))}.sonobus-grid.two{grid-template-columns:repeat(2,1fr)}.sonobus-grid button,.sonobus-form button,.sonobus-close{min-height:50px;border-radius:16px;background:#ffffff18;border:1px solid #ffffff14;color:#fff;font-weight:750}.sonobus-grid button.active{background:linear-gradient(135deg,#3f8eff,#865dff);box-shadow:0 9px 24px #503dd05c}.sonobus-manage{margin-top:18px}.sonobus-note{color:#b9b4c5;font-size:12px;margin:12px 2px 0}.sonobus-form{display:grid;gap:10px;margin-top:12px}.sonobus-form input{width:100%;min-height:48px;border:1px solid #ffffff1f;border-radius:14px;padding:0 14px;background:#0e1018;color:#fff}.sonobus-profile{display:flex;align-items:center;gap:10px;padding:11px 0;border-bottom:1px solid #ffffff12}.sonobus-profile-main{flex:1}.sonobus-profile-name{font-weight:800}.sonobus-profile-meta{font-size:12px;color:#b9b4c5}.sonobus-profile button{min-height:38px;padding:0 12px;border-radius:12px;background:#ffffff17;color:#fff}.sonobus-profile.selected{color:#a9d4ff}#sonobus-state-badge{padding:7px 10px;border-radius:999px;background:#ffffff16;font-size:12px;color:#c9c5d2}\n\n#restart-sonobus.is-restarting {\n  position: relative;\n  color: transparent;\n  pointer-events: none;\n}\n#restart-sonobus.is-restarting::after {\n  content: "Restarting SonoBus…";\n  position: absolute;\n  inset: 0;\n  display: grid;\n  place-items: center;\n  color: #fff;\n}\n#sonobus-state-badge.is-restarting {\n  border-color: rgba(255, 190, 92, 0.52);\n  background: rgba(255, 159, 10, 0.16);\n  color: #ffd39a;\n}\n\n.batch-toolbar { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin:12px 0; padding:12px; border-radius:14px; background:rgba(255,255,255,.055); }\n.batch-toolbar button { min-height:42px; }\n.batch-select { width:24px; height:24px; flex:0 0 auto; accent-color:#64b5ff; }\n.batch-selected { background:rgba(100,181,255,.1); border-color:rgba(100,181,255,.45); }\n\n/* Library artwork. A missing cover remains a deliberate, clean tile. */\n.song-management-row { grid-template-columns: 34px minmax(0, 1fr) 52px; align-items: center; }\n.song-management-row .batch-select { margin: auto; }\n.song-button.has-artwork, .playlist-button.has-artwork {\n  display: flex; align-items: center; gap: 12px;\n}\n.song-copy, .playlist-copy { min-width: 0; flex: 1; }\n.song-artwork {\n  flex: 0 0 48px; width: 48px; height: 48px;\n  position: relative; display: grid; place-items: center; overflow: hidden;\n  border-radius: 11px; background: linear-gradient(145deg, #433b68, #222d42);\n  color: #c8c1e9; font-size: 24px; line-height: 1;\n}\n.song-artwork::before { content: \'♫\'; }\n.song-artwork img { position: absolute; inset: 0; display: block; width: 100%; height: 100%; object-fit: cover; }\n.playlist-artwork { flex-basis: 54px; width: 54px; height: 54px; }\n.playlist-candidate-row { grid-template-columns: 30px 48px minmax(0, 1fr); }\n#song-manage-artwork { width: 80px; height: 80px; margin: 0 auto 14px; border-radius: 16px; font-size: 34px; }\n/* Webremote UI spacing, volume glyphs, and back-to-top */\n.volume-slider-row {\n  grid-template-columns: 22px minmax(0, 1fr) 22px;\n  gap: 10px;\n  width: 100%;\n  margin-left: 0;\n}\n.volume-icon { display: grid; place-items: center; }\n.volume-icon svg { width: 19px; height: 19px; display: block; fill: none;\n  stroke: currentColor; stroke-width: 1.8; stroke-linecap: round;\n  stroke-linejoin: round; }\n#song-list, #all-song-list, #playlist-add-list { margin-top: 14px; }\n#global-song-results:empty { display: none; }\n#playlist-list { margin-top: 12px; }\n#back-to-top {\n  position: fixed;\n  z-index: 100;\n  top: calc(env(safe-area-inset-top) + 68px);\n  right: max(18px, env(safe-area-inset-right));\n  width: auto;\n  max-width: calc(100vw - 36px);\n  min-height: 44px;\n  padding: 10px 16px;\n  border: 1px solid rgba(255,255,255,.24);\n  border-radius: 999px;\n  background: #32254d;\n  box-shadow: 0 8px 28px rgba(0,0,0,.42);\n  font-size: 14px;\n  font-weight: 700;\n}\n/* Final song-list consistency pass */\n#song-list .song-title, #all-song-list .song-title {\n  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;\n  font-size: 17px; font-weight: 700; line-height: 1.3;\n  -webkit-text-size-adjust: 100%; text-size-adjust: 100%;\n}\n#song-list .song-artist, #all-song-list .song-artist {\n  font-size: 13px; font-weight: 400; line-height: 1.35;\n  -webkit-text-size-adjust: 100%; text-size-adjust: 100%;\n}\n/* Webremote Apple Music submenu navigation */\n.music-menu-launch {\n  display: block;\n  min-height: 58px;\n  margin: 20px 0 0;\n  padding: 12px 18px;\n  border-radius: 19px;\n  background: linear-gradient(135deg, #7b5cff, #3d73dc);\n  font-size: 17px;\n  font-weight: 750;\n}\n#music-screen .header-row { margin-bottom: 22px; }\n#music-screen .section-heading:first-of-type { margin-top: 0; }\n#main-screen > .section-heading:first-of-type { margin-top: 8px; }\n#main-screen > .system-controls { margin-top: 12px; }\n\n/* Shared indigo, blue and mint surfaces with compact route controls. */\n:root{--v:#8574f5;--b:#6c9cff;--g:#55d9ae}\nbody{background:radial-gradient(900px 520px at 50% -150px,#514784,#1d2039 48%,#0b101b)}\nmain{width:min(100%,480px)}\n#main-screen>.sonobus-card{margin:13px 0;padding:16px;border-color:#a8b7ef25;background:linear-gradient(145deg,#b8c8ff18,#a8b8ee0a)}\n#main-screen>.sonobus-card .sonobus-section-label{margin:12px 2px 7px}\n#main-screen>.sonobus-card .sonobus-grid.three{gap:9px}\n#main-screen>.sonobus-card .sonobus-grid.three button{min-height:50px;padding:8px 5px;border-radius:15px;font-size:14px}\n#main-screen>.sonobus-card .sonobus-manage{margin-top:12px}\n#main-screen>.section-heading{margin-top:21px;margin-bottom:9px}\n#main-screen>.system-media-card{border-color:#a8b7ef25;background:linear-gradient(145deg,#b8c8ff18,#a8b8ee0a)}\n#main-screen>.music-menu-launch{background:linear-gradient(135deg,var(--b),var(--v))}\n#main-screen>.sonobus-card .sonobus-grid button.active{background:linear-gradient(135deg,var(--b),var(--v))}\n</style>\n</head>\n\n<body>\n<main>\n  <section id="main-screen">\n    <h1>iPad Music Remote</h1>\n    <div id="upload-complete-panel" class="upload-complete-panel hidden" aria-live="polite"></div>\n\n    <div class="section-heading"><div><div class="section-title">System Media</div></div></div>\n    <div class="system-media-card">\n      <div class="system-media-heading"><div class="system-media-copy"><div id="system-current-title" class="system-media-title">Loading…</div><div id="system-current-details" class="system-media-details"></div></div><span class="system-media-badge">System</span></div>\n      <div class="system-media-controls">\n        <button class="system-transport" type="button" data-system-command="previous" aria-label="Previous system track"><svg class="media-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5v14"></path><path d="M18 6.5 8.5 12 18 17.5z"></path></svg></button>\n        <button class="system-transport" id="system-toggle" type="button" data-system-command="toggle" aria-label="Play system media"><svg class="media-icon" viewBox="0 0 24 24" aria-hidden="true"><path class="icon-fill" d="M8 5.5 19 12 8 18.5z"></path></svg></button>\n        <button class="system-transport" type="button" data-system-command="next" aria-label="Next system track"><svg class="media-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 5v14"></path><path d="M6 6.5 15.5 12 6 17.5z"></path></svg></button>\n      </div>\n      <div class="system-progress"><input id="system-playback-seek" type="range" min="0" max="0" step="0.1" value="0" disabled aria-label="System playback position"><div class="playback-times"><span id="system-playback-elapsed">0:00</span><span id="system-playback-duration">0:00</span></div></div>\n      <div class="volume-control">\n        <div class="volume-slider-row">\n          <span class="volume-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 10v4h4l5 4V6l-5 4H4z"/></svg></span>\n          <input id="system-volume-slider" type="range" min="0" max="100" step="6.25" value="0" aria-label="iPad system volume">\n          <span class="volume-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 10v4h4l5 4V6l-5 4H3z"/><path d="M16 9a4 4 0 0 1 0 6"/><path d="M19 6a8 8 0 0 1 0 12"/></svg></span>\n        </div>\n      </div>\n    </div>\n    <button id="open-music-menu" class="music-menu-launch" type="button" aria-controls="music-screen">\n      Apple Music\n    </button>\n    <section id="sonobus-home" class="sonobus-card">\n      <div class="sonobus-head"><div><h2>Audio destinations</h2></div><span id="sonobus-state-badge">Loading</span></div>\n      <div class="sonobus-section-label">Playing from external</div>\n      <div class="sonobus-grid three">\n        <button data-sonobus-preset="ipad-local">External</button><button data-sonobus-preset="ipad-laptop">Laptop</button><button data-sonobus-preset="ipad-both">Both</button>\n      </div>\n      <div class="sonobus-section-label">Playing from laptop</div>\n      <div class="sonobus-grid three">\n        <button data-sonobus-preset="laptop-ipad">External</button><button data-sonobus-preset="laptop-local">Laptop</button><button data-sonobus-preset="laptop-both">Both</button>\n      </div>\n    </section>\n    <div class="section-heading"><div><div class="section-title">AirPlay &amp; Device</div></div></div>\n    <div class="system-controls">\n\n      <button\n        id="connect-airplay"\n        class="system-button"\n        type="button"\n      >\n        Connect AirPlay\n      </button>\n\n      <button\n        id="airplay-devices"\n        class="system-button"\n        type="button"\n      >\n        AirPlay Devices\n      </button>\n\n      <button\n        id="disconnect-airplay"\n        class="system-button"\n        type="button"\n      >\n        Disconnect AirPlay\n      </button>\n\n      <button\n        id="restart-music"\n        class="system-button"\n        type="button"\n      >\n        Restart Music\n      </button>\n      <button id="restart-sonobus" class="system-button" type="button">Restart SonoBus</button>\n      <button\n        id="home-device"\n        class="system-button"\n        type="button"\n      >\n        Wake iPad\n      </button>\n    </div>\n\n\n\n  </section>\n\n  <section id="music-screen" class="hidden">\n    <div class="header-row">\n      <button id="music-menu-back" class="back" type="button">Back</button>\n      <h1>Apple Music</h1><div></div>\n    </div>\n    <div class="section-heading"><div><div class="section-title">Apple Music</div></div></div>\n    <div class="now-playing">\n      <div class="now-label">Now Playing</div>\n      <div class="apple-now-playing-header">\n        <span id="apple-now-playing-artwork" class="song-artwork" aria-hidden="true"></span>\n        <div class="apple-now-playing-copy">\n          <div id="current-title">Loading…</div>\n          <div id="current-details"></div>\n        </div>\n      </div>\n\n      <div class="playback-progress">\n        <input\n          id="playback-seek"\n          type="range"\n          min="0"\n          max="0"\n          step="0.1"\n          value="0"\n          disabled\n          aria-label="Playback position"\n        >\n\n        <div class="playback-times">\n          <span id="playback-elapsed">0:00</span>\n          <span id="playback-duration">0:00</span>\n        </div>\n      </div>\n\n      <div class="volume-control">\n        <div class="volume-slider-row">\n          <span class="volume-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 10v4h4l5 4V6l-5 4H4z"/></svg></span>\n\n          <input\n            id="volume-slider"\n            type="range"\n            min="0"\n            max="100"\n            step="6.25"\n            value="0"\n            aria-label="iPad volume"\n          >\n\n          <span class="volume-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 10v4h4l5 4V6l-5 4H3z"/><path d="M16 9a4 4 0 0 1 0 6"/><path d="M19 6a8 8 0 0 1 0 12"/></svg></span>\n        </div>\n\n\n        <div class="queue-mode-controls">\n          <button\n            id="repeat-mode"\n            type="button"\n            aria-label="Repeat mode off"\n          >\n            Repeat Off\n          </button>\n\n          <button\n            id="shuffle-queue"\n            type="button"\n            aria-label="Queue shuffle off"\n          >\n            Shuffle Off\n          </button>\n        </div>\n      </div>\n    </div>\n\n    <div class="controls">\n      <button\n        class="transport"\n        type="button"\n        data-command="previous"\n        aria-label="Previous track"\n      >\n        <svg\n          class="media-icon"\n          viewBox="0 0 24 24"\n          aria-hidden="true"\n        >\n          <path d="M6 5v14"></path>\n          <path d="M18 6.5 8.5 12 18 17.5z"></path>\n        </svg>\n      </button>\n\n      <button\n        class="transport"\n        id="toggle"\n        type="button"\n        data-command="toggle"\n        aria-label="Play or pause"\n      >\n        <svg\n          class="media-icon"\n          viewBox="0 0 24 24"\n          aria-hidden="true"\n        >\n          <path class="icon-fill" d="M8 5.5 19 12 8 18.5z"></path>\n        </svg>\n      </button>\n\n      <button\n        class="transport"\n        type="button"\n        data-command="next"\n        aria-label="Next track"\n      >\n        <svg\n          class="media-icon"\n          viewBox="0 0 24 24"\n          aria-hidden="true"\n        >\n          <path d="M18 5v14"></path>\n          <path d="M6 6.5 15.5 12 6 17.5z"></path>\n        </svg>\n      </button>\n    </div>\n\n    <div class="section-heading"><div><div class="section-title">Music Library</div></div></div>\n    <div class="library-launchers">\n      <button id="open-all-songs" type="button">All Songs</button>\n      <button id="open-upload" type="button">Upload Music</button>\n    </div>\n\n    <div class="section-heading"><div><div class="section-title">Playlists</div></div></div>\n    <button\n      id="create-playlist"\n      class="playlist-management-button"\n      type="button"\n    >\n      New Playlist\n    </button>\n\n    <div\n      id="playlist-list"\n      class="list"\n    ></div>\n  </section>\n\n  <section\n    id="playlist-screen"\n    class="hidden"\n  >\n    <div class="header-row">\n      <button\n        id="back"\n        class="back"\n        type="button"\n      >\n        Back\n      </button>\n\n      <h1 id="playlist-title">\n        Playlist\n      </h1>\n\n      <div></div>\n    </div>\n\n\n    <div class="playlist-management-bar">\n      <button\n        id="playlist-add-songs"\n        class="playlist-management-button"\n        type="button"\n      >\n        Add Songs\n      </button>\n\n      <button\n        id="playlist-rename"\n        class="playlist-management-button"\n        type="button"\n      >\n        Rename Playlist\n      </button>\n\n      <button\n        id="playlist-remove"\n        class="playlist-management-button"\n        type="button"\n      >\n        Remove Playlist\n      </button>\n    </div>\n\n    <div class="batch-toolbar">\n      <label><input id="playlist-select-all" type="checkbox"> Select all</label>\n      <button id="playlist-batch-remove" type="button">Remove selected from playlist</button>\n      <button id="playlist-batch-library" class="destructive" type="button">Remove selected from library</button>\n    </div>\n\n    <input\n      id="playlist-song-search"\n      class="search-box"\n      type="search"\n      inputmode="search"\n      autocomplete="off"\n      placeholder="Search this playlist"\n      aria-label="Search songs in this playlist"\n    >\n\n    <div\n      id="playlist-search-message"\n      class="search-message hidden"\n      aria-live="polite"\n    ></div>\n\n    <div\n      id="song-list"\n      class="list"\n    ></div>\n  </section>\n\n\n  <section id="all-songs-screen" class="hidden">\n    <div class="header-row">\n      <button id="all-songs-back" class="back" type="button">Back</button>\n      <h1>All Songs</h1><div></div>\n    </div>\n    <div class="batch-toolbar">\n      <label><input id="all-songs-select-all" type="checkbox"> Select all</label>\n      <button id="all-songs-batch-library" class="destructive" type="button">Remove selected from library</button>\n    </div>\n    <input id="global-song-search" class="search-box" type="search"\n      inputmode="search" autocomplete="off" placeholder="Search all songs"\n      aria-label="Search all songs">\n    <div id="global-song-results" class="search-results" aria-live="polite"></div>\n    <div id="all-song-list" class="list"></div>\n  </section>\n\n  <section id="upload-screen" class="hidden">\n    <div class="header-row">\n      <button id="upload-back" class="back" type="button">Back</button>\n      <h1>Upload Music</h1><div></div>\n    </div>\n    <div class="upload-card">\n      <input id="music-files" type="file" multiple\n        accept="audio/mp4,audio/m4a,audio/mpeg,audio/aac,audio/wav,.m4a,.mp3,.aac,.alac,.wav">\n      <div id="upload-file-list" class="upload-file-list" aria-live="polite"></div>\n      <div class="playlist-checks" id="upload-playlist-checks"></div>\n      <button id="upload-submit" class="upload-submit" type="button">Import Selected Files</button>\n    </div>\n  </section>\n\n  <section id="song-manage-screen" class="hidden">\n    <div class="header-row">\n      <button id="song-manage-back" class="back" type="button">Back</button>\n      <h1 id="song-manage-title">Song</h1><div></div>\n    </div>\n    <div class="membership-card">\n      <div id="song-manage-artwork" class="song-artwork" aria-hidden="true">♫</div>\n      <div id="song-manage-details" class="song-artist"></div>\n      <div id="song-playlist-checks" class="playlist-checks"></div>\n      <button id="remove-from-library" class="destructive" type="button">Remove from Library</button>\n    </div>\n  </section>\n\n  <section\n    id="airplay-screen"\n    class="hidden"\n  >\n    <div class="header-row">\n      <button\n        id="airplay-back"\n        class="back"\n        type="button"\n      >\n        Back\n      </button>\n\n      <h1>\n        AirPlay Devices\n      </h1>\n\n      <div></div>\n    </div>\n\n    <div\n      id="airplay-list"\n      class="airplay-list"\n    ></div>\n  </section>\n\n\n  <section\n    id="playlist-add-screen"\n    class="hidden"\n  >\n    <div class="header-row">\n      <button\n        id="playlist-add-back"\n        class="back"\n        type="button"\n      >\n        Back\n      </button>\n\n      <h1 id="playlist-add-title">\n        Add Songs\n      </h1>\n\n      <div></div>\n    </div>\n\n    <input\n      id="playlist-add-search"\n      class="search-box"\n      type="search"\n      inputmode="search"\n      autocomplete="off"\n      placeholder="Search available songs"\n      aria-label="Search songs not in this playlist"\n    >\n\n    <div\n      id="playlist-add-list"\n      class="list"\n    ></div>\n\n    <button\n      id="playlist-add-selected"\n      type="button"\n    >\n      Add Selected Songs\n    </button>\n  </section>\n\n  \n</main>\n<button id="back-to-top" class="hidden" type="button" aria-label="Go back to top of page">Back to top ↑</button>\n\n<script>\nconst mainScreen =\n  document.querySelector("#main-screen");\nconst musicScreen = document.querySelector("#music-screen");\n\nconst playlistScreen =\n  document.querySelector("#playlist-screen");\n\nconst playlistList =\n  document.querySelector("#playlist-list");\n\nconst songList =\n  document.querySelector("#song-list");\n\nconst playlistTitle =\n  document.querySelector("#playlist-title");\n\nconst uploadCompletePanel =\n  document.querySelector("#upload-complete-panel");\n\nconst currentTitle =\n  document.querySelector("#current-title");\n\nconst currentDetails =\n  document.querySelector("#current-details");\nconst appleNowPlayingArtwork = document.querySelector("#apple-now-playing-artwork");\nlet appleNowPlayingArtworkID = "";\nfunction updateAppleNowPlayingArtwork(id) {\n  const nextID = id && /^\\d+$/.test(String(id)) ? String(id) : "";\n  if (nextID === appleNowPlayingArtworkID) return;\n  appleNowPlayingArtworkID = nextID;\n  appleNowPlayingArtwork.replaceChildren();\n  if (!nextID) return;\n  const image = document.createElement("img");\n  image.alt = "";\n  image.decoding = "async";\n  image.addEventListener("error", () => image.remove(), {once: true});\n  image.src = "/api/song/artwork?id=" + encodeURIComponent(nextID);\n  appleNowPlayingArtwork.appendChild(image);\n}\nconst playbackSeek =\n  document.querySelector(\n    "#playback-seek"\n  );\n\nconst playbackElapsed =\n  document.querySelector(\n    "#playback-elapsed"\n  );\n\nconst playbackDuration =\n  document.querySelector(\n    "#playback-duration"\n  );\nconst volumeSlider =\n  document.querySelector(\n    "#volume-slider"\n  );\nconst systemVolumeSlider = document.querySelector("#system-volume-slider");\nconst volumeSliders = [volumeSlider, systemVolumeSlider];\nconst repeatModeButton =\n  document.querySelector(\n    "#repeat-mode"\n  );\nconst shuffleQueueButton =\n  document.querySelector(\n    "#shuffle-queue"\n  );\n\nconst toggleButton =\n  document.querySelector("#toggle");\nconst systemCurrentTitle = document.querySelector("#system-current-title");\nconst systemCurrentDetails = document.querySelector("#system-current-details");\nconst systemToggleButton = document.querySelector("#system-toggle");\nconst systemPlaybackSeek = document.querySelector("#system-playback-seek");\nconst systemPlaybackElapsed = document.querySelector("#system-playback-elapsed");\nconst systemPlaybackDuration = document.querySelector("#system-playback-duration");\n\nconst connectAirPlayButton =\n  document.querySelector(\n    "#connect-airplay"\n  );\n\nconst airPlayDevicesButton =\n  document.querySelector(\n    "#airplay-devices"\n  );\n\nconst airPlayScreen =\n  document.querySelector(\n    "#airplay-screen"\n  );\n\nconst airPlayList =\n  document.querySelector(\n    "#airplay-list"\n  );\n\nconst airPlayBackButton =\n  document.querySelector(\n    "#airplay-back"\n  );\n\nconst restartMusicButton =\n  document.querySelector(\n    "#restart-music"\n  );\n\nconst disconnectAirPlayButton =\n  document.querySelector(\n    "#disconnect-airplay"\n  );\nconst homeDeviceButton =\n  document.querySelector(\n    "#home-device"\n  );\n\nconst globalSongSearch =\n  document.querySelector("#global-song-search");\nconst globalSongResults =\n  document.querySelector("#global-song-results");\nconst playlistSongSearch =\n  document.querySelector("#playlist-song-search");\nconst playlistSearchMessage =\n  document.querySelector("#playlist-search-message");\n\nlet allPlaylists = [];\nlet currentPlaylistName = "";\nlet playlistAddCandidates = [];\n\nfunction normalizeSearchText(value) {\n  return String(value || "")\n    .normalize("NFKD")\n    .toLocaleLowerCase();\n}\n\n\nfunction filterCurrentPlaylistSongs() {\n  const query = normalizeSearchText(\n    playlistSongSearch.value.trim()\n  );\n  let visible = 0;\n\n  for (const row of songList.querySelectorAll(\n    ".playlist-song-row"\n  )) {\n    const button =\n      row.querySelector(".song-button");\n\n    const show = !query\n      || normalizeSearchText(\n          button?.textContent\n        ).includes(query);\n\n    row.classList.toggle(\n      "hidden",\n      !show\n    );\n\n    if (show) {\n      visible += 1;\n    }\n  }\n\n  playlistSearchMessage.classList.toggle(\n    "hidden",\n    visible !== 0 || !query\n  );\n  playlistSearchMessage.textContent =\n    visible === 0 && query\n      ? "No matching songs in this playlist"\n      : "";\n}\n\n\nplaylistSongSearch.addEventListener(\n  "input",\n  filterCurrentPlaylistSongs\n);\n\nconst ICONS = {\n  play: `\n    <svg\n      class="media-icon"\n      viewBox="0 0 24 24"\n      aria-hidden="true"\n    >\n      <path\n        class="icon-fill"\n        d="M8 5.5 19 12 8 18.5z"\n      ></path>\n    </svg>\n  `,\n\n  pause: `\n    <svg\n      class="media-icon"\n      viewBox="0 0 24 24"\n      aria-hidden="true"\n    >\n      <rect\n        class="icon-fill"\n        x="7"\n        y="5.5"\n        width="3.5"\n        height="13"\n        rx="1"\n      ></rect>\n\n      <rect\n        class="icon-fill"\n        x="13.5"\n        y="5.5"\n        width="3.5"\n        height="13"\n        rx="1"\n      ></rect>\n    </svg>\n  `\n};\n\nlet seekInteractionActive = false;\nlet liveSeekTimer = null;\nlet liveSeekInFlight = false;\nlet pendingLiveSeek = null;\n\n\nfunction formatPlaybackTime(value) {\n  const totalSeconds =\n    Number.isFinite(Number(value))\n      ? Math.max(\n          0,\n          Math.floor(Number(value))\n        )\n      : 0;\n\n  const hours =\n    Math.floor(totalSeconds / 3600);\n\n  const minutes =\n    Math.floor(\n      (totalSeconds % 3600) / 60\n    );\n\n  const seconds =\n    totalSeconds % 60;\n\n  if (hours > 0) {\n    return (\n      hours\n      + ":"\n      + String(minutes).padStart(2, "0")\n      + ":"\n      + String(seconds).padStart(2, "0")\n    );\n  }\n\n  return (\n    minutes\n    + ":"\n    + String(seconds).padStart(2, "0")\n  );\n}\n\n\nfunction updateSeekDisplay(\n  currentTime,\n  duration\n) {\n  const safeDuration =\n    Number.isFinite(Number(duration))\n      ? Math.max(0, Number(duration))\n      : 0;\n\n  const safeCurrentTime =\n    Number.isFinite(Number(currentTime))\n      ? Math.max(\n          0,\n          Math.min(\n            Number(currentTime),\n            safeDuration > 0\n              ? safeDuration\n              : Number(currentTime)\n          )\n        )\n      : 0;\n\n  if (!seekInteractionActive) {\n    playbackSeek.max =\n      String(safeDuration);\n\n    playbackSeek.value =\n      String(safeCurrentTime);\n  }\n\n  const displayedTime =\n    seekInteractionActive\n      ? Number(playbackSeek.value)\n      : safeCurrentTime;\n\n  const progress =\n    safeDuration > 0\n      ? (\n          displayedTime\n          / safeDuration\n          * 100\n        )\n      : 0;\n\n  playbackSeek.style.setProperty(\n    "--seek-progress",\n    progress + "%"\n  );\n\n  playbackElapsed.textContent =\n    formatPlaybackTime(displayedTime);\n\n  playbackDuration.textContent =\n    formatPlaybackTime(safeDuration);\n\n  playbackSeek.disabled =\n    safeDuration <= 0;\n}\n\n\nasync function sendLiveSeek(\n  seconds\n) {\n  if (liveSeekInFlight) {\n    pendingLiveSeek = seconds;\n    return;\n  }\n\n  liveSeekInFlight = true;\n\n  try {\n    await readJSON(\n      "/api/seek",\n      {\n        method: "POST",\n        headers: {\n          "Content-Type":\n            "application/json"\n        },\n        body: JSON.stringify({\n          seconds: seconds\n        })\n      }\n    );\n\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n\n  } finally {\n    liveSeekInFlight = false;\n\n    if (pendingLiveSeek !== null) {\n      const nextSeek =\n        pendingLiveSeek;\n\n      pendingLiveSeek = null;\n\n      sendLiveSeek(nextSeek);\n    }\n  }\n}\n\n\nfunction scheduleLiveSeek() {\n  const seconds =\n    Number(playbackSeek.value);\n\n  if (liveSeekTimer !== null) {\n    clearTimeout(liveSeekTimer);\n  }\n\n  liveSeekTimer = setTimeout(\n    () => {\n      liveSeekTimer = null;\n      sendLiveSeek(seconds);\n    },\n    120\n  );\n}\n\n\nasync function commitPlaybackSeek() {\n  const seconds =\n    Number(playbackSeek.value);\n\n  if (liveSeekTimer !== null) {\n    clearTimeout(liveSeekTimer);\n    liveSeekTimer = null;\n  }\n\n  pendingLiveSeek = null;\n\n  try {\n    await readJSON(\n      "/api/seek",\n      {\n        method: "POST",\n        headers: {\n          "Content-Type":\n            "application/json"\n        },\n        body: JSON.stringify({\n          seconds: seconds\n        })\n      }\n    );\n\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n\n  } finally {\n    seekInteractionActive = false;\n\n    setTimeout(\n      updateNowPlaying,\n      150\n    );\n  }\n}\n\n\nplaybackSeek.addEventListener(\n  "pointerdown",\n  () => {\n    seekInteractionActive = true;\n  }\n);\n\n\nplaybackSeek.addEventListener(\n  "touchstart",\n  () => {\n    seekInteractionActive = true;\n  },\n  {\n    passive: true\n  }\n);\n\n\nplaybackSeek.addEventListener(\n  "input",\n  () => {\n    seekInteractionActive = true;\n\n    updateSeekDisplay(\n      Number(playbackSeek.value),\n      Number(playbackSeek.max)\n    );\n\n    scheduleLiveSeek();\n  }\n);\n\n\nplaybackSeek.addEventListener(\n  "change",\n  commitPlaybackSeek\n);\n\n\nlet volumeTimer = null;\nlet volumeWriteInFlight = false;\nlet pendingVolumeWrite = null;\nlet volumeDragActive = false;\nlet volumePollAbortController = null;\nlet lastQueuedVolumeSent = null;\n\nfunction clampVolume(value) {\n  const numeric = Number(value);\n  return Number.isFinite(numeric)\n    ? Math.max(0, Math.min(100, numeric))\n    : 0;\n}\n\nfunction drawVolume(value) {\n  const percent = clampVolume(value);\n  for (const slider of volumeSliders) {\n    slider.value = String(percent);\n    slider.style.setProperty("--volume-progress", percent + "%");\n  }\n}\n\nfunction reportedIPadVolume(result) {\n  /*\n   * The normalized 0..1 system-volume value is the source of truth.\n   * percent is used only as a compatibility fallback.\n   */\n  const normalized = Number(result.volume);\n\n  if (Number.isFinite(normalized)) {\n    return clampVolume(normalized * 100);\n  }\n\n  return clampVolume(result.percent);\n}\n\nasync function loadVolumeState() {\n  if (\n    volumeDragActive\n    || volumeWriteInFlight\n    || pendingVolumeWrite !== null\n  ) {\n    return;\n  }\n\n  if (volumePollAbortController !== null) {\n    volumePollAbortController.abort();\n  }\n\n  const controller = new AbortController();\n  volumePollAbortController = controller;\n\n  try {\n    const result = await readJSON(\n      "/api/volume?time=" + Date.now(),\n      {\n        signal: controller.signal\n      }\n    );\n\n    if (\n      controller.signal.aborted\n      || volumeDragActive\n      || volumeWriteInFlight\n      || pendingVolumeWrite !== null\n    ) {\n      return;\n    }\n\n    drawVolume(\n      reportedIPadVolume(result)\n    );\n    for (const slider of volumeSliders) slider.disabled = false;\n  } catch (error) {\n    if (error.name !== "AbortError") {\n      showTaskFeedback(error.message, \'error\');\n    }\n  } finally {\n    if (volumePollAbortController === controller) {\n      volumePollAbortController = null;\n    }\n  }\n}\n\nasync function sendVolume(value) {\n  const requested = clampVolume(value);\n\n  if (volumeWriteInFlight) {\n    pendingVolumeWrite = requested;\n    return;\n  }\n\n  if (volumePollAbortController !== null) {\n    volumePollAbortController.abort();\n    volumePollAbortController = null;\n  }\n\n  volumeWriteInFlight = true;\n\n  try {\n    await readJSON(\n      "/api/volume",\n      {\n        method: "POST",\n        headers: {\n          "Content-Type": "application/json"\n        },\n        body: JSON.stringify({\n          percent: requested\n        })\n      }\n    );\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  } finally {\n    volumeWriteInFlight = false;\n\n    if (pendingVolumeWrite !== null) {\n      const next = pendingVolumeWrite;\n      pendingVolumeWrite = null;\n      sendVolume(next);\n      return;\n    }\n\n    /* The next draw comes only from a fresh iPad volume read. */\n    setTimeout(loadVolumeState, 180);\n  }\n}\n\nfunction queueVolume(event) {\n  const requested = clampVolume(event.currentTarget.value);\n\n  /* Native slider feedback is allowed only while the user interacts. */\n  drawVolume(requested);\n\n  if (volumeTimer !== null) {\n    clearTimeout(volumeTimer);\n  }\n\n  volumeTimer = setTimeout(\n    () => {\n      volumeTimer = null;\n      lastQueuedVolumeSent = requested;\n      sendVolume(requested);\n    },\n    90\n  );\n}\n\nfunction beginVolumeDrag() {\n  if (volumePollAbortController !== null) {\n    volumePollAbortController.abort();\n    volumePollAbortController = null;\n  }\n\n  volumeDragActive = true;\n}\n\nfunction finishVolumeDrag(event) {\n  if (!volumeDragActive) {\n    return;\n  }\n\n  volumeDragActive = false;\n\n  if (volumeTimer !== null) {\n    clearTimeout(volumeTimer);\n    volumeTimer = null;\n  }\n\n  const finalValue = clampVolume(event.currentTarget.value);\n\n  if (lastQueuedVolumeSent !== finalValue) {\n    sendVolume(finalValue);\n  }\n\n  lastQueuedVolumeSent = null;\n}\n\nfor (const slider of volumeSliders) {\n  slider.addEventListener("pointerdown", beginVolumeDrag);\n  slider.addEventListener("touchstart", beginVolumeDrag, {passive: true});\n  slider.addEventListener("input", queueVolume);\n  slider.addEventListener("change", finishVolumeDrag);\n  slider.addEventListener("pointerup", finishVolumeDrag);\n  slider.addEventListener("touchend", finishVolumeDrag);\n}\nfunction renderShuffleMode(enabled) {\n  const active = Boolean(enabled);\n  shuffleQueueButton.classList.toggle(\n    "shuffle-active",\n    active\n  );\n  shuffleQueueButton.textContent =\n    active ? "Shuffle On" : "Shuffle Off";\n  shuffleQueueButton.setAttribute(\n    "aria-label",\n    active ? "Queue shuffle on" : "Queue shuffle off"\n  );\n}\n\nlet shuffleReadInFlight = false;\n\nasync function loadShuffleMode() {\n  if (shuffleReadInFlight) {\n    return;\n  }\n\n  shuffleReadInFlight = true;\n\n  try {\n    const result = await readJSON(\n      "/api/shuffle?time=" + Date.now()\n    );\n    renderShuffleMode(result.enabled);\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  } finally {\n    shuffleReadInFlight = false;\n  }\n}\n\nlet shuffleToggleInFlight = false;\n\nshuffleQueueButton.addEventListener(\n  "click",\n  async () => {\n    if (shuffleToggleInFlight) {\n      return;\n    }\n\n    shuffleToggleInFlight = true;\n    shuffleQueueButton.classList.add("control-busy");\n    shuffleQueueButton.setAttribute("aria-busy", "true");\n\n    try {\n      const result = await readJSON(\n        "/api/shuffle/toggle",\n        { method: "POST" }\n      );\n      renderShuffleMode(result.enabled);\n      setTimeout(loadShuffleMode, 300);\n    } catch (error) {\n      showTaskFeedback(error.message, \'error\');\n    } finally {\n      shuffleToggleInFlight = false;\n      shuffleQueueButton.classList.remove("control-busy");\n      shuffleQueueButton.removeAttribute("aria-busy");\n    }\n  }\n);\n\nfunction renderRepeatMode(mode) {\n  const normalized =\n    mode === "all" || mode === "one"\n      ? mode\n      : "off";\n\n  repeatModeButton.dataset.mode = normalized;\n  repeatModeButton.classList.toggle(\n    "repeat-active",\n    normalized !== "off"\n  );\n\n  if (normalized === "all") {\n    repeatModeButton.textContent = "Repeat All";\n    repeatModeButton.setAttribute(\n      "aria-label",\n      "Repeat all enabled"\n    );\n    return;\n  }\n\n  if (normalized === "one") {\n    repeatModeButton.textContent = "Repeat 1";\n    repeatModeButton.setAttribute(\n      "aria-label",\n      "Repeat one enabled"\n    );\n    return;\n  }\n\n  repeatModeButton.textContent = "Repeat Off";\n  repeatModeButton.setAttribute(\n    "aria-label",\n    "Repeat mode off"\n  );\n}\n\n\nlet repeatReadInFlight = false;\n\nasync function loadRepeatMode() {\n  if (repeatReadInFlight) {\n    return;\n  }\n\n  repeatReadInFlight = true;\n\n  try {\n    const result = await readJSON(\n      "/api/repeat?time=" + Date.now()\n    );\n    renderRepeatMode(result.mode);\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  } finally {\n    repeatReadInFlight = false;\n  }\n}\n\n\nlet repeatToggleInFlight = false;\n\nrepeatModeButton.addEventListener(\n  "click",\n  async () => {\n    if (repeatToggleInFlight) {\n      return;\n    }\n\n    repeatToggleInFlight = true;\n    repeatModeButton.classList.add("control-busy");\n    repeatModeButton.setAttribute("aria-busy", "true");\n\n    try {\n      const result = await readJSON(\n        "/api/repeat/cycle",\n        { method: "POST" }\n      );\n      renderRepeatMode(result.mode);\n      setTimeout(loadRepeatMode, 200);\n    } catch (error) {\n      showTaskFeedback(error.message, \'error\');\n    } finally {\n      repeatToggleInFlight = false;\n      repeatModeButton.classList.remove("control-busy");\n      repeatModeButton.removeAttribute("aria-busy");\n    }\n  }\n);\n\nfunction setToggleState(isPlaying) {\n  toggleButton.innerHTML =\n    isPlaying\n      ? ICONS.pause\n      : ICONS.play;\n\n  toggleButton.setAttribute(\n    "aria-label",\n    isPlaying ? "Pause" : "Play"\n  );\n}\n\nfunction notificationBox() {\n  let banner = document.querySelector(\'#global-task-feedback\');\n  if (!banner) {\n    banner = document.createElement(\'div\');\n    banner.id = \'global-task-feedback\';\n    banner.setAttribute(\'role\', \'status\');\n    banner.setAttribute(\'aria-live\', \'polite\');\n    banner.style.cssText = \'position:fixed;left:12px;right:12px;top:12px;z-index:5000;box-sizing:border-box;padding:14px 64px 14px 18px;border-radius:14px;background:#152033;color:#eef5ff;border:1px solid #43638f;box-shadow:0 12px 32px rgba(0,0,0,.4);font-weight:700;text-align:center;\';\n    const message = document.createElement(\'span\');\n    message.className = \'task-feedback-message\';\n    const close = document.createElement(\'button\');\n    close.type = \'button\';\n    close.className = \'task-feedback-close\';\n    close.textContent = \'×\';\n    close.setAttribute(\'aria-label\', \'Close notification\');\n    close.style.cssText = \'position:absolute;right:8px;top:50%;transform:translateY(-50%);width:48px;height:48px;border:0;border-radius:12px;background:transparent;color:inherit;font-size:38px;font-weight:400;line-height:42px;cursor:pointer;\';\n    close.addEventListener(\'click\', () => {\n      clearTimeout(showTaskFeedback.timer);\n      banner.classList.add(\'hidden\');\n    });\n    banner.append(message, close);\n    document.body.appendChild(banner);\n  }\n  return banner;\n}\n\nfunction showTaskFeedback(message, kind=\'working\') {\n  const banner = notificationBox();\n  const messageNode = banner.querySelector(\'.task-feedback-message\');\n  if (messageNode) messageNode.textContent = String(message || \'Working…\');\n  banner.style.background = kind === \'done\' ? \'#163d2b\' : (kind === \'error\' ? \'#4a2025\' : \'#152033\');\n  banner.style.borderColor = kind === \'done\' ? \'#2f7654\' : (kind === \'error\' ? \'#a64b56\' : \'#43638f\');\n  banner.classList.remove(\'hidden\');\n  clearTimeout(showTaskFeedback.timer);\n  if (kind !== \'working\') {\n    showTaskFeedback.timer = setTimeout(() => banner.classList.add(\'hidden\'), 10000);\n  }\n}\n\nfunction setStatus(text) {\n  const message = String(text || \'\');\n  if (/error|failed|invalid|timed out|could not|not found|unavailable/i.test(message)) {\n    showTaskFeedback(message, \'error\');\n  }\n}\nwindow.addEventListener(\'error\', event => {\n  showTaskFeedback(event?.error?.message || event?.message || \'Unexpected interface error\', \'error\');\n});\nwindow.addEventListener(\'unhandledrejection\', event => {\n  const reason = event?.reason;\n  showTaskFeedback(reason?.message || String(reason || \'Unexpected request error\'), \'error\');\n});\n\nasync function readJSON(url, options = {}) {\n  const response = await fetch(url, {\n    cache: "no-store",\n    ...options\n  });\n\n  let result;\n\n  try {\n    result = await response.json();\n  } catch {\n    throw new Error("Server returned invalid data");\n  }\n\n  if (!response.ok || result.ok === false) {\n    throw new Error(\n      result.error || "Request failed"\n    );\n  }\n\n  return result;\n}\n\nlet nowPlayingReadInFlight = false;\n\nasync function updateNowPlaying() {\n  if (nowPlayingReadInFlight) {\n    return;\n  }\n\n  nowPlayingReadInFlight = true;\n\n  try {\n    const data =\n      await readJSON("/api/now-playing");\n\n    if (!data.available) {\n      currentTitle.textContent =\n        "Nothing playing";\n\n      currentDetails.textContent = "";\n      updateAppleNowPlayingArtwork("");\n      setToggleState(false);\n      updateSeekDisplay(0, 0);\n\n      return;\n    }\n\n    setToggleState(data.playing);\n    updateAppleNowPlayingArtwork(data.id);\n    currentTitle.textContent =\n      data.title || "Unknown title";\n\n    const details = [\n      data.artist,\n      data.album\n    ].filter(Boolean);\n\n    currentDetails.textContent =\n      details.join(" • ");\n    updateSeekDisplay(\n      Number(data.currentTime || 0),\n      Number(data.duration || 0)\n    );\n\n  } catch {\n    currentTitle.textContent =\n      "Now Playing unavailable";\n\n    currentDetails.textContent = "";\n    updateAppleNowPlayingArtwork("");\n\n    setToggleState(false);\n    updateSeekDisplay(0, 0);\n  } finally {\n    nowPlayingReadInFlight = false;\n  }\n}\n\nlet systemSeekActive = false;\nlet systemSeekTimer = null;\nfunction drawSystemSeek(currentTime, duration) {\n  const total = Number.isFinite(Number(duration)) ? Math.max(0, Number(duration)) : 0;\n  const position = Number.isFinite(Number(currentTime)) ? Math.max(0, Math.min(Number(currentTime), total > 0 ? total : Number(currentTime))) : 0;\n  if (!systemSeekActive) {\n    systemPlaybackSeek.max = String(total);\n    systemPlaybackSeek.value = String(position);\n  }\n  const shown = systemSeekActive ? Number(systemPlaybackSeek.value) : position;\n  systemPlaybackSeek.style.setProperty("--seek-progress", (total > 0 ? shown / total * 100 : 0) + "%");\n  systemPlaybackElapsed.textContent = formatPlaybackTime(shown);\n  systemPlaybackDuration.textContent = formatPlaybackTime(total);\n  systemPlaybackSeek.disabled = total <= 0;\n}\nfunction setSystemToggleState(isPlaying) {\n  systemToggleButton.innerHTML = isPlaying ? ICONS.pause : ICONS.play;\n  systemToggleButton.setAttribute("aria-label", isPlaying ? "Pause system media" : "Play system media");\n}\nasync function updateSystemNowPlaying() {\n  try {\n    const data = await readJSON("/api/system/now-playing");\n    setSystemToggleState(Boolean(data.playing));\n    if (!data.available) {\n      systemCurrentTitle.textContent = "Nothing playing";\n      systemCurrentDetails.textContent = "";\n      drawSystemSeek(0, 0);\n      return;\n    }\n    systemCurrentTitle.textContent = data.title || "Unknown title";\n    systemCurrentDetails.textContent = [data.artist, data.album].filter(Boolean).join(" • ");\n    drawSystemSeek(data.currentTime, data.duration);\n  } catch {\n    setSystemToggleState(false);\n    systemCurrentTitle.textContent = "System Now Playing unavailable";\n    systemCurrentDetails.textContent = "";\n    drawSystemSeek(0, 0);\n  }\n}\nasync function sendSystemCommand(command) {\n  try {\n    await readJSON("/api/system/" + command, {method: "POST"});\n    setStatus("System command sent");\n    setTimeout(updateSystemNowPlaying, 200);\n  } catch (error) { showTaskFeedback(error.message, \'error\'); }\n}\nasync function sendSystemSeek() {\n  if (systemSeekTimer !== null) clearTimeout(systemSeekTimer);\n  systemSeekTimer = null;\n  try {\n    await readJSON("/api/system/seek", {\n      method: "POST",\n      headers: {"Content-Type": "application/json"},\n      body: JSON.stringify({seconds: Number(systemPlaybackSeek.value)})\n    });\n  } catch (error) { showTaskFeedback(error.message, \'error\'); }\n  finally { systemSeekActive = false; setTimeout(updateSystemNowPlaying, 150); }\n}\nsystemPlaybackSeek.addEventListener("pointerdown", () => { systemSeekActive = true; });\nsystemPlaybackSeek.addEventListener("touchstart", () => { systemSeekActive = true; }, {passive: true});\nsystemPlaybackSeek.addEventListener("input", () => {\n  systemSeekActive = true;\n  drawSystemSeek(systemPlaybackSeek.value, systemPlaybackSeek.max);\n  if (systemSeekTimer !== null) clearTimeout(systemSeekTimer);\n  systemSeekTimer = setTimeout(sendSystemSeek, 120);\n});\nsystemPlaybackSeek.addEventListener("change", sendSystemSeek);\nfor (const button of document.querySelectorAll("[data-system-command]")) {\n  button.addEventListener("click", () => sendSystemCommand(button.dataset.systemCommand));\n}\n\nasync function sendTransport(command) {\n  try {\n    await readJSON(\n      "/api/" + command,\n      {\n        method: "POST"\n      }\n    );\n\n    setStatus("Done");\n\n    setTimeout(\n      updateNowPlaying,\n      250\n    );\n\n\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  }\n}\n\nasync function runSystemAction(\n  button,\n  endpoint,\n  workingLabel,\n  successLabel\n) {\n  if (button.disabled) {\n    return;\n  }\n\n  const normalLabel =\n    button.textContent;\n\n  button.disabled = true;\n  button.textContent = workingLabel;\n  const showProgress = endpoint === \'/api/music/restart\';\n  if (showProgress) showTaskFeedback(workingLabel, \'working\');\n\n  try {\n    const result =\n      await readJSON(\n        endpoint,\n        {\n          method: "POST"\n        }\n      );\n\n    if (showProgress) showTaskFeedback(result.message || successLabel, \'done\');\n\n    setTimeout(\n      updateNowPlaying,\n      700\n    );\n\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n\n  } finally {\n    button.disabled = false;\n    button.textContent =\n      normalLabel;\n  }\n}\n\nasync function connectAirPlayDevice(\n  device\n) {\n  try {\n    const result =\n      await readJSON(\n        "/api/airplay/connect-device",\n        {\n          method: "POST",\n          headers: {\n            "Content-Type":\n              "application/json"\n          },\n          body: JSON.stringify({\n            uid: device.uid,\n            name: device.name\n          })\n        }\n      );\n\n    setStatus(\n      result.message\n      || "Connected to "\n      + device.name\n    );\n\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  }\n}\n\n\nasync function setDefaultAirPlayDevice(\n  device\n) {\n  try {\n    const result =\n      await readJSON(\n        "/api/airplay/default",\n        {\n          method: "POST",\n          headers: {\n            "Content-Type":\n              "application/json"\n          },\n          body: JSON.stringify({\n            uid: device.uid,\n            name: device.name\n          })\n        }\n      );\n\n    setStatus(\n      result.message\n      || "Default set to "\n      + device.name\n    );\n\n    await loadAirPlayDevices(true);\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  }\n}\n\n\nasync function loadAirPlayDevices(silent=false) {\n  airPlayList.innerHTML = "";\n  if (!silent) showTaskFeedback(\'Discovering AirPlay devices…\', \'working\');\n\n  try {\n    const result =\n      await readJSON(\n        "/api/airplay/devices"\n      );\n\n    const devices =\n      Array.isArray(result.devices)\n        ? result.devices\n        : [];\n\n    if (\n      devices.length === 0\n    ) {\n      if (!silent) showTaskFeedback(\'No external AirPlay devices found\', \'done\');\n      airPlayList.textContent =\n        "No external AirPlay devices are "\n        + "currently exposed by Music. "\n        + "Open Music\'s AirPlay picker once "\n        + "to refresh the list.";\n\n      return;\n    }\n\n    for (\n      const device\n      of devices\n    ) {\n      const card =\n        document.createElement("div");\n\n      card.className =\n        "airplay-device";\n\n      const name =\n        document.createElement("div");\n\n      name.className =\n        "airplay-device-name";\n\n      name.textContent =\n        device.name;\n\n      const uid =\n        document.createElement("div");\n\n      uid.className =\n        "airplay-device-uid";\n\n      uid.textContent =\n        device.uid;\n\n      card.append(\n        name,\n        uid\n      );\n\n      if (device.default) {\n        const defaultLabel =\n          document.createElement("div");\n\n        defaultLabel.className =\n          "airplay-device-default";\n\n        defaultLabel.textContent =\n          "Default";\n\n        card.appendChild(\n          defaultLabel\n        );\n      }\n\n      const actions =\n        document.createElement("div");\n\n      actions.className =\n        "airplay-device-actions";\n\n      const connectButton =\n        document.createElement("button");\n\n      connectButton.className =\n        "airplay-connect-button";\n      connectButton.type = "button";\n\n      connectButton.textContent =\n        "Connect";\n\n      connectButton.addEventListener(\n        "click",\n        () => {\n          connectAirPlayDevice(\n            device\n          );\n        }\n      );\n\n      const defaultButton =\n        document.createElement("button");\n\n      defaultButton.className =\n        "airplay-default-button";\n      defaultButton.type = "button";\n\n      defaultButton.textContent =\n        device.default\n          ? "Default"\n          : "Set Default";\n\n      defaultButton.disabled =\n        Boolean(device.default);\n\n      defaultButton.addEventListener(\n        "click",\n        () => {\n          setDefaultAirPlayDevice(\n            device\n          );\n        }\n      );\n\n      actions.append(\n        connectButton,\n        defaultButton\n      );\n\n      card.appendChild(\n        actions\n      );\n\n      airPlayList.appendChild(\n        card\n      );\n    }\n    if (!silent) showTaskFeedback(\'AirPlay devices loaded\', \'done\');\n\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  }\n}\n\n\nasync function playPlaylistOrdered(name) {\n  try {\n    await readJSON(\n      "/api/playlist/play",\n      {\n        method: "POST",\n        headers: {\n          "Content-Type": "application/json"\n        },\n        body: JSON.stringify({\n          playlist: name\n        })\n      }\n    );\n    setStatus("Playing " + name);\n    setTimeout(updateNowPlaying, 400);\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  }\n}\n\nasync function shufflePlaylist(name) {\n  try {\n    await readJSON(\n      "/api/shuffle",\n      {\n        method: "POST",\n        headers: {\n          "Content-Type":\n            "application/json"\n        },\n        body: JSON.stringify({\n          playlist: name\n        })\n      }\n    );\n\n    setStatus(\n      "Shuffling " + name\n    );\n\n    setTimeout(\n      updateNowPlaying,\n      400\n    );\n\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  }\n}\n\nfunction makeArtwork(id, playlist=false) {\n  const tile = document.createElement(\'span\');\n  tile.className = \'song-artwork\' + (playlist ? \' playlist-artwork\' : \'\');\n  tile.setAttribute(\'aria-hidden\', \'true\');\n  if (id && /^\\d+$/.test(String(id))) {\n    const image = document.createElement(\'img\');\n    image.alt = \'\';\n    image.loading = \'lazy\';\n    image.decoding = \'async\';\n    image.addEventListener(\'error\', () => image.remove(), {once: true});\n    image.src = \'/api/song/artwork?id=\' + encodeURIComponent(String(id));\n    tile.appendChild(image);\n  }\n  return tile;\n}\n\nasync function loadPlaylists() {\n  playlistList.innerHTML = "";\n  allPlaylists = [];\n\n  try {\n    const data =\n      await readJSON("/api/playlists");\n\n    allPlaylists = Array.isArray(data.playlists)\n      ? data.playlists\n      : [];\n\n    if (allPlaylists.length === 0) {\n      playlistList.textContent =\n        "No playlists available";\n\n      return;\n    }\n\n    for (const playlist of allPlaylists) {\n      const row =\n        document.createElement("div");\n\n      row.className = "playlist-row";\n\n      const openButton =\n        document.createElement("button");\n\n      openButton.className =\n        "playlist-button";\n      openButton.type = "button";\n\n      const name =\n        document.createElement("span");\n\n      name.className =\n        "playlist-name";\n\n      name.textContent =\n        playlist.name;\n\n      const count =\n        document.createElement("span");\n\n      count.className =\n        "playlist-count";\n\n      count.textContent =\n        playlist.count +\n        (\n          playlist.count === 1\n            ? " song"\n            : " songs"\n        );\n\n      const playlistCopy = document.createElement(\'span\');\n      playlistCopy.className = \'playlist-copy\';\n      playlistCopy.append(name, count);\n      openButton.classList.add(\'has-artwork\');\n      openButton.append(makeArtwork(playlist.coverID, true), playlistCopy);\n\n      openButton.addEventListener(\n        "click",\n        () => {\n          openPlaylist(playlist.name);\n        }\n      );\n\n      const plainPlayButton =\n        document.createElement("button");\n      plainPlayButton.className =\n        "playlist-play-button";\n      plainPlayButton.type = "button";\n      plainPlayButton.innerHTML = \'<svg class="playlist-action-icon" viewBox="0 0 24 24" aria-hidden="true"><path class="play-glyph" d="M8 5.5 19 12 8 18.5z"/></svg>\';\n      plainPlayButton.setAttribute(\n        "aria-label",\n        "Play " + playlist.name\n      );\n      plainPlayButton.addEventListener(\n        "click",\n        () => {\n          playPlaylistOrdered(playlist.name);\n        }\n      );\n      const shuffleButton =\n        document.createElement("button");\n\n      shuffleButton.className =\n        "shuffle-button";\n      shuffleButton.type = "button";\n\n      shuffleButton.innerHTML = \'<svg class="playlist-action-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h2c5 0 7 10 12 10h2"/><path d="m17 14 3 3-3 3"/><path d="M4 17h2c2.1 0 3.6-1.8 5-4"/><path d="M14 8c1.1-.7 2.4-1 4-1h2"/><path d="m17 4 3 3-3 3"/></svg>\';\n\n      shuffleButton.setAttribute(\n        "aria-label",\n        "Shuffle " + playlist.name\n      );\n\n      shuffleButton.addEventListener(\n        "click",\n        () => {\n          shufflePlaylist(playlist.name);\n        }\n      );\n\n      row.append(\n        openButton,\n        plainPlayButton,\n        shuffleButton\n      );\n\n      playlistList.appendChild(row);\n    }\n\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  }\n}\n\nasync function openPlaylist(name) {\n  songList.innerHTML = "";\n  playlistSongSearch.value = "";\n  playlistSearchMessage.textContent = "";\n  playlistSearchMessage.classList.add("hidden");\n\n  currentPlaylistName = name;\n  playlistTitle.textContent = name;\n\n  showOnly(playlistScreen);\n\n\n  try {\n    const data =\n      await readJSON(\n        "/api/playlist?name=" +\n        encodeURIComponent(name)\n      );\n\n\n    const songs =\n      Array.isArray(data.songs)\n        ? data.songs\n        : [];\n    window.__lastPlaylistSongs = songs;\n\n    if (songs.length === 0) {\n      songList.textContent =\n        "This playlist has no available songs";\n\n      return;\n    }\n\n    for (const song of songs) {\n      const row =\n        document.createElement("div");\n\n      row.className =\n        "playlist-song-row";\n      row.dataset.songId = String(song.id);\n\n      const membership =\n        document.createElement("label");\n\n      membership.className =\n        "playlist-song-membership";\n\n      const checkbox =\n        document.createElement("input");\n\n      checkbox.type = "checkbox";\n      checkbox.checked = true;\n\n      checkbox.setAttribute(\n        "aria-label",\n        "Keep "\n        + (song.title || "song")\n        + " in "\n        + name\n      );\n\n      checkbox.addEventListener(\n        "change",\n        async () => {\n          if (checkbox.checked) {\n            return;\n          }\n\n          checkbox.disabled = true;\n\n          try {\n            await readJSON(\n              "/api/song/playlist",\n              {\n                method: "POST",\n                headers: {\n                  "Content-Type":\n                    "application/json"\n                },\n                body: JSON.stringify({\n                  id: song.id,\n                  playlist: name,\n                  included: false\n                })\n              }\n            );\n\n            row.remove();\n\n            if (\n              songList.querySelectorAll(\n                ".playlist-song-row"\n              ).length === 0\n            ) {\n              songList.textContent =\n                "This playlist has no available songs";\n            }\n\n            setStatus(\n              "Removed from " + name\n            );\n\n            await loadPlaylists();\n\n          } catch (error) {\n            checkbox.checked = true;\n            checkbox.disabled = false;\n            showTaskFeedback(error.message, \'error\');\n          }\n        }\n      );\n\n      membership.appendChild(\n        checkbox\n      );\n\n      const button =\n        document.createElement("button");\n\n      button.className =\n        "song-button";\n\n      button.type = "button";\n\n      const title =\n        document.createElement("span");\n\n      title.className =\n        "song-title";\n\n      title.textContent =\n        song.title || "Unknown title";\n\n      const artist =\n        document.createElement("span");\n\n      artist.className =\n        "song-artist";\n\n      artist.textContent = [\n        song.artist,\n        song.album\n      ].filter(Boolean).join(" • ");\n\n      const songCopy = document.createElement(\'span\');\n      songCopy.className = \'song-copy\';\n      songCopy.append(title, artist);\n      button.classList.add(\'has-artwork\');\n      button.append(makeArtwork(song.id), songCopy);\n\n      button.addEventListener(\n        "click",\n        async () => {\n          try {\n            await readJSON(\n              "/api/song",\n              {\n                method: "POST",\n                headers: {\n                  "Content-Type":\n                    "application/json"\n                },\n                body: JSON.stringify({\n                  playlist: name,\n                  id: song.id\n                })\n              }\n            );\n\n            setStatus(\n              "Playing "\n              + (\n                song.title\n                || "selected song"\n              )\n            );\n\n            setTimeout(\n              updateNowPlaying,\n              350\n            );\n\n          } catch (error) {\n            showTaskFeedback(error.message, \'error\');\n          }\n        }\n      );\n\n      row.append(\n        membership,\n        button\n      );\n\n      songList.appendChild(row);\n    }\n\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  }\n}\n\ndocument\n  .querySelector("#back")\n  .addEventListener(\n    "click",\n    () => {\n      showOnly(musicScreen);\n\n      updateNowPlaying();\n    }\n  );\n\nfor (\n  const button\n  of document.querySelectorAll(\n    "[data-command]"\n  )\n) {\n  button.addEventListener(\n    "click",\n    () => {\n      sendTransport(\n        button.dataset.command\n      );\n    }\n  );\n}\n\nairPlayDevicesButton.addEventListener(\n  "click",\n  () => {\n    mainScreen.classList.add(\n      "hidden"\n    );\n\n    playlistScreen.classList.add(\n      "hidden"\n    );\n\n    airPlayScreen.classList.remove(\n      "hidden"\n    );\n\n    loadAirPlayDevices();\n  }\n);\n\nairPlayBackButton.addEventListener(\n  "click",\n  () => {\n    airPlayScreen.classList.add(\n      "hidden"\n    );\n\n    mainScreen.classList.remove(\n      "hidden"\n    );\n\n    updateNowPlaying();\n  }\n);\n\nconnectAirPlayButton.addEventListener(\n  "click",\n  () => {\n    runSystemAction(\n      connectAirPlayButton,\n      "/api/airplay/connect",\n      "Connecting…",\n      "Connected to default AirPlay device"\n    );\n  }\n);\n\ndisconnectAirPlayButton.addEventListener(\n  "click",\n  () => {\n    runSystemAction(\n      disconnectAirPlayButton,\n      "/api/airplay/disconnect",\n      "Disconnecting…",\n      "AirPlay disconnected"\n    );\n  }\n);\nrestartMusicButton.addEventListener(\n  "click",\n  () => {\n    runSystemAction(\n      restartMusicButton,\n      "/api/music/restart",\n      "Restarting…",\n      "Music restarted"\n    );\n  }\n);\n\nhomeDeviceButton.addEventListener(\n  "click",\n  () => {\n    runSystemAction(\n      homeDeviceButton,\n      "/api/device/home",\n      "Waking…",\n      "iPad awakened"\n    );\n  }\n);\n\n\nconst allSongsScreen = document.querySelector(\'#all-songs-screen\');\nconst uploadScreen = document.querySelector(\'#upload-screen\');\nconst songManageScreen = document.querySelector(\'#song-manage-screen\');\nconst allSongList = document.querySelector(\'#all-song-list\');\nconst uploadPlaylistChecks = document.querySelector(\'#upload-playlist-checks\');\nconst songPlaylistChecks = document.querySelector(\'#song-playlist-checks\');\nconst musicFiles = document.querySelector(\'#music-files\');\nconst uploadFileList = document.querySelector(\'#upload-file-list\');\nlet selectedUploadFiles = [];\nlet allSongs = [];\nlet selectedManagedSong = null;\n\nfunction uploadFileKey(file) {\n  return [file.name, file.size, file.lastModified].join(\'::\');\n}\n\nfunction renderSelectedUploadFiles() {\n  uploadFileList.innerHTML = \'\';\n\n  for (const file of selectedUploadFiles) {\n    const row = document.createElement(\'div\');\n    row.className = \'upload-file-row\';\n\n    const name = document.createElement(\'div\');\n    name.className = \'upload-file-name\';\n    name.textContent = file.name;\n    name.title = file.name;\n\n    const remove = document.createElement(\'button\');\n    remove.className = \'upload-file-remove\';\n    remove.type = \'button\';\n    remove.textContent = \'×\';\n    remove.setAttribute(\'aria-label\', \'Remove \' + file.name + \' from upload\');\n    remove.addEventListener(\'click\', () => {\n      const key = uploadFileKey(file);\n      selectedUploadFiles = selectedUploadFiles.filter(\n        candidate => uploadFileKey(candidate) !== key\n      );\n      renderSelectedUploadFiles();\n    });\n\n    row.append(name, remove);\n    uploadFileList.appendChild(row);\n  }\n}\n\nmusicFiles.addEventListener(\'change\', () => {\n  const known = new Set(selectedUploadFiles.map(uploadFileKey));\n  for (const file of musicFiles.files) {\n    const key = uploadFileKey(file);\n    if (!known.has(key)) {\n      known.add(key);\n      selectedUploadFiles.push(file);\n    }\n  }\n  musicFiles.value = \'\';\n  renderSelectedUploadFiles();\n});\n\n\nfunction showOnly(screen) {\n  for (const section of [\n    mainScreen,\n    musicScreen,\n    playlistScreen,\n    airPlayScreen,\n    allSongsScreen,\n    uploadScreen,\n    songManageScreen,\n    playlistAddScreen\n  ]) {\n    section.classList.toggle(\'hidden\', section !== screen);\n  }\n}\n\ndocument.querySelector(\'#open-music-menu\').addEventListener(\'click\', () => {\n  showOnly(musicScreen);\n  window.scrollTo({top: 0, behavior: \'auto\'});\n});\ndocument.querySelector(\'#music-menu-back\').addEventListener(\'click\', () => {\n  showOnly(mainScreen);\n  window.scrollTo({top: 0, behavior: \'auto\'});\n});\nfunction completeOnHome(message) {\n  showOnly(mainScreen);\n  window.scrollTo({top: 0, behavior: \'smooth\'});\n  showTaskFeedback(message, \'done\');\n}\n\nvar playlistSelectedSongs = new Map();\nvar allSongsSelectedSongs = new Map();\n\nfunction createSongManagementRow(song) {\n  const row = document.createElement(\'div\');\n  row.className = \'song-management-row\';\n  row.dataset.songId = String(song.id);\n  const play = document.createElement(\'button\');\n  play.className = \'song-button\';\n  play.type = \'button\';\n  play.classList.add(\'has-artwork\');\n  const songCopy = document.createElement(\'span\');\n  songCopy.className = \'song-copy\';\n  songCopy.innerHTML = \'<span class="song-title"></span><span class="song-artist"></span>\';\n  play.append(makeArtwork(song.id), songCopy);\n  play.querySelector(\'.song-title\').textContent = song.title || \'Unknown title\';\n  play.querySelector(\'.song-artist\').textContent = [song.artist, song.album].filter(Boolean).join(\' • \');\n  play.addEventListener(\'click\', async () => {\n    try {\n      await readJSON(\'/api/song/play\', {method:\'POST\', headers:{\'Content-Type\':\'application/json\'}, body:JSON.stringify({id:song.id})});\n      setStatus(\'Playing \' + (song.title || \'selected song\'));\n      setTimeout(updateNowPlaying, 350);\n    } catch (error) { showTaskFeedback(error.message, \'error\'); }\n  });\n  const menu = document.createElement(\'button\');\n  menu.className = \'song-menu-button\';\n  menu.type = \'button\';\n  menu.textContent = \'⋯\';\n  menu.setAttribute(\'aria-label\', \'Manage \' + (song.title || \'song\'));\n  menu.addEventListener(\'click\', () => openSongManager(song));\n  row.append(play, menu);\n  return row;\n}\n\nfunction renderAllSongs() {\n  const query = normalizeSearchText(globalSongSearch.value.trim());\n  allSongList.innerHTML = \'\';\n  const matches = allSongs.filter(song => (song._webremoteSearchText || \'\').includes(query));\n  const fragment = document.createDocumentFragment();\n  globalSongResults.textContent = matches.length ? \'\' : \'No matching songs\';\n  for (const song of matches) {\n    const row = createSongManagementRow(song);\n    row.prepend(selectionCheckbox(song, allSongsSelectedSongs, row));\n    fragment.appendChild(row);\n  }\n  allSongList.appendChild(fragment);\n}\n\nasync function loadAllSongs() {\n  const response = await readJSON(\'/api/songs\');\n  allSongs = Array.isArray(response.songs) ? response.songs : [];\n  for (const song of allSongs) {\n    song._webremoteSearchText = normalizeSearchText(\n      [song.title, song.artist, song.album].filter(Boolean).join(\' \'));\n  }\n  renderAllSongs();\n}\n\nlet allSongsSearchTimer = null;\nglobalSongSearch.addEventListener(\'input\', () => {\n  clearTimeout(allSongsSearchTimer);\n  allSongsSearchTimer = setTimeout(renderAllSongs, 120);\n});\n\ndocument.querySelector(\'#open-all-songs\').addEventListener(\'click\', async () => {\n  showOnly(allSongsScreen);\n  try { await loadAllSongs(); } catch (error) { showTaskFeedback(error.message, \'error\'); }\n});\ndocument.querySelector(\'#all-songs-back\').addEventListener(\'click\', () => showOnly(musicScreen));\n\ndocument.querySelector(\'#open-upload\').addEventListener(\'click\', () => {\n  showOnly(uploadScreen);\n  uploadPlaylistChecks.innerHTML = \'\';\n  for (const playlist of allPlaylists) {\n    const label = document.createElement(\'label\');\n    label.className = \'playlist-check\';\n    label.innerHTML = \'<input type="checkbox"><span></span>\';\n    label.querySelector(\'input\').value = playlist.name;\n    label.querySelector(\'span\').textContent = playlist.name;\n    uploadPlaylistChecks.appendChild(label);\n  }\n});\ndocument.querySelector(\'#upload-back\').addEventListener(\'click\', () => showOnly(musicScreen));\n\nconst uploadSubmitButton = document.querySelector(\'#upload-submit\');\n\nasync function waitForMusicImportJob(jobID) {\n  const labels = {\n    queued: \'Queued…\',\n    \'opening-filza\': \'Opening Filza…\',\n    \'waking-ipad\': \'Waking iPad…\',\n    \'filza-ready\': \'Filza ready…\',\n    \'triggering-filza\': \'Sending batch to Filza…\',\n    \'filza-importing\': \'Filza is importing the batch. Keep Filza open…\',\n    \'verifying-results\': \'Filza finished. Checking every import result…\',\n    \'preserving-playlists\': \'Preserving playlist memberships…\',\n    \'replacing-duplicates\': \'Replacing older duplicate library files…\',\n    \'resolving-duplicates\': \'Resolving duplicates automatically…\',\n    \'refreshing-library\': \'Refreshing Apple Music library…\',\n    \'processing-library\': \'Updating playlists and library…\',\n    finalizing: \'Finalizing import…\'\n  };\n  let failures = 0;\n  while (true) {\n    await new Promise(resolve => setTimeout(resolve, 750));\n    let state;\n    try {\n      state = await readJSON(\'/api/music/import/status?id=\' + encodeURIComponent(jobID));\n      failures = 0;\n    } catch (error) {\n      failures += 1;\n      uploadSubmitButton.textContent = \'Checking import status…\';\n      showTaskFeedback(\'Import is still running. Reconnecting to status…\', \'working\');\n      if (failures < 8) continue;\n      throw error;\n    }\n    if (state.status === \'awaiting-duplicates\') {\n      uploadSubmitButton.textContent = \'Resolving duplicates…\';\n      showTaskFeedback(\'Resolving duplicates automatically…\', \'working\');\n      continue;\n    }\n    if (state.status === \'done\') {\n      uploadSubmitButton.textContent = \'Import complete\';\n      showTaskFeedback(\'Import complete. Finalizing the web interface…\', \'working\');\n      return state.result;\n    }\n    if (state.status === \'failed\') throw new Error(state.error || \'Music import failed\');\n    const done = Number(state.completed || 0);\n    const total = Number(state.total || 0);\n    const label = labels[state.status] || \'Importing…\';\n    uploadSubmitButton.textContent = total > 0 && done > 0\n      ? label + \' \' + done + \' / \' + total\n      : label;\n    showTaskFeedback(total > 0 && done > 0 ? label + \' \' + done + \' of \' + total : label, \'working\');\n  }\n}\n\ndocument.querySelector(\'#upload-submit\').addEventListener(\'click\', async () => {\n  if (!selectedUploadFiles.length) {\n    showTaskFeedback(\'Choose at least one audio file\', \'error\');\n    return;\n  }\n\n  const submitButton = uploadSubmitButton;\n\n  const playlists = [\n    ...uploadPlaylistChecks.querySelectorAll(\n      \'input:checked\'\n    )\n  ].map(input => input.value);\n\n  const data = new FormData();\n\n  for (const file of selectedUploadFiles) {\n    data.append(\n      \'files\',\n      file,\n      file.name\n    );\n  }\n\n  data.append(\n    \'playlists\',\n    JSON.stringify(playlists)\n  );\n\n  submitButton.disabled = true;\n  submitButton.textContent = \'Opening Filza…\';\n\n  try {\n    showTaskFeedback(\'Preparing upload session…\', \'working\');\n    const session = await readJSON(\'/api/music/upload-session\', {\n      method: \'POST\',\n      headers: {\'Content-Type\':\'application/json\'},\n      body: JSON.stringify({playlists})\n    });\n    let uploaded = 0;\n    for (const file of selectedUploadFiles) {\n      submitButton.textContent = \'Uploading \' + (uploaded + 1) + \' / \' + selectedUploadFiles.length + \'…\';\n      showTaskFeedback(submitButton.textContent, \'working\');\n      const part = new FormData();\n      part.append(\'file\', file, file.name);\n      await readJSON(\'/api/music/upload-file?session=\' + encodeURIComponent(session.sessionID), {\n        method: \'POST\', body: part\n      });\n      uploaded += 1;\n    }\n    submitButton.textContent = \'Upload complete\';\n    showTaskFeedback(\'All files uploaded. Opening Filza once for the complete batch…\', \'working\');\n    const accepted = await readJSON(\'/api/music/upload-commit\', {\n      method: \'POST\',\n      headers: {\'Content-Type\':\'application/json\'},\n      body: JSON.stringify({sessionID: session.sessionID})\n    });\n    const result = accepted.jobID\n      ? await waitForMusicImportJob(accepted.jobID)\n      : accepted;\n\n    const imported =\n      Array.isArray(result.imported)\n        ? result.imported\n        : [];\n\n    const duplicates =\n      Array.isArray(result.duplicates)\n        ? result.duplicates\n        : [];\n\n    const failed =\n      Array.isArray(result.failed)\n        ? [...result.failed]\n        : [];\n\n    const resolved = duplicates;\n\n    const completedCount =\n      imported.length\n      + resolved.length;\n\n    const failedCount =\n      failed.length;\n\n    let message =\n      completedCount === 1\n        ? \'Music upload complete: 1 song processed.\'\n        : (\n            \'Music upload complete: \'\n            + completedCount\n            + \' songs processed.\'\n          );\n\n    if (failedCount > 0) {\n      message += (\n        \' \'\n        + failedCount\n        + (\n            failedCount === 1\n              ? \' file needs attention.\'\n              : \' files need attention.\'\n          )\n      );\n    }\n\n    const failedNames = new Set(\n      failed\n        .map(item => item.filename)\n        .filter(Boolean)\n    );\n\n    selectedUploadFiles =\n      selectedUploadFiles.filter(\n        file => failedNames.has(file.name)\n      );\n\n    musicFiles.value = \'\';\n    renderSelectedUploadFiles();\n\n    completeOnHome(result.message || message);\n\n    Promise.allSettled([loadPlaylists(), loadAllSongs()]);\n\n\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n\n  } finally {\n    submitButton.disabled = false;\n    submitButton.textContent =\n      \'Import Selected Files\';\n  }\n});\n\nasync function openSongManager(song) {\n  selectedManagedSong = song;\n  document.querySelector(\'#song-manage-title\').textContent = song.title || \'Song\';\n  document.querySelector(\'#song-manage-details\').textContent = [song.artist, song.album].filter(Boolean).join(\' • \');\n  document.querySelector(\'#song-manage-artwork\').replaceWith(Object.assign(makeArtwork(song.id), {id: \'song-manage-artwork\'}));\n  songPlaylistChecks.innerHTML = \'Loading…\';\n  showOnly(songManageScreen);\n  try {\n    const response = await readJSON(\'/api/song/playlists?id=\' + encodeURIComponent(song.id));\n    songPlaylistChecks.innerHTML = \'\';\n    for (const playlist of response.playlists || []) {\n      const label = document.createElement(\'label\');\n      label.className = \'playlist-check\';\n      label.innerHTML = \'<input type="checkbox"><span></span>\';\n      const input = label.querySelector(\'input\');\n      input.checked = Boolean(playlist.included);\n      label.querySelector(\'span\').textContent = playlist.name;\n      input.addEventListener(\'change\', async () => {\n        input.disabled = true;\n        try {\n          await readJSON(\'/api/song/playlist\', {method:\'POST\', headers:{\'Content-Type\':\'application/json\'}, body:JSON.stringify({id:song.id, playlist:playlist.name, included:input.checked})});\n        } catch (error) { input.checked = !input.checked; showTaskFeedback(error.message, \'error\'); }\n        finally { input.disabled = false; }\n      });\n      songPlaylistChecks.appendChild(label);\n    }\n  } catch (error) { songPlaylistChecks.textContent = error.message; showTaskFeedback(error.message, \'error\'); }\n}\n\ndocument.querySelector(\'#song-manage-back\').addEventListener(\'click\', () => showOnly(allSongsScreen));\ndocument.querySelector(\'#remove-from-library\').addEventListener(\'click\', async () => {\n  if (!selectedManagedSong) return;\n  if (!confirm(\'Remove "\' + (selectedManagedSong.title || \'this song\') + \'" from your Apple Music library?\')) return;\n\n  const button = document.querySelector(\'#remove-from-library\');\n  button.disabled = true;\n  button.textContent = \'Removing…\';\n\n  try {\n    showTaskFeedback(\'Removing song from the library…\', \'working\');\n    await readJSON(\'/api/song/library\', {\n      method: \'DELETE\',\n      headers: {\'Content-Type\': \'application/json\'},\n      body: JSON.stringify({id:selectedManagedSong.id})\n    });\n    const removedTitle = selectedManagedSong.title || \'Song\';\n    selectedManagedSong = null;\n    await loadAllSongs();\n    await loadPlaylists();\n    completeOnHome(\'Removed "\' + removedTitle + \'" from the Apple Music library.\');\n  } catch (error) {\n    showTaskFeedback(error.message, \'error\');\n  } finally {\n    button.disabled = false;\n    button.textContent = \'Remove from Library\';\n  }\n});\n\n\nconst playlistAddScreen =\n  document.querySelector(\n    "#playlist-add-screen"\n  );\n\nconst playlistAddList =\n  document.querySelector(\n    "#playlist-add-list"\n  );\n\nconst playlistAddSearch =\n  document.querySelector(\n    "#playlist-add-search"\n  );\n\nconst playlistAddSelectedButton =\n  document.querySelector(\n    "#playlist-add-selected"\n  );\n\nplaylistAddSearch.parentNode.insertBefore(\n  playlistAddSelectedButton,\n  playlistAddSearch\n);\n\nfunction renderPlaylistAddCandidates() {\n  const query = normalizeSearchText(\n    playlistAddSearch.value.trim()\n  );\n\n  playlistAddList.innerHTML = "";\n\n  const matches =\n    playlistAddCandidates.filter(\n      song =>\n        normalizeSearchText([\n          song.title,\n          song.artist,\n          song.album\n        ].filter(Boolean).join(" "))\n          .includes(query)\n    );\n\n  if (matches.length === 0) {\n    playlistAddList.textContent =\n      query\n        ? "No matching songs"\n        : "Every library song is already in this playlist";\n    return;\n  }\n\n  for (const song of matches) {\n    const label =\n      document.createElement("label");\n\n    label.className =\n      "playlist-candidate-row";\n\n    const input =\n      document.createElement("input");\n\n    input.type = "checkbox";\n    input.value = song.id;\n\n    const details =\n      document.createElement("span");\n\n    details.className =\n      "playlist-candidate-details";\n\n    const title =\n      document.createElement("span");\n\n    title.className =\n      "playlist-candidate-title";\n\n    title.textContent =\n      song.title || "Unknown title";\n\n    const artist =\n      document.createElement("span");\n\n    artist.className =\n      "playlist-candidate-artist";\n\n    artist.textContent = [\n      song.artist,\n      song.album\n    ].filter(Boolean).join(" • ");\n\n    details.append(\n      title,\n      artist\n    );\n\n    label.append(input, makeArtwork(song.id), details);\n\n    playlistAddList.appendChild(label);\n  }\n}\n\nasync function openPlaylistAddSongs() {\n  if (!currentPlaylistName) {\n    return;\n  }\n\n  playlistAddSearch.value = "";\n  playlistAddList.textContent = "Loading…";\n\n  document.querySelector(\n    "#playlist-add-title"\n  ).textContent =\n    "Add to " + currentPlaylistName;\n\n  showOnly(playlistAddScreen);\n\n  try {\n    const [libraryResult, playlistResult] =\n      await Promise.all([\n        readJSON("/api/songs"),\n        readJSON(\n          "/api/playlist?name="\n          + encodeURIComponent(\n              currentPlaylistName\n            )\n        )\n      ]);\n\n    const librarySongs =\n      Array.isArray(libraryResult.songs)\n        ? libraryResult.songs\n        : [];\n\n    const playlistSongs =\n      Array.isArray(playlistResult.songs)\n        ? playlistResult.songs\n        : [];\n\n    const existingIDs =\n      new Set(\n        playlistSongs.map(\n          song => String(song.id)\n        )\n      );\n\n    playlistAddCandidates =\n      librarySongs.filter(\n        song =>\n          !existingIDs.has(\n            String(song.id)\n          )\n      );\n\n    renderPlaylistAddCandidates();\n\n  } catch (error) {\n    playlistAddList.textContent =\n      error.message;\n    showTaskFeedback(error.message, \'error\');\n  }\n}\n\nplaylistAddSearch.addEventListener(\n  "input",\n  renderPlaylistAddCandidates\n);\n\ndocument.querySelector(\n  "#playlist-add-songs"\n).addEventListener(\n  "click",\n  openPlaylistAddSongs\n);\n\ndocument.querySelector(\n  "#playlist-add-back"\n).addEventListener(\n  "click",\n  () => showOnly(playlistScreen)\n);\n\nplaylistAddSelectedButton.addEventListener(\n  "click",\n  async () => {\n    const button =\n      playlistAddSelectedButton;\n\n    const identifiers = [\n      ...playlistAddList.querySelectorAll(\n        \'input[type="checkbox"]:checked\'\n      )\n    ].map(input => input.value);\n\n    if (identifiers.length === 0) {\n      showTaskFeedback("Select at least one song", "error");\n      return;\n    }\n\n    const playlistName =\n      currentPlaylistName;\n\n    button.disabled = true;\n    button.textContent = "Adding…";\n\n    const failed = [];\n    if (identifiers.length > 1) showTaskFeedback(\'Adding \' + identifiers.length + \' songs to playlist…\', \'working\');\n\n    try {\n      for (const identifier of identifiers) {\n        try {\n          await readJSON(\n            "/api/song/playlist",\n            {\n              method: "POST",\n              headers: {\n                "Content-Type":\n                  "application/json"\n              },\n              body: JSON.stringify({\n                id: identifier,\n                playlist: playlistName,\n                included: true\n              })\n            }\n          );\n        } catch (error) {\n          failed.push(\n            error.message\n          );\n        }\n      }\n\n      playlistAddCandidates = [];\n      playlistAddSearch.value = "";\n      playlistAddList.innerHTML = "";\n\n      /*\n       * Close every other application screen before reloading\n       * the playlist. This prevents playlist-add-screen from\n       * remaining visible underneath playlist-screen.\n       */\n      showOnly(playlistScreen);\n\n      await openPlaylist(\n        playlistName\n      );\n\n      window.scrollTo({\n        top: 0,\n        behavior: "smooth"\n      });\n\n      const addedCount = identifiers.length - failed.length;\n      const completionMessage = failed.length > 0\n        ? \'Finished adding songs to "\' + playlistName + \'": \'\n          + addedCount + \' added, \' + failed.length + \' failed.\'\n        : \'Added \' + addedCount + \' song\' + (addedCount === 1 ? \'\' : \'s\')\n          + \' to "\' + playlistName + \'".\';\n      if (failed.length) {\n        showOnly(mainScreen);\n        showTaskFeedback(completionMessage + \' \' + failed[0], \'error\');\n      } else if (identifiers.length > 1) {\n        completeOnHome(completionMessage);\n      } else {\n        showOnly(mainScreen);\n        window.scrollTo({top: 0, behavior: \'smooth\'});\n      }\n\n    } catch (error) {\n      /*\n       * Keep the selection screen available only when an\n       * unexpected outer failure prevents playlist reload.\n       */\n      showOnly(\n        playlistAddScreen\n      );\n\n      showTaskFeedback(error.message, \'error\');\n\n    } finally {\n      button.disabled = false;\n      button.textContent =\n        "Add Selected Songs";\n    }\n  }\n);\n\ndocument.querySelector(\n  "#create-playlist"\n).addEventListener(\n  "click",\n  async () => {\n    const requested =\n      prompt("New playlist name");\n\n    if (requested === null) {\n      return;\n    }\n\n    const name = requested.trim();\n\n    if (!name) {\n      setStatus(\n        "Enter a playlist name"\n      );\n      return;\n    }\n\n    try {\n      await readJSON(\n        "/api/playlist/create",\n        {\n          method: "POST",\n          headers: {\n            "Content-Type":\n              "application/json"\n          },\n          body: JSON.stringify({\n            name: name\n          })\n        }\n      );\n\n      await loadPlaylists();\n      setStatus(\n        \'Created playlist "\' + name + \'"\'\n      );\n\n    } catch (error) {\n      showTaskFeedback(error.message, \'error\');\n    }\n  }\n);\n\ndocument.querySelector("#playlist-rename").addEventListener(\n  "click",\n  async () => {\n    if (!currentPlaylistName) return;\n    const oldName = currentPlaylistName;\n    const requested = prompt("Rename playlist", oldName);\n    if (requested === null) return;\n    const newName = requested.trim();\n    if (!newName) {\n      showTaskFeedback("Enter a playlist name", "error");\n      return;\n    }\n    if (newName === oldName) {\n      return;\n    }\n    const button = document.querySelector("#playlist-rename");\n    const normalLabel = button.textContent;\n    button.disabled = true;\n    button.textContent = "Renaming…";\n    showTaskFeedback(\'Renaming "\' + oldName + \'" to "\' + newName + \'"…\', "working");\n    try {\n      const result = await readJSON("/api/playlist/rename", {\n        method: "POST",\n        headers: {"Content-Type": "application/json"},\n        body: JSON.stringify({oldName, newName})\n      });\n      currentPlaylistName = result.name || newName;\n      playlistTitle.textContent = currentPlaylistName;\n      await loadPlaylists();\n      completeOnHome(result.message || (\'Renamed "\' + oldName + \'" to "\' + currentPlaylistName + \'".\'));\n    } catch (error) {\n      showTaskFeedback(error.message, "error");\n    } finally {\n      button.disabled = false;\n      button.textContent = normalLabel;\n    }\n  }\n);\n\ndocument.querySelector(\n  "#playlist-remove"\n).addEventListener(\n  "click",\n  async () => {\n    if (!currentPlaylistName) {\n      return;\n    }\n\n    if (\n      !confirm(\n        \'Remove playlist "\'\n        + currentPlaylistName\n        + \'"?\\n\\n\'\n        + "Songs will remain in your Apple Music library."\n      )\n    ) {\n      return;\n    }\n\n    const name = currentPlaylistName;\n    const button =\n      document.querySelector(\n        "#playlist-remove"\n      );\n\n    button.disabled = true;\n    button.textContent = "Removing…";\n    showTaskFeedback(\'Removing playlist "\' + name + \'"…\', \'working\');\n\n    try {\n      await readJSON(\n        "/api/playlist/remove",\n        {\n          method: "DELETE",\n          headers: {\n            "Content-Type":\n              "application/json"\n          },\n          body: JSON.stringify({\n            name: name\n          })\n        }\n      );\n\n      currentPlaylistName = "";\n      await loadPlaylists();\n      completeOnHome(\n        \'Removed playlist "\'\n        + name\n        + \'". Songs were kept.\'\n      );\n\n    } catch (error) {\n      showTaskFeedback(error.message, \'error\');\n\n    } finally {\n      button.disabled = false;\n      button.textContent =\n        "Remove Playlist";\n    }\n  }\n);\n\nlet ipadStateTimer = null;\nlet routeStateTimer = null;\nlet pageRefreshGeneration = 0;\nasync function refreshIPadState(){\n  if(document.hidden)return;\n  await Promise.allSettled([updateNowPlaying(),updateSystemNowPlaying(),loadVolumeState(),loadRepeatMode(),loadShuffleMode()]);\n}\nfunction scheduleIPadStatePoll(generation){\n  clearTimeout(ipadStateTimer);\n  if(document.hidden||generation!==pageRefreshGeneration)return;\n  ipadStateTimer=setTimeout(async()=>{await refreshIPadState();scheduleIPadStatePoll(generation)},1500);\n}\n\n\n// Selection stores are declared before the song renderers.\nconst playlistSelectAll = document.querySelector(\'#playlist-select-all\');\nconst allSongsSelectAll = document.querySelector(\'#all-songs-select-all\');\n\nfunction selectionCheckbox(song, store, row) {\n  const input = document.createElement(\'input\');\n  input.type = \'checkbox\';\n  input.className = \'batch-select\';\n  input.checked = store.has(String(song.id));\n  input.setAttribute(\'aria-label\', \'Select \' + (song.title || \'song\'));\n  input.addEventListener(\'change\', () => {\n    if (input.checked) store.set(String(song.id), song);\n    else store.delete(String(song.id));\n    row.classList.toggle(\'batch-selected\', input.checked);\n  });\n  return input;\n}\n\nfunction setVisibleSelection(container, store, checked) {\n  for (const input of container.querySelectorAll(\'.batch-select\')) {\n    if (input.checked !== checked) { input.checked = checked; input.dispatchEvent(new Event(\'change\')); }\n  }\n}\n\nasync function runSongBatch(action, store, playlist=\'\') {\n  const ids = [...store.keys()];\n  if (!ids.length) { showTaskFeedback(\'Select at least one song\', \'error\'); return false; }\n  const fromPlaylist = action === \'playlist-remove\';\n  const label = fromPlaylist ? \'remove selected songs from this playlist\' : \'remove selected songs from the library\';\n  if (!confirm(\'Are you sure you want to \' + label + \'?\')) return false;\n  const button = fromPlaylist\n    ? document.querySelector(\'#playlist-batch-remove\')\n    : (store === playlistSelectedSongs\n        ? document.querySelector(\'#playlist-batch-library\')\n        : document.querySelector(\'#all-songs-batch-library\'));\n  const originalText = button ? button.textContent : \'\';\n  if (button) {\n    button.disabled = true;\n    button.textContent = fromPlaylist ? \'Removing from playlist…\' : \'Removing from library…\';\n  }\n  showTaskFeedback(\n    fromPlaylist\n      ? \'Removing \' + ids.length + \' selected song\' + (ids.length === 1 ? \'\' : \'s\') + \' from "\' + playlist + \'"…\'\n      : \'Removing \' + ids.length + \' selected song\' + (ids.length === 1 ? \'\' : \'s\') + \' from the library…\',\n    \'working\'\n  );\n  try {\n    const response = await readJSON(\'/api/songs/batch\', {\n      method:\'POST\', headers:{\'Content-Type\':\'application/json\'},\n      body:JSON.stringify({action, ids, playlist})\n    });\n    const failures = (response.results || []).filter(item => !item.ok);\n    const succeeded = ids.length - failures.length;\n    const failedIDs = new Set(failures.map(item => String(item.id)));\n    for (const id of ids) {\n      if (!failedIDs.has(id)) store.delete(id);\n    }\n    if (failures.length) {\n      const container = fromPlaylist || store === playlistSelectedSongs ? songList : allSongList;\n      for (const row of container.querySelectorAll(\'[data-song-id]\')) {\n        if (ids.includes(row.dataset.songId) && !failedIDs.has(row.dataset.songId)) row.remove();\n      }\n      showTaskFeedback(\'Removed \' + succeeded + \' of \' + ids.length + \'. \' +\n        failures.length + \' failed: \' + (failures[0].error || \'Please retry selected songs.\'), \'error\');\n      return false;\n    }\n    const completionMessage = failures.length\n      ? \'Finished: \' + succeeded + \' completed, \' + failures.length + \' failed.\'\n      : (fromPlaylist\n          ? \'Removed \' + succeeded + \' song\' + (succeeded === 1 ? \'\' : \'s\') + \' from "\' + playlist + \'".\'\n          : \'Removed \' + succeeded + \' song\' + (succeeded === 1 ? \'\' : \'s\') + \' from the library.\');\n    completeOnHome(completionMessage);\n    return true;\n  } catch (error) {\n    setStatus(\'Removal failed: \' + error.message);\n    return false;\n  } finally {\n    if (button) {\n      button.disabled = false;\n      button.textContent = originalText;\n    }\n  }\n}\n\nconst originalOpenPlaylist = openPlaylist;\nopenPlaylist = async function(name) {\n  playlistSelectedSongs.clear();\n  playlistSelectAll.checked = false;\n  await originalOpenPlaylist(name);\n  for (const row of songList.querySelectorAll(\'.playlist-song-row\')) {\n    const song = (window.__lastPlaylistSongs || []).find(item => String(item.id) === row.dataset.songId);\n    if (!song) continue;\n    const old = row.querySelector(\'.playlist-song-membership\');\n    if (old) old.remove();\n    row.prepend(selectionCheckbox(song, playlistSelectedSongs, row));\n  }\n};\n\nplaylistSelectAll.addEventListener(\'change\', () => setVisibleSelection(songList, playlistSelectedSongs, playlistSelectAll.checked));\ndocument.querySelector(\'#playlist-batch-remove\').addEventListener(\'click\', async () => {\n  if (await runSongBatch(\'playlist-remove\', playlistSelectedSongs, currentPlaylistName)) {\n    await loadPlaylists();\n  }\n});\ndocument.querySelector(\'#playlist-batch-library\').addEventListener(\'click\', async () => {\n  if (await runSongBatch(\'library-remove\', playlistSelectedSongs)) {\n    await loadPlaylists();\n  }\n});\n\nallSongsSelectAll.addEventListener(\'change\', () => setVisibleSelection(allSongList, allSongsSelectedSongs, allSongsSelectAll.checked));\ndocument.querySelector(\'#all-songs-batch-library\').addEventListener(\'click\', async () => {\n  if (await runSongBatch(\'library-remove\', allSongsSelectedSongs)) { await loadAllSongs(); await loadPlaylists(); }\n});\n\nconst sonobusUI={state:null,busy:false};\nasync function sonobusJSON(url,options){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),8000);try{const response=await fetch(url,{cache:\'no-store\',signal:controller.signal,...(options||{})});const data=await response.json();if(!response.ok||data.ok===false)throw new Error(data.error||\'SonoBus request failed\');return data}finally{clearTimeout(timer)}}\nfunction sonobusRender(state){sonobusUI.state=state;document.querySelectorAll(\'[data-sonobus-preset]\').forEach(button=>{const selected=button.dataset.sonobusPreset===state.activePreset;button.classList.toggle(\'active\',selected);button.setAttribute(\'aria-pressed\',String(selected))});const badge=document.querySelector(\'#sonobus-state-badge\');if(badge){const sono=state.sonobusRunning?((state.group||\'SonoBus\')+\' · Running\'):\'SonoBus stopped\';const air=state.airplayAvailable?(state.airplayConnected?(\'AirPlay \'+(state.airplayName||\'connected\')):\'AirPlay off\'):\'AirPlay unknown\';badge.textContent=sono+\' · \'+air}const list=document.querySelector(\'#sonobus-profile-list\');if(list){list.innerHTML=\'\';Object.entries(state.profiles||{}).forEach(([id,profile])=>{const row=document.createElement(\'div\');row.className=\'sonobus-profile\'+(id===state.selectedProfile?\' selected\':\'\');row.innerHTML=\'<div class="sonobus-profile-main"><div class="sonobus-profile-name"></div><div class="sonobus-profile-meta"></div></div><button data-use>Use</button><button data-delete>Delete</button>\';row.querySelector(\'.sonobus-profile-name\').textContent=profile.name||id;row.querySelector(\'.sonobus-profile-meta\').textContent=(profile.username||\'\')+\' · \'+(profile.group||\'\');row.querySelector(\'[data-use]\').onclick=()=>sonobusPost(\'/api/sonobus/profile/select\',{id});row.querySelector(\'[data-delete]\').onclick=()=>sonobusPost(\'/api/sonobus/profile/delete\',{id});list.appendChild(row)})}}\nasync function sonobusRefresh(){if(sonobusUI.busy||document.hidden)return;try{sonobusRender(await sonobusJSON(\'/api/sonobus/state\'))}catch(error){setStatus(error.name===\'AbortError\'?\'Route status timed out\':error.message)}}\nasync function sonobusPost(url,payload){if(sonobusUI.busy)return;sonobusUI.busy=true;try{const data=await sonobusJSON(url,{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(payload||{})});if(data.state)sonobusRender(data.state);if(url===\'/api/sonobus/preset\')showTaskFeedback(data.message||\'Routing updated\',\'done\')}catch(error){showTaskFeedback(error.message, \'error\')}finally{sonobusUI.busy=false;sonobusRefresh()}}\ndocument.querySelectorAll(\'[data-sonobus-preset]\').forEach(button=>button.onclick=async()=>{\n  if(sonobusUI.busy)return;\n  const preset=button.dataset.sonobusPreset;\n  document.querySelectorAll(\'[data-sonobus-preset]\').forEach(item=>{\n    item.classList.toggle(\'active\',item===button);\n    item.disabled=true;\n  });\n  button.setAttribute(\'aria-pressed\',\'true\');\n  showTaskFeedback(\'Applying \'+button.textContent.trim()+\' destination…\', \'working\');\n  try{\n    await sonobusPost(\'/api/sonobus/preset\',{preset});\n  }finally{\n    document.querySelectorAll(\'[data-sonobus-preset]\').forEach(item=>{\n      item.disabled=false;\n      item.setAttribute(\'aria-pressed\',String(item.classList.contains(\'active\')));\n    });\n  }\n});\nconst restartSonoBusButton=document.querySelector(\'#restart-sonobus\');\nasync function restartSonoBusWithFeedback(){\n  if(!restartSonoBusButton||sonobusUI.busy)return;\n  const badge=document.querySelector(\'#sonobus-state-badge\');\n  const previousBadge=badge?badge.textContent:\'\';\n  sonobusUI.busy=true;\n  restartSonoBusButton.disabled=true;\n  restartSonoBusButton.classList.add(\'is-restarting\');\n  restartSonoBusButton.setAttribute(\'aria-busy\',\'true\');\n  if(badge){badge.textContent=\'Restarting SonoBus…\';badge.classList.add(\'is-restarting\')}\n  showTaskFeedback(\'Restarting SonoBus…\', \'working\');\n  try{\n    const data=await sonobusJSON(\'/api/sonobus/restart\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:\'{}\'});\n    let state=null;\n    for(let attempt=0;attempt<10;attempt+=1){\n      await new Promise(resolve=>setTimeout(resolve,500));\n      try{\n        state=await sonobusJSON(\'/api/sonobus/state\');\n        if(state.sonobusRunning)break;\n      }catch(_error){}\n    }\n    if(state)sonobusRender(state);\n    showTaskFeedback(state&&state.sonobusRunning?\'SonoBus restarted\':\'SonoBus restart sent\', \'done\');\n  }catch(error){\n    if(badge)badge.textContent=previousBadge||\'SonoBus stopped\';\n    showTaskFeedback(error.message, \'error\');\n  }finally{\n    restartSonoBusButton.disabled=false;\n    restartSonoBusButton.classList.remove(\'is-restarting\');\n    restartSonoBusButton.removeAttribute(\'aria-busy\');\n    if(badge)badge.classList.remove(\'is-restarting\');\n    sonobusUI.busy=false;\n    sonobusRefresh();\n  }\n}\nif(restartSonoBusButton)restartSonoBusButton.addEventListener(\'click\',restartSonoBusWithFeedback);\nasync function refreshVisiblePage(){if(document.hidden)return;await Promise.allSettled([refreshIPadState(),sonobusRefresh()])}\nfunction scheduleRouteStatePoll(generation){clearTimeout(routeStateTimer);if(document.hidden||generation!==pageRefreshGeneration)return;routeStateTimer=setTimeout(async()=>{await sonobusRefresh();scheduleRouteStatePoll(generation)},2500)}\nfunction startVisiblePolling(){pageRefreshGeneration+=1;const generation=pageRefreshGeneration;refreshVisiblePage();scheduleIPadStatePoll(generation);scheduleRouteStatePoll(generation)}\ndocument.addEventListener(\'visibilitychange\',()=>{if(document.hidden){pageRefreshGeneration+=1;clearTimeout(ipadStateTimer);clearTimeout(routeStateTimer);return}loadPlaylists();startVisiblePolling()});\n// One floating control, visible only after scrolling in song lists.\nconst backToTop = document.querySelector(\'#back-to-top\');\nconst backToTopScreens = [playlistScreen, document.querySelector(\'#all-songs-screen\')];\nfunction updateBackToTop() {\n  const inSongList = backToTopScreens.some(screen => !screen.classList.contains(\'hidden\'));\n  backToTop.classList.toggle(\'hidden\', !inSongList || window.scrollY < 420);\n}\nwindow.addEventListener(\'scroll\', updateBackToTop, {passive: true});\nfor (const screen of backToTopScreens) {\n  new MutationObserver(updateBackToTop).observe(screen, {attributes: true, attributeFilter: [\'class\']});\n}\nbackToTop.addEventListener(\'click\', () => {\n  window.scrollTo({top: 0, behavior: window.matchMedia(\'(prefers-reduced-motion: reduce)\').matches ? \'auto\' : \'smooth\'});\n});\nupdateBackToTop();\n\nloadPlaylists();startVisiblePolling();\n</script>\n</body>\n</html>\n'

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
