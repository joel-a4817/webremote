

/* Every button gets horizontal progress. Network-backed actions remain active until
 * their request completes; immediate UI/navigation actions use a short pulse. */
let interactionButton = null;
let interactionToken = 0;
function beginButtonProgress(button) {
  if (!(button instanceof HTMLButtonElement) || button.disabled) return;
  const token = ++interactionToken;
  interactionButton = button;
  button.classList.add('button-progress-active');
  button.dataset.progressToken = String(token);
  setTimeout(() => {
    if (button.dataset.progressToken === String(token)) {
      button.classList.remove('button-progress-active');
      delete button.dataset.progressToken;
    }
  }, 900);
}
function finishButtonProgress(button, token) {
  if (!button) return;
  if (token && button.dataset.progressToken !== token) return;
  button.classList.remove('button-progress-active');
  delete button.dataset.progressToken;
}
document.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (button) beginButtonProgress(button);
}, true);
const nativeFetch = window.fetch.bind(window);
window.fetch = (...args) => {
  const button = interactionButton;
  interactionButton = null;
  const token = button?.dataset.progressToken || '';
  if (button) button.classList.add('button-progress-active');
  return nativeFetch(...args).finally(() => finishButtonProgress(button, token));
};
const mainScreen =
  document.querySelector("#main-screen");
const musicScreen = document.querySelector("#music-screen");

const playlistScreen =
  document.querySelector("#playlist-screen");

const playlistList =
  document.querySelector("#playlist-list");

const songList =
  document.querySelector("#song-list");

const playlistTitle =
  document.querySelector("#playlist-title");

const uploadCompletePanel =
  document.querySelector("#upload-complete-panel");

const currentTitle =
  document.querySelector("#current-title");

const currentDetails =
  document.querySelector("#current-details");
