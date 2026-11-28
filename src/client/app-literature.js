// Literature: collection, listing and detail views.

const literatureDialog = byId("literature-dialog");
const literatureCase = byId("literature-case");
const literatureKinds = byId("literature-kinds");
const literatureMessage = byId("literature-message");
const literatureQuery = byId("literature-query");
const literatureCollect = byId("collect-literature");
const literatureList = byId("literature-list");
const literatureDetail = byId("literature-detail");
const literatureExport = byId("literature-export");
const literatureExpand = byId("expand-literature");
const literatureGenerate = byId("generate-candidates");
const candidateDialog = byId("candidate-dialog");
const candidateForm = byId("candidate-form");
const candidatesDialog = byId("candidates-dialog");
const candidatesList = byId("candidates-list");
const candidatesHint = byId("candidates-hint");
let literatureRevision = 0;
let literatureSelection = "";
let collectingLiterature = false;
let candidateArticle = null;
let literatureTotal = 0;
let literatureLoadingMore = false;
const LITERATURE_PAGE_SIZE = 30;

function articleLink(url, label) {
  if (typeof url !== "string" || !url.startsWith("https://")) return null;
  const link = element("a", "file-action", label);
  link.href = url;
  link.target = "_blank";
  link.rel = "noreferrer noopener";
  return link;
}

function articleDetails(article) {
  const title = element("h3", "", article.title);
  const meta = element("p", "file-meta", [
    article.journal || article.venue, article.year, article.provider,
    article.citation_count ? "引用 " + article.citation_count : "",
    article.open_access ? "开放获取" : "",
  ].filter(Boolean).join(" · "));
  const topics = article.topics?.length
    ? element("p", "file-meta", "主题：" + article.topics.join(" · "))
    : null;
  const links = element("div", "reference-links");
  for (const link of [
    articleLink(article.url, "查看来源"),
    articleLink(article.doi ? "https://doi.org/" + article.doi.split("/").map(encodeURIComponent).join("/") : "", "DOI"),
  ]) {
    if (link) links.append(link);
  }
  const summary = element("section", "literature-abstract");
  const dataset = article.provider === "Zenodo";
  summary.append(element("h4", "", dataset ? "数据说明" : "摘要"),
    element("p", "", article.abstract || "来源未提供说明"));
  literatureDetail.replaceChildren(title, meta);
  if (topics) literatureDetail.append(topics);
  if (article.authors) literatureDetail.append(element("p", "file-meta", article.authors));
  literatureDetail.append(links, summary);
  if (dataset) {
    literatureDetail.append(datasetFiles(article));
    return;
  }
  if (article.fulltext) {
    const fulltext = element("details", "literature-fulltext");
    fulltext.append(element("summary", "", "已入库的开放全文"));
    const license = articleLink(article.fulltext.license, "查看开放许可");
    if (license) fulltext.append(license);
    if (article.fulltext.license_text) fulltext.append(element("p", "file-meta", article.fulltext.license_text));
    fulltext.append(element("p", "literature-text", article.fulltext.text));
    literatureDetail.append(fulltext);
  } else if (article.can_fetch) {
    const download = button("file-action", "采集开放全文", async () => {
      download.disabled = true;
      const progress = element("p", "file-meta", "正在采集全文…");
      download.after(progress);
      try {
        const updated = await request("/api/literature/" + article.id + "/fulltext", {});
        if (literatureSelection === article.id) {
          articleDetails(updated);
          literatureDetail.querySelector("details").open = true;
        }
      } catch (error) {
        progress.textContent = error.message;
      } finally {
        download.disabled = false;
      }
    });
    literatureDetail.append(download);
  }
  literatureDetail.append(
    button("file-action", "生成候选条目", () => generateCandidates([article.id])),
    button("file-action", "加入待核对条目", () => openCandidate(article, literatureCase.value)),
  );
}

