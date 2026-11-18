"use strict";

// Ghostwriter app window. The Python side (ghostwriter/window.py) owns the files; this page only asks it to read
// and change them, through window.pywebview.api.

const app = document.getElementById("app");
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
let state = null;
// What the History page is showing, and the last stamp and day seen, so new dictations and a new day show up while
// the window is open. The limit is set from state.pageSize once the first state arrives.
const shown = { query: "", app: "", limit: 0, apps: "", stamp: null, day: null, summary: null, request: 0 };
// The welcome on a new install: which step it's on, and the download's progress over time for the time left.
const setup = { step: 1, status: {}, timer: null, samples: [] };

const api = () => window.pywebview.api;

window.addEventListener("pywebviewready", async () => {
  bindPage();
  render(await api().state());
  shown.limit = state.pageSize;
  if (state.firstRun) startSetup();
  else watchEngine();  // in case an engine switch is still going
  app.classList.add("loaded");
  renderDictionary(await api().dictionary());
  await watchHistory();
  watchSettings.stamp = await api().settings_stamp();
  setInterval(watchHistory, 1000);
  setInterval(watchSettings, 1000);
});

// The tray menu can change settings while the window is open; this keeps the page in step with it.
async function watchSettings() {
  if (document.hidden) return;
  const stamp = await api().settings_stamp();
  if (stamp === watchSettings.stamp) return;
  watchSettings.stamp = stamp;
  render(await api().state());
}

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
      if (micTest.where) startMicTest(micTest.where);  // switch the test over to the new mic
    });
  });

  document.getElementById("start-at-login").addEventListener("click", async () => {
    render(await api().set_start_at_login(!state.startAtLogin));
  });
  document.getElementById("engines").addEventListener("change", async (event) => {
    await change("engine", event.target.value);
    watchEngine(true);
  });
  const styles = document.getElementById("sound-styles");
  styles.addEventListener("change", (event) => change("sound", event.target.value));
  styles.addEventListener("click", (event) => { if (event.target.matches("input")) api().preview_sound(event.target.value); });

  for (const [where, test] of Object.entries(MIC_TESTS)) {
    document.getElementById(test.meter).replaceChildren(...Array.from({ length: test.bars }, () => document.createElement("span")));
    document.getElementById(test.button).addEventListener("click", () => (micTest.where === where ? stopMicTest() : startMicTest(where)));
  }
  restWave();
  document.getElementById("hands-free-minutes").addEventListener("change", (event) => {
    change("hands_free_minutes", Number(event.target.value));
  });
  document.getElementById("other-sounds").addEventListener("change", (event) => {
    change("other_sounds", Number(event.target.value));
  });

  document.getElementById("hotkeys").addEventListener("change", (event) => change("hotkey", event.target.value));
  document.getElementById("setup-hotkeys").addEventListener("change", (event) => change("hotkey", event.target.value));
  document.getElementById("themes").addEventListener("change", (event) => change("theme", event.target.value));

  const openers = { log: "open_log", folder: "open_folder" };
  document.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", () => api()[openers[button.dataset.open]]());
  });
  document.getElementById("open-dictionary-file").addEventListener("click", () => api().open_dictionary_file());
  const importExport = document.getElementById("import-export");
  importExport.addEventListener("click", () => openMenu(importExport, [
    { label: "Import from a file…", choose: () => dictionaryFile("import_dictionary") },
    { label: "Export to a file…", choose: () => dictionaryFile("export_dictionary") },
  ]));

  document.getElementById("check-updates").addEventListener("click", checkForUpdates);

  document.getElementById("tab-words").addEventListener("click", () => showTab("words"));
  document.getElementById("tab-fixes").addEventListener("click", () => showTab("fixes"));
  document.getElementById("add-word").addEventListener("submit", addWord);
  document.getElementById("add-fix").addEventListener("submit", addFix);
  document.getElementById("dictionary-search").addEventListener("input", (event) => {
    dictionaryView.query = event.target.value.trim().toLowerCase();
    renderEntries();
  });
  document.getElementById("dictionary-sort").addEventListener("change", (event) => {
    dictionaryView.sort = event.target.value;
    renderEntries();
  });

  let typing = null;
  document.getElementById("history-search").addEventListener("input", (event) => {
    clearTimeout(typing);
    typing = setTimeout(() => showHistory({ query: event.target.value.trim() }), 150);
  });
  document.getElementById("history-filters").addEventListener("change", (event) => showHistory({ app: event.target.value }));
  document.getElementById("history-more").addEventListener("click", () => showHistory({ limit: shown.limit + state.pageSize }));
  document.getElementById("history-on").addEventListener("click", () => change("history", true));
  document.getElementById("clear-history").addEventListener("click", askToClear);
  document.getElementById("clear-cancel").addEventListener("click", () => showClearQuestion(false));
  document.getElementById("clear-yes").addEventListener("click", clearHistory);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
    if (event.ctrlKey && event.key.toLowerCase() === "f" && !document.getElementById("history").hidden) {
      event.preventDefault();
      document.getElementById("history-search").focus();
    }
  });
  document.addEventListener("click", (event) => { if (!event.target.closest(".menu, [data-menu]")) closeMenu(); });
  document.querySelector("main").addEventListener("scroll", closeMenu);

  document.getElementById("setup-back").addEventListener("click", () => showStep(setup.step - 1));
  document.getElementById("setup-next").addEventListener("click", () => (setup.step < 3 ? showStep(setup.step + 1) : finishSetup()));
}

