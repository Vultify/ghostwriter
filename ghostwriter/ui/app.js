"use strict";

// Ghostwriter app window. The Python side (ghostwriter/window.py) owns the files; this page only asks it to read
// and change them, through window.pywebview.api.

const app = document.getElementById("app");
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
const PAGE_SIZE = 200;
let state = null;
// What the History page is showing, and the last stamp seen, so new dictations show up while the window is open.
const shown = { query: "", app: "", limit: PAGE_SIZE, apps: "", stamp: null, summary: null, request: 0 };
// The welcome on a new install: which step it's on, and the download's progress over time for the time left.
const setup = { step: 1, status: {}, timer: null, samples: [] };

const api = () => window.pywebview.api;

window.addEventListener("pywebviewready", async () => {
  bindPage();
  render(await api().state());
  if (state.firstRun) startSetup();
  app.classList.add("loaded");
  renderDictionary(await api().dictionary());
  await watchHistory();
  setInterval(watchHistory, 1000);
});

darkQuery.addEventListener("change", () => state && applyTheme());

// Wiring that only needs doing once.
function bindPage() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });

  const windowActions = { minimize: "minimize", maximize: "toggle_maximize", close: "close" };
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => api()[windowActions[button.dataset.action]]());
  });

  document.querySelectorAll(".switch[data-setting]").forEach((button) => {
    button.addEventListener("click", () => change(button.dataset.setting, !state.settings[button.dataset.setting]));
  });

  document.querySelectorAll("select[data-setting='microphone']").forEach((select) => {
    select.addEventListener("change", async () => {
      await change("microphone", select.value || null);
      if (micTest.timer) startMicTest();  // switch the test over to the new mic
    });
  });

  document.getElementById("start-with-windows").addEventListener("click", async () => {
    render(await api().set_start_with_windows(!state.startWithWindows));
  });
  const styles = document.getElementById("sound-styles");
  styles.addEventListener("change", (event) => change("sound", event.target.value));
  styles.addEventListener("click", (event) => { if (event.target.matches("input")) api().preview_sound(event.target.value); });

  const meter = document.getElementById("mic-meter");
  meter.replaceChildren(...Array.from({ length: METER_BARS }, () => document.createElement("span")));
  document.getElementById("mic-test").addEventListener("click", () => (micTest.timer ? stopMicTest() : startMicTest()));
  document.getElementById("hands-free-minutes").addEventListener("change", (event) => {
    change("hands_free_minutes", Number(event.target.value));
  });

  document.getElementById("hotkeys").addEventListener("change", (event) => change("hotkey", event.target.value));
  document.getElementById("setup-hotkeys").addEventListener("change", (event) => change("hotkey", event.target.value));
  document.getElementById("themes").addEventListener("change", (event) => change("theme", event.target.value));

  const openers = { log: "open_log", folder: "open_folder" };
  document.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", () => api()[openers[button.dataset.open]]());
  });
  document.getElementById("open-dictionary-file").addEventListener("click", () => api().open_dictionary_file());

  document.getElementById("check-updates").addEventListener("click", checkForUpdates);

  document.getElementById("tab-words").addEventListener("click", () => showTab("words"));
  document.getElementById("tab-fixes").addEventListener("click", () => showTab("fixes"));
  document.getElementById("add-word").addEventListener("submit", addWord);
  document.getElementById("add-fix").addEventListener("submit", addFix);

  let typing = null;
  document.getElementById("history-search").addEventListener("input", (event) => {
    clearTimeout(typing);
    typing = setTimeout(() => showHistory({ query: event.target.value.trim() }), 150);
  });
  document.getElementById("history-filters").addEventListener("change", (event) => showHistory({ app: event.target.value }));
  document.getElementById("history-more").addEventListener("click", () => showHistory({ limit: shown.limit + PAGE_SIZE }));
  document.getElementById("history-on").addEventListener("click", () => change("history", true));
  document.getElementById("clear-history").addEventListener("click", askToClear);
  document.getElementById("clear-cancel").addEventListener("click", () => showClearQuestion(false));
  document.getElementById("clear-yes").addEventListener("click", clearHistory);

  document.getElementById("setup-back").addEventListener("click", () => showStep(setup.step - 1));
  document.getElementById("setup-next").addEventListener("click", () => (setup.step < 3 ? showStep(setup.step + 1) : finishSetup()));
}

