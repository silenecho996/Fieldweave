// Workspace: examples, projects, chats, navigation, transcript and editors.

function renderExamples(item) {
  if (item === exampleCase) return;
  exampleCase = item;
  const samples = Object.keys(MODES).flatMap((mode) => {
    const text = item?.examples[mode];
    if (!text) return [];
    const row = element("label", "example-option");
    const choice = element("input", "example-radio");
    const title = element("strong", "example-title", MODES[mode].label);
    const description = element("span", "example-description", text);
    choice.type = "radio";
    choice.name = "research-example";
    choice.value = mode;
    title.id = "example-title-" + mode;
    description.id = "example-description-" + mode;
    choice.setAttribute("aria-labelledby", title.id);
    choice.setAttribute("aria-describedby", description.id);
    choice.addEventListener("change", () => fillQuestion(text, item.code, { focus: false }));
    row.append(choice, title, description);
    return [row];
  });
  exampleList.replaceChildren(...samples);
  byId("examples").hidden = !samples.length;
}

function renderContext() {
  const item = currentCase();
  const scope = currentProject();
  byId("chat-title").textContent = chatTitle(active);
  byId("chat-title").title = chatTitle(active);
  const projectLabel = byId("project-label");
  byId("thread-meta").hidden = !scope && !active.id;
  byId("thread-project").hidden = !scope;
  projectLabel.textContent = scope?.name || "";
  projectLabel.title = scope ? [scope.name, scope.description].filter(Boolean).join(" · ") : "";
  byId("case-scope").textContent = item ? item.label : "选择主题";
  byId("case-heading").title = item ? "示例主题 · " + caseName(item) : "选择示例主题";
  for (const node of byId("cases").querySelectorAll("button")) {
    node.setAttribute("aria-pressed", String(node.dataset.code === active.case_code));
  }
  renderExamples(item);
}

function caseButton(item) {
  const node = button("case-button", null, () => {
    active.case_code = item.code;
    renderContext();
    saveTab();
    closeToolbarPopup(casePicker);
  });
  node.dataset.code = item.code;
  node.append(element("strong", "", item.label));
  if (item.discipline) node.append(element("small", "", item.discipline));
  return node;
}

const SIDEBAR_ICONS = {
  edit: ["m14 6 4 4", "M5 19l4.2-.8L19 8.4a2.4 2.4 0 0 0-3.4-3.4L5.8 14.8 5 19Z"],
  pin: ["M12 17v5", "M5 17h14", "M7 3h10l-1 7a4 4 0 0 1-8 0z"],
  move: ["M3 7h7l2 2h9v10H3z", "M12 12v5", "m9.5 14.5 2.5 2.5 2.5-2.5"],
  download: ["M12 3v12", "m7 10 5 5 5-5", "M5 21h14"],
  trash: ["M4 7h16", "M9 7V4h6v3", "M6 7l1 14h10l1-14", "M10 11v6", "M14 11v6"],
  plus: ["M12 5v14", "M5 12h14"],
  folder: ["M3.5 7A1.5 1.5 0 0 1 5 5.5h4.5l2 2H19A1.5 1.5 0 0 1 20.5 9v8A1.5 1.5 0 0 1 19 18.5H5A1.5 1.5 0 0 1 3.5 17Z"],
  chat: ["M21 12a8 8 0 0 1-8 8H6l-3 2 1-4.5A8 8 0 1 1 21 12Z"],
  overview: ["M4 4h7v7H4z", "M13 4h7v7h-7z", "M4 13h7v7H4z", "M13 13h7v7h-7z"],
};

function projectOrder(a, b) {
  return (a.sort_order ?? 0) - (b.sort_order ?? 0) || String(a.id).localeCompare(String(b.id));
}

function chatOrder(a, b) {
  return (a.sort_order ?? 0) - (b.sort_order ?? 0) || String(a.id).localeCompare(String(b.id));
}

function pinnedChats() {
  return conversations.filter((chat) => chat.pinned_at).sort(chatOrder);
}

function projectChats(projectId) {
  return conversations.filter((chat) => !chat.pinned_at && chat.project_id === projectId).sort(chatOrder);
}

function independentChats() {
  return conversations.filter((chat) => !chat.pinned_at && !chat.project_id).sort(chatOrder);
}

function rowIconButton(label, icon, handler, text = null) {
  const node = element("button", "row-icon-button", text);
  node.type = "button";
  node.setAttribute("aria-label", label);
  node.title = label;
  if (icon) node.append(iconSvg(icon));
  node.addEventListener("click", (event) => {
    event.stopPropagation();
    handler(event);
  });
  return node;
}

function chatRow(chat) {
  const row = element("div", "chat-row");
  row.dataset.chatId = chat.id;
  row.draggable = true;
  row.classList.toggle("is-active", chat.id === active.id);
  const open = button("history-button chat-open", chatTitle(chat), () => openConversation(chat.id));
  open.title = chatTitle(chat);
  open.setAttribute("aria-pressed", String(chat.id === active.id));
  let more;
  more = rowIconButton("聊天操作", null, () => openChatMenu(more, chat), "⋯");
  more.classList.add("row-more-button");
  row.append(open, more);
  attachChatDrag(row, chat);
  attachChatRowDrop(row, chat);
  return row;
}

function projectRow(project) {
  const expanded = expandedProjects.has(project.id);
  const folder = element("div", "project-folder");
  const row = element("div", "project-row");
  row.dataset.projectId = project.id;
  row.draggable = true;
  row.classList.toggle("is-active", active.project_id === project.id);
  const toggle = button("project-button", null, () => toggleProject(project.id));
  toggle.dataset.projectId = project.id;
  toggle.title = project.description || project.name;
  toggle.setAttribute("aria-expanded", String(expanded));
  toggle.setAttribute("aria-controls", "project-contents-" + project.id);
  const icons = byId("project-icons").content.cloneNode(true);
  icons.querySelector(".project-name").textContent = project.name;
  toggle.append(icons);
  let more;
  more = rowIconButton("项目操作", null, () => openProjectMenu(more, project), "⋯");
  more.classList.add("row-more-button");
  const edit = rowIconButton("编辑项目", SIDEBAR_ICONS.edit, () => showEditor("project", project));
  row.append(toggle, more, edit);

  const contents = element("div", "project-contents");
  contents.id = "project-contents-" + project.id;
  contents.hidden = !expanded;
  const chats = projectChats(project.id);
  const showAll = expandedProjectChats.has(project.id);
  const visible = showAll ? chats : chats.slice(0, 5);
  contents.append(...visible.map(chatRow));
  if (!chats.length) contents.append(element("p", "project-empty", "暂无聊天"));
  if (chats.length > 5) {
    const expand = button("project-more-button", showAll ? "收起" : "展开显示",
      () => toggleProjectChats(project.id));
    expand.dataset.projectChats = project.id;
    expand.title = showAll ? "收起项目聊天" : `显示全部 ${chats.length} 条聊天`;
    contents.append(expand);
  }
  folder.append(row, contents);
  attachProjectDrag(row, project);
  attachProjectDrop(row, project);
  return folder;
}

function renderSidebar() {
  const pinned = pinnedChats();
  const independent = independentChats();
  byId("pinned").replaceChildren(...pinned.map(chatRow));
  byId("pinned-section").hidden = !pinned.length;
  const orderedProjects = [...projects].sort(projectOrder);
  byId("projects").replaceChildren(
    ...(orderedProjects.length
      ? orderedProjects.map(projectRow)
      : [element("p", "sidebar-empty", "还没有项目")]),
  );
  byId("chats").replaceChildren(...independent.map(chatRow));
  byId("chats-section").hidden = !independent.length;
  byId("new-chat").title = "开始独立聊天";
  applySectionCollapse();
}

function applySectionCollapse() {
  for (const [key, contentId, toggleId] of [
    ["pinned", "pinned", "toggle-pinned"],
    ["projects", "projects", "toggle-projects"],
    ["chats", "chats", "toggle-chats"],
  ]) {
    const collapsed = collapsedSections.has(key);
    byId(contentId).hidden = collapsed;
    byId(toggleId).setAttribute("aria-expanded", String(!collapsed));
  }
}

function toggleSection(key) {
  if (collapsedSections.has(key)) collapsedSections.delete(key);
  else collapsedSections.add(key);
  applySectionCollapse();
  saveTab();
}