function datasetFiles(dataset) {
  const section = element("section", "literature-data-files");
  section.append(element("h4", "", "原始文件"));
  if (dataset.license) section.append(element("p", "file-meta", "许可 " + dataset.license.toUpperCase()));
  if (!dataset.files.length) section.append(element("p", "file-meta", "来源未列出可用文件"));
  for (const file of dataset.files) {
    const row = element("div", "literature-file-row");
    const meta = element("div", "");
    meta.append(element("strong", "", file.name), element("small", "file-meta", readableSize(file.size)));
    row.append(meta);
    const endpoint = "/api/literature/" + dataset.id + "/files/" + file.id;
    if (file.imported) {
      const link = element("a", "file-action", "下载已入库文件");
      link.href = endpoint;
      row.append(link);
    } else if (file.can_import) {
      const status = element("p", "file-meta");
      const save = button("file-action", "采集原始文件", async () => {
        status.textContent = "下载并校验中…";
        save.disabled = true;
        try {
          const updated = await request(endpoint, {});
          if (literatureSelection === dataset.id) articleDetails(updated);
        } catch (error) {
          status.textContent = error.message;
        } finally {
          save.disabled = false;
        }
      });
      row.append(save, status);
    } else {
      const source = articleLink(dataset.url, "前往来源");
      if (source) row.append(source);
    }
    section.append(row);
  }
  return section;
}

async function selectArticle(id) {
  literatureSelection = id;
  for (const row of literatureList.querySelectorAll("button")) {
    row.setAttribute("aria-pressed", String(row.dataset.id === id));
  }
  literatureDetail.replaceChildren(element("p", "file-empty", "正在读取文献…"));
  try {
    const article = await request("/api/literature/" + id);
    if (literatureSelection === id) articleDetails(article);
  } catch (error) {
    if (literatureSelection === id) literatureDetail.replaceChildren(element("p", "file-empty", error.message));
  }
}

function literatureRow(article) {
  const row = button("literature-row", null, () => selectArticle(article.id));
  row.dataset.id = article.id;
  row.setAttribute("aria-pressed", "false");
  row.append(element("strong", "", article.title),
    element("small", "file-meta", [
      article.year, article.provider,
      article.citation_count ? "引用 " + article.citation_count : "",
      article.open_access ? "开放获取" : "",
      article.has_fulltext ? "已有全文" : "",
    ].filter(Boolean).join(" · ")));
  return row;
}

function appendLiteratureRows(articles) {
  for (const article of articles) literatureList.append(literatureRow(article));
}

function appendLiteratureMore(data) {
  literatureList.querySelector(".literature-more-button")?.remove();
  if (!data.has_more) return;
  const loaded = literatureList.querySelectorAll("button[data-id]").length;
  const more = button("secondary-button literature-more-button",
    `加载更多（已显示 ${loaded} / ${data.total}）`, loadMoreLiterature);
  more.type = "button";
  literatureList.append(more);
}

async function loadMoreLiterature() {
  if (literatureLoadingMore) return;
  const revision = literatureRevision;
  const code = literatureCase.value;
  const kind = literatureKinds.querySelector(":checked").value;
  const loaded = literatureList.querySelectorAll("button[data-id]").length;
  literatureLoadingMore = true;
  literatureList.querySelector(".literature-more-button")?.setAttribute("disabled", "true");
  try {
    const query = "?case=" + encodeURIComponent(code)
      + "&kind=" + kind + "&limit=" + LITERATURE_PAGE_SIZE + "&offset=" + loaded;
    const data = await request("/api/literature" + query);
    if (revision !== literatureRevision) return;
    literatureTotal = data.total;
    appendLiteratureRows(data.articles);
    appendLiteratureMore(data);
    literatureMessage.textContent = [
      "来源 " + data.provider,
      `已加载 ${literatureList.querySelectorAll("button[data-id]").length} / ${data.total}`,
    ].join(" · ");
  } catch (error) {
    if (revision === literatureRevision) literatureMessage.textContent = error.message;
  } finally {
    literatureLoadingMore = false;
    literatureList.querySelector(".literature-more-button")?.removeAttribute("disabled");
  }
}

async function refreshLiterature({ message = "", selection = "" } = {}) {
  const revision = ++literatureRevision;
  const code = literatureCase.value;
  const kind = literatureKinds.querySelector(":checked").value;
  const dataset = kind === "dataset";
  literatureSelection = "";
  literatureTotal = 0;
  literatureLoadingMore = false;
  literatureCollect.disabled = true;
  literatureExport.hidden = true;
  literatureList.replaceChildren();
  literatureDetail.replaceChildren(element("p", "file-empty", dataset ? "选择一个数据集查看文件" : "选择一篇文献查看详情"));
  literatureMessage.textContent = "正在读取本地记录…";
  try {
    const query = "?case=" + encodeURIComponent(code) + "&kind=" + kind;
    const pageQuery = query + "&limit=" + LITERATURE_PAGE_SIZE + "&offset=0";
    const data = await request("/api/literature" + pageQuery);
    if (revision !== literatureRevision) return;
    literatureTotal = data.total;
    literatureQuery.placeholder = data.default_query.replaceAll('"', "");
    literatureMessage.textContent = [message, "来源 " + data.provider,
      "已入库 " + data.total + (dataset ? " 个数据集" : " 篇")].filter(Boolean).join(" · ");
    literatureExport.hidden = !data.total;
    literatureExport.href = "/api/literature/export" + query;
    literatureCollect.disabled = collectingLiterature;
    literatureExpand.disabled = collectingLiterature || dataset;
    literatureGenerate.disabled = collectingLiterature || dataset || !data.total;
    if (!data.articles.length) {
      literatureList.append(element("p", "file-empty", "暂无记录，可直接用默认检索词开始采集"));
    }
    appendLiteratureRows(data.articles);
    appendLiteratureMore(data);
    if (selection && data.articles.some((article) => article.id === selection)) await selectArticle(selection);
  } catch (error) {
    if (revision === literatureRevision) literatureMessage.textContent = error.message;
  }
}

