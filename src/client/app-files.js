// Files: upload, drag and drop, preview, download and removal.

function visibleFiles() {
  return files.filter((file) => (active.id && file.chat_id === active.id) ||
    (active.project_id && file.project_id === active.project_id));
}

function dialogFiles() {
  return fileDialogProject ? files.filter((file) => file.project_id === fileDialogProject) : visibleFiles();
}

function readableSize(size) {
  if (size < 1024) return size + " B";
  if (size < 1024 * 1024) return Math.round(size / 1024) + " KB";
  return (size / (1024 * 1024)).toFixed(1) + " MB";
}

function fileDownload(id) {
  const anchor = element("a", "file-action", "下载");
  anchor.href = API + "/files/" + encodeURIComponent(id) + "/download";
  anchor.download = "";
  return anchor;
}

function renderFileSurfaces() {
  const available = visibleFiles();
  const count = byId("file-count");
  count.hidden = !available.length;
  count.textContent = available.length || "";
  byId("show-files").setAttribute("aria-label", available.length ? `查看文件，${available.length} 份` : "查看文件");
  const chips = byId("attached-files");
  const attached = active.id ? available.filter((file) => file.chat_id === active.id) : [];
  chips.replaceChildren(...attached.map((file) =>
    button("file-chip", file.name, () => openFiles(file.id)),
  ));
  chips.hidden = !attached.length;
  const dialog = byId("files-dialog");
  if (dialog.open) renderFileList();
}

function renderFileList() {
  const project = projects.find((item) => item.id === fileDialogProject);
  const projectScope = fileDialogProject || active.project_id;
  byId("files-dialog-title").textContent = project ? project.name + " · 项目资料" : "文件资料";
  byId("file-manager-upload").textContent = projectScope ? "上传到项目" : "上传到对话";
  byId("file-list-hint").textContent = projectScope
    ? "项目中的对话可使用这些资料，每个文件最多 5 MB"
    : "资料保存在这条对话中，每个文件最多 5 MB";
  const list = byId("file-list");
  list.replaceChildren();
  const available = dialogFiles();
  if (!available.length) {
    list.append(element("p", "file-empty", "还没有资料，可以先上传文档、数据表或图片"));
    return;
  }
  for (const file of available) {
    const row = element("div", "file-row");
    row.dataset.fileId = file.id;
    if (byId("file-preview").dataset.fileId === file.id) row.classList.add("is-selected");
    const main = element("div", "file-row-main");
    const name = button("file-action file-name", file.name, () => showFile(file.id));
    name.title = file.name;
    main.append(name, element("p", "file-meta", (file.chat_id ? "对话资料" : "项目资料") + " · " + readableSize(file.size)));
    const actions = element("div", "file-row-actions");
    actions.append(fileDownload(file.id), button("file-action file-remove", "移除", () => removeFile(file)));
    row.append(main, actions);
    list.append(row);
  }
  updateControls();
}

function clearPreview() {
  previewVersion += 1;
  delete byId("file-preview").dataset.fileId;
  byId("file-list").querySelector(".is-selected")?.classList.remove("is-selected");
  byId("file-preview-title").textContent = "文件预览";
  byId("file-preview").replaceChildren(element("p", "file-empty", "选择一份资料查看内容"));
}

function openFiles(id, projectId = null) {
  const dialog = byId("files-dialog");
  if (typeof dialog.showModal !== "function") return;
  if (!dialog.open) {
    fileDialogProject = projectId;
    closeNavigation(false);
    clearPreview();
    dialog.showModal();
    renderFileList();
  }
  if (id) showFile(id);
}

