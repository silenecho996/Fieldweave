// Whitelisted method-document collection and reading.

const methodDocsDialog = byId("method-docs-dialog");
const methodDocsSource = byId("method-docs-source");
const methodDocsCase = byId("method-docs-case");
const methodDocsCollect = byId("collect-method-docs");
const methodDocsMessage = byId("method-docs-message");
const methodDocsList = byId("method-docs-list");
const methodDocsDetail = byId("method-docs-detail");
let methodDocsSources = [];
let methodDocs = [];
let methodDocCurrent = null;
let methodDocsBusy = false;

function methodDocCaseLabel(code) {
  return cases.find((item) => item.code === code)?.label || code;
}

function methodDocDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("zh-CN");
}

function methodDocLink(url, label) {
  if (typeof url !== "string" || !url.startsWith("https://")) return null;
  const link = element("a", "file-action", label);
  link.href = url;
  link.target = "_blank";
  link.rel = "noreferrer noopener";
  return link;
}

function setMethodDocsBusy(value) {
  methodDocsBusy = value;
  methodDocsSource.disabled = value;
  methodDocsCase.disabled = value;
  methodDocsCollect.disabled = value;
  methodDocsCollect.textContent = value ? "正在采集…" : "采集方法文档";
}

function fillMethodDocCases() {
  const previous = methodDocsCase.value;
  methodDocsCase.replaceChildren(...cases.map((item) => {
    const option = element("option", "", item.label);
    option.value = item.code;
    return option;
  }));
  if (previous && cases.some((item) => item.code === previous)) {
    methodDocsCase.value = previous;
  } else {
    methodDocsCase.value = cases.some((item) => item.code === active.case_code)
      ? active.case_code : (cases[0]?.code || "");
  }
}

function fillMethodDocSources() {
  const previous = methodDocsSource.value;
  methodDocsSource.replaceChildren(...methodDocsSources.map((source) => {
    const option = element("option", "", source.label + " · " + source.domain);
    option.value = source.key;
    return option;
  }));
  if (previous && methodDocsSources.some((item) => item.key === previous)) {
    methodDocsSource.value = previous;
  }
}

async function loadMethodDocSources() {
  if (methodDocsSources.length) return;
  try {
    const data = await request("/api/method-docs/sources");
    methodDocsSources = data.sources || [];
    fillMethodDocSources();
  } catch (error) {
    methodDocsMessage.textContent = error.message;
  }
}

function methodDocPlaceholder(message) {
  methodDocsDetail.replaceChildren(element("p", "file-empty", message));
}

function renderMethodDocs() {
  if (!methodDocs.length) {
    methodDocsList.replaceChildren(element("p", "file-empty", "还没有采集方法文档"));
    return;
  }
  methodDocsList.replaceChildren(...methodDocs.map((document) => {
    const row = button("method-doc-row", null, () => selectMethodDoc(document.id));
    row.setAttribute("aria-pressed", String(methodDocCurrent?.id === document.id));
    row.append(
      element("strong", "", document.title),
      element("small", "",
        [document.source_label, methodDocCaseLabel(document.case_code),
          methodDocDate(document.fetched_at)].filter(Boolean).join(" · ")),
      element("p", "file-meta", document.excerpt || ""),
    );
    return row;
  }));
}

async function loadMethodDocs() {
  const code = methodDocsCase.value;
  try {
    const data = await request("/api/method-docs?case=" + encodeURIComponent(code));
    methodDocs = data.documents || [];
    renderMethodDocs();
  } catch (error) {
    methodDocsMessage.textContent = error.message;
    methodDocsList.replaceChildren(element("p", "file-empty", error.message));
  }
}

async function loadMethodDocRunStatus() {
  try {
    const data = await request("/api/method-docs/runs?limit=1");
    const run = data.runs?.[0];
    if (!run) return;
    const source = methodDocsSources.find((item) => item.key === run.source);
    methodDocsMessage.textContent =
      `上次采集：${source?.label || run.source} / ${run.case_code}`
      + ` · 新增 ${run.created}，更新 ${run.updated}`
      + (run.errors?.length ? `，${run.errors.length} 个页面失败` : "");
  } catch {
    // The list still works when run history is unavailable.
  }
}