function toggleProject(id) {
  if (busy) return;
  if (expandedProjects.has(id)) expandedProjects.delete(id);
  else expandedProjects.add(id);
  renderSidebar();
  saveTab();
  byId("projects").querySelector(`.project-row[data-project-id="${id}"] .project-button`)
    ?.focus({ preventScroll: true });
}

function toggleProjectChats(id) {
  if (expandedProjectChats.has(id)) expandedProjectChats.delete(id);
  else expandedProjectChats.add(id);
  renderSidebar();
  saveTab();
  byId("projects").querySelector(`.project-more-button[data-project-chats="${id}"]`)
    ?.focus({ preventScroll: true });
}

let sidebarMenu = null;
let sidebarMenuAnchor = null;

function closeSidebarMenu(restoreFocus = false) {
  if (!sidebarMenu) return;
  const anchor = sidebarMenuAnchor;
  sidebarMenu.remove();
  sidebarMenu = null;
  sidebarMenuAnchor = null;
  if (restoreFocus) anchor?.focus({ preventScroll: true });
}

function openSidebarMenu(anchor, items) {
  closeSidebarMenu();
  const menu = element("div", "sidebar-menu");
  menu.setAttribute("role", "menu");
  for (const item of items) {
    if (item.separator) {
      menu.append(element("div", "sidebar-menu-separator"));
      continue;
    }
    const row = element("button", "sidebar-menu-item" + (item.danger ? " is-danger" : ""), null);
    row.type = "button";
    row.setAttribute("role", "menuitem");
    row.disabled = Boolean(item.disabled);
    if (item.icon) row.append(iconSvg(item.icon));
    row.append(element("span", "sidebar-menu-label", item.label));
    if (item.hint) row.append(element("span", "sidebar-menu-hint", item.hint));
    row.addEventListener("click", (event) => {
      event.stopPropagation();
      closeSidebarMenu();
      item.run();
    });
    menu.append(row);
  }
  document.body.append(menu);
  const rect = anchor.getBoundingClientRect();
  const width = menu.offsetWidth;
  const height = menu.offsetHeight;
  let left = rect.right + 6;
  if (left + width > window.innerWidth - 8) left = Math.max(8, rect.left - width - 6);
  const top = Math.max(8, Math.min(rect.top, window.innerHeight - height - 8));
  menu.style.left = left + "px";
  menu.style.top = top + "px";
  sidebarMenu = menu;
  sidebarMenuAnchor = anchor;
  menu.querySelector("button:not(:disabled)")?.focus({ preventScroll: true });
}

function openChatMenu(anchor, chat) {
  const items = [
    { label: chat.pinned_at ? "取消置顶" : "置顶聊天", icon: SIDEBAR_ICONS.pin,
      run: () => setChatPinned(chat, !chat.pinned_at) },
    { label: "重命名", icon: SIDEBAR_ICONS.edit, run: () => showEditor("chat", chat) },
    { label: "移动到项目", icon: SIDEBAR_ICONS.move, run: () => openMoveChatMenu(anchor, chat) },
  ];
  if (chat.project_id) {
    items.push({ label: "移出项目", icon: SIDEBAR_ICONS.move, run: () => moveChatToProject(chat, null) });
  }
  items.push(
    { separator: true },
    { label: "导出为 Markdown", icon: SIDEBAR_ICONS.download, run: () => exportChatById(chat.id) },
    { label: "移到回收站", icon: SIDEBAR_ICONS.trash, danger: true, run: () => removeChat(chat) },
  );
  openSidebarMenu(anchor, items);
}

function openMoveChatMenu(anchor, chat) {
  const items = [...projects].sort(projectOrder).map((project) => ({
    label: project.name,
    icon: SIDEBAR_ICONS.folder,
    hint: chat.project_id === project.id ? "当前" : "",
    run: () => moveChatToProject(chat, project.id),
  }));
  if (!projects.length) items.push({ label: "还没有项目", disabled: true });
  items.push(
    { separator: true },
    { label: "独立聊天", icon: SIDEBAR_ICONS.chat, run: () => moveChatToProject(chat, null) },
  );
  openSidebarMenu(anchor, items);
}

function openProjectMenu(anchor, project) {
  openSidebarMenu(anchor, [
    { label: "项目概览", icon: SIDEBAR_ICONS.overview, run: () => openProjectDashboard(project) },
    { label: "在此项目中新建聊天", icon: SIDEBAR_ICONS.plus, run: () => newChatInProject(project) },
    { label: "重命名项目", icon: SIDEBAR_ICONS.edit, run: () => showEditor("project", project) },
    { label: "项目资料", icon: SIDEBAR_ICONS.folder, run: () => openFiles(null, project.id) },
    { separator: true },
    { label: "移到回收站", icon: SIDEBAR_ICONS.trash, danger: true, run: () => removeProject(project) },
  ]);
}

async function refreshSidebar() {
  const data = await request(API);
  useCatalog(data);
  if (active.id) {
    const current = conversations.find((chat) => chat.id === active.id);
    if (current) active = { ...active, ...current, turns: active.turns || [] };
  }
  if (active.project_id) expandedProjects.add(active.project_id);
  const projectIds = new Set(projects.map((project) => project.id));
  for (const id of [...expandedProjects]) if (!projectIds.has(id)) expandedProjects.delete(id);
  for (const id of [...expandedProjectChats]) if (!projectIds.has(id)) expandedProjectChats.delete(id);
  paintWorkspace();
  saveTab();
}

async function setChatPinned(chat, pinned) {
  if (busy) return;
  setBusy(true);
  try {
    await request(`${API}/chats/${chat.id}/pin`, { pinned });
    await refreshSidebar();
    note(pinned ? "已置顶" : "已取消置顶", "success");
  } catch (error) {
    note(error.message);
  } finally {
    setBusy(false);
  }
}

async function moveChatToProject(chat, projectId) {
  if (busy) return;
  setBusy(true);
  try {
    await request(`${API}/chats/${chat.id}/move`, { project_id: projectId });
    if (projectId) expandedProjects.add(projectId);
    await refreshSidebar();
    note(projectId ? "已移动到项目" : "已移出项目", "success");
  } catch (error) {
    note(error.message);
  } finally {
    setBusy(false);
  }
}

async function removeChat(chat) {
  if (busy) return;
  const wasActive = active.id === chat.id;
  const caseCode = active.case_code;
  setBusy(true);
  try {
    await request(`${API}/chats/${chat.id}/remove`, {});
    if (wasActive) switchTo(newConversation(chat.project_id, caseCode));
    await refreshSidebar();
    note("已移到回收站，可在「工具 → 回收站」恢复", "success");
  } catch (error) {
    note(error.message);
  } finally {
    setBusy(false);
  }
}

async function removeProject(project) {
  if (busy) return;
  const activeInProject = active.id
    && conversations.some((chat) => chat.id === active.id && chat.project_id === project.id);
  const caseCode = active.case_code;
  setBusy(true);
  try {
    await request(`${API}/projects/${project.id}/remove`, { delete_files: false });
    expandedProjects.delete(project.id);
    expandedProjectChats.delete(project.id);
    if (projectFilter === project.id) projectFilter = null;
    if (activeInProject) switchTo(newConversation(null, caseCode));
    else if (active.project_id === project.id) active = { ...active, project_id: null };
    await refreshSidebar();
    note("项目已移到回收站，可在「工具 → 回收站」恢复", "success");
  } catch (error) {
    note(error.message);
  } finally {
    setBusy(false);
  }
}

function newChatInProject(project) {
  if (busy) return;
  expandedProjects.add(project.id);
  projectFilter = project.id;
  drafts.delete("draft:" + project.id);
  switchTo(newConversation(project.id, active.case_code));
}

async function persistChatOrder(ids) {
  if (busy) return;
  setBusy(true);
  try {
    await request(API + "/reorder", { chats: ids });
    await refreshSidebar();
  } catch (error) {
    note(error.message);
  } finally {
    setBusy(false);
  }
}

async function persistProjectOrder(ids) {
  if (busy) return;
  setBusy(true);
  try {
    await request(API + "/reorder", { projects: ids });
    await refreshSidebar();
  } catch (error) {
    note(error.message);
  } finally {
    setBusy(false);
  }
}

