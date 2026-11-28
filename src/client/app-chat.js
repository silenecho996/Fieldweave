// Chat: citation rendering, answer cards, transcript turns and question submission.

function sourceId(index, entryId) {
  return "reference-" + index + "-" + entryId;
}

function referenceUrls(item) {
  const links = [];
  for (const value of item.links || []) {
    try {
      const url = new URL(value);
      if (["https:", "http:"].includes(url.protocol) && !url.username && !url.password) links.push(url);
    } catch { continue; }
  }
  if (links.length) return [...new Map(links.map((url) => [url.href, url])).values()];
  // Saved conversations may predate the addition of these verified paper links.
  const title = item.text.split(/\r?\n/).find((line) => line.trim()) || "";
  const paper = verifiedPaperIds.get(title.trim().replace(/\s*[（(]\d{4}[）)]$/, ""));
  return paper ? [new URL("https://arxiv.org/abs/" + paper)] : [];
}

function openReference(anchor, url) {
  anchor.href = url.href;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
}

let citationTip;
let citationAnchor;
let citationHideTimer;

function hideCitationTip(immediate = false) {
  clearTimeout(citationHideTimer);
  const hide = () => { if (citationTip) citationTip.hidden = true; };
  if (immediate) hide();
  else citationHideTimer = setTimeout(hide, 120);
}

function showCitationTip(anchor, id, entry) {
  clearTimeout(citationHideTimer);
  if (!citationTip) {
    citationTip = element("div", "citation-tip");
    citationTip.id = "citation-tip";
    citationTip.setAttribute("role", "tooltip");
    citationTip.hidden = true;
    citationTip.addEventListener("pointerenter", () => clearTimeout(citationHideTimer));
    citationTip.addEventListener("pointerleave", () => hideCitationTip());
    document.body.append(citationTip);
  }
  citationTip.replaceChildren(
    element("strong", "", "[" + id + "]"),
    element("p", "", entry.text || "知识库条目"),
  );
  const urls = entry.urls || [];
  if (urls.length) {
    const links = element("div", "citation-tip-links");
    for (const [position, destination] of urls.entries()) {
      const link = element("a", "", urls.length === 1 ? "打开原文" : "打开文献 " + (position + 1));
      openReference(link, destination);
      links.append(link);
    }
    citationTip.append(links);
  }
  citationAnchor = anchor;
  citationTip.hidden = false;
  positionCitationTip(anchor);
}

function positionCitationTip(anchor) {
  const rect = anchor.getBoundingClientRect();
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - citationTip.offsetWidth - 8));
  let top = rect.bottom + 8;
  if (top + citationTip.offsetHeight > window.innerHeight - 8) {
    top = Math.max(8, rect.top - citationTip.offsetHeight - 8);
  }
  citationTip.style.left = left + "px";
  citationTip.style.top = Math.max(8, top) + "px";
}

function describeCitation(anchor, id, entry) {
  anchor.setAttribute("aria-describedby", "citation-tip");
  anchor.addEventListener("pointerenter", () => showCitationTip(anchor, id, entry));
  anchor.addEventListener("pointerleave", () => hideCitationTip());
  anchor.addEventListener("focus", () => showCitationTip(anchor, id, entry));
  anchor.addEventListener("blur", () => hideCitationTip(true));
}

window.addEventListener("scroll", () => {
  if (citationTip && !citationTip.hidden && citationAnchor) positionCitationTip(citationAnchor);
}, true);
window.addEventListener("resize", () => {
  if (citationTip && !citationTip.hidden && citationAnchor) positionCitationTip(citationAnchor);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideCitationTip(true);
});

function citation(id, index, refs) {
  const anchor = element("a", "citation", "[" + id + "]");
  const entry = refs.get(id) || { urls: [], text: "" };
  const links = entry.urls || [];
  describeCitation(anchor, id, entry);
  if (links.length === 1) {
    openReference(anchor, links[0]);
    anchor.setAttribute("aria-label", "打开文献 " + id + "（新标签页）");
    return anchor;
  }
  const targetId = sourceId(index, id);
  anchor.href = "#" + encodeURIComponent(targetId);
  anchor.setAttribute("aria-label", "查看参考条目 " + id);
  anchor.addEventListener("click", (event) => {
    const target = byId(targetId);
    if (!target) return;
    event.preventDefault();
    target.closest("details").open = true;
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "nearest" });
  });
  return anchor;
}