const appleNowPlayingArtwork = document.querySelector("#apple-now-playing-artwork");
let appleNowPlayingArtworkID = "";
function updateAppleNowPlayingArtwork(id) {
  const nextID = id && /^\d+$/.test(String(id)) ? String(id) : "";
  if (nextID === appleNowPlayingArtworkID) return;
  appleNowPlayingArtworkID = nextID;
  appleNowPlayingArtwork.replaceChildren();
  if (!nextID) return;
  const image = document.createElement("img");
  image.alt = "";
  image.decoding = "async";
  image.addEventListener("error", () => image.remove(), {once: true});
  image.src = "/api/song/artwork?id=" + encodeURIComponent(nextID);
  appleNowPlayingArtwork.appendChild(image);
}
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
const systemVolumeSlider = document.querySelector("#system-volume-slider");
const volumeSliders = [volumeSlider, systemVolumeSlider];
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
    <svg class="media-icon pause-icon" viewBox="0 0 24 24" aria-hidden="true">
      <rect class="icon-fill" x="5.5" y="4.5" width="4.5" height="15" rx="1.5"></rect>
      <rect class="icon-fill" x="14" y="4.5" width="4.5" height="15" rx="1.5"></rect>
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
    showTaskFeedback(error.message, 'error');

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
    showTaskFeedback(error.message, 'error');

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
  for (const slider of volumeSliders) {
    slider.value = String(percent);
    slider.style.setProperty("--volume-progress", percent + "%");
  }
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
    for (const slider of volumeSliders) slider.disabled = false;
  } catch (error) {
    if (error.name !== "AbortError") {
      showTaskFeedback(error.message, 'error');
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
    showTaskFeedback(error.message, 'error');
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

function queueVolume(event) {
  const requested = clampVolume(event.currentTarget.value);

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

function finishVolumeDrag(event) {
  if (!volumeDragActive) {
    return;
  }

  volumeDragActive = false;

  if (volumeTimer !== null) {
    clearTimeout(volumeTimer);
    volumeTimer = null;
  }

  const finalValue = clampVolume(event.currentTarget.value);

  if (lastQueuedVolumeSent !== finalValue) {
    sendVolume(finalValue);
  }

  lastQueuedVolumeSent = null;
}

for (const slider of volumeSliders) {
  slider.addEventListener("pointerdown", beginVolumeDrag);
  slider.addEventListener("touchstart", beginVolumeDrag, {passive: true});
  slider.addEventListener("input", queueVolume);
  slider.addEventListener("change", finishVolumeDrag);
  slider.addEventListener("pointerup", finishVolumeDrag);
  slider.addEventListener("touchend", finishVolumeDrag);
}
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
    showTaskFeedback(error.message, 'error');
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
      showTaskFeedback(error.message, 'error');
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
    showTaskFeedback(error.message, 'error');
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
      showTaskFeedback(error.message, 'error');
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

function notificationBox() {
  let banner = document.querySelector('#global-task-feedback');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'global-task-feedback';
    banner.setAttribute('role', 'status');
    banner.setAttribute('aria-live', 'polite');
    const message = document.createElement('span');
    message.className = 'task-feedback-message';
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'task-feedback-close';
    close.textContent = '×';
    close.setAttribute('aria-label', 'Close notification');
    const dismiss = event => {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      event?.stopImmediatePropagation?.();
      clearTimeout(showTaskFeedback.timer);
      banner.classList.add('hidden');
      banner.setAttribute('aria-hidden', 'true');
    };
    close.addEventListener('pointerup', dismiss);
    close.addEventListener('click', dismiss);
    banner.append(message, close);
    document.body.appendChild(banner);
  }
  return banner;
}

function showTaskFeedback(message, kind='working') {
  if (kind === 'working') return;
  const banner = notificationBox();
  const messageNode = banner.querySelector('.task-feedback-message');
  if (messageNode) messageNode.textContent = String(message || 'Working…');
  banner.classList.remove('hidden', 'feedback-done', 'feedback-error');
  banner.setAttribute('aria-hidden', 'false');
  if (kind === 'done') banner.classList.add('feedback-done');
  if (kind === 'error') banner.classList.add('feedback-error');
  clearTimeout(showTaskFeedback.timer);
  if (kind !== 'working') {
    showTaskFeedback.timer = setTimeout(() => banner.classList.add('hidden'), 10000);
  }
}

function setStatus(text) {
  const message = String(text || '');
  if (/error|failed|invalid|timed out|could not|not found|unavailable/i.test(message)) {
    showTaskFeedback(message, 'error');
  }
}
window.addEventListener('error', event => {
  showTaskFeedback(event?.error?.message || event?.message || 'Unexpected interface error', 'error');
});
window.addEventListener('unhandledrejection', event => {
  const reason = event?.reason;
  showTaskFeedback(reason?.message || String(reason || 'Unexpected request error'), 'error');
});

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
      updateAppleNowPlayingArtwork("");
      setToggleState(false);
      updateSeekDisplay(0, 0);

      return;
    }

    setToggleState(data.playing);
    updateAppleNowPlayingArtwork(data.id);
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
    updateAppleNowPlayingArtwork("");

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
  } catch (error) { showTaskFeedback(error.message, 'error'); }
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
  } catch (error) { showTaskFeedback(error.message, 'error'); }
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
    showTaskFeedback(error.message, 'error');
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
  const showProgress = endpoint === '/api/music/restart';
  if (showProgress) showTaskFeedback(workingLabel, 'working');

  try {
    const result =
      await readJSON(
        endpoint,
        {
          method: "POST"
        }
      );

    showTaskFeedback(result.message || successLabel, 'done');

    setTimeout(
      updateNowPlaying,
      700
    );

  } catch (error) {
    showTaskFeedback(error.message, 'error');

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

    showTaskFeedback(
      result.message || "Connected to " + device.name,
      'done'
    );

  } catch (error) {
    showTaskFeedback(error.message, 'error');
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

    showTaskFeedback(
      result.message || "Default set to " + device.name,
      'done'
    );

    await loadAirPlayDevices(true);
  } catch (error) {
    showTaskFeedback(error.message, 'error');
  }
}


async function loadAirPlayDevices(silent=false) {
  airPlayList.innerHTML = "";
  if (!silent) showTaskFeedback('Discovering AirPlay devices…', 'working');

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
      if (!silent) showTaskFeedback('No external AirPlay devices found', 'done');
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
    if (!silent) showTaskFeedback('AirPlay devices loaded', 'done');

  } catch (error) {
    showTaskFeedback(error.message, 'error');
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
    showTaskFeedback(error.message, 'error');
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
    showTaskFeedback(error.message, 'error');
  }
}