function downloadChatMarkdown(chat) {
  const blob = new Blob([markdownForChat(chat)], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = element("a", "sr-only");
  anchor.href = url;
  anchor.download = (chatTitle(chat).replace(/[\\/:*?"<>|]+/g, "-").trim().slice(0, 80) || "chat") + ".md";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportChatById(chatId) {
  if (busy) return;
  setBusy(true);
  try {
    const { chat } = await request(API + "/chats/" + chatId);
    downloadChatMarkdown(chat);
    note("已导出对话", "success");
  } catch (error) {
    note(error.message);
  } finally {
    setBusy(false);
  }
}

let draggingChat = null;
let draggingProject = null;
let dragExpandTimer = null;

function clearDragState() {
  draggingChat = null;
  draggingProject = null;
  clearTimeout(dragExpandTimer);
  dragExpandTimer = null;
  for (const node of document.querySelectorAll(
    ".is-dragging, .is-drop-target, .is-drop-section, .drop-before, .drop-after")) {
    node.classList.remove("is-dragging", "is-drop-target", "is-drop-section", "drop-before", "drop-after");
  }
}

function attachChatDrag(row, chat) {
  row.addEventListener("dragstart", (event) => {
    if (event.target.closest(".row-icon-button")) {
      event.preventDefault();
      return;
    }
    closeSidebarMenu();
    draggingChat = chat;
    draggingProject = null;
    row.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", chat.id);
  });
  row.addEventListener("dragend", clearDragState);
}

function attachChatRowDrop(row, chat) {
  row.addEventListener("dragover", (event) => {
    if (!draggingChat || draggingChat.id === chat.id) return;
    event.preventDefault();
    event.stopPropagation();
    const rect = row.getBoundingClientRect();
    const after = event.clientY > rect.top + rect.height / 2;
    row.classList.toggle("drop-before", !after);
    row.classList.toggle("drop-after", after);
  });
  row.addEventListener("dragleave", () => {
    row.classList.remove("drop-before", "drop-after");
  });
  row.addEventListener("drop", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!draggingChat || draggingChat.id === chat.id) {
      clearDragState();
      return;
    }
    const after = row.classList.contains("drop-after");
    const dragged = draggingChat;
    clearDragState();
    dropChatOnChat(dragged, chat, after);
  });
}

function attachProjectDrag(row, project) {
  row.addEventListener("dragstart", (event) => {
    if (event.target.closest(".row-icon-button")) {
      event.preventDefault();
      return;
    }
    closeSidebarMenu();
    draggingProject = project;
    draggingChat = null;
    row.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", project.id);
  });
  row.addEventListener("dragend", clearDragState);
}

function attachProjectDrop(row, project) {
  row.addEventListener("dragover", (event) => {
    if (!draggingChat && !draggingProject) return;
    if (draggingProject?.id === project.id) return;
    event.preventDefault();
    event.stopPropagation();
    row.classList.add("is-drop-target");
    if (draggingChat) {
      scheduleProjectExpand(project);
      return;
    }
    const rect = row.getBoundingClientRect();
    const after = event.clientY > rect.top + rect.height / 2;
    row.classList.toggle("drop-before", !after);
    row.classList.toggle("drop-after", after);
  });
  row.addEventListener("dragleave", (event) => {
    if (row.contains(event.relatedTarget)) return;
    row.classList.remove("is-drop-target", "drop-before", "drop-after");
    clearTimeout(dragExpandTimer);
  });
  row.addEventListener("drop", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const chat = draggingChat;
    const draggedProject = draggingProject;
    clearDragState();
    if (chat) {
      moveChatToProject(chat, project.id);
      return;
    }
    if (draggedProject && draggedProject.id !== project.id) {
      const rect = row.getBoundingClientRect();
      dropProjectOnProject(draggedProject, project,
        event.clientY > rect.top + rect.height / 2);
    }
  });
}

function attachSectionDrop(section, handler) {
  section.addEventListener("dragover", (event) => {
    if (!draggingChat) return;
    if (event.target.closest(".chat-row, .project-row")) return;
    event.preventDefault();
    section.classList.add("is-drop-section");
  });
  section.addEventListener("dragleave", (event) => {
    if (!section.contains(event.relatedTarget)) section.classList.remove("is-drop-section");
  });
  section.addEventListener("drop", (event) => {
    if (!draggingChat || event.target.closest(".chat-row")) return;
    event.preventDefault();
    event.stopPropagation();
    const chat = draggingChat;
    clearDragState();
    handler(chat);
  });
}

function scheduleProjectExpand(project) {
  clearTimeout(dragExpandTimer);
  if (expandedProjects.has(project.id)) return;
  dragExpandTimer = setTimeout(() => {
    expandedProjects.add(project.id);
    const contents = byId("project-contents-" + project.id);
    if (contents) contents.hidden = false;
    byId("projects")
      .querySelector(`.project-row[data-project-id="${project.id}"] .project-button`)
      ?.setAttribute("aria-expanded", "true");
    saveTab();
  }, 600);
}

function chatGroup(chat) {
  if (chat.pinned_at) return "pinned";
  return chat.project_id ? "project:" + chat.project_id : "chats";
}

async function dropChatOnChat(dragged, target, after) {
  if (chatGroup(dragged) !== chatGroup(target)) {
    if (target.pinned_at) await setChatPinned(dragged, true);
    else if (target.project_id) await moveChatToProject(dragged, target.project_id);
    else await moveChatToProject(dragged, null);
    return;
  }
  const ids = conversations
    .filter((chat) => chatGroup(chat) === chatGroup(target))
    .sort(chatOrder)
    .map((chat) => chat.id)
    .filter((id) => id !== dragged.id);
  const index = ids.indexOf(target.id);
  if (index < 0) return;
  ids.splice(after ? index + 1 : index, 0, dragged.id);
  await persistChatOrder(ids);
}

async function dropProjectOnProject(dragged, target, after) {
  const ids = [...projects].sort(projectOrder)
    .map((project) => project.id)
    .filter((id) => id !== dragged.id);
  const index = ids.indexOf(target.id);
  if (index < 0) return;
  ids.splice(after ? index + 1 : index, 0, dragged.id);
  await persistProjectOrder(ids);
}

for (const [key, toggleId] of [
  ["pinned", "toggle-pinned"],
  ["projects", "toggle-projects"],
  ["chats", "toggle-chats"],
]) {
  byId(toggleId).addEventListener("click", () => toggleSection(key));
}

attachSectionDrop(byId("pinned-section"), (chat) => setChatPinned(chat, true));
attachSectionDrop(byId("chats-section"), (chat) => moveChatToProject(chat, null));

document.addEventListener("click", (event) => {
  if (!sidebarMenu) return;
  if (sidebarMenu.contains(event.target) || sidebarMenuAnchor?.contains(event.target)) return;
  closeSidebarMenu();
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !sidebarMenu) return;
  event.preventDefault();
  closeSidebarMenu(true);
});
window.addEventListener("scroll", () => closeSidebarMenu(), true);
window.addEventListener("resize", () => closeSidebarMenu());
window.addEventListener("dragend", clearDragState);

function paintWorkspace() {
  renderContext();
  renderSidebar();
  renderFileSurfaces();
  updateControls();
}

async function importPreviousChats() {
  const saved = readTab(LEGACY_HISTORY);
  if (!Array.isArray(saved?.chats)) return null;
  for (const item of saved.chats) {
    if (typeof item?.id !== "string" || !item.turns?.length || !Object.hasOwn(MODES, item.mode)) continue;
    if (conversations.some((chat) => chat.id === item.id)) continue;
    await request(API + "/chats", {
      id: item.id,
      title: item.turns[0].question.replace(/\s+/g, " ").slice(0, 120),
      case_code: item.caseCode,
      mode: item.mode,
      project_id: null,
      turns: item.turns,
    });
  }
  try { sessionStorage.removeItem(LEGACY_HISTORY); } catch { /* Session storage can be unavailable. */ }
  return saved.activeId;
}

function useCatalog(data) {
  projects = data.projects;
  conversations = data.chats;
  files = data.files;
  const projectIds = new Set(projects.map((project) => project.id));
  for (const id of [...expandedProjects]) if (!projectIds.has(id)) expandedProjects.delete(id);
  for (const id of [...expandedProjectChats]) if (!projectIds.has(id)) expandedProjectChats.delete(id);
}