function citations(ids, index, refs) {
  const list = element("div", "citation-list");
  list.append(...ids.map((id) => citation(id, index, refs)));
  return list;
}

// Accept [ID], 【ID】, [ ID ], and comma-separated groups; render one marker per id.
const CITATION_GROUP = /[\[【]\s*([A-Z][A-Z0-9_-]{1,30}-\d+(?:\s*[,，、]\s*[A-Z][A-Z0-9_-]{1,30}-\d+)*)\s*[\]】]/g;

function normalizeCitations(line) {
  return line.replace(CITATION_GROUP, (_, group) => group
    .split(/[,，、]/).map((id) => id.trim()).filter(Boolean)
    .map((id) => "[" + id + "]").join(""));
}

const MATH_SYMBOLS = {
  "\\times": " × ", "\\cdot": " · ", "\\leq": " ≤ ", "\\geq": " ≥ ",
  "\\le": " ≤ ", "\\ge": " ≥ ", "\\neq": " ≠ ", "\\approx": " ≈ ",
  "\\infty": " ∞ ", "\\pm": " ± ", "\\mp": " ∓ ", "\\int": " ∫ ",
  "\\sum": " ∑ ", "\\prod": " ∏ ", "\\partial": " ∂ ", "\\nabla": " ∇ ",
  "\\alpha": "α", "\\beta": "β", "\\gamma": "γ", "\\delta": "δ",
  "\\theta": "θ", "\\lambda": "λ", "\\mu": "μ", "\\sigma": "σ",
  "\\pi": "π", "\\Delta": "Δ", "\\Omega": "Ω", "\\rightarrow": " → ",
  "\\to": " → ", "\\in": " ∈ ", "\\subset": " ⊂ ", "\\cup": " ∪ ",
  "\\cap": " ∩ ", "\\log": " log ", "\\ln": " ln ", "\\exp": " exp ",
  "\\max": " max ", "\\min": " min ", "\\arg": " arg ",
};

function mathNode(latex, display = false) {
  let text = String(latex).trim();
  text = text.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, "($1)/($2)");
  text = text.replace(/\\sqrt\s*\{([^{}]*)\}/g, "√($1)");
  text = text.replace(/\\(?:text|mathrm|mathbf|mathbb|operatorname)\s*\{([^{}]*)\}/g, "$1");
  text = text.replace(/\\left|\\right/g, "");
  text = text.replace(/\\[,;:!]/g, " ");
  text = text.replace(/\\quad|\\qquad|\\\\/g, " ");
  text = text.replace(/\\ /g, " ");
  for (const [command, symbol] of Object.entries(MATH_SYMBOLS)) {
    text = text.split(command).join(symbol);
  }
  text = text.replace(/\s+/g, " ").trim();
  const node = element(display ? "div" : "span", display ? "math-block" : "math-inline");
  const pattern = /([_^])(?:\{([^{}]*)\}|([A-Za-z0-9+\-−π∑√]))/g;
  let offset = 0;
  for (const token of text.matchAll(pattern)) {
    node.append(text.slice(offset, token.index).replace(/[{}]/g, ""));
    const part = element(token[1] === "^" ? "sup" : "sub");
    part.textContent = token[2] ?? token[3] ?? "";
    node.append(part);
    offset = token.index + token[0].length;
  }
  node.append(text.slice(offset).replace(/[{}]/g, ""));
  return node;
}

