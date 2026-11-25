// Core: DOM references, shared state, utilities, API access and global controls.

const byId = (id) => document.getElementById(id);
const form = byId("question-form");
const question = byId("question");
const submit = byId("send");
const transcript = byId("transcript");
const viewport = byId("thread-scroll");
const exampleList = byId("example-list");
const casePicker = byId("case-picker");
const toolRail = byId("tool-rail");
const navToggle = byId("open-nav");
const shell = byId("shell");
const modelPicker = byId("model-picker");
const chatSearch = byId("chat-search");
const searchToggle = byId("open-search");
const mobileLayout = matchMedia("(max-width: 48rem)");

const LEGACY_HISTORY = "research-conversations-v1";
const TAB_STATE = "research-workspace-v2";
const API = "/api/workspace";
const settingsEndpoint = "/api/settings/model";
const MAX_UPLOAD = 5 * 1024 * 1024;
const MODES = {
  auto: { label: "自动" },
  method: { label: "方法推荐" },
  concept: { label: "概念对齐" },
};
const METHOD_FIELDS = [["推荐理由", "rationale"], ["适用条件", "conditions"], ["局限", "limitations"]];
const drafts = new Map();
const pendingTurns = new Map();
let verifiedPaperIds = new Map();
let active = newConversation();
let sidebarCollapsed = Boolean(readTab(TAB_STATE)?.sidebarCollapsed);
let projectFilter = null;
let expandedProjects = new Set();
let expandedProjectChats = new Set();
let collapsedSections = new Set();
let projects = [];
let conversations = [];
let files = [];
let cases = [];
let ready = false;
let busy = false;
let loading = false;
let modelConfigured = false;
let currentModelSettings = null;
let modelPending = false;
let editorState;
let uploadScope;
let fileDialogProject = null;
let previewVersion = 0;
let exampleCase;

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value != null) node.textContent = value;
  return node;
}

function statusText(value) {
  return String(value).replace(/。\s*$/, "");
}

function button(className, label, handler) {
  const template = byId("shadcn-normal-button");
  const node = template?.content.firstElementChild.cloneNode(true) ?? document.createElement("button");
  node.classList.add(...className.split(/\s+/));
  if (label != null) node.textContent = label;
  node.type = "button";
  node.addEventListener("click", handler);
  return node;
}

function readTab(key) {
  try {
    return JSON.parse(sessionStorage.getItem(key));
  } catch {
    return null;
  }
}

function saveTab() {
  try {
    sessionStorage.setItem(TAB_STATE, JSON.stringify({
      chat: active.id, project: projectFilter, draftProject: active.project_id,
      caseCode: active.case_code, sidebarCollapsed,
      expandedProjects: [...expandedProjects],
      expandedProjectChats: [...expandedProjectChats],
      collapsedSections: [...collapsedSections],
    }));
  } catch {
    // The workspace itself is stored on the local server.
  }
}

async function request(path, payload, signal) {
  const options = { signal };
  if (payload !== undefined) {
    options.method = "POST";
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(path, options);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(response.ok ? "服务返回了无法解析的内容" : "请求未完成（HTTP " + response.status + "）");
  }
  if (!response.ok) {
    const error = new Error(statusText(data.error || "操作未完成，请重试"));
    error.status = response.status;
    throw error;
  }
  return data;
}

function newConversation(projectId = null, caseCode = "") {
  return { id: null, title: "新对话", project_id: projectId, case_code: caseCode, mode: "auto", turns: [] };
}

function chatTitle(chat) {
  return chat.title || chat.turns?.[0]?.question.replace(/\s+/g, " ") || "新对话";
}

function caseName(item) {
  return [item.label, item.discipline].filter(Boolean).join(" × ");
}

function currentCase() {
  return cases.find((item) => item.code === active.case_code);
}

function currentProject() {
  return projects.find((item) => item.id === active.project_id);
}

let noteTimer = null;

function note(message = "", kind = "error") {
  const target = byId("workspace-note");
  if (noteTimer) {
    clearTimeout(noteTimer);
    noteTimer = null;
  }
  target.textContent = message;
  target.dataset.kind = kind;
  target.hidden = !message;
  if (message && kind !== "error") {
    noteTimer = setTimeout(() => {
      target.textContent = "";
      target.hidden = true;
      noteTimer = null;
    }, 3000);
  }
}

function showConnectionError(message = "") {
  byId("page-message").textContent = message;
  byId("connection-note").hidden = !message;
}

function updateInput() {
  submit.disabled = !ready || busy || modelPending || !question.value.trim();
  for (const choice of exampleList.querySelectorAll("input")) {
    choice.checked = question.value === exampleCase?.examples[choice.value];
  }
}

function updateControls() {
  for (const id of ["go-home", "new-chat", "new-project", "show-files", "show-literature",
    "attach-file", "file-manager-upload", "chat-search", "open-search", "export-chat",
    "show-candidates", "show-compare", "show-alignment", "show-method-docs",
    "show-knowledge", "show-trash"]) {
    byId(id).disabled = !ready || busy;
  }
  byId("export-chat").disabled = !ready || busy || !active.id;
  byId("chat-actions").disabled = !ready || busy || !active.id;
  byId("rail-settings").disabled = !ready || busy || modelPending;
  byId("export-workspace").classList.toggle("is-disabled", !ready || busy);
  byId("export-workspace").setAttribute("aria-disabled", String(!ready || busy));
  if (!active.id && !active.project_id) byId("go-home").setAttribute("aria-current", "page");
  else byId("go-home").removeAttribute("aria-current");
  byId("editor-save").disabled = busy;
  exampleList.disabled = !ready || busy;
  for (const node of document.querySelectorAll(".case-button, .history-button, .project-button, .project-file-button, .file-remove")) {
    node.disabled = busy;
  }
  question.readOnly = busy;
  const sendLabel = loading ? "正在查询" : "发送";
  submit.setAttribute("aria-label", sendLabel);
  submit.setAttribute("aria-busy", String(loading));
  submit.title = sendLabel;
  byId("model-heading").setAttribute("aria-disabled", String(!ready || busy));
  byId("quick-model").disabled = !currentModelSettings || modelPending || busy;
  byId("quick-effort").disabled = !currentModelSettings || modelPending || busy;
  byId("show-settings").disabled = modelPending || busy;
  updateInput();
}

function setBusy(value) {
  busy = value;
  if (busy) modelPicker.open = false;
  updateControls();
}

// A server started before the script split serves only app.js. Make that
// failure visible instead of leaving every button silently dead.
window.addEventListener("load", () => {
  const missing = ["initialize", "askQuestion", "renderFileSurfaces", "openLiterature",
    "openAlignment", "openMethodDocs", "showModelSettings"]
    .filter((name) => typeof window[name] !== "function");
  if (!missing.length) return;
  showConnectionError("网页脚本未完整加载，通常是本地服务仍在运行旧版本。请关闭启动窗口，重新双击启动脚本（Windows：Start.cmd；macOS：Start.command），然后按 Ctrl+F5 刷新。");
  const reload = byId("reload-cases");
  if (reload) reload.hidden = true;
});