function makeArtwork(id, playlist=false) {
  const tile = document.createElement('span');
  tile.className = 'song-artwork' + (playlist ? ' playlist-artwork' : '');
  tile.setAttribute('aria-hidden', 'true');
  if (id && /^\d+$/.test(String(id))) {
    const image = document.createElement('img');
    image.alt = '';
    image.loading = 'lazy';
    image.decoding = 'async';
    image.addEventListener('error', () => image.remove(), {once: true});
    image.src = '/api/song/artwork?id=' + encodeURIComponent(String(id));
    tile.appendChild(image);
  }
  return tile;
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

      const playlistCopy = document.createElement('span');
      playlistCopy.className = 'playlist-copy';
      playlistCopy.append(name, count);
      openButton.classList.add('has-artwork');
      openButton.append(makeArtwork(playlist.coverID, true), playlistCopy);

      openButton.addEventListener(
        "click",
        () => {
          openPlaylist(playlist.name);
        }
      );

      const plainPlayButton =
        document.createElement("button");
      plainPlayButton.className =
        "playlist-play-button playlist-quick-play";
      plainPlayButton.type = "button";
      plainPlayButton.innerHTML = '<svg class="playlist-action-icon" viewBox="0 0 24 24" aria-hidden="true"><path class="play-glyph" d="M8 5.5 19 12 8 18.5z"/></svg>';
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
        "shuffle-button playlist-shuffle-button playlist-shuffle";
      shuffleButton.type = "button";

      shuffleButton.innerHTML = '<svg class="playlist-action-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h2c5 0 7 10 12 10h2"/><path d="m17 14 3 3-3 3"/><path d="M4 17h2c2.1 0 3.6-1.8 5-4"/><path d="M14 8c1.1-.7 2.4-1 4-1h2"/><path d="m17 4 3 3-3 3"/></svg>';

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
    showTaskFeedback(error.message, 'error');
  }
}

async function openPlaylist(name) {
  songList.innerHTML = "";
  playlistSongSearch.value = "";
  playlistSearchMessage.textContent = "";
  playlistSearchMessage.classList.add("hidden");

  currentPlaylistName = name;
  playlistTitle.textContent = name;

  showOnly(playlistScreen);


  try {
    const data =
      await readJSON(
        "/api/playlist?name=" +
        encodeURIComponent(name)
      );


    const songs =
      Array.isArray(data.songs)
        ? data.songs
        : [];
    window.__lastPlaylistSongs = songs;

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
      row.dataset.songId = String(song.id);

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
            showTaskFeedback(error.message, 'error');
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

      const songCopy = document.createElement('span');
      songCopy.className = 'song-copy';
      songCopy.append(title, artist);
      button.classList.add('has-artwork');
      button.append(makeArtwork(song.id), songCopy);

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
            showTaskFeedback(error.message, 'error');
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
    showTaskFeedback(error.message, 'error');
  }
}