function openLiterature(caseCode = active.case_code, selection = "") {
  literatureCase.replaceChildren(...cases.map((item) => {
    const option = element("option", "", item.label);
    option.value = item.code;
    return option;
  }));
  literatureCase.value = caseCode;
  if (!literatureCase.value) literatureCase.selectedIndex = 0;
  literatureQuery.value = "";
  if (selection) literatureKinds.querySelector('[value="article"]').checked = true;
  if (!literatureDialog.open) literatureDialog.showModal();
  refreshLiterature({ selection });
}

byId("show-literature").addEventListener("click", () => openLiterature());
byId("literature-close").addEventListener("click", () => literatureDialog.close());
literatureCase.addEventListener("change", () => {
  literatureQuery.value = "";
  refreshLiterature();
});
literatureKinds.addEventListener("change", () => {
  literatureQuery.value = "";
  refreshLiterature();
});
byId("literature-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (collectingLiterature) return;
  const caseCode = literatureCase.value;
  const kind = literatureKinds.querySelector(":checked").value;
  collectingLiterature = true;
  literatureCollect.disabled = true;
  literatureExpand.disabled = true;
  literatureGenerate.disabled = true;
  literatureCase.disabled = true;
  literatureKinds.disabled = true;
  literatureMessage.textContent = "正在检索公开来源并写入本地库…";
  try {
    const result = await request("/api/literature/collect", {
      case: caseCode, kind, query: literatureQuery.value, limit: Number(byId("literature-limit").value),
    });
    const unit = kind === "dataset" ? " 个数据集" : " 篇";
    const message = "采集 " + result.found + unit + "，新增 " + result.added + unit;
    await refreshLiterature({ message });
  } catch (error) {
    literatureMessage.textContent = error.message;
  } finally {
    collectingLiterature = false;
    literatureCase.disabled = false;
    literatureKinds.disabled = false;
    literatureCollect.disabled = false;
    literatureExpand.disabled = literatureKinds.querySelector(":checked").value === "dataset";
    literatureGenerate.disabled = literatureKinds.querySelector(":checked").value === "dataset";
  }
});

literatureExpand.addEventListener("click", async () => {
  if (collectingLiterature) return;
  const kind = literatureKinds.querySelector(":checked").value;
  if (kind !== "article") {
    literatureMessage.textContent = "批量扩展只用于论文";
    return;
  }
  collectingLiterature = true;
  literatureCollect.disabled = true;
  literatureExpand.disabled = true;
  literatureGenerate.disabled = true;
  literatureCase.disabled = true;
  literatureKinds.disabled = true;
  literatureMessage.textContent = "正在从多个公开来源批量扩展文献，可能需要几十秒…";
  try {
    const result = await request("/api/literature/expand", {
      case: literatureCase.value, limit_per_query: 4,
    });
    const counts = Object.entries(result.provider_counts || {})
      .map(([name, value]) => `${name} ${value}`).join("，");
    const suffix = result.errors?.length ? `；部分来源未完成：${result.errors[0]}` : "";
    await refreshLiterature({
      message: `扩展完成：找到 ${result.found} 篇，新增 ${result.added} 篇（${counts}）${suffix}`,
    });
  } catch (error) {
    literatureMessage.textContent = error.message;
  } finally {
    collectingLiterature = false;
    literatureCase.disabled = false;
    literatureKinds.disabled = false;
    literatureCollect.disabled = false;
    literatureExpand.disabled = literatureKinds.querySelector(":checked").value === "dataset";
    literatureGenerate.disabled = literatureKinds.querySelector(":checked").value === "dataset";
  }
});