async function initialize() {
  showConnectionError();
  note();
  try {
    const [catalog, workspace, settings] = await Promise.all([
      request("/api/cases"), request(API), request(settingsEndpoint).catch(() => null),
    ]);
    cases = catalog.cases;
    verifiedPaperIds = new Map(Object.entries(catalog.paper_links || {}));
    if (!cases.length) throw new Error("知识库里还没有可用的案例");
    useCatalog(workspace);
    let previousChat;
    try {
      previousChat = await importPreviousChats();
      if (previousChat) useCatalog(await request(API));
    } catch {
      note("旧标签页的对话暂未导入，再次打开网页时会重试");
    }
    const tab = readTab(TAB_STATE);
    const storedExpanded = Array.isArray(tab?.expandedProjects) ? tab.expandedProjects : null;
    expandedProjects = new Set(storedExpanded
      ? storedExpanded.filter((id) => projects.some((item) => item.id === id))
      : projects.map((item) => item.id));
    expandedProjectChats = new Set(Array.isArray(tab?.expandedProjectChats)
      ? tab.expandedProjectChats : []);
    collapsedSections = new Set(Array.isArray(tab?.collapsedSections)
      ? tab.collapsedSections : []);
    const chatId = tab?.chat || previousChat;
    if (conversations.some((chat) => chat.id === chatId)) {
      active = (await request(API + "/chats/" + chatId)).chat;
    } else {
      const draftProject = tab && Object.hasOwn(tab, "draftProject") ? tab.draftProject : tab?.project;
      const projectId = projects.some((item) => item.id === draftProject) ? draftProject : null;
      active = newConversation(projectId, tab?.caseCode);
    }
    projectFilter = tab && (tab.project === null || projects.some((item) => item.id === tab.project))
      ? tab.project : active.project_id;
    if (tab?.chat && tab.chat === active.id) {
      active.case_code = tab.caseCode || active.case_code;
    }
    if (active.project_id) expandedProjects.add(active.project_id);
    if (!currentCase()) active.case_code = cases[0].code;
    byId("cases").replaceChildren(...cases.map(caseButton));
    modelConfigured = catalog.model_configured;
    paintModelSelection(settings);
    ready = true;
    paintWorkspace();
    renderTranscript();
    saveTab();
  } catch (error) {
    showConnectionError(error instanceof TypeError ? "无法连接本地服务，请确认启动程序仍在运行" : error.message);
  }
}

function scrollToTurn(node) {
  if (!node) {
    viewport.scrollTop = 0;
    return;
  }
  viewport.scrollTop += node.getBoundingClientRect().top - viewport.getBoundingClientRect().top - 20;
}

function updatePane() {
  transcript.hidden = !active.turns.length;
  byId("welcome").hidden = !transcript.hidden;
}

function renderTranscript() {
  editingIndex = null;
  transcript.replaceChildren(...active.turns.map((turn, index) => turnView(turn, index).node));
  updatePane();
  scrollToTurn(transcript.lastElementChild);
}

function rememberDraft() {
  const key = active.id || "draft:" + (active.project_id || "");
  drafts.set(key, question.value);
}

function switchTo(chat) {
  rememberDraft();
  active = chat;
  if (!currentCase()) active.case_code = cases[0].code;
  const key = active.id || "draft:" + (active.project_id || "");
  question.value = drafts.get(key) || "";
  paintWorkspace();
  renderTranscript();
  saveTab();
  closeNavigation(false);
  question.focus();
}

async function openConversation(id) {
  if (busy) return;
  note();
  setBusy(true);
  try {
    let { chat } = await request(API + "/chats/" + id);
    const unsaved = pendingTurns.get(id);
    if (unsaved?.length) {
      try {
        chat = await savePendingTurns(id);
      } catch {
        chat.turns.push(...pendingTurns.get(id).map((item) => item.turn));
        note("有回答还未写入本地记录，请保持网页打开后重试");
      }
    }
    projectFilter = chat.project_id;
    if (chat.project_id) expandedProjects.add(chat.project_id);
    switchTo(chat);
  } catch (error) {
    note(error.message);
  } finally {
    setBusy(false);
    if (active.id === id) question.focus();
  }
}

function fillQuestion(text, caseCode = active.case_code, { focus = true } = {}) {
  if (!ready || busy) return;
  if (cases.some((item) => item.code === caseCode)) active.case_code = caseCode;
  question.value = text;
  renderContext();
  updateControls();
  saveTab();
  if (focus) {
    question.focus();
    question.setSelectionRange(text.length, text.length);
  }
}

function rememberChat(chat) {
  conversations = [chat, ...conversations.filter((item) => item.id !== chat.id)];
}

async function ensureActiveChat() {
  if (active.id) return active.id;
  const { chat } = await request(API + "/chats", {
    id: active.pending_id || (active.pending_id = crypto.randomUUID()),
    project_id: active.project_id, case_code: active.case_code, mode: active.mode,
  });
  active = chat;
  rememberChat(chat);
  saveTab();
  paintWorkspace();
  return chat.id;
}

async function savePendingTurns(id) {
  let saved;
  const queue = pendingTurns.get(id);
  while (queue.length) {
    const item = queue[0];
    const data = await request(API + "/chats/" + id, item);
    saved = data.chat;
    queue.shift();
    rememberChat(saved);
  }
  pendingTurns.delete(id);
  return saved;
}



function renderNavigation() {
  shell.classList.toggle("nav-collapsed", sidebarCollapsed);
  const expanded = mobileLayout.matches ? shell.classList.contains("nav-open") : !sidebarCollapsed;
  byId("sidebar").inert = !expanded;
  const label = expanded ? "收起项目与聊天" : "展开项目与聊天";
  navToggle.setAttribute("aria-expanded", String(expanded));
  navToggle.setAttribute("aria-label", label);
  navToggle.title = label;
}

function toggleNavigation() {
  if (!mobileLayout.matches) {
    shell.classList.add("nav-animated");
    sidebarCollapsed = !sidebarCollapsed;
    renderNavigation();
    saveTab();
    return;
  }
  if (shell.classList.contains("nav-open")) {
    closeNavigation();
    return;
  }
  shell.classList.add("nav-open");
  byId("sidebar").setAttribute("role", "dialog");
  byId("sidebar").setAttribute("aria-modal", "true");
  byId("workspace").inert = true;
  toolRail.inert = true;
  renderNavigation();
  byId("close-nav").focus();
}

function closeNavigation(restoreFocus = true) {
  if (!shell.classList.contains("nav-open")) return;
  shell.classList.remove("nav-open");
  byId("sidebar").removeAttribute("role");
  byId("sidebar").removeAttribute("aria-modal");
  byId("workspace").inert = false;
  toolRail.inert = false;
  renderNavigation();
  if (restoreFocus && mobileLayout.matches) navToggle.focus();
}

function showEditor(kind, record) {
  if (!ready || busy) return;
  editorState = { kind, record };
  const project = kind === "project";
  byId("editor-title").textContent = project ? (record ? "编辑项目" : "新建项目") : "对话设置";
  byId("name-label").textContent = project ? "项目名称" : "对话名称";
  const name = byId("editor-name");
  name.value = project ? record?.name || "" : chatTitle(record);
  name.maxLength = project ? 80 : 120;
  byId("editor-description-group").hidden = !project;
  byId("editor-description").value = project ? record?.description || "" : "";
  byId("editor-project-group").hidden = project;
  byId("editor-project").replaceChildren(...[{ id: "", name: "独立对话" }, ...projects].map((item) => {
    const node = element("option", "", item.name);
    node.value = item.id;
    return node;
  }));
  byId("editor-project").value = record?.project_id || "";
  byId("editor-error").hidden = true;
  closeNavigation(false);
  byId("editor-dialog").showModal();
  name.focus();
}