document
  .querySelector("#back")
  .addEventListener(
    "click",
    () => {
      showOnly(musicScreen);

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
    remove.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      const key = uploadFileKey(file);
      selectedUploadFiles = selectedUploadFiles.filter(
        candidate => uploadFileKey(candidate) !== key
      );
      renderSelectedUploadFiles();
      musicFiles.value = '';
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
    musicScreen,
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

document.querySelector('#open-music-menu').addEventListener('click', () => {
  showOnly(musicScreen);
  window.scrollTo({top: 0, behavior: 'auto'});
});
document.querySelector('#music-menu-back').addEventListener('click', () => {
  showOnly(mainScreen);
  window.scrollTo({top: 0, behavior: 'auto'});
});
function completeOnHome(message) {
  showOnly(mainScreen);
  window.scrollTo({top: 0, behavior: 'smooth'});
  showTaskFeedback(message, 'done');
}

var playlistSelectedSongs = new Map();
var allSongsSelectedSongs = new Map();

function createSongManagementRow(song) {
  const row = document.createElement('div');
  row.className = 'song-management-row';
  row.dataset.songId = String(song.id);
  const play = document.createElement('button');
  play.className = 'song-button';
  play.type = 'button';
  play.classList.add('has-artwork');
  const songCopy = document.createElement('span');
  songCopy.className = 'song-copy';
  songCopy.innerHTML = '<span class="song-title"></span><span class="song-artist"></span>';
  play.append(makeArtwork(song.id), songCopy);
  play.querySelector('.song-title').textContent = song.title || 'Unknown title';
  play.querySelector('.song-artist').textContent = [song.artist, song.album].filter(Boolean).join(' • ');
  play.addEventListener('click', async () => {
    try {
      await readJSON('/api/song/play', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id:song.id})});
      setStatus('Playing ' + (song.title || 'selected song'));
      setTimeout(updateNowPlaying, 350);
    } catch (error) { showTaskFeedback(error.message, 'error'); }
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
  const matches = allSongs.filter(song => (song._webremoteSearchText || '').includes(query));
  const fragment = document.createDocumentFragment();
  globalSongResults.textContent = matches.length ? '' : 'No matching songs';
  for (const song of matches) {
    const row = createSongManagementRow(song);
    row.prepend(selectionCheckbox(song, allSongsSelectedSongs, row));
    fragment.appendChild(row);
  }
  allSongList.appendChild(fragment);
}

async function loadAllSongs() {
  const response = await readJSON('/api/songs');
  allSongs = Array.isArray(response.songs) ? response.songs : [];
  for (const song of allSongs) {
    song._webremoteSearchText = normalizeSearchText(
      [song.title, song.artist, song.album].filter(Boolean).join(' '));
  }
  renderAllSongs();
}

let allSongsSearchTimer = null;
globalSongSearch.addEventListener('input', () => {
  clearTimeout(allSongsSearchTimer);
  allSongsSearchTimer = setTimeout(renderAllSongs, 120);
});

document.querySelector('#open-all-songs').addEventListener('click', async () => {
  showOnly(allSongsScreen);
  try { await loadAllSongs(); } catch (error) { showTaskFeedback(error.message, 'error'); }
});
document.querySelector('#all-songs-back').addEventListener('click', () => showOnly(musicScreen));

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
document.querySelector('#upload-back').addEventListener('click', () => showOnly(musicScreen));

const uploadSubmitButton = document.querySelector('#upload-submit');

async function waitForMusicImportJob(jobID) {
  const labels = {
    queued: 'Queued…',
    'opening-filza': 'Opening Filza…',
    'waking-ipad': 'Waking iPad…',
    'filza-ready': 'Filza ready…',
    'triggering-filza': 'Sending batch to Filza…',
    'filza-importing': 'Filza is importing the batch. Keep Filza open…',
    'verifying-results': 'Filza finished. Checking every import result…',
    'preserving-playlists': 'Preserving playlist memberships…',
    'replacing-duplicates': 'Replacing older duplicate library files…',
    'resolving-duplicates': 'Resolving duplicates automatically…',
    'refreshing-library': 'Refreshing Apple Music library…',
    'processing-library': 'Updating playlists and library…',
    finalizing: 'Finalizing import…'
  };
  let failures = 0;
  while (true) {
    await new Promise(resolve => setTimeout(resolve, 750));
    let state;
    try {
      state = await readJSON('/api/music/import/status?id=' + encodeURIComponent(jobID));
      failures = 0;
    } catch (error) {
      failures += 1;
      uploadSubmitButton.textContent = 'Checking import status…';
      showTaskFeedback('Import is still running. Reconnecting to status…', 'working');
      if (failures < 8) continue;
      throw error;
    }
    if (state.status === 'awaiting-duplicates') {
      uploadSubmitButton.textContent = 'Resolving duplicates…';
      showTaskFeedback('Resolving duplicates automatically…', 'working');
      continue;
    }
    if (state.status === 'done') {
      uploadSubmitButton.textContent = 'Import complete';
      showTaskFeedback('Import complete. Finalizing the web interface…', 'working');
      return state.result;
    }
    if (state.status === 'failed') throw new Error(state.error || 'Music import failed');
    const done = Number(state.completed || 0);
    const total = Number(state.total || 0);
    const label = labels[state.status] || 'Importing…';
    uploadSubmitButton.textContent = total > 0 && done > 0
      ? label + ' ' + done + ' / ' + total
      : label;
    showTaskFeedback(total > 0 && done > 0 ? label + ' ' + done + ' of ' + total : label, 'working');
  }
}

document.querySelector('#upload-submit').addEventListener('click', async () => {
  if (!selectedUploadFiles.length) {
    showTaskFeedback('Choose at least one audio file', 'error');
    return;
  }

  const submitButton = uploadSubmitButton;

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
  submitButton.textContent = 'Opening Filza…';

  try {
    showTaskFeedback('Preparing upload session…', 'working');
    const session = await readJSON('/api/music/upload-session', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({playlists})
    });
    let uploaded = 0;
    for (const file of selectedUploadFiles) {
      submitButton.textContent = 'Uploading ' + (uploaded + 1) + ' / ' + selectedUploadFiles.length + '…';
      showTaskFeedback(submitButton.textContent, 'working');
      const part = new FormData();
      part.append('file', file, file.name);
      await readJSON('/api/music/upload-file?session=' + encodeURIComponent(session.sessionID), {
        method: 'POST', body: part
      });
      uploaded += 1;
    }
    submitButton.textContent = 'Upload complete';
    showTaskFeedback('All files uploaded. Opening Filza once for the complete batch…', 'working');
    const accepted = await readJSON('/api/music/upload-commit', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({sessionID: session.sessionID})
    });
    const result = accepted.jobID
      ? await waitForMusicImportJob(accepted.jobID)
      : accepted;

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

    const resolved = duplicates;

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

    completeOnHome(result.message || message);

    Promise.allSettled([loadPlaylists(), loadAllSongs()]);


  } catch (error) {
    showTaskFeedback(error.message, 'error');

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
  document.querySelector('#song-manage-artwork').replaceWith(Object.assign(makeArtwork(song.id), {id: 'song-manage-artwork'}));
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
        } catch (error) { input.checked = !input.checked; showTaskFeedback(error.message, 'error'); }
        finally { input.disabled = false; }
      });
      songPlaylistChecks.appendChild(label);
    }
  } catch (error) { songPlaylistChecks.textContent = error.message; showTaskFeedback(error.message, 'error'); }
}

