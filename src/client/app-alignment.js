// Cross-disciplinary alignment: AI analysis with human confirmation.

const alignmentDialog = byId("alignment-dialog");
const alignmentForm = byId("alignment-form");
const alignmentSource = byId("alignment-source");
const alignmentTarget = byId("alignment-target");
const alignmentTask = byId("alignment-task");
const alignmentText = byId("alignment-text");
const alignmentAnalyze = byId("alignment-analyze");
const alignmentMeta = byId("alignment-meta");
const alignmentHistory = byId("alignment-history");
const alignmentResult = byId("alignment-result");
let alignmentRecords = [];
let alignmentCurrent = null;
let alignmentBusy = false;

const ALIGNMENT_TASKS = { term: "术语对齐", compare: "观点对照" };
const ALIGNMENT_STATUSES = { pending: "待确认", accepted: "已采纳", rejected: "已驳回" };
const ALIGNMENT_CONFIDENCE = { low: "低", medium: "中", high: "高" };

function alignmentCaseLabel(code) {
  return cases.find((item) => item.code === code)?.label || code;
}

function alignmentDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("zh-CN");
}

function alignmentExternalLink(url, label) {
  if (typeof url !== "string" || !url.startsWith("https://")) return null;
  const link = element("a", "file-action", label);
  link.href = url;
  link.target = "_blank";
  link.rel = "noreferrer noopener";
  return link;
}

function fillAlignmentCases() {
  const options = cases.map((item) => {
    const option = element("option", "", item.label);
    option.value = item.code;
    return option;
  });
  for (const select of [alignmentSource, alignmentTarget]) {
    const previous = select.value;
    select.replaceChildren(...options.map((option) => option.cloneNode(true)));
    if (previous && cases.some((item) => item.code === previous)) select.value = previous;
  }
  if (!alignmentSource.value) {
    alignmentSource.value = cases.some((item) => item.code === active.case_code)
      ? active.case_code : (cases[0]?.code || "");
  }
  if (!alignmentTarget.value || alignmentTarget.value === alignmentSource.value) {
    alignmentTarget.value = cases.find((item) => item.code !== alignmentSource.value)?.code || "";
  }
}

function alignmentPlaceholder(message) {
  alignmentResult.replaceChildren(element("p", "file-empty", message));
}

function setAlignmentBusy(value) {
  alignmentBusy = value;
  alignmentAnalyze.disabled = value || !ready || busy || cases.length < 2;
  alignmentSource.disabled = value;
  alignmentTarget.disabled = value;
  alignmentTask.disabled = value;
  alignmentText.readOnly = value;
}

function updateAlignmentMeta() {
  alignmentMeta.textContent = modelConfigured
    ? "选择源学科和目标学科，AI 分析会自动保存并等待人工确认"
    : "未配置模型：可以查看历史记录，新分析需要先在 API 设置中配置模型";
  setAlignmentBusy(alignmentBusy);
}

function alignmentBadge(label, className) {
  return element("span", "alignment-badge " + className, label);
}

function alignmentList(items, className = "alignment-list") {
  const list = element("ul", className);
  for (const item of items) list.append(element("li", "", item));
  return list;
}

function alignmentPairs(items, titleField, fields) {
  const wrap = element("div", "alignment-pairs");
  for (const item of items) {
    const card = element("article", "alignment-pair");
    card.append(element("strong", "", item[titleField] || "未命名条目"));
    for (const [field, label] of fields) {
      if (item[field]) card.append(element("p", "", `${label}：${item[field]}`));
    }
    wrap.append(card);
  }
  return wrap;
}

function alignmentSection(title, body) {
  const section = element("section", "alignment-section");
  section.append(element("h4", "", title), body);
  return section;
}