function appendInline(target, line, allowed, index) {
  line = normalizeCitations(line);
  const markers = /\*\*([^*\n]+)\*\*|\x60([^\x60\n]+)\x60|\\\((.+?)\\\)|\\\[(.+?)\\\]|\$([^$\n]+)\$|\[([A-Z][A-Z0-9_-]{1,30}-\d+)\]/g;
  let offset = 0;
  for (const token of line.matchAll(markers)) {
    target.append(line.slice(offset, token.index));
    if (token[1]) {
      const strong = element("strong");
      appendInline(strong, token[1], allowed, index);
      target.append(strong);
    } else if (token[2]) {
      target.append(element("code", "", token[2]));
    } else if (token[3] || token[4] || token[5]) {
      target.append(mathNode(token[3] ?? token[4] ?? token[5], Boolean(token[4])));
    } else {
      target.append(allowed.has(token[6]) ? citation(token[6], index, allowed) : token[0]);
    }
    offset = token.index + token[0].length;
  }
  target.append(line.slice(offset));
}

function modelBlock(answer, allowed, index) {
  const article = element("article", "model-answer");
  let section = article;
  let list;
  let led = false;
  for (const line of answer.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed === "---") {
      // A blank line between numbered items should not restart the list.
      continue;
    }
    const displayMath = /^\\\[([\s\S]+)\\\]$/.exec(trimmed);
    if (displayMath) {
      list = null;
      section.append(mathNode(displayMath[1], true));
      continue;
    }
    const heading = /^#{1,6}\s+(.+)$/.exec(trimmed);
    if (heading) {
      list = null;
      const title = heading[1].trim().replace(/^\*\*(.+)\*\*$/, "$1");
      if (!led && /^(结论|核心结论|结论先行)[：:]?$/.test(title)) {
        section = element("section", "answer-lead");
        article.prepend(section);
        led = true;
      } else {
        section = article;
      }
      section.append(element("h3", "", title));
      continue;
    }
    const bullet = /^([-*]|\d+\.)\s+(.+)$/.exec(trimmed);
    if (bullet) {
      const listType = /\d/.test(bullet[1]) ? "ol" : "ul";
      if (!list || list.localName !== listType) {
        list = element(listType);
        section.append(list);
      }
      const item = element("li");
      appendInline(item, bullet[2], allowed, index);
      list.append(item);
      continue;
    }
    list = null;
    const inlineConclusion = !led && /^(?:\*\*)?(?:结论|核心结论|结论先行)[：:](?:\*\*)?\s*/.exec(trimmed);
    if (inlineConclusion) {
      const lead = element("section", "answer-lead");
      lead.append(element("h3", "", "结论"));
      const paragraph = element("p");
      appendInline(paragraph, trimmed.slice(inlineConclusion[0].length), allowed, index);
      lead.append(paragraph);
      article.prepend(lead);
      led = true;
      continue;
    }
    const paragraph = element("p");
    appendInline(paragraph, trimmed, allowed, index);
    section.append(paragraph);
  }
  if (!led) article.querySelector("p")?.classList.add("answer-opening");
  return article;
}

function methodCard(item, index, refs, lead) {
  const card = element("article", "result-entry");
  if (lead) {
    card.classList.add("answer-lead");
    card.append(element("p", "answer-lead-label", "最相关的方法"));
  }
  card.append(element("h3", "", item.method), element("p", "result-context", item.scenario));
  const fields = element("dl", "result-data");
  for (const [label, key] of METHOD_FIELDS) {
    fields.append(element("dt", "", label), element("dd", "", item[key]));
  }
  card.append(fields, citations([item.entry_id], index, refs));
  return card;
}

function relationIcon() {
  const namespace = "http://www.w3.org/2000/svg";
  const icon = document.createElementNS(namespace, "svg");
  icon.setAttribute("viewBox", "0 0 26 16");
  icon.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(namespace, "path");
  path.setAttribute("d", "M2 8h20m-5-5 5 5-5 5");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.5");
  icon.append(path);
  return icon;
}

function mappingCard(item, index, refs, lead) {
  const card = element("article", "result-entry");
  if (lead) {
    card.classList.add("answer-lead");
    card.append(element("p", "answer-lead-label", "最匹配的概念对齐"));
  }
  const diagram = element("div", "concept-map");
  diagram.setAttribute("role", "img");
  diagram.setAttribute("aria-label", item.source + " 对应 " + item.target);
  const arrow = element("span", "concept-arrow");
  arrow.append(relationIcon());
  diagram.append(
    element("span", "concept-node concept-source", item.source),
    arrow,
    element("span", "concept-node concept-target", item.target),
  );
  card.append(element("h3", "", item.relation), diagram, element("p", "", item.explanation),
    citations(item.entry_ids, index, refs));
  return card;
}