document.querySelector('#song-manage-back').addEventListener('click', () => showOnly(allSongsScreen));
document.querySelector('#remove-from-library').addEventListener('click', async () => {
  if (!selectedManagedSong) return;
  if (!confirm('Remove "' + (selectedManagedSong.title || 'this song') + '" from your Apple Music library?')) return;

  const button = document.querySelector('#remove-from-library');
  button.disabled = true;
  button.textContent = 'Removing…';

  try {
    showTaskFeedback('Removing song from the library…', 'working');
    await readJSON('/api/song/library', {
      method: 'DELETE',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id:selectedManagedSong.id})
    });
    const removedTitle = selectedManagedSong.title || 'Song';
    selectedManagedSong = null;
    await loadAllSongs();
    await loadPlaylists();
    completeOnHome('Removed "' + removedTitle + '" from the Apple Music library.');
  } catch (error) {
    showTaskFeedback(error.message, 'error');
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

    label.append(input, makeArtwork(song.id), details);

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
    showTaskFeedback(error.message, 'error');
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
      showTaskFeedback("Select at least one song", "error");
      return;
    }

    const playlistName =
      currentPlaylistName;

    button.disabled = true;
    button.textContent = "Adding…";

    const failed = [];
    if (identifiers.length > 1) showTaskFeedback('Adding ' + identifiers.length + ' songs to playlist…', 'working');

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

      const addedCount = identifiers.length - failed.length;
      const completionMessage = failed.length > 0
        ? 'Finished adding songs to "' + playlistName + '": '
          + addedCount + ' added, ' + failed.length + ' failed.'
        : 'Added ' + addedCount + ' song' + (addedCount === 1 ? '' : 's')
          + ' to "' + playlistName + '".';
      if (failed.length) {
        showOnly(mainScreen);
        showTaskFeedback(completionMessage + ' ' + failed[0], 'error');
      } else if (identifiers.length > 1) {
        completeOnHome(completionMessage);
      } else {
        showOnly(mainScreen);
        window.scrollTo({top: 0, behavior: 'smooth'});
      }

    } catch (error) {
      /*
       * Keep the selection screen available only when an
       * unexpected outer failure prevents playlist reload.
       */
      showOnly(
        playlistAddScreen
      );

      showTaskFeedback(error.message, 'error');

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
      showTaskFeedback(error.message, 'error');
    }
  }
);