byId("editor-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || !editorState) return;
  const name = byId("editor-name").value.trim();
  const errorNote = byId("editor-error");
  if (!name) {
    errorNote.textContent = "请输入名称";
    errorNote.hidden = false;
    byId("editor-name").focus();
    return;
  }
  const { kind, record } = editorState;
  errorNote.hidden = true;
  setBusy(true);
  try {
    if (kind === "project") {
      const path = API + "/projects" + (record ? "/" + record.id : "");
      const { project } = await request(path, { name, description: byId("editor-description").value.trim() });
      if (record) {
        projects = projects.map((item) => item.id === project.id ? project : item).sort(projectOrder);
        paintWorkspace();
      } else {
        projects = [...projects, project].sort(projectOrder);
        expandedProjects.add(project.id);
        projectFilter = project.id;
        paintWorkspace();
        saveTab();
      }
    } else {
      const { chat } = await request(API + "/chats/" + record.id, {
        title: name, project_id: byId("editor-project").value || null,
        case_code: active.case_code, mode: active.mode,
      });
      projectFilter = chat.project_id;
      if (chat.project_id) expandedProjects.add(chat.project_id);
      active.title = chat.title;
      active.project_id = chat.project_id;
      active.pinned_at = chat.pinned_at;
      active.sort_order = chat.sort_order;
      rememberChat(chat);
      paintWorkspace();
      saveTab();
    }
    byId("editor-dialog").close();
  } catch (error) {
    errorNote.textContent = error.message;
    errorNote.hidden = false;
  } finally {
    setBusy(false);
    if (!byId("editor-dialog").open) question.focus();
  }
});

byId("new-chat").addEventListener("click", () => {
  drafts.delete("draft:");
  projectFilter = null;
  note();
  switchTo(newConversation(null, active.case_code));
});
byId("go-home").addEventListener("click", () => {
  projectFilter = null;
  note();
  switchTo(newConversation(null, active.case_code));
});
byId("new-project").addEventListener("click", () => showEditor("project"));
byId("chat-actions").addEventListener("click", () => {
  showEditor("chat", active);
});
byId("editor-cancel").addEventListener("click", () => byId("editor-dialog").close());
byId("show-files").addEventListener("click", () => openFiles());
byId("files-close").addEventListener("click", () => byId("files-dialog").close());
byId("files-dialog").addEventListener("close", () => {
  fileDialogProject = null;
  clearPreview();
});
byId("attach-file").addEventListener("click", () => chooseFiles("chat"));
byId("file-manager-upload").addEventListener("click", () => chooseFiles("project"));
navToggle.addEventListener("click", toggleNavigation);
byId("close-nav").addEventListener("click", () => closeNavigation());
byId("nav-backdrop").addEventListener("click", () => closeNavigation());
byId("reload-cases").addEventListener("click", initialize);
function closeToolbarPopup(popup) {
  popup.open = false;
  popup.querySelector("summary").focus();
}
const toolbarPopups = [casePicker, modelPicker];
document.addEventListener("click", (event) => {
  for (const popup of toolbarPopups) {
    if (popup.open && !popup.contains(event.target)) popup.open = false;
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const openPopup = toolbarPopups.find((popup) => popup.open);
  if (openPopup) closeToolbarPopup(openPopup);
  closeNavigation();
});
mobileLayout.addEventListener("change", () => {
  if (!mobileLayout.matches) closeNavigation(false);
  renderNavigation();
});

const searchOverlay = byId("search-overlay");
const searchClose = byId("close-search");
const searchTabs = byId("search-tabs");
const searchEmpty = byId("search-empty");
const searchSections = {
  actions: byId("search-actions-section"),
  chats: byId("search-chats-section"),
  files: byId("search-files-section"),
  text: byId("search-text-section"),
};
const searchLists = {
  actions: byId("search-actions"),
  chats: byId("search-chats"),
  files: byId("search-files"),
  text: byId("search-text"),
};

const SEARCH_ICONS = {
  newChat: ["M12 5v14", "M5 12h14"],
  folder: ["M3.5 7A1.5 1.5 0 0 1 5 5.5h4.5l2 2H19A1.5 1.5 0 0 1 20.5 9v8A1.5 1.5 0 0 1 19 18.5H5A1.5 1.5 0 0 1 3.5 17Z"],
  chat: ["M21 12a8 8 0 0 1-8 8H6l-3 2 1-4.5A8 8 0 1 1 21 12Z"],
  file: ["M6 3h8l4 4v14H6z", "M14 3v5h5"],
  text: ["M5 6h14", "M5 11h14", "M5 16h9"],
};

const SEARCH_ACTIONS = [
  {
    key: "new-chat", label: "新建聊天", hint: "Ctrl+N", icon: SEARCH_ICONS.newChat,
    aliases: "new chat 新建 聊天", run: () => byId("new-chat").click(),
  },
  {
    key: "open-files", label: "打开文件", hint: "Ctrl+O", icon: SEARCH_ICONS.file,
    aliases: "open folder files 打开 文件 资料", run: () => byId("show-files").click(),
  },
];

let searchTimer;
let searchRevision = 0;
let searchFilter = "all";
let searchQuery = "";
let searchCounts = { actions: 0, chats: 0, files: 0, text: 0 };

function searchProjectName(id) {
  return projects.find((item) => item.id === id)?.name || "";
}

function searchCaseName(code) {
  return cases.find((item) => item.code === code)?.label || "";
}

function searchRow({ icon, title, meta = "", snippet = "", hint = "", handler }) {
  const row = button("search-row", null, handler);
  row.append(iconSvg(icon));
  const main = element("div", "search-row-main");
  main.append(element("span", "search-row-title", title));
  if (snippet) main.append(element("span", "search-row-snippet", snippet));
  row.append(main);
  if (meta) row.append(element("span", "search-row-meta", meta));
  if (hint) row.append(element("span", "search-shortcut", hint));
  return row;
}

function renderSearchActions(query) {
  const folded = query.toLowerCase();
  const actions = SEARCH_ACTIONS.filter((action) => !query
    || action.label.toLowerCase().includes(folded)
    || action.key.includes(folded)
    || action.aliases.includes(folded));
  searchLists.actions.replaceChildren(...actions.map((action) => searchRow({
    icon: action.icon,
    title: action.label,
    hint: action.hint,
    handler: () => {
      closeSearch();
      action.run();
    },
  })));
  return actions.length;
}

function renderSearchChats(query, data) {
  const rows = [];
  const seen = new Set();
  for (const result of data?.results || []) {
    if (seen.has(result.chat_id)) continue;
    seen.add(result.chat_id);
    rows.push({
      id: result.chat_id,
      title: result.title,
      meta: searchProjectName(result.project_id) || searchCaseName(result.case_code),
      snippet: "",
    });
  }
  const needle = query.toLowerCase();
  const recent = query
    ? conversations.filter((chat) => chatTitle(chat).toLowerCase().includes(needle))
    : conversations.slice(0, 8);
  for (const chat of recent) {
    if (seen.has(chat.id)) continue;
    seen.add(chat.id);
    rows.push({
      id: chat.id,
      title: chatTitle(chat),
      meta: searchProjectName(chat.project_id) || searchCaseName(chat.case_code),
      snippet: "",
    });
  }
  const visible = rows.slice(0, 12);
  searchLists.chats.replaceChildren(...visible.map((chat) => searchRow({
    icon: SEARCH_ICONS.chat,
    title: chat.title,
    meta: chat.meta,
    snippet: chat.snippet,
    handler: () => {
      closeSearch();
      openConversation(chat.id);
    },
  })));
  return visible.length;
}

function renderSearchFiles(query) {
  const needle = query.toLowerCase();
  const matched = files.filter((file) => !query || file.name.toLowerCase().includes(needle)).slice(0, 8);
  searchLists.files.replaceChildren(...matched.map((file) => searchRow({
    icon: SEARCH_ICONS.file,
    title: file.name,
    meta: [searchProjectName(file.project_id) || (file.chat_id ? "对话资料" : "资料"),
      readableSize(file.size)].filter(Boolean).join(" · "),
    snippet: file.preview_available ? "可预览" : "",
    handler: () => {
      closeSearch();
      openFiles(file.id);
    },
  })));
  return matched.length;
}

function renderSearchText(query, data) {
  if (!query) return 0;
  const rows = [];
  for (const result of data?.results || []) {
    for (const match of result.matches) {
      rows.push({
        id: result.chat_id,
        title: result.title,
        meta: searchProjectName(result.project_id) || searchCaseName(result.case_code),
        snippet: match.snippet,
      });
    }
  }
  const visible = rows.slice(0, 12);
  searchLists.text.replaceChildren(...visible.map((row) => searchRow({
    icon: SEARCH_ICONS.text,
    title: row.title,
    meta: row.meta,
    snippet: row.snippet,
    handler: () => {
      closeSearch();
      openConversation(row.id);
    },
  })));
  return visible.length;
}

function searchEmptyMessage() {
  if (searchFilter === "actions") return searchQuery ? "没有匹配的操作" : "没有可用操作";
  if (searchFilter === "files") return searchQuery ? "没有匹配的文件" : "还没有上传资料";
  if (searchFilter === "chats") return searchQuery ? "没有找到匹配的聊天" : "还没有聊天记录";
  if (searchFilter === "text") return searchQuery ? "没有匹配的回答文本" : "输入关键词搜索回答文本";
  return searchQuery ? "没有找到相关内容" : "没有可显示的内容";
}

function applySearchFilter() {
  let visible = 0;
  for (const [key, section] of Object.entries(searchSections)) {
    const show = searchCounts[key] > 0 && (searchFilter === "all" || searchFilter === key);
    section.hidden = !show;
    if (show) visible += 1;
  }
  searchEmpty.hidden = visible > 0;
  if (!visible) searchEmpty.textContent = searchEmptyMessage();
  for (const tab of searchTabs.querySelectorAll("button")) {
    tab.setAttribute("aria-pressed", String(tab.dataset.filter === searchFilter));
  }
}

function setSearchFilter(filter) {
  searchFilter = filter;
  applySearchFilter();
}

function renderSearch(query, data = null) {
  searchQuery = query;
  searchCounts = {
    actions: renderSearchActions(query),
    chats: renderSearchChats(query, data),
    files: renderSearchFiles(query),
    text: renderSearchText(query, data),
  };
  applySearchFilter();
}

async function runSearch(query) {
  const revision = ++searchRevision;
  try {
    const data = await request("/api/workspace/search?q=" + encodeURIComponent(query));
    if (revision !== searchRevision) return;
    renderSearch(query, data);
  } catch (error) {
    if (revision !== searchRevision) return;
    renderSearch(query, { results: [] });
    searchEmpty.textContent = error.message;
    searchEmpty.hidden = false;
  }
}

function openSearch() {
  if (!ready || busy) return;
  searchOverlay.hidden = false;
  document.body.classList.add("search-open");
  searchToggle.setAttribute("aria-expanded", "true");
  searchFilter = "all";
  chatSearch.value = "";
  chatSearch.disabled = false;
  renderSearch("");
  chatSearch.focus();
}

function closeSearch() {
  searchRevision += 1;
  clearTimeout(searchTimer);
  searchOverlay.hidden = true;
  document.body.classList.remove("search-open");
  searchToggle.setAttribute("aria-expanded", "false");
  chatSearch.value = "";
  searchQuery = "";
  searchToggle.focus();
}

function toggleSearch() {
  if (searchOverlay.hidden) openSearch();
  else closeSearch();
}

chatSearch.addEventListener("input", () => {
  const query = chatSearch.value.trim();
  clearTimeout(searchTimer);
  if (!query) {
    searchRevision += 1;
    renderSearch("");
    return;
  }
  searchTimer = setTimeout(() => runSearch(query), 220);
});
chatSearch.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  event.preventDefault();
  closeSearch();
});
searchToggle.addEventListener("click", toggleSearch);
searchClose.addEventListener("click", closeSearch);
searchOverlay.addEventListener("click", (event) => {
  if (event.target === searchOverlay) closeSearch();
});
searchTabs.addEventListener("click", (event) => {
  const tab = event.target.closest("button[data-filter]");
  if (tab) setSearchFilter(tab.dataset.filter);
});
document.addEventListener("keydown", (event) => {
  const mod = event.ctrlKey || event.metaKey;
  if (mod && event.key.toLowerCase() === "k") {
    event.preventDefault();
    if (searchOverlay.hidden) openSearch();
    else closeSearch();
    return;
  }
  if (searchOverlay.hidden) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeSearch();
    return;
  }
  if (!mod) return;
  const key = event.key.toLowerCase();
  if (key === "n") {
    event.preventDefault();
    closeSearch();
    byId("new-chat").click();
  } else if (key === "o") {
    event.preventDefault();
    closeSearch();
    byId("show-files").click();
  }
});