function evidenceDrawer(items, index, refs) {
  const evidence = element("details", "evidence");
  evidence.append(element("summary", "", "参考依据 · " + items.length + " 条"));
  for (const item of items) {
    const entry = element("article", "reference");
    entry.id = sourceId(index, item.entry_id);
    entry.tabIndex = -1;
    const lines = item.text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    const [title, ...details] = lines.filter((line) => !item.links.includes(line));
    const heading = element("h3", "", title || "知识库条目");
    const urls = refs.get(item.entry_id)?.urls || [];
    if (urls.length === 1) {
      const anchor = element("a", "reference-title-link", heading.textContent);
      openReference(anchor, urls[0]);
      heading.replaceChildren(anchor);
    }
    entry.append(element("span", "reference-id", item.entry_id), heading);
    if (details.length) entry.append(element("p", "", details.join("\n")));
    const links = element("div", "reference-links");
    for (const [position, destination] of urls.entries()) {
      const label = urls.length === 1 ? "打开原文" : "打开文献 " + (position + 1);
      const anchor = element("a", "", label);
      openReference(anchor, destination);
      links.append(anchor);
    }
    if (links.childElementCount) entry.append(links);
    evidence.append(entry);
  }
  return evidence;
}

function thinkingBlock(text, live = false, label = "Thinking...") {
  const block = element("details", "thinking-block" + (live ? " is-live" : ""));
  block.open = live;
  block.append(element("summary", "", label));
  block.append(element("div", "thinking-body", text));
  return block;
}

function localSummary(payload) {
  const results = payload.results || [];
  if (!results.length) return null;
  const first = results[0];
  if (first.method) {
    const entry = first.entry_id ? `（${first.entry_id}）` : "";
    const others = results.slice(1).map((item) => item.method).filter(Boolean);
    let text = `检索到 ${results.length} 个相关方法。综合来看，优先查看 ${first.method}${entry}`;
    if (first.scenario) {
      text += `，适用于${String(first.scenario).replace(/[。；;]+$/, "")}`;
    }
    text += "。";
    if (others.length) text += `其他匹配包括 ${others.join("、")}。`;
    text += "选择前建议重点核对各方法的适用条件和局限。";
    return element("p", "local-summary", text);
  }
  const others = results.slice(1).map((item) => `${item.source} → ${item.target}`);
  let text = `检索到 ${results.length} 条概念关系。最匹配的是「${first.source} → ${first.target}」（${first.relation}）。`;
  if (first.explanation) {
    text += first.explanation.replace(/[。；;]+$/, "") + "。";
  }
  if (others.length) text += `其他关系包括 ${others.join("；")}。`;
  return element("p", "local-summary", text);
}

function matchingResults(payload, index, refs) {
  const renderCard = payload.mode === "method" ? methodCard : mappingCard;
  const results = element("div", "answer-matches");
  const visible = payload.answer ? [] : payload.results.slice(0, 2);
  const details = payload.answer ? payload.results : payload.results.slice(2);
  visible.forEach((item, position) => {
    results.append(renderCard(item, index, refs, position === 0));
  });
  if (details.length) {
    const fold = element("details", "match-details");
    const label = payload.answer ? "查看知识库匹配" : "其他匹配";
    fold.append(element("summary", "", label + " · " + details.length + " 条"));
    const list = element("div", "result-list");
    list.append(...details.map((item) => renderCard(item, index, refs)));
    fold.append(list);
    results.append(fold);
  }
  return results;
}

function greetingReply(turn) {
  if (!/^(?:你好|您好|嗨|哈[喽啰]|hi|hello|hey)[\s!！.。~～]*$/i.test(turn.question.trim())) return null;
  return {
    mode: turn.mode,
    source: "conversation",
    answer: "你好！我是 Fieldweave。你可以问我一个研究问题，我可以帮你找相关方法、对齐概念和查看文献依据",
    results: [],
    references: [],
  };
}