function renderAlignment(record) {
  if (!record) {
    alignmentPlaceholder("选择一条记录或开始新的分析。");
    return;
  }
  const result = record.result || {};
  const sourceLabel = result.source_label || alignmentCaseLabel(record.source_case);
  const targetLabel = result.target_label || alignmentCaseLabel(record.target_case);
  alignmentResult.replaceChildren();

  const head = element("div", "alignment-head");
  const title = element("h3", "", `${sourceLabel} → ${targetLabel}`);
  const badges = element("div", "alignment-badges");
  badges.append(alignmentBadge(
    ALIGNMENT_STATUSES[record.status] || "待确认", "is-" + (record.status || "pending")));
  if (record.edited) badges.append(alignmentBadge("已人工修订", "is-edited"));
  head.append(title, badges);
  alignmentResult.append(head);

  const metaParts = [
    ALIGNMENT_TASKS[record.task] || record.task,
    record.input,
    result.model,
    result.confidence ? "置信度 " + (ALIGNMENT_CONFIDENCE[result.confidence] || result.confidence) : "",
    record.created_at ? alignmentDate(record.created_at) : "",
  ].filter(Boolean);
  alignmentResult.append(element("p", "alignment-meta", metaParts.join(" · ")));
  if (result.notice) alignmentResult.append(element("p", "alignment-notice", result.notice));

  if (result.source_concept || result.target_concept || result.relation) {
    const concept = element("section", "alignment-concept");
    if (result.source_concept) {
      const item = element("div", "alignment-concept-item");
      item.append(element("span", "file-meta", "源学科概念"),
        element("strong", "", result.source_concept));
      concept.append(item);
    }
    if (result.target_concept) {
      const item = element("div", "alignment-concept-item");
      item.append(element("span", "file-meta", "目标学科概念"),
        element("strong", "", result.target_concept));
      concept.append(item);
    }
    if (result.relation) concept.append(element("p", "alignment-relation", result.relation));
    alignmentResult.append(alignmentSection("概念对应", concept));
  }

  const listSections = [
    ["共同点", result.same],
    ["适用条件", result.conditions],
    ["局限与注意事项", result.limitations],
    ["共识", result.consensus],
    ["互补之处", result.complements],
    ["协调建议", result.suggestions],
  ];
  for (const [titleText, items] of listSections) {
    if (Array.isArray(items) && items.length) {
      alignmentResult.append(alignmentSection(titleText, alignmentList(items)));
    }
  }

  if (Array.isArray(result.differences) && result.differences.length) {
    alignmentResult.append(alignmentSection("关键差异", alignmentPairs(
      result.differences, "dimension",
      [["source", "源学科"], ["target", "目标学科"]],
    )));
  }
  if (Array.isArray(result.conflicts) && result.conflicts.length) {
    alignmentResult.append(alignmentSection("冲突点", alignmentPairs(
      result.conflicts, "point",
      [["source", "源学科观点"], ["target", "目标学科观点"], ["reason", "冲突来源"]],
    )));
  }

  if (Array.isArray(result.references) && result.references.length) {
    const evidence = element("div", "alignment-evidence");
    for (const reference of result.references) {
      const item = element("article", "alignment-evidence-item");
      const heading = element("p", "");
      heading.append(
        element("code", "alignment-evidence-id", `[${reference.entry_id}]`),
        " ",
        reference.case_name || alignmentCaseLabel(reference.case_code),
        " · ",
        reference.method || reference.concept,
      );
      item.append(heading);
      if (reference.concept) item.append(element("p", "file-meta", reference.concept));
      if (reference.text) {
        const text = String(reference.text);
        item.append(element("p", "alignment-evidence-text",
          text.length > 360 ? text.slice(0, 359) + "…" : text));
      }
      for (const link of reference.links || []) {
        const anchor = alignmentExternalLink(link, "查看来源");
        if (anchor) item.append(anchor);
      }
      evidence.append(item);
    }
    alignmentResult.append(alignmentSection("本地证据", evidence));
  }

  if (record.id) {
    const review = element("section", "alignment-review");
    review.append(
      element("h4", "", "人工确认"),
      element("p", "file-meta", record.reviewed_at
        ? "确认时间 " + alignmentDate(record.reviewed_at)
        : "AI 结果尚未人工确认，请核对后再采纳。"),
    );
    const targetField = element("div", "alignment-review-field");
    const targetLabelNode = element("label", "", "目标概念（可人工修订）");
    targetLabelNode.htmlFor = "alignment-edit-target";
    const targetInput = element("input", "");
    targetInput.id = "alignment-edit-target";
    targetInput.maxLength = 300;
    targetInput.value = result.target_concept || "";
    targetField.append(targetLabelNode, targetInput);

    const relationField = element("div", "alignment-review-field");
    const relationLabel = element("label", "", "对应关系（可人工修订）");
    relationLabel.htmlFor = "alignment-edit-relation";
    const relationInput = element("textarea", "");
    relationInput.id = "alignment-edit-relation";
    relationInput.rows = 2;
    relationInput.maxLength = 800;
    relationInput.value = result.relation || "";
    relationField.append(relationLabel, relationInput);

    const noteField = element("div", "alignment-review-field");
    const noteLabel = element("label", "", "人工备注");
    noteLabel.htmlFor = "alignment-edit-note";
    const noteInput = element("textarea", "");
    noteInput.id = "alignment-edit-note";
    noteInput.rows = 2;
    noteInput.maxLength = 2000;
    noteInput.value = record.note || "";
    noteField.append(noteLabel, noteInput);

    const actions = element("div", "alignment-review-actions");
    const pending = button("secondary-button", "保存为待核对", () => saveAlignmentReview("pending"));
    pending.type = "button";
    const reject = button("secondary-button", "驳回", () => saveAlignmentReview("rejected"));
    reject.type = "button";
    const accept = button("primary-button", "采纳并保存", () => saveAlignmentReview("accepted"));
    accept.type = "button";
    actions.append(pending, reject, accept);
    review.append(targetField, relationField, noteField);
    if (record.edited && record.model_result) {
      const original = element("details", "alignment-original");
      original.append(element("summary", "", "查看 AI 原始结果"));
      original.append(element("p", "file-meta",
        "原目标概念：" + (record.model_result.target_concept || "未填写")));
      original.append(element("p", "file-meta",
        "原对应关系：" + (record.model_result.relation || "未填写")));
      review.append(original);
    }
    review.append(actions);
    alignmentResult.append(review);
  }
  alignmentResult.scrollTop = 0;
}