document.querySelector("#playlist-rename").addEventListener(
  "click",
  async () => {
    if (!currentPlaylistName) return;
    const oldName = currentPlaylistName;
    const requested = prompt("Rename playlist", oldName);
    if (requested === null) return;
    const newName = requested.trim();
    if (!newName) {
      showTaskFeedback("Enter a playlist name", "error");
      return;
    }
    if (newName === oldName) {
      return;
    }
    const button = document.querySelector("#playlist-rename");
    const normalLabel = button.textContent;
    button.disabled = true;
    button.textContent = "Renaming…";
    showTaskFeedback('Renaming "' + oldName + '" to "' + newName + '"…', "working");
    try {
      const result = await readJSON("/api/playlist/rename", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({oldName, newName})
      });
      currentPlaylistName = result.name || newName;
      playlistTitle.textContent = currentPlaylistName;
      await loadPlaylists();
      completeOnHome(result.message || ('Renamed "' + oldName + '" to "' + currentPlaylistName + '".'));
    } catch (error) {
      showTaskFeedback(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = normalLabel;
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
    showTaskFeedback('Removing playlist "' + name + '"…', 'working');

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
      completeOnHome(
        'Removed playlist "'
        + name
        + '". Songs were kept.'
      );

    } catch (error) {
      showTaskFeedback(error.message, 'error');

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


// Selection stores are declared before the song renderers.
const playlistSelectAll = document.querySelector('#playlist-select-all');
const allSongsSelectAll = document.querySelector('#all-songs-select-all');

function selectionCheckbox(song, store, row) {
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.className = 'batch-select';
  input.checked = store.has(String(song.id));
  input.setAttribute('aria-label', 'Select ' + (song.title || 'song'));
  input.addEventListener('change', () => {
    if (input.checked) store.set(String(song.id), song);
    else store.delete(String(song.id));
    row.classList.toggle('batch-selected', input.checked);
  });
  return input;
}

function setVisibleSelection(container, store, checked) {
  for (const input of container.querySelectorAll('.batch-select')) {
    if (input.checked !== checked) { input.checked = checked; input.dispatchEvent(new Event('change')); }
  }
}

async function runSongBatch(action, store, playlist='') {
  const ids = [...store.keys()];
  if (!ids.length) { showTaskFeedback('Select at least one song', 'error'); return false; }
  const fromPlaylist = action === 'playlist-remove';
  const label = fromPlaylist ? 'remove selected songs from this playlist' : 'remove selected songs from the library';
  if (!confirm('Are you sure you want to ' + label + '?')) return false;
  const button = fromPlaylist
    ? document.querySelector('#playlist-batch-remove')
    : (store === playlistSelectedSongs
        ? document.querySelector('#playlist-batch-library')
        : document.querySelector('#all-songs-batch-library'));
  const originalText = button ? button.textContent : '';
  if (button) {
    button.disabled = true;
    button.textContent = fromPlaylist ? 'Removing from playlist…' : 'Removing from library…';
  }
  showTaskFeedback(
    fromPlaylist
      ? 'Removing ' + ids.length + ' selected song' + (ids.length === 1 ? '' : 's') + ' from "' + playlist + '"…'
      : 'Removing ' + ids.length + ' selected song' + (ids.length === 1 ? '' : 's') + ' from the library…',
    'working'
  );
  try {
    const response = await readJSON('/api/songs/batch', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action, ids, playlist})
    });
    const failures = (response.results || []).filter(item => !item.ok);
    const succeeded = ids.length - failures.length;
    const failedIDs = new Set(failures.map(item => String(item.id)));
    for (const id of ids) {
      if (!failedIDs.has(id)) store.delete(id);
    }
    if (failures.length) {
      const container = fromPlaylist || store === playlistSelectedSongs ? songList : allSongList;
      for (const row of container.querySelectorAll('[data-song-id]')) {
        if (ids.includes(row.dataset.songId) && !failedIDs.has(row.dataset.songId)) row.remove();
      }
      showTaskFeedback('Removed ' + succeeded + ' of ' + ids.length + '. ' +
        failures.length + ' failed: ' + (failures[0].error || 'Please retry selected songs.'), 'error');
      return false;
    }
    const completionMessage = failures.length
      ? 'Finished: ' + succeeded + ' completed, ' + failures.length + ' failed.'
      : (fromPlaylist
          ? 'Removed ' + succeeded + ' song' + (succeeded === 1 ? '' : 's') + ' from "' + playlist + '".'
          : 'Removed ' + succeeded + ' song' + (succeeded === 1 ? '' : 's') + ' from the library.');
    completeOnHome(completionMessage);
    return true;
  } catch (error) {
    setStatus('Removal failed: ' + error.message);
    return false;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

const originalOpenPlaylist = openPlaylist;
openPlaylist = async function(name) {
  playlistSelectedSongs.clear();
  playlistSelectAll.checked = false;
  await originalOpenPlaylist(name);
  for (const row of songList.querySelectorAll('.playlist-song-row')) {
    const song = (window.__lastPlaylistSongs || []).find(item => String(item.id) === row.dataset.songId);
    if (!song) continue;
    const old = row.querySelector('.playlist-song-membership');
    if (old) old.remove();
    row.prepend(selectionCheckbox(song, playlistSelectedSongs, row));
  }
};

playlistSelectAll.addEventListener('change', () => setVisibleSelection(songList, playlistSelectedSongs, playlistSelectAll.checked));
document.querySelector('#playlist-batch-remove').addEventListener('click', async () => {
  if (await runSongBatch('playlist-remove', playlistSelectedSongs, currentPlaylistName)) {
    await loadPlaylists();
  }
});
document.querySelector('#playlist-batch-library').addEventListener('click', async () => {
  if (await runSongBatch('library-remove', playlistSelectedSongs)) {
    await loadPlaylists();
  }
});

allSongsSelectAll.addEventListener('change', () => setVisibleSelection(allSongList, allSongsSelectedSongs, allSongsSelectAll.checked));
document.querySelector('#all-songs-batch-library').addEventListener('click', async () => {
  if (await runSongBatch('library-remove', allSongsSelectedSongs)) { await loadAllSongs(); await loadPlaylists(); }
});

const sonobusUI={state:null,busy:false};
async function sonobusJSON(url,options){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),8000);try{const response=await fetch(url,{cache:'no-store',signal:controller.signal,...(options||{})});const data=await response.json();if(!response.ok||data.ok===false)throw new Error(data.error||'SonoBus request failed');return data}finally{clearTimeout(timer)}}
function sonobusRender(state){sonobusUI.state=state;document.querySelectorAll('[data-sonobus-preset]').forEach(button=>{const selected=button.dataset.sonobusPreset===state.activePreset;button.classList.toggle('active',selected);button.setAttribute('aria-pressed',String(selected))});const badge=document.querySelector('#sonobus-state-badge');if(badge){const sono=state.sonobusRunning?((state.group||'SonoBus')+' · Running'):'SonoBus stopped';const air=state.airplayAvailable?(state.airplayConnected?('AirPlay '+(state.airplayName||'connected')):'AirPlay off'):'AirPlay unknown';badge.textContent=sono+' · '+air}const list=document.querySelector('#sonobus-profile-list');if(list){list.innerHTML='';Object.entries(state.profiles||{}).forEach(([id,profile])=>{const row=document.createElement('div');row.className='sonobus-profile'+(id===state.selectedProfile?' selected':'');row.innerHTML='<div class="sonobus-profile-main"><div class="sonobus-profile-name"></div><div class="sonobus-profile-meta"></div></div><button data-use>Use</button><button data-delete>Delete</button>';row.querySelector('.sonobus-profile-name').textContent=profile.name||id;row.querySelector('.sonobus-profile-meta').textContent=(profile.username||'')+' · '+(profile.group||'');row.querySelector('[data-use]').onclick=()=>sonobusPost('/api/sonobus/profile/select',{id});row.querySelector('[data-delete]').onclick=()=>sonobusPost('/api/sonobus/profile/delete',{id});list.appendChild(row)})}}
async function sonobusRefresh(){if(sonobusUI.busy||document.hidden)return;try{sonobusRender(await sonobusJSON('/api/sonobus/state'))}catch(error){setStatus(error.name==='AbortError'?'Route status timed out':error.message)}}
async function sonobusPost(url,payload){if(sonobusUI.busy)return;sonobusUI.busy=true;try{const data=await sonobusJSON(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload||{})});if(data.state)sonobusRender(data.state);if(url==='/api/sonobus/preset')showTaskFeedback(data.message||'Routing updated','done')}catch(error){showTaskFeedback(error.message, 'error')}finally{sonobusUI.busy=false;sonobusRefresh()}}
document.querySelectorAll('[data-sonobus-preset]').forEach(button=>button.onclick=async()=>{
  if(sonobusUI.busy)return;
  const preset=button.dataset.sonobusPreset;
  document.querySelectorAll('[data-sonobus-preset]').forEach(item=>{
    item.classList.toggle('active',item===button);
    item.disabled=true;
  });
  button.setAttribute('aria-pressed','true');
  showTaskFeedback('Applying '+button.textContent.trim()+' destination…', 'working');
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
  showTaskFeedback('Restarting SonoBus…', 'working');
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
    showTaskFeedback(state&&state.sonobusRunning?'SonoBus restarted':'SonoBus restart sent', 'done');
  }catch(error){
    if(badge)badge.textContent=previousBadge||'SonoBus stopped';
    showTaskFeedback(error.message, 'error');
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
async function refreshVisiblePage(){if(document.hidden)return;await Promise.allSettled([refreshIPadState(),sonobusRefresh()])}
function scheduleRouteStatePoll(generation){clearTimeout(routeStateTimer);if(document.hidden||generation!==pageRefreshGeneration)return;routeStateTimer=setTimeout(async()=>{await sonobusRefresh();scheduleRouteStatePoll(generation)},2500)}
function startVisiblePolling(){pageRefreshGeneration+=1;const generation=pageRefreshGeneration;refreshVisiblePage();scheduleIPadStatePoll(generation);scheduleRouteStatePoll(generation)}
document.addEventListener('visibilitychange',()=>{if(document.hidden){pageRefreshGeneration+=1;clearTimeout(ipadStateTimer);clearTimeout(routeStateTimer);return}loadPlaylists();startVisiblePolling()});
// One floating control, visible only after scrolling in song lists.
const backToTop = document.querySelector('#back-to-top');
const backToTopScreens = [playlistScreen, document.querySelector('#all-songs-screen')];
function updateBackToTop() {
  const inSongList = backToTopScreens.some(screen => !screen.classList.contains('hidden'));
  backToTop.classList.toggle('hidden', !inSongList || window.scrollY < 420);
}
window.addEventListener('scroll', updateBackToTop, {passive: true});
for (const screen of backToTopScreens) {
  new MutationObserver(updateBackToTop).observe(screen, {attributes: true, attributeFilter: ['class']});
}
backToTop.addEventListener('click', () => {
  window.scrollTo({top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
});
updateBackToTop();

loadPlaylists();startVisiblePolling();

async function skipTen(target, delta) {
  const system = target === "system";
  const slider = system ? systemPlaybackSeek : playbackSeek;
  const current = Number(slider.value) || 0;
  const duration = Number(slider.max);
  const next = Math.max(0, Number.isFinite(duration) && duration > 0 ? Math.min(duration, current + delta) : current + delta);
  await readJSON(system ? "/api/system/seek" : "/api/seek", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({seconds:next})});
  slider.value = String(next);
  setTimeout(system ? updateSystemNowPlaying : updateNowPlaying, 120);
}
for (const button of document.querySelectorAll("[data-seek-delta]")) {
  button.addEventListener("click", async () => {
    button.disabled = true;
    try { await skipTen(button.dataset.seekTarget, Number(button.dataset.seekDelta)); }
    catch (error) { showTaskFeedback(error.message, "error"); }
    finally { button.disabled = false; }
  });
}


// Unified tactile and async feedback for every button.
document.addEventListener('pointerdown',event=>{const b=event.target.closest('button');if(b&&!b.disabled)b.classList.add('is-pressed')});
for(const name of ['pointerup','pointercancel','pointerleave'])document.addEventListener(name,event=>{const b=event.target.closest('button');if(b)b.classList.remove('is-pressed')});