function renderReply(turn, index, view) {
  const { heading, body, reply } = view;
  body.replaceChildren();
  const saved = turn.response;
  const payload = saved?.source === "local" && !saved.results.length ? (greetingReply(turn) || saved) : saved;
  reply.setAttribute("aria-busy", String(!payload && !turn.error));
  if (turn.error) {
    heading.textContent = "查询未完成";
    body.append(element("p", "notice", statusText(turn.error)));
    const retry = element("button", "secondary-button", "填回输入框");
    retry.type = "button";
    retry.addEventListener("click", () => fillQuestion(turn.question, turn.caseCode));
    body.append(retry);
    return;
  }
  if (!payload) {
    heading.textContent = "科研助手";
    body.append(thinkingBlock(
      modelConfigured ? "正在理解问题、检索知识库并组织回答…" : "正在检索本地知识库…",
      true,
      modelConfigured ? "Thinking..." : "正在检索…",
    ));
    return;
  }
  heading.textContent = payload.kind === "external"
    ? "外部文献回答"
    : (payload.kind !== "general" && payload.source === "local" ? "知识库回答" : "科研助手");
  const modeLabel = (MODES[payload.mode] || MODES[turn.mode] || {}).label || "问答";
  const scopeText = payload.kind === "external"
    ? "公开文献 · 外部检索"
    : (payload.kind === "general" || payload.source === "conversation"
      ? "对话"
      : (cases.find((item) => item.code === payload.retrieval_case)?.label || turn.caseLabel) + " · " + modeLabel);
  view.user.title = scopeText;
  view.label.title = scopeText;
  const refs = new Map(payload.references.map((item) => [item.entry_id, {
    urls: referenceUrls(item), text: item.text,
  }]));
  for (const source of payload.external_sources || []) {
    let sourceUrl = null;
    try {
      if (source.url) sourceUrl = new URL(source.url);
    } catch { /* Ignore malformed external URLs. */ }
    refs.set(source.id, {
      urls: sourceUrl ? [sourceUrl] : [],
      text: [source.title, source.authors, source.year, source.venue, source.doi]
        .filter(Boolean).join(" · "),
    });
  }
  if (payload.thinking?.trim()) body.append(thinkingBlock(payload.thinking.trim()));
  if (payload.answer) {
    body.append(modelBlock(payload.answer, refs, index));
  }
  const summary = payload.answer ? null : localSummary(payload);
  if (summary) body.append(summary);
  if (payload.results.length) body.append(matchingResults(payload, index, refs));
  if (payload.notice) body.append(element("p", "reply-note", statusText(payload.notice)));
  const coverage = coverageNote(payload, turn);
  if (coverage) body.append(coverage);
  if (payload.references.length) body.append(evidenceDrawer(payload.references, index, refs));
  if (payload.external_sources?.length) body.append(externalSources(payload.external_sources));
  if (payload.local_sources?.length) body.append(localSources(payload.local_sources));
  if (payload.published_sources?.length) body.append(publishedSources(payload.published_sources, payload.retrieval_case || turn.caseCode));
  if (payload.source !== "conversation") body.append(replyActions(turn, payload, index));
}

function coverageNote(payload, turn) {
  if (payload.kind === "general" || payload.kind === "external"
      || payload.source === "conversation") return null;
  const evidence = payload.references?.length || 0;
  const published = payload.published_sources?.length || 0;
  if (evidence >= 3 || evidence + published >= 3) return null;
  const note = element("aside", "coverage-note");
  const message = element("p");
  message.append(
    element("strong", "coverage-note-lead", "本地证据较少"),
    "：知识库命中 " + evidence + " 条，相关采集文献 " + published
      + " 篇。可以补充研究对象、数据类型或方法名，或采集更多文献。",
  );
  note.append(message);
  note.append(button("file-action", "打开文献与数据", () => openLiterature(payload.retrieval_case || turn.caseCode)));
  return note;
}