function renderMethodDoc(document) {
  methodDocCurrent = document;
  methodDocsDetail.replaceChildren();
  const head = element("div", "method-doc-head");
  const title = element("h3", "", document.title);
  const meta = element("p", "file-meta", [
    document.source_label, methodDocCaseLabel(document.case_code),
    methodDocDate(document.fetched_at),
  ].filter(Boolean).join(" · "));
  const actions = element("div", "method-doc-actions");
  const sourceLink = methodDocLink(document.url, "打开来源");
  if (sourceLink) actions.append(sourceLink);
  actions.append(button("file-action", "生成候选条目", () => generateMethodDocCandidates(document)));
  actions.append(button("file-action", "移出", () => removeMethodDoc(document)));
  head.append(title, meta, actions);
  methodDocsDetail.append(head, element("pre", "method-doc-text", document.text));
  methodDocsDetail.scrollTop = 0;
}

async function selectMethodDoc(id) {
  if (methodDocsBusy) return;
  try {
    const data = await request("/api/method-docs/" + id);
    renderMethodDoc(data.document);
    renderMethodDocs();
  } catch (error) {
    methodDocsMessage.textContent = error.message;
  }
}

async function generateMethodDocCandidates(document) {
  if (methodDocsBusy) return;
  if (!modelConfigured) {
    methodDocsMessage.textContent = "请先在 API 设置中配置模型，再生成候选条目";
    return;
  }
  setMethodDocsBusy(true);
  methodDocsMessage.textContent = "正在从方法文档生成候选条目，可能需要几十秒…";
  try {
    const result = await request(`/api/method-docs/${document.id}/candidates`, {
      case: methodDocsCase.value,
    });
    methodDocsMessage.textContent =
      `生成候选：新增 ${result.created.length} 条，跳过重复 ${result.skipped.length} 条`;
    if (result.created.length) note("候选条目已生成，可在「工具 → 待核对条目」审核", "success");
  } catch (error) {
    methodDocsMessage.textContent = error.message;
  } finally {
    setMethodDocsBusy(false);
  }
}

async function removeMethodDoc(document) {
  if (methodDocsBusy) return;
  if (!window.confirm(`确认移出「${document.title}」？`)) return;
  setMethodDocsBusy(true);
  try {
    await request(`/api/method-docs/${document.id}/remove`, {});
    if (methodDocCurrent?.id === document.id) {
      methodDocCurrent = null;
      methodDocPlaceholder("选择一份方法文档查看正文");
    }
    await loadMethodDocs();
    methodDocsMessage.textContent = "方法文档已移出";
  } catch (error) {
    methodDocsMessage.textContent = error.message;
  } finally {
    setMethodDocsBusy(false);
  }
}

async function openMethodDocs() {
  if (!ready || busy) return;
  fillMethodDocCases();
  if (!methodDocsDialog.open) methodDocsDialog.showModal();
  methodDocsMessage.textContent = "仅采集配置中的白名单站点，并遵守 robots.txt";
  await loadMethodDocSources();
  await loadMethodDocs();
  await loadMethodDocRunStatus();
  if (!methodDocCurrent) {
    methodDocPlaceholder("选择一份方法文档查看正文");
  }
}

byId("show-method-docs").addEventListener("click", openMethodDocs);
byId("method-docs-close").addEventListener("click", () => methodDocsDialog.close());
methodDocsCase.addEventListener("change", () => {
  methodDocCurrent = null;
  methodDocPlaceholder("选择一份方法文档查看正文");
  loadMethodDocs();
});
methodDocsCollect.addEventListener("click", async () => {
  if (!ready || busy || methodDocsBusy) return;
  const source = methodDocsSource.value;
  const caseCode = methodDocsCase.value;
  if (!source || !caseCode) {
    methodDocsMessage.textContent = "请选择文档来源和研究案例";
    return;
  }
  setMethodDocsBusy(true);
  methodDocsMessage.textContent = "正在按白名单顺序抓取方法文档，可能需要几十秒…";
  try {
    const result = await request("/api/method-docs/collect", {
      source, case: caseCode,
    });
    const suffix = result.errors?.length
      ? `，${result.errors.length} 个页面未采集：${result.errors[0]}` : "";
    methodDocsMessage.textContent =
      `采集完成：找到 ${result.found} 页，新增 ${result.added}，更新 ${result.updated}${suffix}`;
    await loadMethodDocs();
    setMethodDocsBusy(false);
    if (result.documents?.length) {
      await selectMethodDoc(result.documents[0].id);
    }
  } catch (error) {
    methodDocsMessage.textContent = error.message;
  } finally {
    setMethodDocsBusy(false);
  }
});