async function change(name, value) {
  render(await api().set_setting(name, value));
}

function showView(name) {
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== name; });
  showClearQuestion(false);
  closeMenu();
  stopMicTest();
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
  app.classList.toggle("system-frame", !state.ownFrame);  // the desktop draws the frame
  applyTheme();

  const text = { hotkey: settings.hotkey, version: `v${state.version}`, model: state.model, gpu: state.gpu,
    system: state.system, modelSize: `${state.modelSize} · ${state.modelDownloaded ? "downloaded" : "downloading"}` };
  document.querySelectorAll("[data-text]").forEach((node) => { node.textContent = text[node.dataset.text]; });

  document.querySelectorAll(".switch[data-setting]").forEach((button) => {
    button.setAttribute("aria-pressed", String(settings[button.dataset.setting]));
  });

  document.getElementById("hero-hint").textContent = settings.hands_free
    ? "Double tap for hands free. Tap once more to stop and paste."
    : "Hands free is off, so quick taps are simply ignored.";
  const style = settings.sound[0].toUpperCase() + settings.sound.slice(1);
  document.getElementById("quick-sound-hint").textContent = `${style} on start and stop`;

  document.querySelectorAll("select[data-setting='microphone']").forEach((select) => fillMicrophones(select, settings.microphone));
  fillMinutes(settings);
  fillOtherSounds(settings);
  fillHotkeys("hotkeys", settings.hotkey);
  fillHotkeys("setup-hotkeys", settings.hotkey);
  document.querySelectorAll("#themes input").forEach((input) => { input.checked = input.value === settings.theme; });
  document.getElementById("history-off").hidden = settings.history;
  document.getElementById("setup-tip").hidden = !settings.hands_free;
  document.getElementById("start-at-login-label").textContent = `Start with ${state.system}`;
  document.getElementById("start-at-login").setAttribute("aria-pressed", String(state.startAtLogin));
  fillSoundStyles(settings);
  fillEngines();
  showStatus(state.status);
  if (shown.summary) renderSummary(shown.summary);
}

// The sidebar card: whether dictation is ready, and what it runs on.
function showStatus(status) {
  const words = { downloading: "Downloading", loading: "Starting", failed: "Couldn't start" };
  // During an engine switch the old engine keeps dictating, so only loading at startup counts here.
  const word = (!status.running && words[status.model]) || "Ready";
  document.getElementById("status-word").textContent = word;
  const badge = document.getElementById("hero-status");
  badge.textContent = word;
  badge.className = word === "Ready" ? "badge" : status.model === "failed" ? "badge failed" : "badge busy";
  const where = state.gpu.startsWith("Your ") ? state.gpu[0].toLowerCase() + state.gpu.slice(1) : state.gpu;
  document.getElementById("status-text").textContent = `Runs offline on ${where}. Nothing leaves this PC.`;
}