function plainReply(payload) {
  if (payload.answer) return payload.answer;
  const lines = [];
  if (payload.notice) lines.push(payload.notice);
  for (const item of payload.results || []) {
    if (item.method) {
      lines.push("方法：" + item.method);
      for (const [label, key] of METHOD_FIELDS) lines.push(label + "：" + (item[key] || ""));
    } else {
      lines.push(item.source + " → " + item.target, item.explanation || "");
    }
    lines.push("");
  }
  for (const item of payload.references || []) lines.push("[" + item.entry_id + "] " + item.text);
  return lines.join("\n").trim();
}

function announce(message) {
  byId("turn-updates").textContent = message;
}

async function copyToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Fall through to execCommand when the browser denies the async API.
    }
  }
  const area = element("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "-1000px";
  area.style.left = "0";
  document.body.append(area);
  area.focus();
  area.select();
  area.setSelectionRange(0, text.length);
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } finally {
    area.remove();
  }
  if (!copied) throw new Error("复制失败");
}

const COPY_ICON = ["M9 9h10v10H9z", "M5 15V5h10"];
const CHECK_ICON = ["m5 12 4 4L19 6"];
const REFRESH_ICON = ["M21 12a9 9 0 1 1-2.64-6.36", "M21 3v6h-6"];
const EDIT_ICON = ["m14 6 4 4", "M5 19l4.2-.8L19 8.4a2.4 2.4 0 0 0-3.4-3.4L5.8 14.8 5 19Z"];
const ICON_NS = "http://www.w3.org/2000/svg";