function markdownForChat(chat) {
  const lines = ["# " + chatTitle(chat), ""];
  const label = cases.find((item) => item.code === chat.case_code)?.label;
  if (label) lines.push("案例：" + label, "");
  for (const turn of chat.turns || []) {
    lines.push("## 问：" + turn.question, "");
    if (turn.error) lines.push("> " + turn.error, "");
    const payload = turn.response;
    if (payload?.answer) lines.push(payload.answer, "");
    for (const item of payload?.results || []) {
      if (item.method) {
        lines.push("### " + item.method, "");
        lines.push("- 研究场景：" + (item.scenario || ""));
        for (const [name, key] of METHOD_FIELDS) lines.push("- " + name + "：" + (item[key] || ""));
        lines.push("");
      } else {
        lines.push("### " + item.source + " → " + item.target, "");
        if (item.explanation) lines.push(item.explanation, "");
      }
    }
    if (payload?.references?.length) {
      lines.push("参考依据：", "");
      for (const item of payload.references) {
        lines.push("- [" + item.entry_id + "] " + item.text.replace(/\s+/g, " "));
      }
      lines.push("");
    }
  }
  return lines.join("\n").trim() + "\n";
}

function exportChatMarkdown() {
  if (!active.id) return;
  downloadChatMarkdown(active);
}

byId("export-chat").addEventListener("click", exportChatMarkdown);
byId("show-candidates").addEventListener("click", () => openCandidates());

let projectDashboardProject = null;

function projectDashboardCases(project) {
  return [...new Set(conversations
    .filter((chat) => chat.project_id === project.id)
    .map((chat) => chat.case_code)
    .filter(Boolean))];
}

function projectDateLabel(ns) {
  const ms = Math.floor((Number(ns) || 0) / 1e6);
  return ms ? new Date(ms).toLocaleDateString("zh-CN") : "";
}

function projectStat(label, value) {
  const node = element("div", "project-stat");
  node.append(element("strong", "", String(value)), element("span", "", label));
  return node;
}

function projectListRow(title, meta, snippet, handler) {
  const row = button("project-row-item", null, handler);
  const main = element("div", "project-row-main");
  main.append(element("strong", "", title));
  if (snippet) main.append(element("small", "", snippet));
  row.append(main);
  if (meta) row.append(element("span", "project-row-meta", meta));
  return row;
}

function renderProjectDashboard(project, { candidates = [], literature = {}, coverage = [] } = {}) {
  const chats = conversations
    .filter((chat) => chat.project_id === project.id)
    .sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
  const chatIds = new Set(chats.map((chat) => chat.id));
  const projectFiles = files.filter((file) =>
    file.project_id === project.id || (file.chat_id && chatIds.has(file.chat_id)));
  const projectCases = [...new Set(chats.map((chat) => chat.case_code).filter(Boolean))];
  const activeCandidates = candidates.filter((item) =>
    item.status === "pending" || item.status === "approved");

  byId("project-stats").replaceChildren(
    projectStat("聊天", chats.length),
    projectStat("资料", projectFiles.length),
    projectStat("待审核条目", activeCandidates.length),
    projectStat("案例", projectCases.length),
  );

  const chatList = byId("project-recent-chats");
  chatList.replaceChildren(...(chats.length
    ? chats.slice(0, 5).map((chat) => projectListRow(
      chatTitle(chat),
      projectDateLabel(chat.updated_at),
      "",
      () => {
        byId("project-dialog").close();
        openConversation(chat.id);
      },
    ))
    : [element("p", "file-empty", "还没有聊天")]));

  const fileList = byId("project-recent-files");
  fileList.replaceChildren(...(projectFiles.length
    ? projectFiles.slice(0, 5).map((file) => projectListRow(
      file.name,
      readableSize(file.size),
      file.project_id ? "项目资料" : "对话资料",
      () => {
        byId("project-dialog").close();
        openFiles(file.id);
      },
    ))
    : [element("p", "file-empty", "还没有项目资料")]));

  const candidateList = byId("project-candidates");
  candidateList.replaceChildren(...(candidates.length
    ? candidates.slice(0, 5).map((item) => projectListRow(
      item.title,
      { pending: "待核对", approved: "已通过", rejected: "已驳回", merged: "已入库" }[item.status] || "待核对",
      item.method,
      () => {
        byId("project-dialog").close();
        openCandidates();
      },
    ))
    : [element("p", "file-empty", "还没有相关候选条目")]));

  const caseList = byId("project-cases");
  caseList.replaceChildren(...(projectCases.length
    ? projectCases.map((code) => projectListRow(
      caseLabel(code),
      literature[code] == null ? "" : `${literature[code]} 篇文献`,
      `${chats.filter((chat) => chat.case_code === code).length} 个聊天`,
      () => {
        byId("project-dialog").close();
        openLiterature(code);
      },
    ))
    : [element("p", "file-empty", "还没有涉及案例")]));

  const coverageNode = byId("project-coverage");
  if (coverage.length) {
    renderCoverage(coverageNode, projectCases, coverage);
  } else {
    coverageNode.replaceChildren(element("p", "file-empty",
      projectCases.length ? "正在统计覆盖情况…" : "项目还没有涉及案例"));
  }
}