// Only PCs with an NVIDIA card have a choice; everywhere else whisper.cpp is the one engine that runs.
function fillEngines() {
  const fieldset = document.getElementById("engines");
  if (!fieldset.querySelector("input")) {
    fieldset.append(...state.engines.map((engine) => {
      const label = document.createElement("label");
      label.append(Object.assign(document.createElement("input"), { type: "radio", name: "engine", value: engine }),
        element("span", "choice", engine));
      return label;
    }));
  }
  fieldset.querySelectorAll("input").forEach((input) => { input.checked = input.value === state.engine; });
  fieldset.hidden = state.engines.length < 2;
  document.getElementById("engine-hint").hidden = state.engines.length < 2;
}

// While the tray app switches engines it reports progress in startup.json; this shows it until the new one is ready.
// Right after a pick, it allows a few seconds for the tray app to notice the new setting.
async function watchEngine(picked = false) {
  clearTimeout(watchEngine.timer);
  if (picked) watchEngine.pickedAt = performance.now();
  const status = await api().startup_status();
  const line = document.getElementById("engine-status");
  const current = status.engine === state.engine;
  const noticing = !current && performance.now() - (watchEngine.pickedAt ?? -Infinity) < 10000;
  const busy = current && (status.model === "downloading" || status.model === "loading");
  const failed = current && status.model === "failed";
  const messages = {
    downloading: status.total ? `Downloading the ${state.engine} model: ${gigabytes(status.done)} of ${gigabytes(status.total)} GB` : `Downloading the ${state.engine} model…`,
    loading: `Loading ${state.engine}…`,
    failed: `Couldn't switch to ${state.engine}. Details are in the log.`,
  };
  line.hidden = !(noticing || busy || failed);
  line.textContent = noticing ? `Switching to ${state.engine}…` : messages[status.model] || "";
  line.classList.toggle("failed", failed);
  if (noticing || busy) {
    watchEngine.watching = true;
    watchEngine.timer = setTimeout(watchEngine, 500);
  } else if (watchEngine.watching) {
    watchEngine.watching = false;
    watchEngine.pickedAt = null;
    if (current && status.model === "ready") render(await api().state());  // picks up which graphics it runs on
  }
  showStatus(status);
}

function applyTheme() {
  const choice = state.settings.theme;
  app.dataset.theme = choice === "system" ? (darkQuery.matches ? "dark" : "light") : choice;
}

function fillMicrophones(select, chosen) {
  const options = [["", `${state.system} default`], ...state.microphones.map((name) => [name, name])];
  if (chosen && !state.microphones.includes(chosen)) options.push([chosen, `${chosen} (not connected)`]);
  select.replaceChildren(...options.map(([value, label]) => new Option(label, value)));
  select.value = chosen || "";
}

// How loud other apps play while you talk: 100 leaves them be, 0 mutes them.
function fillOtherSounds(settings) {
  const label = (percent) => (percent === 100 ? "Keep playing" : percent === 0 ? "Mute" : `Lower to ${percent}%`);
  const select = document.getElementById("other-sounds");
  select.replaceChildren(...state.otherSounds.map((percent) => new Option(label(percent), String(percent))));
  select.value = String(settings.other_sounds);
}

function fillMinutes(settings) {
  const select = document.getElementById("hands-free-minutes");
  select.replaceChildren(...state.handsFreeMinutes.map((minutes) => new Option(`${minutes} minutes`, String(minutes))));
  select.value = String(settings.hands_free_minutes);
  select.disabled = !settings.hands_free;
}

// Settings and the welcome each have a set of keycaps, with their own radio group named after the fieldset. Built
// once, so arrow keys keep their place.
function fillHotkeys(id, chosen) {
  const fieldset = document.getElementById(id);
  if (!fieldset.querySelector("input")) {
    fieldset.append(...state.hotkeys.map((name) => {
      const label = document.createElement("label");
      label.append(Object.assign(document.createElement("input"), { type: "radio", name: id, value: name }),
        Object.assign(document.createElement("span"), { className: "keycap", textContent: name }));
      return label;
    }));
  }
  fieldset.querySelectorAll("input").forEach((input) => { input.checked = input.value === chosen; });
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
  document.getElementById("sound-note").textContent = SOUND_NOTES[settings.sound] ?? "";
}

