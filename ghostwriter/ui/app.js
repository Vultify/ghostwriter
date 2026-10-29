"use strict";

// Ghostwriter app window. The Python side (ghostwriter/window.py) owns the files; this page only asks it to read
// and change them, through window.pywebview.api.

const app = document.getElementById("app");
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
let state = null;

const api = () => window.pywebview.api;

window.addEventListener("pywebviewready", async () => {
  bindPage();
  render(await api().state());
  renderDictionary(await api().dictionary());
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
}

async function change(name, value) {
  render(await api().set_setting(name, value));
}

function showView(name) {
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== name; });
  document.querySelectorAll("[data-view]").forEach((button) => {
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