async function openProjectDashboard(project) {
  if (busy) return;
  projectDashboardProject = project;
  byId("project-dialog-title").textContent = project.name;
  byId("project-dialog-meta").textContent = project.description || "项目概览";
  if (!byId("project-dialog").open) byId("project-dialog").showModal();
  renderProjectDashboard(project);
  const projectCases = projectDashboardCases(project);
  try {
    const [candidatesData, literatureEntries, coverageData] = await Promise.all([
      request("/api/workspace/candidates"),
      Promise.all(projectCases.map(async (code) => {
        try {
          const data = await request("/api/literature?case=" + encodeURIComponent(code) + "&kind=article");
          return [code, data.articles.length];
        } catch {
          return [code, null];
        }
      })),
      request("/api/coverage"),
    ]);
    if (!projectDashboardProject || projectDashboardProject.id !== project.id) return;
    const candidates = candidatesData.candidates.filter((item) =>
      projectCases.includes(item.case_code));
    renderProjectDashboard(project, {
      candidates,
      literature: Object.fromEntries(literatureEntries),
      coverage: coverageData.cases || [],
    });
  } catch (error) {
    byId("project-dialog-meta").textContent = error.message;
  }
}

const compareCase = byId("compare-case");
const compareFilter = byId("compare-filter");
const compareList = byId("compare-list");
const compareTable = byId("compare-table");
const compareOutline = byId("compare-outline");
const compareExport = byId("compare-export");
const compareMeta = byId("compare-meta");
let compareEntries = [];
let compareSelected = new Set();
let compareMarkdown = "";

function compareCaseLabel() {
  return cases.find((item) => item.code === compareCase.value)?.label || compareCase.value;
}

function compareOption(value, label) {
  const node = element("option", "", label);
  node.value = value;
  return node;
}

function compareMatches(entry) {
  const needle = compareFilter.value.trim().toLowerCase();
  if (!needle) return true;
  return [entry.method, entry.concept, entry.scenario, entry.entry_id]
    .join(" ").toLowerCase().includes(needle);
}

function updateCompareAvailability() {
  for (const input of compareList.querySelectorAll("input[type=checkbox]")) {
    input.disabled = !input.checked && compareSelected.size >= 5;
  }
  compareMeta.textContent = compareSelected.size
    ? `已选 ${compareSelected.size} 个 · ${compareCaseLabel()}`
    : "选择 2 至 5 个方法生成对比表和综述大纲";
}

function renderCompareList() {
  const visible = compareEntries.filter(compareMatches);
  if (!visible.length) {
    compareList.replaceChildren(element("p", "file-empty", "没有匹配的方法"));
    updateCompareAvailability();
    return;
  }
  compareList.replaceChildren(...visible.map((entry) => {
    const label = element("label", "compare-item");
    const input = element("input");
    input.type = "checkbox";
    input.value = entry.entry_id;
    input.checked = compareSelected.has(entry.entry_id);
    input.disabled = !input.checked && compareSelected.size >= 5;
    input.addEventListener("change", () => {
      if (input.checked) {
        if (compareSelected.size >= 5) {
          input.checked = false;
          return;
        }
        compareSelected.add(entry.entry_id);
      } else {
        compareSelected.delete(entry.entry_id);
      }
      updateCompareAvailability();
      renderComparePreview();
    });
    const main = element("span", "compare-item-main");
    main.append(
      element("strong", "", entry.method),
      element("small", "file-meta", `${entry.entry_id} · ${entry.concept || "未标注概念"}`),
      element("small", "compare-item-scenario", entry.scenario),
    );
    label.append(input, main);
    return label;
  }));
  updateCompareAvailability();
}

function compareCell(value) {
  return String(value || "").replace(/\|/g, "\\|").replace(/\r?\n/g, " ").trim();
}

function comparisonMarkdown(entries) {
  const label = compareCaseLabel();
  const lines = [
    `# 方法对比：${label}`,
    "",
    `> 由 Fieldweave 工作台知识库生成，共 ${entries.length} 个方法。`,
    "",
    "## 对比表",
    "",
    "| 方法 | 研究场景 | 关联概念 | 推荐理由 | 适用条件 | 局限 |",
    "|---|---|---|---|---|---|",
  ];
  for (const entry of entries) {
    lines.push(`| ${[
      `${entry.method} [${entry.entry_id}]`,
      entry.scenario,
      entry.concept,
      entry.rationale,
      entry.conditions,
      entry.limitations,
    ].map(compareCell).join(" | ")} |`);
  }
  lines.push("", "## 方法要点", "");
  for (const entry of entries) {
    lines.push(
      `### ${entry.method} [${entry.entry_id}]`,
      "",
      `- 研究场景：${entry.scenario || "未说明"}`,
      `- 关联概念：${entry.concept || "未说明"}`,
      `- 推荐理由：${entry.rationale || "未说明"}`,
      `- 适用条件：${entry.conditions || "未说明"}`,
      `- 局限：${entry.limitations || "未说明"}`,
      `- 证据：${compareCell(entry.evidence) || "未提供"}`,
      "",
    );
  }
  lines.push(
    "## 需要进一步核对",
    "",
    "- 各方法的数据前提、标注要求和评价指标是否一致。",
    "- 证据是否来自同一任务和同一评价口径。",
    "- 是否遗漏了需要对比的基线或外部验证。",
    "",
  );
  return lines.join("\n");
}

function splitCompareTableRow(line) {
  const text = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  const cells = [];
  let current = "";
  let escaped = false;
  for (const char of text) {
    if (escaped) {
      current += char;
      escaped = false;
    } else if (char === "\\") {
      escaped = true;
    } else if (char === "|") {
      cells.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current.trim());
  return cells;
}

function appendCompareInline(target, text) {
  const pattern = /(\*\*[^*\n]+\*\*|`[^`\n]+`|https?:\/\/[^\s<>"'）】]+)/g;
  let offset = 0;
  for (const match of text.matchAll(pattern)) {
    target.append(document.createTextNode(text.slice(offset, match.index)));
    const token = match[0];
    if (token.startsWith("**")) {
      target.append(element("strong", "", token.slice(2, -2)));
    } else if (token.startsWith("`")) {
      target.append(element("code", "", token.slice(1, -1)));
    } else {
      const trailing = token.match(/[。，；、）】」』？！.,;:]+$/);
      const urlText = trailing ? token.slice(0, -trailing[0].length) : token;
      const anchor = element("a", "", urlText);
      anchor.href = urlText;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      target.append(anchor);
      if (trailing) target.append(document.createTextNode(trailing[0]));
    }
    offset = match.index + token.length;
  }
  target.append(document.createTextNode(text.slice(offset)));
}

function compareTableNode(lines, start) {
  const table = element("table");
  const head = element("thead");
  const headRow = element("tr");
  for (const cell of splitCompareTableRow(lines[start])) {
    const cellNode = element("th");
    appendCompareInline(cellNode, cell);
    headRow.append(cellNode);
  }
  head.append(headRow);
  table.append(head);
  const body = element("tbody");
  let index = start + 2;
  while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
    const row = element("tr");
    for (const cell of splitCompareTableRow(lines[index])) {
      const cellNode = element("td");
      appendCompareInline(cellNode, cell);
      row.append(cellNode);
    }
    body.append(row);
    index += 1;
  }
  table.append(body);
  return { table, next: index };
}