// Mic test: opens the chosen mic and draws its level, newest on the right. Home draws it as a wave that rests in
// its usual shape; Settings as a row of bars.

const MIC_TESTS = {
  home: { button: "home-mic-test", meter: "home-meter", bars: 27 },
  settings: { button: "mic-test", meter: "mic-meter", bars: 24 },
};
const WAVE_SHAPE = [6, 9, 12, 9, 14, 11, 9, 16, 22, 30, 38, 46, 34, 54, 34, 46, 38, 30, 22, 16, 9, 11, 14, 9, 12, 9, 6];
const MIC_TEST_SECONDS = 20;  // stops by itself, so the mic never stays open by accident
const micTest = { where: null, timer: null, levels: [], startedAt: 0, hint: null };

async function startMicTest(where) {
  stopMicTest();
  const hint = document.getElementById("mic-hint");
  micTest.hint ??= hint.textContent;
  const opened = await api().start_mic_test();
  hint.textContent = opened ? micTest.hint : "Couldn't open that mic. Check that it's plugged in, or pick another one.";
  if (!opened) return;
  const test = MIC_TESTS[where];
  Object.assign(micTest, { where, levels: [], startedAt: performance.now(), timer: setInterval(drawMicLevel, 60) });
  buttonLabel(test.button).textContent = "Stop test";
  document.getElementById(test.meter).classList.add("live");
}

function stopMicTest() {
  if (!micTest.timer) return;
  clearInterval(micTest.timer);
  const test = MIC_TESTS[micTest.where];
  Object.assign(micTest, { where: null, timer: null });
  api().stop_mic_test();
  buttonLabel(test.button).textContent = "Test mic";
  const meter = document.getElementById(test.meter);
  meter.classList.remove("live");
  meter.querySelectorAll("span").forEach((bar) => { bar.style.height = ""; });
  restWave();
}

function buttonLabel(id) {
  const button = document.getElementById(id);
  return button.querySelector("span") ?? button;
}

function restWave() {
  [...document.getElementById("home-meter").children].forEach((bar, index) => { bar.style.height = `${WAVE_SHAPE[index]}px`; });
}

async function drawMicLevel() {
  if (performance.now() - micTest.startedAt > MIC_TEST_SECONDS * 1000) return stopMicTest();
  const where = micTest.where;
  const test = MIC_TESTS[where];
  const level = await api().mic_level();
  if (micTest.where !== where) return;  // stopped while the level was on its way
  micTest.levels = [...micTest.levels, level].slice(-test.bars);
  const bars = document.getElementById(test.meter).children;
  const offset = test.bars - micTest.levels.length;
  const reach = where === "home" ? 56 : 24;
  micTest.levels.forEach((value, index) => { bars[offset + index].style.height = `${4 + Math.round(value * reach)}px`; });
}

// Dictionary

// What the Dictionary page shows: which tab, the search, the sort, and the entry being changed, if any.
const dictionaryView = { entries: { words: [], fixes: [] }, tab: "words", query: "", sort: "az", editing: null };
const addedFormat = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" });
const BOOK_ICON = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 5.5C5 4.5 8.5 4.5 12 6.5c3.5-2 7-2 9-1V19c-2-1-5.5-1-9 1-3.5-2-7-2-9-1z"/><path d="M12 6.5V20"/></svg>';
const SWAP_ICON = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 8h14"/><path d="M14 4l4 4-4 4"/><path d="M20 16H6"/><path d="M10 12l-4 4 4 4"/></svg>';
const PENCIL_ICON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/></svg>';
const TRASH_ICON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/><path d="M9 7V4h6v3"/></svg>';

function showTab(name) {
  dictionaryView.tab = name;
  dictionaryView.editing = null;
  const isWords = name === "words";
  document.getElementById("tab-words").setAttribute("aria-selected", String(isWords));
  document.getElementById("tab-fixes").setAttribute("aria-selected", String(!isWords));
  document.getElementById("word-panel").hidden = !isWords;
  document.getElementById("fix-panel").hidden = isWords;
  document.getElementById("dictionary-search").placeholder = isWords ? "Search words…" : "Search fixes…";
  renderEntries();
}