function iconSvg(paths) {
  const svg = document.createElementNS(ICON_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  for (const d of paths) {
    const path = document.createElementNS(ICON_NS, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

function iconAction(label, paths, handler) {
  const node = button("turn-action", null, handler);
  node.append(iconSvg(paths));
  node.setAttribute("aria-label", label);
  node.title = label;
  return node;
}

function setActionLabel(node, label, paths) {
  node.replaceChildren(iconSvg(paths));
  node.setAttribute("aria-label", label);
  node.title = label;
}

let editingIndex = null;

function copyAction(text, label, success) {
  const node = iconAction(label, COPY_ICON, async () => {
    try {
      await copyToClipboard(text);
      setActionLabel(node, "已复制", CHECK_ICON);
      announce(success);
      setTimeout(() => setActionLabel(node, label, COPY_ICON), 1600);
    } catch {
      setActionLabel(node, "复制失败", COPY_ICON);
      announce("复制失败，请重试");
      setTimeout(() => setActionLabel(node, label, COPY_ICON), 1600);
    }
  });
  return node;
}

function userActions(turn, index) {
  const actions = element("div", "user-actions");
  actions.append(
    copyAction(turn.question, "复制问题", "问题已复制"),
    iconAction("编辑问题", EDIT_ICON, () => beginEditTurn(index)),
  );
  return actions;
}

function replyActions(turn, payload, index) {
  const actions = element("div", "turn-actions");
  actions.append(
    copyAction(plainReply(payload), "复制回答", "回答已复制"),
    iconAction("重新生成", REFRESH_ICON, () => regenerateTurn(index)),
  );
  return actions;
}

async function rewindAndAsk(index, text, caseCode) {
  if (!ready || busy || !active.id) return false;
  if (pendingTurns.get(active.id)?.length) {
    try {
      active = await savePendingTurns(active.id);
    } catch {
      note("有回答还未写入本地记录，请稍后重试");
      return false;
    }
  }
  setBusy(true);
  let prepared = false;
  try {
    const { chat } = await request(`${API}/chats/${active.id}/truncate`, { keep: index });
    active = chat;
    rememberChat(chat);
    renderTranscript();
    prepared = true;
  } catch (error) {
    note(error.status === 404 && error.message.includes("工作台接口")
      ? "这个操作需要重启本地服务后生效。请关闭启动窗口并重新启动（Windows：Start.cmd；macOS：Start.command），然后按 Ctrl+F5。"
      : error.message);
    renderTranscript();
  } finally {
    setBusy(false);
  }
  if (prepared) await askQuestion(text, caseCode, { clearInput: false });
  return prepared;
}

async function regenerateTurn(index) {
  const turn = active.turns[index];
  if (!turn) return;
  if (index < active.turns.length - 1) announce("正在重新生成这一轮，其后的回答会被移除");
  await rewindAndAsk(index, turn.question, turn.caseCode);
}

function cancelEditTurn() {
  if (editingIndex === null) return;
  editingIndex = null;
  const top = viewport.scrollTop;
  renderTranscript();
  viewport.scrollTop = top;
}

function beginEditTurn(index) {
  if (!ready || busy || !active.id) return;
  if (editingIndex !== null) cancelEditTurn();
  const turn = active.turns[index];
  const node = transcript.children[index];
  const message = node?.querySelector(".user-message");
  const text = message?.querySelector(".user-text");
  if (!turn || !message || !text) return;
  editingIndex = index;
  message.classList.add("is-editing");
  text.hidden = true;
  const userActionsNode = message.querySelector(".user-actions");
  if (userActionsNode) userActionsNode.hidden = true;
  const editor = element("textarea", "edit-question");
  editor.value = turn.question;
  editor.maxLength = 600;
  editor.rows = 2;
  editor.setAttribute("aria-label", "编辑问题");
  const save = button("primary-button", "保存并重新生成", () => saveEditedTurn(index, editor, save));
  const cancel = button("secondary-button", "取消", cancelEditTurn);
  cancel.classList.add("edit-cancel");
  const actions = element("div", "edit-actions");
  actions.append(save, cancel);
  message.append(editor);
  if (index < active.turns.length - 1) {
    message.append(element("p", "edit-hint", "保存后会重新生成这一轮，并移除其后的回答。"));
  }
  message.append(actions);
  editor.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      cancelEditTurn();
      return;
    }
    if (event.key !== "Enter" || event.shiftKey || event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    if (!save.disabled) save.click();
  });
  editor.focus();
  editor.setSelectionRange(editor.value.length, editor.value.length);
  scrollToTurn(node);
}

async function saveEditedTurn(index, editor, saveButton) {
  if (editingIndex !== index) return;
  const value = editor.value.trim();
  if (!value) {
    editor.focus();
    return;
  }
  if (!ready || busy || !active.id) return;
  const turn = active.turns[index];
  if (!turn) return;
  editingIndex = null;
  const cancelButton = saveButton.parentElement?.querySelector(".edit-cancel");
  editor.disabled = true;
  saveButton.disabled = true;
  if (cancelButton) cancelButton.disabled = true;
  saveButton.textContent = "正在重新生成…";
  const prepared = await rewindAndAsk(index, value, turn.caseCode);
  if (!prepared && editor.isConnected) {
    editingIndex = index;
    editor.disabled = false;
    saveButton.disabled = false;
    if (cancelButton) cancelButton.disabled = false;
    saveButton.textContent = "保存并重新生成";
  }
}

function localSources(sources) {
  const drawer = element("details", "local-sources");
  drawer.append(element("summary", "", "本地资料摘录 · " + sources.length + " 份"));
  for (const source of sources) {
    const entry = element("article", "local-source");
    entry.append(button("file-action", source.name, () => openFiles(source.id)),
      element("p", "", source.excerpt));
    drawer.append(entry);
  }
  return drawer;
}

function publishedSources(sources, caseCode) {
  const drawer = element("details", "local-sources");
  drawer.append(element("summary", "", "相关采集文献 · " + sources.length + " 篇"));
  for (const source of sources) {
    const entry = element("article", "local-source");
    entry.append(button("literature-link", source.title, () => openLiterature(caseCode, source.id)),
      element("p", "", [source.provider, source.year, source.doi].filter(Boolean).join(" · ")));
    drawer.append(entry);
  }
  return drawer;
}

function externalSources(sources) {
  const drawer = element("details", "local-sources external-sources");
  drawer.append(element("summary",
    "", "外部文献检索 · " + sources.length + " 篇（未进入本地知识库）"));
  for (const source of sources) {
    const entry = element("article", "local-source");
    const link = element("a", "literature-link", source.title);
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noreferrer noopener";
    entry.append(link,
      element("p", "",
        [source.provider, source.year, source.venue, source.doi]
          .filter(Boolean).join(" · ")));
    if (source.abstract) {
      entry.append(element("p", "external-abstract", source.abstract));
    }
    drawer.append(entry);
  }
  return drawer;
}

function turnView(turn, index) {
  const node = element("article", "turn");
  const user = element("div", "user-message");
  const userLabel = element("div", "user-label");
  const initialScope = turn.mode === "auto"
    ? "自动"
    : turn.caseLabel + " · " + (MODES[turn.mode]?.label || "问答");
  user.title = initialScope;
  userLabel.title = initialScope;
  userLabel.append(element("strong", "", "你"));
  user.append(userLabel, element("p", "user-text", turn.question), userActions(turn, index));
  const reply = element("section", "reply");
  const title = element("header", "reply-title");
  const mark = element("span", "reply-mark");
  mark.append(byId("reply-mark").content.cloneNode(true));
  const heading = element("h2");
  const body = element("div", "reply-body");
  title.append(mark, heading);
  reply.append(title, body);
  node.append(user, reply);
  const view = { node, heading, body, reply, user, label: userLabel };
  renderReply(turn, index, view);
  return view;
}



async function askQuestion(text, caseCode = active.case_code, { clearInput = true } = {}) {
  const item = cases.find((entry) => entry.code === caseCode) || currentCase();
  const value = (text || "").trim();
  if (!ready || busy || loading || modelPending || !item || !value) return;
  const turn = { question: value, caseCode: item.code, caseLabel: item.label, mode: "auto" };
  note();
  loading = true;
  updateControls();
  try {
    const id = await ensureActiveChat();
    const index = active.turns.length;
    active.turns.push(turn);
    if (clearInput) question.value = "";
    const view = turnView(turn, index);
    transcript.append(view.node);
    updatePane();
    scrollToTurn(view.node);
    byId("turn-updates").textContent = "正在检索";

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), modelConfigured ? 165000 : 55000);
    try {
      turn.response = greetingReply(turn) || await request(
        "/api/ask", { case: turn.caseCode, mode: turn.mode, question: value, chat_id: id }, controller.signal,
      );
    } catch (error) {
      turn.error = error.name === "AbortError" ? "等待超时，可以把问题填回输入框后重试"
        : error instanceof TypeError ? "无法连接本地服务，请确认启动程序仍在运行" : error.message;
    } finally {
      clearTimeout(timeout);
    }
    renderReply(turn, index, view);
    const queue = pendingTurns.get(id) || [];
    queue.push({ turn, turn_id: crypto.randomUUID(), case_code: turn.caseCode, mode: turn.mode });
    pendingTurns.set(id, queue);
    try {
      active = await savePendingTurns(id);
      paintWorkspace();
    } catch {
      note("这条回答暂未保存，重新打开这条对话时会尝试保存");
    }
    saveTab();
    byId("turn-updates").textContent = turn.error ? "查询未完成" : "知识库回答已就绪";
  } catch (error) {
    note(error.message);
  } finally {
    loading = false;
    updateControls();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  askQuestion(question.value);
});

let composing = false;
let enterInComposition = false;

question.addEventListener("compositionstart", () => {
  composing = true;
  enterInComposition = false;
});
question.addEventListener("compositionend", () => {
  composing = false;
  if (!enterInComposition) return;
  enterInComposition = false;
  // Some IMEs leave a line break behind when Enter confirms a candidate.
  requestAnimationFrame(() => {
    if (question.value.endsWith("\n")) {
      question.value = question.value.replace(/\n+$/, "");
      updateInput();
    }
  });
});
question.addEventListener("input", updateInput);
question.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  if (event.isComposing || composing || event.keyCode === 229) {
    if (!event.shiftKey) enterInComposition = true;
    return;
  }
  if (event.defaultPrevented || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
  event.preventDefault();
  if (!event.repeat && !submit.disabled) form.requestSubmit(submit);
});