function renderCompareMarkdown(markdown) {
  const container = byId("compare-outline");
  container.replaceChildren();
  const lines = markdown.split(/\r?\n/);
  let list = null;
  let listTag = "";
  for (let index = 0; index < lines.length; index += 1) {
    const trimmed = lines[index].trim();
    if (!trimmed) {
      list = null;
      listTag = "";
      continue;
    }
    if (trimmed.startsWith("|") && index + 1 < lines.length
        && /^[|\s:-]+$/.test(lines[index + 1].trim()) && lines[index + 1].includes("-")) {
      const parsed = compareTableNode(lines, index);
      container.append(parsed.table);
      index = parsed.next - 1;
      list = null;
      listTag = "";
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed);
    if (heading) {
      const node = element("h" + Math.min(heading[1].length, 3));
      appendCompareInline(node, heading[2].trim());
      container.append(node);
      list = null;
      listTag = "";
      continue;
    }
    if (trimmed.startsWith(">")) {
      const quote = element("blockquote");
      appendCompareInline(quote, trimmed.replace(/^>\s?/, ""));
      container.append(quote);
      list = null;
      listTag = "";
      continue;
    }
    const bullet = /^[-*]\s+(.*)$/.exec(trimmed);
    if (bullet) {
      if (!list || listTag !== "ul") {
        list = element("ul");
        listTag = "ul";
        container.append(list);
      }
      const item = element("li");
      appendCompareInline(item, bullet[1]);
      list.append(item);
      continue;
    }
    const ordered = /^\d+\.\s+(.*)$/.exec(trimmed);
    if (ordered) {
      if (!list || listTag !== "ol") {
        list = element("ol");
        listTag = "ol";
        container.append(list);
      }
      const item = element("li");
      appendCompareInline(item, ordered[1]);
      list.append(item);
      continue;
    }
    const paragraph = element("p");
    appendCompareInline(paragraph, trimmed);
    container.append(paragraph);
    list = null;
    listTag = "";
  }
}

function renderComparePreview() {
  const selected = compareEntries.filter((entry) => compareSelected.has(entry.entry_id));
  compareExport.disabled = selected.length < 2;
  if (selected.length < 2) {
    compareTable.replaceChildren(element("p", "file-empty", "选择至少 2 个方法查看对比表"));
    byId("compare-outline").replaceChildren(
      element("p", "file-empty", "选择至少 2 个方法后生成对比表和综述大纲。"));
    compareMarkdown = "";
    return;
  }
  const table = element("table", "compare-table");
  const head = element("thead");
  const headRow = element("tr");
  for (const title of ["方法", "研究场景", "关联概念", "推荐理由", "适用条件", "局限"]) {
    headRow.append(element("th", "", title));
  }
  head.append(headRow);
  const body = element("tbody");
  for (const entry of selected) {
    const row = element("tr");
    const method = element("td");
    method.append(element("strong", "", entry.method), element("small", "compare-id", entry.entry_id));
    row.append(
      method,
      element("td", "", entry.scenario || "—"),
      element("td", "", entry.concept || "—"),
      element("td", "", entry.rationale || "—"),
      element("td", "", entry.conditions || "—"),
      element("td", "", entry.limitations || "—"),
    );
    body.append(row);
  }
  table.append(head, body);
  compareTable.replaceChildren(table);
  compareMarkdown = comparisonMarkdown(selected);
  renderCompareMarkdown(compareMarkdown);
}

async function loadCompareEntries() {
  compareEntries = [];
  compareSelected = new Set();
  compareList.replaceChildren(element("p", "file-empty", "正在读取知识库…"));
  compareTable.replaceChildren();
  compareOutline.textContent = "";
  compareExport.disabled = true;
  try {
    const data = await request("/api/knowledge?case=" + encodeURIComponent(compareCase.value));
    compareEntries = data.entries;
    renderCompareList();
    renderComparePreview();
  } catch (error) {
    compareList.replaceChildren(element("p", "file-empty", error.message));
  }
}

function openCompare() {
  if (!ready || busy) return;
  compareCase.replaceChildren(...cases.map((item) => compareOption(item.code, item.label)));
  compareCase.value = cases.some((item) => item.code === active.case_code)
    ? active.case_code : cases[0]?.code || "";
  compareFilter.value = "";
  if (!byId("compare-dialog").open) byId("compare-dialog").showModal();
  loadCompareEntries();
}

function downloadComparison() {
  if (!compareMarkdown) return;
  const blob = new Blob([compareMarkdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = element("a", "sr-only");
  anchor.href = url;
  anchor.download = `方法对比-${compareCaseLabel()}.md`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

byId("project-dialog-new-chat").addEventListener("click", () => {
  const project = projectDashboardProject;
  if (!project) return;
  byId("project-dialog").close();
  newChatInProject(project);
});
byId("project-dialog-close").addEventListener("click", () => byId("project-dialog").close());
byId("show-compare").addEventListener("click", openCompare);
compareCase.addEventListener("change", loadCompareEntries);
compareFilter.addEventListener("input", renderCompareList);
compareExport.addEventListener("click", downloadComparison);
byId("compare-close").addEventListener("click", () => byId("compare-dialog").close());

const trashDialog = byId("trash-dialog");
const trashList = byId("trash-list");
const trashHint = byId("trash-hint");

function trashRow(kind, item) {
  const row = element("article", "trash-row");
  const main = element("div", "knowledge-main");
  const title = element("h3");
  title.append(
    element("span", "trash-kind", kind === "project" ? "项目" : "聊天"),
    " ",
    kind === "project" ? item.name : item.title,
  );
  main.append(title, element("p", "file-meta", "删除于 " + item.deleted_at));
  const actions = element("div", "candidate-actions");
  actions.append(button("file-action", "恢复", () => restoreTrash(kind, item)));
  actions.append(button("file-action", "永久删除", () => purgeTrash(kind, item)));
  row.append(main, actions);
  return row;
}

function renderTrash(data) {
  const count = data.projects.length + data.chats.length;
  trashHint.textContent = count ? `${count} 项已删除，可恢复或永久删除` : "回收站是空的";
  if (!count) {
    trashList.replaceChildren(element("p", "file-empty", "删除的聊天和项目会保留在这里"));
    return;
  }
  trashList.replaceChildren(
    ...data.projects.map((project) => trashRow("project", project)),
    ...data.chats.map((chat) => trashRow("chat", chat)),
  );
}

async function loadTrash() {
  trashHint.textContent = "正在读取…";
  trashList.replaceChildren(element("p", "file-empty", "正在读取回收站…"));
  try {
    renderTrash(await request("/api/workspace/trash"));
  } catch (error) {
    trashHint.textContent = error.message;
    trashList.replaceChildren(element("p", "file-empty", error.message));
  }
}

async function openTrash() {
  if (!ready || busy) return;
  if (!trashDialog.open) trashDialog.showModal();
  await loadTrash();
}

async function restoreTrash(kind, item) {
  if (busy) return;
  setBusy(true);
  try {
    await request(`${API}/${kind === "project" ? "projects" : "chats"}/${item.id}/restore`, {});
    if (kind === "project") expandedProjects.add(item.id);
    await refreshSidebar();
    await loadTrash();
    note("已从回收站恢复", "success");
  } catch (error) {
    trashHint.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function purgeTrash(kind, item) {
  const name = kind === "project" ? item.name : item.title;
  if (busy || !confirm(`永久删除「${name}」？此操作无法恢复。`)) return;
  setBusy(true);
  try {
    await request(`${API}/${kind === "project" ? "projects" : "chats"}/${item.id}/purge`, {});
    await refreshSidebar();
    await loadTrash();
    note("已永久删除", "success");
  } catch (error) {
    trashHint.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

byId("project-report").addEventListener("click", () => {
  const project = projectDashboardProject;
  if (!project) return;
  const anchor = element("a", "sr-only");
  anchor.href = `${API}/projects/${project.id}/report`;
  anchor.download = "";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
});
byId("show-trash").addEventListener("click", openTrash);
byId("trash-close").addEventListener("click", () => trashDialog.close());