function renderDictionary(entries) {
  dictionaryView.entries = entries;
  document.getElementById("word-count").textContent = entries.words.length;
  document.getElementById("fix-count").textContent = entries.fixes.length;
  renderEntries();
}

// Both lists, searched and sorted, with the heading and column names of the open tab. Fixes are matched on both
// what it hears and what it writes.
function renderEntries() {
  const isWords = dictionaryView.tab === "words";
  const shownWords = listEntries(dictionaryView.entries.words, true);
  const shownFixes = listEntries(dictionaryView.entries.fixes, false);
  document.getElementById("word-panel").replaceChildren(...shownWords.map((entry) => row(entry, true)));
  document.getElementById("fix-panel").replaceChildren(...shownFixes.map((entry) => row(entry, false)));

  const all = isWords ? dictionaryView.entries.words : dictionaryView.entries.fixes;
  document.getElementById("list-title").textContent = `${isWords ? "Your words" : "Your fixes"} (${all.length})`;
  const head = document.getElementById("table-head");
  head.className = `table-head ${isWords ? "words" : "fixes"}`;
  head.replaceChildren(...(isWords ? ["", "Word", "Type", "Added", ""] : ["", "When it hears", "", "Write", "Type", "Added", ""])
    .map((label) => element("span", "", label)));
  const empty = document.getElementById("no-entries");
  empty.hidden = (isWords ? shownWords : shownFixes).length > 0;
  empty.textContent = all.length
    ? "Nothing matches."
    : isWords ? "No words yet. Add names or terms Whisper should spell your way." : "No fixes yet. Add one when Whisper keeps writing a word the wrong way.";
}

function listEntries(entries, isWords) {
  const text = (entry) => (isWords ? entry.text : `${entry.heard} ${entry.write}`).toLowerCase();
  const name = (entry) => (isWords ? entry.text : entry.write);
  const order = {
    az: (a, b) => name(a).localeCompare(name(b), undefined, { sensitivity: "base" }),
    za: (a, b) => name(b).localeCompare(name(a), undefined, { sensitivity: "base" }),
    new: (a, b) => b.added.localeCompare(a.added),
    old: (a, b) => a.added.localeCompare(b.added),
  }[dictionaryView.sort];
  return entries.filter((entry) => text(entry).includes(dictionaryView.query)).sort(order);
}

function row(entry, isWords) {
  return dictionaryView.editing === entry ? editRow(entry, isWords) : entryRow(entry, isWords);
}

function entryRow(entry, isWords) {
  const row = element("li", `dict-row ${isWords ? "words" : "fixes"}`);
  const icon = element("span", "dict-icon");
  icon.innerHTML = isWords ? BOOK_ICON : SWAP_ICON;
  row.append(icon);
  if (isWords) {
    row.append(element("span", "dict-word", entry.text));
  } else {
    const arrow = element("span", "arrow", "→");
    arrow.setAttribute("aria-label", "becomes");
    row.append(element("span", "dict-heard", entry.heard), arrow, element("span", "dict-word", entry.write));
  }
  const label = isWords ? entry.text : `the fix for ${entry.write}`;
  const change = iconButton("row-button", `Change ${label}`, PENCIL_ICON);
  change.addEventListener("click", () => { dictionaryView.editing = entry; renderEntries(); });
  const remove = iconButton("row-button remove", `Remove ${label}`, TRASH_ICON);
  remove.addEventListener("click", () => (isWords
    ? editDictionary("remove_word", [entry.text], "word-error")
    : editDictionary("remove_fix", [entry.heard, entry.write], "fix-error")));
  row.append(element("span", "type-badge", isWords ? "Word" : "Fix"), element("span", "added", addedDay(entry.added)), change, remove);
  return row;
}