async function change(name, value) {
  render(await api().set_setting(name, value));
}

function showView(name) {
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== name; });
  showClearQuestion(false);
  if (name !== "settings") stopMicTest();
  document.querySelectorAll(".nav[data-view]").forEach((button) => {
    if (button.dataset.view === name) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  document.querySelector("main").scrollTop = 0;
}

// Settings

function render(next) {
  state = next;
  const settings = state.settings;
  applyTheme();

  const text = { hotkey: settings.hotkey, version: `v${state.version}`, model: state.model, gpu: state.gpu, modelSize: `${state.modelSize} · downloaded` };
  document.querySelectorAll("[data-text]").forEach((node) => { node.textContent = text[node.dataset.text]; });

  document.querySelectorAll(".switch[data-setting]").forEach((button) => {
    button.setAttribute("aria-pressed", String(settings[button.dataset.setting]));
  });

  document.getElementById("hero-hint").textContent = settings.hands_free
    ? "Double tap for hands free. Tap once more to stop and paste."
    : "Hands free is off, so quick taps are simply ignored.";
  document.getElementById("tryit").placeholder = `Click in this box, hold ${settings.hotkey}, and say something…`;

  document.querySelectorAll("select[data-setting='microphone']").forEach((select) => fillMicrophones(select, settings.microphone));
  fillMinutes(settings);
  fillHotkeys("hotkeys", settings.hotkey);
  fillHotkeys("setup-hotkeys", settings.hotkey);
  document.querySelectorAll("#themes input").forEach((input) => { input.checked = input.value === settings.theme; });
  document.getElementById("history-off").hidden = settings.history;
  document.getElementById("setup-tip").hidden = !settings.hands_free;
  document.getElementById("start-with-windows").setAttribute("aria-pressed", String(state.startWithWindows));
  fillSoundStyles(settings);
  if (shown.summary) renderSummary(shown.summary);
}

function applyTheme() {
  const choice = state.settings.theme;
  app.dataset.theme = choice === "system" ? (darkQuery.matches ? "dark" : "light") : choice;
}

function fillMicrophones(select, chosen) {
  const options = [["", "Windows default"], ...state.microphones.map((name) => [name, name])];
  if (chosen && !state.microphones.includes(chosen)) options.push([chosen, `${chosen} (not connected)`]);
  select.replaceChildren(...options.map(([value, label]) => new Option(label, value)));
  select.value = chosen || "";
}

function fillMinutes(settings) {
  const select = document.getElementById("hands-free-minutes");
  select.replaceChildren(...state.handsFreeMinutes.map((minutes) => new Option(`${minutes} minutes`, String(minutes))));
  select.value = String(settings.hands_free_minutes);
  select.disabled = !settings.hands_free;
}

// Settings and the welcome each have a set of keycaps, with their own radio group named after the fieldset.
function fillHotkeys(id, chosen) {
  const fieldset = document.getElementById(id);
  const legend = fieldset.querySelector("legend");
  const caps = state.hotkeys.map((name) => {
    const input = Object.assign(document.createElement("input"), { type: "radio", name: id, value: name, checked: name === chosen });
    const cap = Object.assign(document.createElement("span"), { className: "keycap", textContent: name });
    const label = document.createElement("label");
    label.append(input, cap);
    return label;
  });
  fieldset.replaceChildren(legend, ...caps);
}

const SOUND_NOTES = {
  soft: "Soft, low bloops. Short, so they never step on your first word.",
  glass: "A struck-glass note. Press rings high, release answers lower, and it rings out a little.",
  bubble: "A round water-drop pop that bends up on press and down on release.",
  wood: "A warm marimba tap that sits under game audio instead of cutting through it.",
  tap: "A quiet keyboard-style click with a low thump. Barely there.",
  chime: "Two quick notes, rising on press and falling on release.",
};

// Picking a sound plays it, and so does clicking the one already picked. Built once, so arrow keys keep their place.
function fillSoundStyles(settings) {
  const fieldset = document.getElementById("sound-styles");
  if (!fieldset.querySelector("input")) {
    fieldset.append(...state.soundStyles.map((style) => {
      const label = document.createElement("label");
      label.append(Object.assign(document.createElement("input"), { type: "radio", name: "sound", value: style }),
        element("span", "choice", style[0].toUpperCase() + style.slice(1)));
      return label;
    }));
  }
  fieldset.querySelectorAll("input").forEach((input) => { input.checked = input.value === settings.sound; });
  fieldset.disabled = !settings.sounds;
  document.getElementById("sound-note").textContent = SOUND_NOTES[settings.sound];
}

// Mic test: opens the chosen mic and draws its level as bars that scroll left, newest on the right.

const METER_BARS = 24;
const MIC_TEST_SECONDS = 20;  // stops by itself, so the mic never stays open by accident
const micTest = { timer: null, levels: [], startedAt: 0, hint: null };

async function startMicTest() {
  stopMicTest();
  const button = document.getElementById("mic-test");
  const hint = document.getElementById("mic-hint");
  micTest.hint ??= hint.textContent;
  const opened = await api().start_mic_test();
  hint.textContent = opened ? micTest.hint : "Couldn't open that mic. Check that it's plugged in, or pick another one.";
  if (!opened) return;
  micTest.levels = [];
  micTest.startedAt = performance.now();
  micTest.timer = setInterval(drawMicLevel, 60);
  button.textContent = "Stop test";
  document.getElementById("mic-meter").classList.add("live");
}

function stopMicTest() {
  if (!micTest.timer) return;
  clearInterval(micTest.timer);
  micTest.timer = null;
  api().stop_mic_test();
  document.getElementById("mic-test").textContent = "Test mic";
  const meter = document.getElementById("mic-meter");
  meter.classList.remove("live");
  meter.querySelectorAll("span").forEach((bar) => { bar.style.height = ""; });
}

async function drawMicLevel() {
  if (performance.now() - micTest.startedAt > MIC_TEST_SECONDS * 1000) return stopMicTest();
  micTest.levels = [...micTest.levels, await api().mic_level()].slice(-METER_BARS);
  const bars = document.getElementById("mic-meter").children;
  const offset = METER_BARS - micTest.levels.length;
  micTest.levels.forEach((level, index) => { bars[offset + index].style.height = `${4 + Math.round(level * 24)}px`; });
}

// Dictionary

function showTab(name) {
  const words = name === "words";
  document.getElementById("tab-words").setAttribute("aria-selected", String(words));
  document.getElementById("tab-fixes").setAttribute("aria-selected", String(!words));
  document.getElementById("panel-words").hidden = !words;
  document.getElementById("panel-fixes").hidden = words;
}

function renderDictionary(entries) {
  document.getElementById("word-count").textContent = entries.words.length;
  document.getElementById("fix-count").textContent = entries.fixes.length;

  const words = entries.words.map((word) => {
    const chip = Object.assign(document.createElement("li"), { className: "chip" });
    chip.append(word, removeButton(`Remove ${word}`, () => editDictionary("remove_word", [word], "word-error")));
    return chip;
  });
  document.getElementById("word-list").replaceChildren(...words);
  document.getElementById("no-words").hidden = words.length > 0;

  const fixes = entries.fixes.map((fix) => {
    const row = Object.assign(document.createElement("li"), { className: "fix-row" });
    const heard = Object.assign(document.createElement("span"), { textContent: fix.heard });
    const arrow = Object.assign(document.createElement("span"), { className: "arrow", textContent: "→" });
    arrow.setAttribute("aria-label", "becomes");
    const write = Object.assign(document.createElement("span"), { className: "write", textContent: fix.write });
    row.append(heard, arrow, write, removeButton(`Remove the fix for ${fix.write}`, () => editDictionary("remove_fix", [fix.heard, fix.write], "fix-error")));
    return row;
  });
  document.getElementById("fix-list").replaceChildren(...fixes);
  document.getElementById("no-fixes").hidden = fixes.length > 0;
}

function removeButton(label, onClick) {
  const button = Object.assign(document.createElement("button"), { type: "button", className: "remove" });
  button.setAttribute("aria-label", label);
  button.innerHTML = '<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
  button.addEventListener("click", onClick);
  return button;
}

async function editDictionary(action, values, errorId) {
  const entries = await api()[action](...values);
  showError(errorId, entries.error);
  renderDictionary(entries);
  return !entries.error;
}

async function addWord(event) {
  event.preventDefault();
  const input = document.getElementById("new-word");
  if (await editDictionary("add_word", [input.value], "word-error")) input.value = "";
  input.focus();
}

async function addFix(event) {
  event.preventDefault();
  const heard = document.getElementById("new-heard");
  const write = document.getElementById("new-write");
  if (await editDictionary("add_fix", [heard.value, write.value], "fix-error")) {
    heard.value = "";
    write.value = "";
  }
  heard.focus();
}

function showError(id, message) {
  const node = document.getElementById(id);
  node.textContent = message || "";
  node.hidden = !message;
}

// History

const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
const dayFormat = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" });
const dayAndYearFormat = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
const COPY_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>';
const COPIED_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>';

// Checked every second; the stamp only changes when a dictation is saved or the history is cleared.
async function watchHistory() {
  if (document.hidden) return;
  const stamp = await api().history_stamp();
  if (stamp === shown.stamp) return;
  shown.stamp = stamp;
  renderSummary(await api().history_summary());
  await showHistory();
}

async function showHistory(changes = {}) {
  if ("query" in changes || "app" in changes) shown.limit = PAGE_SIZE;
  Object.assign(shown, changes);
  const request = ++shown.request;
  const result = await api().history(shown.query, shown.app, shown.limit);
  if (request !== shown.request) return;  // a newer search already started
  fillFilters(result.apps);
  renderHistory(result);
}

function renderSummary(summary) {
  shown.summary = summary;
  document.getElementById("words-today").textContent = summary.words_today.toLocaleString();
  document.getElementById("dictations-today").textContent = summary.dictations_today.toLocaleString();
  document.getElementById("words-month").textContent = summary.words_month.toLocaleString();
  document.getElementById("recent-list").replaceChildren(...summary.recent.map((item) => entry(item, true)));
  const empty = document.getElementById("recent-empty");
  empty.hidden = summary.recent.length > 0;
  empty.textContent = state.settings.history
    ? `Nothing yet. Hold ${state.settings.hotkey}, talk, and it shows up here.`
    : "History is off, so dictations aren't saved. Turn it on in Settings.";
  document.getElementById("clear-history").disabled = summary.total === 0;
}

function fillFilters(apps) {
  const choices = shown.app && !apps.includes(shown.app) ? [...apps, shown.app] : apps;
  if (choices.join("\n") === shown.apps) return;  // rebuilding would lose keyboard focus
  shown.apps = choices.join("\n");
  const fieldset = document.getElementById("history-filters");
  const legend = fieldset.querySelector("legend");
  const filters = [["", "All"], ...choices.map((name) => [name, name])].map(([value, label]) => {
    const input = Object.assign(document.createElement("input"), { type: "radio", name: "history-app", value, checked: value === shown.app });
    const wrapper = document.createElement("label");
    wrapper.append(input, element("span", "filter", label));
    return wrapper;
  });
  fieldset.replaceChildren(legend, ...filters);
}

function renderHistory(result) {
  const days = [];
  for (const item of result.items) {
    const label = dayLabel(new Date(item.at));
    if (days.at(-1)?.label !== label) days.push({ label, list: element("ul", "entries") });
    days.at(-1).list.append(entry(item, false));
  }
  document.getElementById("history-days").replaceChildren(...days.flatMap((day) => [element("h2", "day", day.label), day.list]));
  const empty = document.getElementById("history-empty");
  empty.hidden = result.items.length > 0;
  empty.textContent = shown.query || shown.app ? "Nothing matches." : "Nothing here yet. Your dictations show up here as you make them.";
  document.getElementById("history-more").hidden = result.total <= result.items.length;
}

// One dictation: Home's short version shows the time, the first line, and the app; History's shows it all.
function entry(item, short) {
  const row = element("li", short ? "entry short" : "entry");
  const when = element("div", "entry-when mono");
  when.append(element("span", "", timeFormat.format(new Date(item.at))));
  if (!short) when.append(element("span", "faint", clockLength(item.seconds)));
  const body = element("div", "entry-body");
  const about = element("div", "entry-about");
  if (short) {
    about.append(element("span", "", item.app));
  } else {
    about.append(element("span", "app-tag", item.app), element("span", "", `${item.words.toLocaleString()} ${item.words === 1 ? "word" : "words"}`));
  }
  body.append(element("p", "entry-text", item.text), about);
  row.append(when, body, copyButton(item.text));
  return row;
}

function copyButton(text) {
  const button = element("button", "icon-button");
  button.type = "button";
  button.title = "Copy";
  button.setAttribute("aria-label", "Copy");
  button.innerHTML = COPY_ICON;
  button.addEventListener("click", async () => {
    await navigator.clipboard.writeText(text);
    button.innerHTML = COPIED_ICON;
    button.classList.add("copied");
    button.setAttribute("aria-label", "Copied");
    setTimeout(() => {
      button.innerHTML = COPY_ICON;
      button.classList.remove("copied");
      button.setAttribute("aria-label", "Copy");
    }, 1200);
  });
  return button;
}

function askToClear() {
  const total = shown.summary.total;
  document.getElementById("clear-question").textContent = total === 1 ? "Delete your 1 dictation?" : `Delete all ${total.toLocaleString()} dictations?`;
  showClearQuestion(true);
  document.getElementById("clear-cancel").focus();
}

function showClearQuestion(asking) {
  document.getElementById("clear-history").hidden = asking;
  document.getElementById("clear-confirm").hidden = !asking;
}

async function clearHistory() {
  await api().clear_history();
  showClearQuestion(false);
  await watchHistory();
}

function dayLabel(date) {
  const day = new Date(date).setHours(0, 0, 0, 0);
  const daysAgo = Math.round((new Date().setHours(0, 0, 0, 0) - day) / 86400000);
  if (daysAgo === 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  return (date.getFullYear() === new Date().getFullYear() ? dayFormat : dayAndYearFormat).format(date);
}

function clockLength(seconds) {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// First run

const DOWNLOAD_TEXT = {
  downloading: ["Getting the speech model", "A one-time 1.6 GB download. After this, Ghostwriter never needs the internet to hear you."],
  loading: ["Setting it up", "Loading the speech model onto your graphics card. This takes a few seconds."],
  ready: ["Ready to go", "The speech model is on this PC now, so nothing you say ever needs the internet."],
  failed: ["The download stopped", "Check your internet connection, then start Ghostwriter again from the Start menu. It picks up where it left off."],
};

function startSetup() {
  app.classList.add("in-setup");
  document.getElementById("window-title").textContent = "Ghostwriter setup";
  showStep(1);
  watchDownload();
  setup.timer = setInterval(watchDownload, 500);
}

function finishSetup() {
  clearInterval(setup.timer);
  app.classList.remove("in-setup");
  document.getElementById("window-title").textContent = "Ghostwriter";
  showView("home");
}

function showStep(step) {
  setup.step = step;
  document.querySelectorAll(".setup-step").forEach((section) => { section.hidden = Number(section.dataset.step) !== step; });
  document.querySelectorAll("#steps span").forEach((dot, index) => {
    dot.className = index + 1 === step ? "current" : index + 1 < step ? "done" : "";
  });
  document.getElementById("steps").setAttribute("aria-label", `Step ${step} of 3`);
  document.getElementById("setup-back").hidden = step === 1;
  const next = document.getElementById("setup-next");
  next.textContent = ["Continue", "Next", "Finish"][step - 1];
  next.disabled = step === 1 && setup.status.model !== "ready";
  if (step === 3) document.getElementById("setup-try").focus();
}

// The tray app saves its progress a few times a second; this follows it until the model is ready.
async function watchDownload() {
  const status = await api().startup_status();
  if (!DOWNLOAD_TEXT[status.model]) return;  // caught mid-write; the next check will have it
  setup.status = status;
  renderDownload(status);
  if (setup.step === 1) document.getElementById("setup-next").disabled = status.model !== "ready";
  if (status.model === "ready") clearInterval(setup.timer);
}

function renderDownload(status) {
  const [title, text] = DOWNLOAD_TEXT[status.model];
  document.getElementById("download-title").textContent = title;
  document.getElementById("download-text").textContent = text;
  const downloading = status.model === "downloading";
  const bar = document.getElementById("download-bar");
  bar.classList.toggle("stopped", status.model === "failed");
  if (status.model !== "failed") {
    const fraction = downloading ? (status.total ? status.done / status.total : 0) : 1;
    bar.firstElementChild.style.width = `${fraction * 100}%`;
    bar.setAttribute("aria-valuenow", String(Math.round(fraction * 100)));
  }
  const amount = {
    downloading: status.total ? `${gigabytes(status.done)} of ${gigabytes(status.total)} GB` : "Starting…",
    loading: "Downloaded",
    ready: "Downloaded",
    failed: "Stopped",
  };
  document.getElementById("download-amount").textContent = amount[status.model];
  document.getElementById("download-left").textContent = downloading ? timeLeft(status) : status.model === "loading" ? "Loading…" : "";
}

// Estimated from the last ten seconds, so it settles quickly and follows changes in speed.
function timeLeft(status) {
  const now = performance.now();
  setup.samples.push([now, status.done]);
  while (setup.samples.length > 2 && now - setup.samples[0][0] > 10000) setup.samples.shift();
  const [since, doneThen] = setup.samples[0];
  const rate = (status.done - doneThen) / ((now - since) / 1000);
  if (now - since < 2000 || rate <= 0) return "";
  const seconds = (status.total - status.done) / rate;
  return seconds < 60 ? "less than a minute left" : `about ${Math.round(seconds / 60)} min left`;
}

function gigabytes(bytes) {
  return (bytes / 1e9).toFixed(1);
}

// Updates

async function checkForUpdates() {
  const note = document.getElementById("update-note");
  note.hidden = false;
  note.replaceChildren("Checking…");
  const result = await api().check_for_updates();
  const messages = {
    current: "You're up to date.",
    git: "This copy is a git checkout, so it updates with git pull.",
    error: "Couldn't check. Check your internet connection and try again.",
  };
  if (result.status !== "available") {
    note.replaceChildren(messages[result.status]);
    return;
  }
  const update = Object.assign(document.createElement("button"), { type: "button", textContent: "Update now" });
  update.addEventListener("click", () => {
    note.replaceChildren("Updating. Ghostwriter will close and start again.");
    api().start_update();
  });
  note.replaceChildren(`Version ${result.latest} is available.`, document.createElement("br"), update);
}