async function generateCandidates(articleIds) {
  if (collectingLiterature || !articleIds.length) return;
  if (!modelConfigured) {
    literatureMessage.textContent = "请先在 API 设置中配置模型，再生成候选条目";
    return;
  }
  collectingLiterature = true;
  literatureCollect.disabled = true;
  literatureExpand.disabled = true;
  literatureGenerate.disabled = true;
  literatureCase.disabled = true;
  literatureKinds.disabled = true;
  let created = 0;
  let skipped = 0;
  let failed = 0;
  try {
    for (const [index, articleId] of articleIds.entries()) {
      literatureMessage.textContent =
        `正在从文献生成候选 ${index + 1}/${articleIds.length}，可能需要几十秒…`;
      try {
        const result = await request(`/api/literature/${articleId}/candidates`, {
          case: literatureCase.value,
        });
        created += result.created.length;
        skipped += result.skipped.length;
      } catch (error) {
        failed += 1;
        if (error.message.includes("配置模型")) {
          literatureMessage.textContent = error.message;
          return;
        }
      }
    }
    literatureMessage.textContent =
      `生成候选：新增 ${created} 条，跳过重复 ${skipped} 条`
      + (failed ? `，失败 ${failed} 篇` : "");
    if (created) note("候选条目已生成，可在「工具 → 待核对条目」审核", "success");
  } finally {
    collectingLiterature = false;
    literatureCase.disabled = false;
    literatureKinds.disabled = false;
    literatureCollect.disabled = false;
    literatureExpand.disabled = literatureKinds.querySelector(":checked").value === "dataset";
    literatureGenerate.disabled = literatureKinds.querySelector(":checked").value === "dataset";
  }
}

literatureGenerate.addEventListener("click", () => {
  const ids = [...literatureList.querySelectorAll("button[data-id]")]
    .slice(0, 3).map((row) => row.dataset.id);
  if (!ids.length) {
    literatureMessage.textContent = "当前列表还没有文献，请先采集";
    return;
  }
  generateCandidates(ids);
});

function caseLabel(code) {
  return cases.find((item) => item.code === code)?.label || code;
}

let candidateEditing = null;

const CANDIDATE_STATUS = {
  pending: "待核对",
  approved: "已通过",
  rejected: "已驳回",
  merged: "已入库",
};

function candidateStatusText(item) {
  return CANDIDATE_STATUS[item.status] || "待核对";
}

function fillCandidateForm(item, source) {
  byId("candidate-source").textContent = source;
  byId("candidate-scenario").value = item.scenario || "";
  byId("candidate-concept").value = item.concept || "";
  byId("candidate-method").value = item.method || "";
  byId("candidate-rationale").value = item.rationale || "";
  byId("candidate-conditions").value = item.conditions || "";
  byId("candidate-limitations").value = item.limitations || "";
  byId("candidate-evidence").value = item.evidence || "";
  byId("candidate-notes").value = item.notes || "";
  byId("candidate-error").hidden = true;
}

function openCandidate(article, caseCode) {
  candidateEditing = null;
  candidateArticle = { article, caseCode };
  const abstract = (article.abstract || "").trim();
  const evidence = [article.authors, article.year, article.journal,
    article.doi ? "DOI " + article.doi : "", article.url].filter(Boolean).join(" · ");
  fillCandidateForm({
    scenario: abstract.slice(0, 600),
    evidence: (evidence + (abstract ? "\n摘要：" + abstract.slice(0, 1200) : "")).trim(),
  }, "来源：" + article.title);
  if (!candidateDialog.open) candidateDialog.showModal();
  byId("candidate-scenario").focus();
}

function openCandidateEditor(item) {
  candidateEditing = item;
  candidateArticle = null;
  fillCandidateForm(item, "编辑候选条目：" + item.title);
  if (!candidateDialog.open) candidateDialog.showModal();
  byId("candidate-method").focus();
}

function candidatePayload() {
  if (!candidateEditing && !candidateArticle) return null;
  const source = candidateEditing
    ? {
      article_id: candidateEditing.article_id,
      case_code: candidateEditing.case_code,
      title: candidateEditing.title,
    }
    : {
      article_id: candidateArticle.article.id,
      case_code: candidateArticle.caseCode,
      title: candidateArticle.article.title,
    };
  return {
    ...source,
    scenario: byId("candidate-scenario").value.trim(),
    concept: byId("candidate-concept").value.trim(),
    method: byId("candidate-method").value.trim(),
    rationale: byId("candidate-rationale").value.trim(),
    conditions: byId("candidate-conditions").value.trim(),
    limitations: byId("candidate-limitations").value.trim(),
    evidence: byId("candidate-evidence").value.trim(),
    notes: byId("candidate-notes").value.trim(),
  };
}