async function selectAlignment(record) {
  try {
    const data = await request(`/api/alignment/${record.id}`);
    alignmentCurrent = data.alignment;
  } catch {
    alignmentCurrent = record;
  }
  renderAlignment(alignmentCurrent);
  renderAlignmentHistory();
}

async function saveAlignmentReview(status) {
  if (!alignmentCurrent || alignmentBusy) return;
  const target = byId("alignment-edit-target")?.value.trim() || "";
  const relation = byId("alignment-edit-relation")?.value.trim() || "";
  const noteValue = byId("alignment-edit-note")?.value.trim() || "";
  const result = alignmentCurrent.result || {};
  setAlignmentBusy(true);
  try {
    const data = await request(`/api/alignment/${alignmentCurrent.id}/review`, {
      status, note: noteValue,
      result: {
        source_concept: result.source_concept || "",
        target_concept: target,
        relation,
      },
    });
    alignmentCurrent = data.alignment;
    renderAlignment(alignmentCurrent);
    await loadAlignmentHistory();
    note("人工确认已保存", "success");
  } catch (error) {
    note(error.message);
  } finally {
    setAlignmentBusy(false);
  }
}

function renderAlignmentHistory() {
  if (!alignmentRecords.length) {
    alignmentHistory.replaceChildren(element("p", "file-empty", "还没有分析记录"));
    return;
  }
  alignmentHistory.replaceChildren(...alignmentRecords.map((record) => {
    const row = button("alignment-history-item", null, () => selectAlignment(record));
    row.setAttribute("aria-pressed", String(alignmentCurrent?.id === record.id));
    const title = element("strong", "",
      `${alignmentCaseLabel(record.source_case)} → ${alignmentCaseLabel(record.target_case)}`);
    const summary = element("small", "", record.input || "");
    const meta = element("span", "alignment-history-meta",
      `${ALIGNMENT_TASKS[record.task] || record.task} · ${ALIGNMENT_STATUSES[record.status] || "待确认"}`);
    row.append(title, summary, meta);
    return row;
  }));
}

async function loadAlignmentHistory() {
  try {
    const data = await request("/api/alignment");
    alignmentRecords = data.alignments || [];
    renderAlignmentHistory();
  } catch (error) {
    alignmentHistory.replaceChildren(element("p", "file-empty", error.message));
  }
}

function openAlignment() {
  if (!ready || busy) return;
  fillAlignmentCases();
  if (!alignmentDialog.open) alignmentDialog.showModal();
  updateAlignmentMeta();
  if (!alignmentCurrent) {
    alignmentPlaceholder("选择源学科和目标学科，然后输入要比较的术语或研究问题。");
  }
  loadAlignmentHistory();
}

byId("show-alignment").addEventListener("click", openAlignment);
byId("alignment-close").addEventListener("click", () => alignmentDialog.close());
alignmentSource.addEventListener("change", () => {
  if (alignmentTarget.value === alignmentSource.value) {
    alignmentTarget.value = cases.find((item) => item.code !== alignmentSource.value)?.code || "";
  }
});
alignmentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!ready || busy || alignmentBusy) return;
  if (!modelConfigured) {
    alignmentPlaceholder("请先在 API 设置中配置模型，再进行跨学科分析。");
    return;
  }
  const source = alignmentSource.value;
  const target = alignmentTarget.value;
  const text = alignmentText.value.trim();
  if (!source || !target || source === target) {
    alignmentPlaceholder("请选择两个不同的学科。");
    return;
  }
  if (!text) {
    alignmentText.focus();
    return;
  }
  setAlignmentBusy(true);
  alignmentPlaceholder("正在检索双方知识库并生成结构化分析，可能需要几十秒…");
  try {
    const data = await request("/api/alignment", {
      source_case: source, target_case: target, task: alignmentTask.value,
      input: text, project_id: active.project_id || null,
    });
    alignmentCurrent = data.alignment;
    renderAlignment(alignmentCurrent);
    await loadAlignmentHistory();
    note("对齐分析已保存，等待人工确认", "success");
  } catch (error) {
    alignmentPlaceholder(error.message);
  } finally {
    setAlignmentBusy(false);
  }
});
