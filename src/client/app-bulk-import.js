// Bulk pipeline: raw articles/documents -> candidates -> human review.

const bulkImportDialog = byId("bulk-import-dialog");
const bulkImportCase = byId("bulk-import-case");
const bulkImportType = byId("bulk-import-type");
const bulkImportSelectAll = byId("bulk-import-select-all");
const bulkImportGenerate = byId("bulk-import-generate");
const bulkImportMessage = byId("bulk-import-message");
const bulkImportList = byId("bulk-import-list");
const bulkImportOpenCandidates = byId("bulk-import-open-candidates");
let bulkImportItems = [];
let bulkImportBusy = false;

function fillBulkImportCases() {
  const previous = bulkImportCase.value;
  bulkImportCase.replaceChildren(...cases.map((item) => {
    const option = element("option", "", item.label);
    option.value = item.code;
    return option;
  }));
  if (previous && cases.some((item) => item.code === previous)) {
    bulkImportCase.value = previous;
  } else {
    bulkImportCase.value = cases.some((item) => item.code === active.case_code)
      ? active.case_code : (cases[0]?.code || "");
  }
}

function bulkImportChecked() {
  return [...bulkImportList.querySelectorAll("input[type=checkbox]:checked")]
    .map((box) => box.dataset.id);
}

function updateBulkImportSelection() {
  const count = bulkImportChecked().length;
  const total = bulkImportItems.length;
  bulkImportGenerate.disabled = bulkImportBusy || count === 0;
  if (total) {
    bulkImportMessage.textContent = `已选择 ${count} / ${total} 条原始记录`;
  }
}

function renderBulkImportItems() {
  if (!bulkImportItems.length) {
    const message = bulkImportType.value === "document"
      ? "这个案例还没有方法文档，请先在「方法文档」中采集"
      : "这个案例还没有文献，请先在「文献与数据」中采集";
    bulkImportMessage.textContent = message;
    bulkImportList.replaceChildren(element("p", "file-empty", message));
    bulkImportGenerate.disabled = true;
    bulkImportSelectAll.disabled = true;
    return;
  }
  bulkImportSelectAll.disabled = false;
  bulkImportList.replaceChildren(...bulkImportItems.map((item) => {
    const row = element("label", "bulk-import-row");
    const checkbox = element("input", "bulk-import-check");
    checkbox.type = "checkbox";
    checkbox.dataset.id = item.id;
    const main = element("span", "bulk-import-main");
    main.append(
      element("strong", "", item.title),
      element("small", "", item.meta),
    );
    row.append(checkbox, main);
    return row;
  }));
  updateBulkImportSelection();
}

async function loadBulkImportItems() {
  const caseCode = bulkImportCase.value;
  const type = bulkImportType.value;
  bulkImportMessage.textContent = "正在读取原始数据…";
  bulkImportList.replaceChildren(element("p", "file-empty", "正在读取…"));
  bulkImportGenerate.disabled = true;
  try {
    const path = type === "document"
      ? "/api/method-docs?case=" + encodeURIComponent(caseCode)
      : "/api/literature?case=" + encodeURIComponent(caseCode) + "&kind=article";
    const data = await request(path);
    bulkImportItems = type === "document"
      ? (data.documents || []).map((item) => ({
        id: item.id, title: item.title,
        meta: item.source_label || item.source,
      }))
      : (data.articles || []).map((item) => ({
        id: item.id, title: item.title,
        meta: [item.provider, item.year].filter(Boolean).join(" · "),
      }));
    renderBulkImportItems();
  } catch (error) {
    bulkImportItems = [];
    bulkImportMessage.textContent = error.message;
    bulkImportList.replaceChildren(element("p", "file-empty", error.message));
  }
}

function setBulkImportBusy(value) {
  bulkImportBusy = value;
  bulkImportCase.disabled = value;
  bulkImportType.disabled = value;
  bulkImportSelectAll.disabled = value;
  bulkImportGenerate.disabled = value;
  bulkImportGenerate.textContent = value ? "正在生成…" : "生成候选条目";
  if (!value) updateBulkImportSelection();
}

async function generateBulkCandidates() {
  if (bulkImportBusy) return;
  if (!modelConfigured) {
    bulkImportMessage.textContent = "请先在 API 设置中配置模型，再生成候选条目";
    return;
  }
  const selected = bulkImportChecked();
  if (!selected.length) {
    bulkImportMessage.textContent = "请至少选择一条原始记录";
    return;
  }
  const ids = selected.slice(0, 10);
  const limited = selected.length > ids.length;
  setBulkImportBusy(true);
  let created = 0;
  let skipped = 0;
  let failed = 0;
  try {
    for (const [index, id] of ids.entries()) {
      bulkImportMessage.textContent =
        `正在生成候选 ${index + 1}/${ids.length}，可能需要几十秒…`;
      try {
        const result = await request(
          bulkImportType.value === "document"
            ? `/api/method-docs/${id}/candidates`
            : `/api/literature/${id}/candidates`,
          { case: bulkImportCase.value },
        );
        created += result.created.length;
        skipped += result.skipped.length;
      } catch (error) {
        failed += 1;
        if (error.message.includes("配置模型")) {
          bulkImportMessage.textContent = error.message;
          return;
        }
      }
    }
    bulkImportMessage.textContent =
      `生成完成：新增 ${created} 条，跳过重复 ${skipped} 条`
      + (failed ? `，失败 ${failed} 条` : "")
      + (limited ? "，本次只处理前 10 条" : "");
    if (created) note("候选条目已生成，请在待核对条目中审核", "success");
  } finally {
    setBulkImportBusy(false);
  }
}

function openBulkImport() {
  if (!ready || busy) return;
  fillBulkImportCases();
  if (!bulkImportDialog.open) bulkImportDialog.showModal();
  bulkImportOpenCandidates.disabled = false;
  loadBulkImportItems();
}

byId("show-bulk-import").addEventListener("click", openBulkImport);
byId("bulk-import-close").addEventListener("click", () => bulkImportDialog.close());
bulkImportCase.addEventListener("change", loadBulkImportItems);
bulkImportType.addEventListener("change", loadBulkImportItems);
bulkImportList.addEventListener("change", (event) => {
  if (event.target.matches("input[type=checkbox]")) updateBulkImportSelection();
});
bulkImportSelectAll.addEventListener("click", () => {
  const boxes = [...bulkImportList.querySelectorAll("input[type=checkbox]")];
  const target = !boxes.every((box) => box.checked);
  for (const box of boxes) box.checked = target;
  updateBulkImportSelection();
});
bulkImportGenerate.addEventListener("click", generateBulkCandidates);
bulkImportOpenCandidates.addEventListener("click", () => {
  bulkImportDialog.close();
  openCandidates();
});