function renderCandidates(items) {
  const approved = items.filter((item) => item.status === "approved" && !item.merged_entry_id).length;
  const mergeButton = byId("merge-candidates");
  mergeButton.disabled = !approved;
  mergeButton.textContent = approved ? `合并已通过 (${approved})` : "合并已通过";
  candidatesHint.textContent = items.length
    ? `${items.length} 条 · 已通过 ${approved}`
    : "还没有待核对条目";
  if (!items.length) {
    candidatesList.replaceChildren(element("p", "file-empty", "在文献详情中点击「加入待核对条目」"));
    return;
  }
  candidatesList.replaceChildren(...items.map((item) => {
    const row = element("article", "candidate-row");
    const main = element("div", "candidate-main");
    const title = element("h3");
    title.append(item.title, " ",
      element("span", "candidate-status is-" + (item.status || "pending"), candidateStatusText(item)));
    main.append(
      title,
      element("p", "file-meta", [caseLabel(item.case_code), item.method, item.concept]
        .filter(Boolean).join(" · ")),
      element("p", "", item.scenario),
    );
    if (item.rationale) main.append(element("p", "file-meta", item.rationale));
    if (item.review_note) main.append(element("p", "candidate-review-note", "审核备注：" + item.review_note));
    if (item.merged_entry_id) {
      main.append(element("p", "candidate-merged", "已入库条目：[" + item.merged_entry_id + "]"));
    }
    const actions = element("div", "candidate-actions");
    if (item.status !== "merged") {
      if (item.status !== "approved") {
        actions.append(button("file-action", "通过", () => reviewCandidate(item, "approved")));
      }
      if (item.status !== "rejected") {
        actions.append(button("file-action", "驳回", () => reviewCandidate(item, "rejected")));
      }
      if (item.status !== "pending") {
        actions.append(button("file-action", "设为待核对", () => reviewCandidate(item, "pending")));
      }
      actions.append(button("file-action", "编辑", () => openCandidateEditor(item)));
      actions.append(button("file-action", "移除", () => removeCandidate(item)));
    }
    row.append(main, actions);
    return row;
  }));
}

async function refreshCaseCatalog() {
  const catalog = await request("/api/cases");
  cases = catalog.cases;
  modelConfigured = catalog.model_configured;
  byId("cases").replaceChildren(...cases.map(caseButton));
  renderContext();
  updateControls();
  saveTab();
}

async function openCandidates() {
  if (!candidatesDialog.open) candidatesDialog.showModal();
  byId("candidate-versions").hidden = true;
  candidatesList.hidden = false;
  byId("candidate-versions-toggle").textContent = "版本记录";
  candidatesHint.textContent = "正在读取…";
  candidatesList.replaceChildren(element("p", "file-empty", "正在读取待核对条目…"));
  try {
    const data = await request("/api/workspace/candidates");
    renderCandidates(data.candidates);
  } catch (error) {
    candidatesList.replaceChildren(element("p", "file-empty", error.message));
  }
}