// A row being changed: its text in boxes, saved with Enter or the button, and left alone with Escape.
function editRow(entry, isWords) {
  const row = element("li", `dict-row editing ${isWords ? "words" : "fixes"}`);
  const form = element("form", "edit-form");
  const box = (value, label) => {
    const input = Object.assign(document.createElement("input"), { className: "text-input", value, spellcheck: false, autocomplete: "off" });
    input.setAttribute("aria-label", label);
    return input;
  };
  const inputs = isWords ? [box(entry.text, "Word")] : [box(entry.heard, "When it hears"), box(entry.write, "Write")];
  const save = Object.assign(element("button", "button primary", "Save"), { type: "submit" });
  const cancel = Object.assign(element("button", "button", "Cancel"), { type: "button" });
  const stop = () => { dictionaryView.editing = null; renderEntries(); };
  cancel.addEventListener("click", stop);
  form.addEventListener("keydown", (event) => { if (event.key === "Escape") { event.stopPropagation(); stop(); } });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = inputs.map((input) => input.value);
    const saved = isWords
      ? await editDictionary("change_word", [entry.text, ...values], "word-error")
      : await editDictionary("change_fix", [entry.heard, entry.write, ...values], "fix-error");
    if (saved) stop();
  });
  if (isWords) form.append(inputs[0]);
  else form.append(inputs[0], element("span", "arrow", "→"), inputs[1]);
  form.append(save, cancel);
  row.append(form);
  requestAnimationFrame(() => inputs[0].focus());
  return row;
}

function addedDay(day) {
  const [year, month, date] = day.split("-").map(Number);
  return addedFormat.format(new Date(year, month - 1, date));
}

async function editDictionary(action, values, errorId) {
  const entries = await api()[action](...values);
  showError(errorId, entries.error);
  if (entries.error) dictionaryView.editing = null;
  renderDictionary(entries);
  return !entries.error;
}

async function addWord(event) {
  event.preventDefault();
  const input = document.getElementById("new-word");
  if (await editDictionary("add_word", [input.value], "word-error")) {
    input.value = "";
    if (dictionaryView.tab !== "words") showTab("words");
  }
  input.focus();
}

async function addFix(event) {
  event.preventDefault();
  const heard = document.getElementById("new-heard");
  const write = document.getElementById("new-write");
  if (await editDictionary("add_fix", [heard.value, write.value], "fix-error")) {
    heard.value = "";
    write.value = "";
    if (dictionaryView.tab !== "fixes") showTab("fixes");
  }
  heard.focus();
}