async function showFile(id) {
  const stamp = ++previewVersion;
  const title = byId("file-preview-title");
  const preview = byId("file-preview");
  preview.dataset.fileId = id;
  for (const row of byId("file-list").querySelectorAll(".file-row")) {
    row.classList.toggle("is-selected", row.dataset.fileId === id);
  }
  const known = files.find((file) => file.id === id);
  title.textContent = known?.name || "文件预览";
  preview.replaceChildren(element("p", "file-empty", "正在读取资料…"));
  try {
    const { file, text, kind } = await request(API + "/files/" + id);
    if (stamp !== previewVersion) return;
    title.textContent = file.name;
    if (kind === "image") {
      const image = element("img", "file-preview-image");
      image.src = API + "/files/" + encodeURIComponent(id) + "/raw";
      image.alt = file.name;
      image.addEventListener("error", () => {
        preview.replaceChildren(element("p", "file-empty", "图片无法显示，可以下载后用本机应用查看"), fileDownload(id));
      });
      preview.replaceChildren(image, fileDownload(id));
    } else {
      const empty = kind === "pdf"
        ? "PDF 未能提取可检索文本，可以下载后用本机应用查看"
        : "可以下载后用本机应用查看";
      preview.replaceChildren(text
        ? element("pre", "file-preview-text", text)
        : element("p", "file-empty", empty), fileDownload(id));
    }
  } catch (error) {
    if (stamp === previewVersion) preview.replaceChildren(element("p", "notice", error.message));
  }
}

async function removeFile(file) {
  if (busy || !confirm("从工作台移除「" + file.name + "」？")) return;
  setBusy(true);
  try {
    await request(API + "/files/" + file.id + "/remove", {});
    files = files.filter((item) => item.id !== file.id);
    clearPreview();
    renderFileSurfaces();
  } catch (error) {
    byId("file-list-hint").textContent = error.message;
  } finally {
    setBusy(false);
  }
}

function chooseFiles(scope) {
  if (!ready || busy) return;
  uploadScope = scope;
  byId("upload-input").click();
}

function fileBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(reader.result.split(",", 2)[1]));
    reader.addEventListener("error", () => reject(new Error("无法读取该文件")));
    reader.readAsDataURL(file);
  });
}

async function uploadFiles(picked, scope) {
  if (!ready || busy || !picked.length) return;
  const projectId = scope === "project" ? (fileDialogProject || active.project_id) : null;
  const validation = picked.filter((file) => file.size > 0 && file.size <= MAX_UPLOAD);
  const errors = picked.filter((file) => !validation.includes(file))
    .map((file) => file.name + " 为空或超过 5 MB");
  setBusy(true);
  let succeeded = 0;
  const inDialog = byId("files-dialog").open;
  const report = (message, kind) => {
    if (inDialog && byId("files-dialog").open) byId("file-list-hint").textContent = message;
    else note(message, kind);
  };
  report("正在上传 " + picked.length + " 份资料…", "progress");
  try {
    const destination = validation.length
      ? (projectId ? { project_id: projectId } : { chat_id: await ensureActiveChat() }) : {};
    for (const file of validation) {
      try {
        const result = await request(API + "/files", { ...destination, name: file.name, data: await fileBase64(file) });
        files.unshift(result.file);
        succeeded += 1;
      } catch (error) {
        errors.push(file.name + " " + error.message);
      }
    }
  } catch (error) {
    errors.push(error.message);
  } finally {
    renderFileSurfaces();
    setBusy(false);
    if (errors.length) report([...(succeeded ? ["已上传 " + succeeded + " 份"] : []), ...errors].join(" · "), "error");
    else report("已上传 " + succeeded + " 份资料", "success");
  }
}

byId("upload-input").addEventListener("change", (event) => {
  const picked = [...event.target.files];
  event.target.value = "";
  uploadFiles(picked, uploadScope);
});

const workspace = byId("workspace");
let dragDepth = 0;
const hasDraggedFiles = (event) => event.dataTransfer?.types.includes("Files");
const canDropFiles = () => ready && !busy && !workspace.inert && !document.querySelector("dialog[open]");
workspace.addEventListener("dragenter", (event) => {
  if (!hasDraggedFiles(event) || !canDropFiles()) return;
  dragDepth += 1;
  workspace.classList.add("is-file-drop");
});
workspace.addEventListener("dragleave", () => {
  if (dragDepth > 0) dragDepth -= 1;
  if (!dragDepth) workspace.classList.remove("is-file-drop");
});
document.addEventListener("dragover", (event) => {
  if (!hasDraggedFiles(event)) return;
  event.preventDefault();
  const accepts = workspace.contains(event.target) && canDropFiles();
  event.dataTransfer.dropEffect = accepts ? "copy" : "none";
});
document.addEventListener("drop", (event) => {
  if (!hasDraggedFiles(event)) return;
  event.preventDefault();
  dragDepth = 0;
  workspace.classList.remove("is-file-drop");
  if (workspace.contains(event.target) && canDropFiles()) uploadFiles([...event.dataTransfer.files], "chat");
});
