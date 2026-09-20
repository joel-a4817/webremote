#!/var/jb/usr/bin/python3

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from subprocess import run
from urllib.parse import parse_qs, urlparse
import json

MEDIACTL = "/var/jb/usr/local/bin/mediactl"
PORT = 8765

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

body {
  margin: 0;
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
  margin: 0 auto;
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
  grid-template-columns: 1fr auto;
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

.shuffle-button {
  width: 78px;
  min-height: 68px;

  border-radius: 19px;

  font-size: 25px;

  background:
    linear-gradient(
      135deg,
      #fa2d55,
      #8b5cff
    );
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

#connect-airplay {
  background:
    linear-gradient(
      135deg,
      #2f8cff,
      #765cff
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
</style>
</head>

<body>
<main>
  <section id="main-screen">
    <h1>iPad Music</h1>

    <div class="now-playing">
      <div class="now-label">Now Playing</div>
      <div id="current-title">Loading…</div>
      <div id="current-details"></div>
    </div>

    <div class="controls">
      <button
        class="transport"
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
        id="restart-music"
        class="system-button"
        type="button"
      >
        Restart Music
      </button>
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
      >
        Back
      </button>

      <h1 id="playlist-title">
        Playlist
      </h1>

      <div></div>
    </div>

    <div
      id="song-list"
      class="list"
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

const currentTitle =
  document.querySelector("#current-title");

const currentDetails =
  document.querySelector("#current-details");

const toggleButton =
  document.querySelector("#toggle");

const connectAirPlayButton =
  document.querySelector(
    "#connect-airplay"
  );

const restartMusicButton =
  document.querySelector(
    "#restart-music"
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

async function updateNowPlaying() {
  try {
    const data =
      await readJSON("/api/now-playing");

    if (!data.available) {
      currentTitle.textContent =
        "Nothing playing";

      currentDetails.textContent = "";

      toggleButton.textContent = "▶";
      toggleButton.setAttribute(
        "aria-label",
        "Play"
      );

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

  } catch {
    currentTitle.textContent =
      "Now Playing unavailable";

    currentDetails.textContent = "";

    toggleButton.textContent = "▶";
    toggleButton.setAttribute(
      "aria-label",
      "Play or pause"
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

  try {
    const data =
      await readJSON("/api/playlists");

    if (data.playlists.length === 0) {
      playlistList.textContent =
        "No playlists available";

      return;
    }

    for (const playlist of data.playlists) {
      const row =
        document.createElement("div");

      row.className = "playlist-row";

      const openButton =
        document.createElement("button");

      openButton.className =
        "playlist-button";

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

      const shuffleButton =
        document.createElement("button");

      shuffleButton.className =
        "shuffle-button";

      shuffleButton.textContent = "⤨";

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

    if (data.songs.length === 0) {
      songList.textContent =
        "This playlist has no available songs";

      return;
    }

    for (const song of data.songs) {
      const button =
        document.createElement("button");

      button.className =
        "song-button";

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

      const details = [
        song.artist,
        song.album
      ].filter(Boolean);

      artist.textContent =
        details.join(" • ");

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
              "Playing " +
              (
                song.title ||
                "selected song"
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

      songList.appendChild(button);
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

connectAirPlayButton.addEventListener(
  "click",
  () => {
    runSystemAction(
      connectAirPlayButton,
      "/api/airplay/connect",
      "Connecting…",
      "Connected to rt4817"
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

loadPlaylists();
updateNowPlaying();

setInterval(
  updateNowPlaying,
  2000
);
</script>
</body>
</html>
"""


def execute(arguments):
    return run(
        [MEDIACTL, *arguments],
        capture_output=True,
        text=True,
        timeout=10
    )


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
        self.wfile.write(data)

    def send_json(self, status, payload):
        self.send_data(
            status,
            "application/json; charset=utf-8",
            json.dumps(payload).encode()
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

        payload["ok"] = True
        self.send_json(200, payload)

    def read_json_body(self):
        length = int(
            self.headers.get("Content-Length", "0")
        )

        if length <= 0:
            return {}

        return json.loads(
            self.rfile.read(length)
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            self.send_data(
                200,
                "text/html; charset=utf-8",
                PAGE.encode()
            )
            return

        if path == "/api/now-playing":
            self.mediactl_json(
                ["now-playing-json"]
            )
            return

        if path == "/api/playlists":
            self.mediactl_json(
                ["playlists-json"]
            )
            return

        if path == "/api/playlist":
            name = query.get("name", [""])[0]

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

        if path in TRANSPORT_COMMANDS:
            result = execute(
                TRANSPORT_COMMANDS[path]
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

        if path == "/api/airplay/connect":
            result = execute(
                ["airplay-rt4817"]
            )

            succeeded = (
                result.returncode == 0
            )

            self.send_json(
                200 if succeeded else 500,
                {
                    "ok": succeeded,
                    "message": (
                        "Connected to rt4817"
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
                playlist = str(payload["playlist"])
            except Exception:
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
                playlist = str(payload["playlist"])
                identifier = str(payload["id"])
            except Exception:
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

    def log_message(self, format, *args):
        pass


print(
    f"Web remote listening on port {PORT}",
    flush=True
)

ThreadingHTTPServer(
    ("0.0.0.0", PORT),
    Handler
).serve_forever()