async function dictionaryFile(action) {
  const result = await api()[action]();
  if (result.words) renderDictionary(result);
  const note = document.getElementById("dictionary-note");
  note.textContent = result.message || "";
  note.hidden = !result.message;
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
const DOTS_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>';
const CALENDAR_ICON = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17"/><path d="M8 3v4"/><path d="M16 3v4"/></svg>';
const COPY_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>';
const COPIED_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>';

const icons = new Map();  // app name to its icon's data URL, or null for none

async function loadIcons(items) {
  const missing = [...new Set(items.map((item) => item.app))].filter((name) => !icons.has(name));
  if (!missing.length) return;
  const found = await api().app_icons(missing);
  missing.forEach((name) => icons.set(name, found[name] ?? null));
}

const GHOST_ICON = '<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path class="ghost-mark" d="M4 11a8 8 0 0 1 16 0v10l-2.67-1.8L14.67 21 12 19.2 9.33 21l-2.66-1.8L4 21z"/><circle class="ghost-eye" cx="9.5" cy="10.5" r="1.4"/><circle class="ghost-eye" cx="14.5" cy="10.5" r="1.4"/></svg>';

function appIcon(name) {
  if (name === "Ghostwriter") {
    const ghost = element("span", "app-icon ghost");
    ghost.innerHTML = GHOST_ICON;
    return ghost;
  }
  const url = icons.get(name);
  if (url) return Object.assign(document.createElement("img"), { className: "app-icon", src: url, alt: "" });
  const letter = element("span", "app-icon letter");
  letter.dataset.letter = (name.trim()[0] ?? "?").toUpperCase();  // drawn by the stylesheet, so it isn't in the text
  letter.setAttribute("aria-hidden", "true");
  return letter;
}

function appTag(name) {
  const tag = element("span", "app-tag");
  tag.append(appIcon(name), element("span", "", name));
  return tag;
}

// Checked every second; the stamp only changes when a dictation is saved or the history is cleared, and the day is
// checked too so "today" moves on at midnight.
async function watchHistory() {
  if (document.hidden) return;
  const stamp = await api().history_stamp();
  const day = new Date().toDateString();
  if (stamp === shown.stamp && day === shown.day) return;
  Object.assign(shown, { stamp, day });
  // A new dictation may have brought an app's first icon, so ask again for the ones that had none.
  icons.forEach((url, name) => { if (url === null) icons.delete(name); });
  const summary = await api().history_summary();
  await loadIcons(summary.recent);
  renderSummary(summary);
  await showHistory();
}

async function showHistory(changes = {}) {
  if ("query" in changes || "app" in changes) shown.limit = state.pageSize;
  Object.assign(shown, changes);
  const request = ++shown.request;
  const result = await api().history(shown.query, shown.app, shown.limit);
  if (request !== shown.request) return;  // a newer search already started
  await loadIcons([...result.items, ...result.apps.map((app) => ({ app }))]);
  fillFilters(result.apps);
  renderHistory(result);
}

function renderSummary(summary) {
  shown.summary = summary;
  document.getElementById("words-today").textContent = summary.words_today.toLocaleString();
  document.getElementById("dictations-today").textContent = summary.dictations_today.toLocaleString();
  document.getElementById("words-month").textContent = summary.words_month.toLocaleString();
  document.getElementById("total-dictations").textContent = summary.total.toLocaleString();
  document.getElementById("total-words").textContent = summary.total_words.toLocaleString();
  document.getElementById("history-range").textContent = historyRange(summary.first);
  document.getElementById("recent-list").replaceChildren(...summary.recent.map((item) => entry(item, true)));
  const empty = document.getElementById("recent-empty");
  empty.hidden = summary.recent.length > 0;
  empty.textContent = state.settings.history
    ? `Nothing yet. Hold ${state.settings.hotkey}, talk, and it shows up here.`
    : "History is off, so dictations aren't saved. Turn it on in Settings.";
  document.getElementById("clear-history").disabled = summary.total === 0;
}

function fillFilters(apps) {
  const buttons = apps.slice(0, state.filterApps);
  if (shown.app && !buttons.includes(shown.app)) buttons.push(shown.app);
  const more = apps.filter((name) => !buttons.includes(name));
  const key = [...buttons, "|", ...more].join("\n");
  if (key === shown.apps) return;  // rebuilding would lose keyboard focus
  shown.apps = key;
  const fieldset = document.getElementById("history-filters");
  const legend = fieldset.querySelector("legend");
  const filters = [["", "All"], ...buttons.map((name) => [name, name])].map(([value, label]) => {
    const input = Object.assign(document.createElement("input"), { type: "radio", name: "history-app", value, checked: value === shown.app });
    const chip = element("span", "filter");
    if (value) chip.append(appIcon(value));
    chip.append(label);
    const wrapper = document.createElement("label");
    wrapper.append(input, chip);
    return wrapper;
  });
  fieldset.replaceChildren(legend, ...filters);
  if (more.length) {
    const button = iconButton("filter more", "More apps", DOTS_ICON);
    button.dataset.menu = "";
    button.addEventListener("click", () => openMenu(button, more.map((name) => ({
      label: name, icon: appIcon(name), choose: () => showHistory({ app: name }),
    }))));
    fieldset.append(button);
  }
}

function renderHistory(result) {
  const days = [];
  for (const item of result.items) {
    const label = dayLabel(new Date(item.at));
    if (days.at(-1)?.label !== label) days.push({ label, list: element("ul", "entries"), count: 0 });
    days.at(-1).list.append(entry(item, false));
    days.at(-1).count += 1;
  }
  document.getElementById("history-days").replaceChildren(...days.map((day) => {
    const card = element("section", "card day-card");
    const head = element("header", "day-head");
    head.innerHTML = CALENDAR_ICON;
    head.append(element("h2", "day", day.label), element("span", "day-count", day.count === 1 ? "1 entry" : `${day.count} entries`));
    card.append(head, day.list);
    return card;
  }));
  const empty = document.getElementById("history-empty");
  empty.hidden = result.items.length > 0;
  empty.textContent = shown.query || shown.app ? "Nothing matches." : "Nothing here yet. Your dictations show up here as you make them.";
  document.getElementById("history-more").hidden = result.total <= result.items.length;
}

// One dictation: Home's short version shows the time, the first line, and the app; History's shows it all.
function entry(item, short) {
  const row = element("li", short ? "entry short" : "entry long");
  const when = element("div", "entry-when mono");
  when.append(element("span", "", timeFormat.format(new Date(item.at))), element("span", "faint", clockLength(item.seconds)));
  if (short) {
    const body = element("div", "entry-body");
    const about = element("div", "entry-about");
    about.append(appTag(item.app), element("span", "", wordCount(item.words)));
    body.append(element("p", "entry-text", item.text), about);
    row.append(when, body, copyButton(item.text));
    return row;
  }
  const app = element("div", "entry-app");
  app.append(appIcon(item.app), element("span", "", item.app));
  const more = iconButton("icon-button", "More", DOTS_ICON);
  more.dataset.menu = "";
  more.addEventListener("click", () => openMenu(more, [{ label: "Delete", danger: true, choose: () => deleteDictation(item.id) }]));
  row.append(when, app, element("p", "entry-text", item.text), element("span", "word-badge", wordCount(item.words)),
    copyButton(item.text), more);
  return row;
}

async function deleteDictation(id) {
  await api().delete_dictation(id);
  await watchHistory();
}

// A small menu under a button, for a dictation's actions and the apps without their own filter.
function openMenu(button, items) {
  const menu = document.getElementById("row-menu");
  if (!menu.hidden && menu.owner === button) return closeMenu();
  menu.replaceChildren(...items.map((item) => {
    const choice = element("button", item.danger ? "menu-item danger" : "menu-item");
    choice.type = "button";
    choice.setAttribute("role", "menuitem");
    if (item.icon) choice.append(item.icon);
    choice.append(item.label);
    choice.addEventListener("click", () => { closeMenu(); item.choose(); });
    return choice;
  }));
  menu.owner = button;
  menu.hidden = false;
  const place = button.getBoundingClientRect();
  const width = menu.offsetWidth;
  menu.style.left = `${Math.max(8, Math.min(place.right - width, window.innerWidth - width - 8))}px`;
  const below = place.bottom + 6;
  menu.style.top = `${below + menu.offsetHeight > window.innerHeight ? place.top - menu.offsetHeight - 6 : below}px`;
  menu.firstElementChild?.focus();
}

function closeMenu() {
  const menu = document.getElementById("row-menu");
  if (menu.hidden) return;
  menu.hidden = true;
  menu.owner?.focus({ preventScroll: true });
  menu.owner = null;
}

function iconButton(className, label, icon) {
  const button = element("button", className);
  button.type = "button";
  button.title = label;
  button.setAttribute("aria-label", label);
  button.innerHTML = icon;
  return button;
}

// How far back History goes, from its oldest dictation: "Since today", "2 days", "30 days".
function historyRange(first) {
  if (!first) return "None yet";
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(first).setHours(0, 0, 0, 0)) / 86400000) + 1;
  return days === 1 ? "1 day" : `${days.toLocaleString()} days`;
}

function copyButton(text) {
  const button = iconButton("icon-button", "Copy", COPY_ICON);
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

function wordCount(words) {
  return `${words.toLocaleString()} ${words === 1 ? "word" : "words"}`;
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
  downloading: ["Getting the speech model", "A one-time {size} download. After this, Ghostwriter never needs the internet to hear you."],
  loading: ["Setting it up", "Loading the speech model. This takes a few seconds."],
  ready: ["Ready to go", "The speech model is on this PC now, so nothing you say ever needs the internet."],
  failed: ["The download stopped", "Check your internet connection, then start Ghostwriter again from the {appMenu}. It picks up where it left off."],
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
  if (status.model === "ready") {
    clearInterval(setup.timer);
    render(await api().state());  // the sidebar and Settings show the model as ready, too
  }
}

function renderDownload(status) {
  const [title, text] = DOWNLOAD_TEXT[status.model];
  document.getElementById("download-title").textContent = title;
  document.getElementById("download-text").textContent = text.replace("{size}", state.modelSize).replace("{appMenu}", state.appMenu);
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