async function reviewCandidate(item, status) {
  if (busy) return;
  setBusy(true);
  try {
    await request(`/api/workspace/candidates/${item.id}/review`, { status });
    await openCandidates();
    note("审核状态已更新", "success");
  } catch (error) {
    candidatesHint.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function mergeApprovedCandidates() {
  const button = byId("merge-candidates");
  if (busy || button.disabled) return;
  setBusy(true);
  try {
    const result = await request("/api/workspace/knowledge/merge", {});
    await refreshCaseCatalog();
    await openCandidates();
    note(`已合并 ${result.merged} 条，工作台知识库共 ${result.total} 条`, "success");
  } catch (error) {
    candidatesHint.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function showCandidateVersions(show) {
  byId("candidate-versions").hidden = !show;
  candidatesList.hidden = show;
  byId("candidate-versions-toggle").textContent = show ? "查看候选" : "版本记录";
  if (!show) return;
  const meta = byId("versions-meta");
  const list = byId("versions-list");
  meta.textContent = "正在读取…";
  list.replaceChildren();
  try {
    const data = await request("/api/workspace/knowledge/versions");
    meta.textContent = `当前工作台知识库覆盖层 ${data.entries} 条`;
    if (!data.versions.length) {
      list.append(element("p", "file-empty", "还没有知识库版本"));
      return;
    }
    list.replaceChildren(...data.versions.map((version) => {
      const row = element("article", "version-row");
      const main = element("div", "candidate-main");
      main.append(
        element("strong", "", version.note),
        element("p", "file-meta", `${version.created_at} · ${version.count} 条`),
      );
      const changes = [];
      for (const [sign, items] of [
        ["+", version.added], ["-", version.removed], ["~", version.changed],
      ]) {
        if (!items?.length) continue;
        const ids = items.slice(0, 5).map((item) => item.entry_id).join("、");
        changes.push(`${sign} ${ids}${items.length > 5 ? ` 等 ${items.length} 条` : ""}`);
      }
      if (changes.length) main.append(element("p", "version-diff", changes.join(" · ")));
      const actions = element("div", "candidate-actions");
      actions.append(button("file-action", "回滚到此版本", () => rollbackKnowledge(version)));
      row.append(main, actions);
      return row;
    }));
  } catch (error) {
    meta.textContent = error.message;
  }
}

async function rollbackKnowledge(version) {
  if (busy || !confirm(`回滚到「${version.note}」？当前覆盖层条目会被替换。`)) return;
  setBusy(true);
  try {
    await request("/api/workspace/knowledge/rollback", { version: version.id });
    await refreshCaseCatalog();
    const data = await request("/api/workspace/candidates");
    renderCandidates(data.candidates);
    await showCandidateVersions(true);
    note("已回滚知识库版本", "success");
  } catch (error) {
    byId("versions-meta").textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function removeCandidate(item) {
  if (busy || item.status === "merged" || !confirm("移除「" + item.title + "」？")) return;
  setBusy(true);
  try {
    await request("/api/workspace/candidates/" + item.id + "/remove", {});
    await openCandidates();
  } catch (error) {
    candidatesHint.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

candidateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if ((!candidateArticle && !candidateEditing) || busy) return;
  const errorNote = byId("candidate-error");
  const payload = candidatePayload();
  if (!payload) return;
  errorNote.hidden = true;
  if (!payload.scenario || !payload.method) {
    errorNote.textContent = "请填写研究场景和方法名称";
    errorNote.hidden = false;
    (payload.scenario ? byId("candidate-method") : byId("candidate-scenario")).focus();
    return;
  }
  setBusy(true);
  try {
    if (candidateEditing) {
      await request(`/api/workspace/candidates/${candidateEditing.id}`, payload);
      candidateDialog.close();
      await openCandidates();
      note("候选条目已保存", "success");
    } else {
      await request("/api/workspace/candidates", payload);
      candidateDialog.close();
      literatureMessage.textContent = "已加入待核对条目，可在「更多 → 待核对条目」查看";
      note("已加入待核对条目，可在「更多 → 待核对条目」查看", "success");
    }
  } catch (error) {
    errorNote.textContent = error.message;
    errorNote.hidden = false;
  } finally {
    setBusy(false);
  }
});

byId("merge-candidates").addEventListener("click", mergeApprovedCandidates);
byId("candidate-versions-toggle").addEventListener("click", () => {
  showCandidateVersions(byId("candidate-versions").hidden);
});
byId("versions-back").addEventListener("click", () => showCandidateVersions(false));
byId("candidates-close").addEventListener("click", () => candidatesDialog.close());
byId("candidate-cancel").addEventListener("click", () => candidateDialog.close());
candidateDialog.addEventListener("close", () => {
  candidateArticle = null;
  candidateEditing = null;
  candidateForm.reset();
  byId("candidate-error").hidden = true;
});

const knowledgeDialog = byId("knowledge-dialog");
const knowledgeCase = byId("knowledge-case");
const knowledgeFilter = byId("knowledge-filter");
const knowledgeShowInactive = byId("knowledge-show-inactive");
const knowledgeList = byId("knowledge-list");
const knowledgeMeta = byId("knowledge-meta");
const knowledgeCoverageEl = byId("knowledge-coverage");
const knowledgeEntryDialog = byId("knowledge-entry-dialog");
const knowledgeEntryForm = byId("knowledge-entry-form");
let knowledgeEntries = [];
let knowledgeCoverage = [];
let knowledgeEditing = null;

function openKnowledge() {
  if (!ready || busy) return;
  const all = element("option", "", "全部案例");
  all.value = "";
  knowledgeCase.replaceChildren(all, ...cases.map((item) => {
    const option = element("option", "", item.label);
    option.value = item.code;
    return option;
  }));
  knowledgeCase.value = "";
  knowledgeFilter.value = "";
  knowledgeShowInactive.checked = false;
  if (!knowledgeDialog.open) knowledgeDialog.showModal();
  loadKnowledge();
}

async function loadKnowledge() {
  knowledgeMeta.textContent = "正在读取…";
  knowledgeList.replaceChildren(element("p", "file-empty", "正在读取知识库…"));
  knowledgeCoverageEl.replaceChildren(element("p", "coverage-empty", "正在统计覆盖情况…"));
  try {
    const [data, coverage] = await Promise.all([
      request("/api/knowledge?include_inactive=1"),
      request("/api/coverage"),
    ]);
    knowledgeEntries = data.entries;
    knowledgeCoverage = coverage.cases || [];
    renderKnowledge();
  } catch (error) {
    knowledgeMeta.textContent = error.message;
    knowledgeList.replaceChildren(element("p", "file-empty", error.message));
    knowledgeCoverageEl.replaceChildren(element("p", "coverage-empty", error.message));
  }
}

function coverageTask(task) {
  const row = element("div", "coverage-task is-" + task.status);
  const head = element("div", "coverage-task-head");
  head.append(
    element("span", "coverage-task-label", task.label),
    element("span", "coverage-task-count", `${task.count}/${task.target}`),
  );
  const bar = element("div", "coverage-bar");
  const fill = element("span");
  fill.style.width = Math.min(100, Math.round(100 * task.count / Math.max(1, task.target))) + "%";
  bar.append(fill);
  row.append(head, bar);
  if (task.gap) row.append(element("span", "coverage-gap", `缺口 ${task.gap}`));
  return row;
}

function renderCoverage(container, caseFilter, casesData = knowledgeCoverage) {
  if (!container) return;
  const allowed = Array.isArray(caseFilter)
    ? new Set(caseFilter)
    : caseFilter ? new Set([caseFilter]) : null;
  const casesToShow = (casesData || []).filter((item) => !allowed || allowed.has(item.code));
  if (!casesToShow.length) {
    container.replaceChildren(element("p", "coverage-empty", "还没有可统计的案例"));
    return;
  }
  container.replaceChildren(...casesToShow.map((item) => {
    const block = element("section", "coverage-case");
    const head = element("div", "coverage-case-head");
    head.append(
      element("strong", "", item.label + " · " + item.code),
      element("span", "coverage-case-meta",
        `覆盖 ${Math.round((item.coverage || 0) * 100)}% · 缺口 ${item.gaps.length} 项`),
    );
    const tasks = element("div", "coverage-tasks");
    tasks.append(...item.tasks.map(coverageTask));
    block.append(head, tasks);
    return block;
  }));
}

function knowledgeMatches(entry) {
  if (knowledgeCase.value && entry.case_code !== knowledgeCase.value) return false;
  if (!knowledgeShowInactive.checked && !entry.active) return false;
  const needle = knowledgeFilter.value.trim().toLowerCase();
  if (!needle) return true;
  return [entry.entry_id, entry.method, entry.concept, entry.scenario, entry.case_name]
    .join(" ").toLowerCase().includes(needle);
}

function renderKnowledge() {
  const local = knowledgeEntries.filter((entry) => entry.origin === "local").length;
  const inactive = knowledgeEntries.filter((entry) => !entry.active).length;
  knowledgeMeta.textContent = `原始 ${knowledgeEntries.length - local} 条 · 工作台 ${local} 条 · 停用 ${inactive} 条`;
  renderCoverage(knowledgeCoverageEl, knowledgeCase.value);
  const visible = knowledgeEntries.filter(knowledgeMatches);
  if (!visible.length) {
    knowledgeList.replaceChildren(element("p", "file-empty", "没有匹配的知识条目"));
    return;
  }
  knowledgeList.replaceChildren(...visible.map((entry) => {
    const row = element("article", "knowledge-row" + (entry.active ? "" : " is-inactive"));
    const main = element("div", "knowledge-main");
    const title = element("h3");
    title.append(
      element("span", "knowledge-id", `[${entry.entry_id}]`),
      " ",
      entry.method,
      " ",
      element("span", "knowledge-origin " + (entry.origin === "base" ? "is-base" : "is-local"),
        entry.origin === "base" ? "原始" : "工作台"),
    );
    if (!entry.active) title.append(" ", element("span", "knowledge-status", "已停用"));
    main.append(
      title,
      element("p", "file-meta", [entry.case_name, entry.concept, entry.scenario]
        .filter(Boolean).join(" · ")),
      element("p", "knowledge-rationale", entry.rationale || ""),
      element("p", "file-meta", entry.source_row || ""),
    );
    const actions = element("div", "candidate-actions");
    if (entry.origin === "local") {
      actions.append(button("file-action", "编辑", () => openKnowledgeEditor(entry)));
      actions.append(button("file-action", entry.active ? "停用" : "启用",
        () => toggleKnowledgeEntry(entry)));
      actions.append(button("file-action", "移出", () => removeKnowledgeEntry(entry)));
    } else {
      actions.append(element("span", "file-meta", "只读"));
    }
    row.append(main, actions);
    return row;
  }));
}

function openKnowledgeEditor(entry) {
  knowledgeEditing = entry;
  byId("knowledge-entry-source").textContent =
    `[${entry.entry_id}] · ${entry.case_name} · ${entry.origin === "base" ? "原始" : "工作台"}`;
  byId("knowledge-entry-scenario").value = entry.scenario || "";
  byId("knowledge-entry-concept").value = entry.concept || "";
  byId("knowledge-entry-method").value = entry.method || "";
  byId("knowledge-entry-rationale").value = entry.rationale || "";
  byId("knowledge-entry-conditions").value = entry.conditions || "";
  byId("knowledge-entry-limitations").value = entry.limitations || "";
  byId("knowledge-entry-evidence").value = entry.evidence || "";
  byId("knowledge-entry-error").hidden = true;
  if (!knowledgeEntryDialog.open) knowledgeEntryDialog.showModal();
  byId("knowledge-entry-method").focus();
}

async function toggleKnowledgeEntry(entry) {
  if (busy) return;
  setBusy(true);
  try {
    await request(`/api/workspace/knowledge/entries/${encodeURIComponent(entry.entry_id)}/active`,
      { active: !entry.active });
    await refreshCaseCatalog();
    await loadKnowledge();
    note(entry.active ? "条目已停用" : "条目已启用", "success");
  } catch (error) {
    knowledgeMeta.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function removeKnowledgeEntry(entry) {
  if (busy || !confirm(`把「${entry.method}」移出工作台知识库？对应候选会退回「已通过」。`)) return;
  setBusy(true);
  try {
    await request(`/api/workspace/knowledge/entries/${encodeURIComponent(entry.entry_id)}/remove`, {});
    await refreshCaseCatalog();
    await loadKnowledge();
    note("条目已移出知识库", "success");
  } catch (error) {
    knowledgeMeta.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

knowledgeEntryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!knowledgeEditing || busy) return;
  const errorNote = byId("knowledge-entry-error");
  const payload = {
    scenario: byId("knowledge-entry-scenario").value.trim(),
    concept: byId("knowledge-entry-concept").value.trim(),
    method: byId("knowledge-entry-method").value.trim(),
    rationale: byId("knowledge-entry-rationale").value.trim(),
    conditions: byId("knowledge-entry-conditions").value.trim(),
    limitations: byId("knowledge-entry-limitations").value.trim(),
    evidence: byId("knowledge-entry-evidence").value.trim(),
  };
  errorNote.hidden = true;
  if (!payload.scenario || !payload.method) {
    errorNote.textContent = "请填写研究场景和方法名称";
    errorNote.hidden = false;
    (payload.scenario ? byId("knowledge-entry-method") : byId("knowledge-entry-scenario")).focus();
    return;
  }
  setBusy(true);
  try {
    await request(`/api/workspace/knowledge/entries/${encodeURIComponent(knowledgeEditing.entry_id)}`,
      payload);
    knowledgeEntryDialog.close();
    await refreshCaseCatalog();
    await loadKnowledge();
    note("知识条目已保存", "success");
  } catch (error) {
    errorNote.textContent = error.message;
    errorNote.hidden = false;
  } finally {
    setBusy(false);
  }
});

byId("show-knowledge").addEventListener("click", openKnowledge);
byId("knowledge-close").addEventListener("click", () => knowledgeDialog.close());
knowledgeCase.addEventListener("change", renderKnowledge);
knowledgeFilter.addEventListener("input", renderKnowledge);
knowledgeShowInactive.addEventListener("change", renderKnowledge);
byId("knowledge-entry-cancel").addEventListener("click", () => knowledgeEntryDialog.close());
knowledgeEntryDialog.addEventListener("close", () => {
  knowledgeEditing = null;
  knowledgeEntryForm.reset();
  byId("knowledge-entry-error").hidden = true;
});
