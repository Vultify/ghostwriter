"use strict";

// Ghostwriter app window. The Python side (ghostwriter/window.py) owns the files; this page only asks it to read
// and change them, through window.pywebview.api.

const app = document.getElementById("app");
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
const PAGE_SIZE = 200;
let state = null;
// What the History page is showing, and the last stamp seen, so new dictations show up while the window is open.
const shown = { query: "", app: "", limit: PAGE_SIZE, apps: "", stamp: null, summary: null, request: 0 };

const api = () => window.pywebview.api;

window.addEventListener("pywebviewready", async () => {
  bindPage();
  render(await api().state());
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
    select.addEventListener("change", () => change("microphone", select.value || null));
  });
  document.getElementById("hands-free-minutes").addEventListener("change", (event) => {
    change("hands_free_minutes", Number(event.target.value));
  });

  document.getElementById("hotkeys").addEventListener("change", (event) => change("hotkey", event.target.value));
  document.getElementById("themes").addEventListener("change", (event) => change("theme", event.target.value));

  const openers = { log: "open_log", folder: "open_folder", dictionary: "open_dictionary_file" };
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
}

async function change(name, value) {
  render(await api().set_setting(name, value));
}

function showView(name) {
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== name; });
  showClearQuestion(false);
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
  fillHotkeys(settings.hotkey);
  document.querySelectorAll("#themes input").forEach((input) => { input.checked = input.value === settings.theme; });
  document.getElementById("history-off").hidden = settings.history;
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

function fillHotkeys(chosen) {
  const fieldset = document.getElementById("hotkeys");
  const legend = fieldset.querySelector("legend");
  const caps = state.hotkeys.map((name) => {
    const input = Object.assign(document.createElement("input"), { type: "radio", name: "hotkey", value: name, checked: name === chosen });
    const cap = Object.assign(document.createElement("span"), { className: "keycap", textContent: name });
    const label = document.createElement("label");
    label.append(input, cap);
    return label;
  });
  fieldset.replaceChildren(legend, ...caps);
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
