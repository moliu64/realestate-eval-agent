const API_BASE = (window.APP_API_BASE || "").replace(/\/$/, "");
const apiUrl = (path) => `${API_BASE}${path}`;

const answerEl = document.querySelector("#answer");
const sourcesEl = document.querySelector("#sources");
const elapsedEl = document.querySelector("#elapsed");
const stepsEl = document.querySelector("#steps");
const stepCountEl = document.querySelector("#step-count");
const reportJsonEl = document.querySelector("#report-json");
const copyJsonButton = document.querySelector("#copy-json");
const evaluateForm = document.querySelector("#evaluate-form");
const evaluateSubmit = document.querySelector("#estimate-submit");
const presetLoad = document.querySelector("#preset-load");
const presetStatus = document.querySelector("#preset-status");
let presetSources = [];
let presetBasis = "";

const knowledgeToggle = document.querySelector("#knowledge-toggle");
const knowledgePanel = document.querySelector("#knowledge-panel");
const knowledgeClose = document.querySelector("#knowledge-close");
const adminEntry = document.querySelector(".admin-entry");
const adminEntryToggle = document.querySelector("#admin-entry-toggle");
const adminEntryPanel = document.querySelector("#admin-entry-panel");
const adminEntryClose = document.querySelector("#admin-entry-close");
const adminEntryForm = document.querySelector("#admin-entry-form");
const adminEntryToken = document.querySelector("#admin-entry-token");
const adminEntrySubmit = document.querySelector("#admin-entry-submit");
const adminEntryStatus = document.querySelector("#admin-entry-status");

function openKnowledge() {
  knowledgePanel.hidden = false;
  document.body.classList.add("knowledge-open");
  window.requestAnimationFrame(() => knowledgePanel.classList.add("is-open"));
  knowledgeToggle.setAttribute("aria-expanded", "true");
  document.querySelector("#rag-question").focus();
}

function closeKnowledge() {
  knowledgePanel.classList.remove("is-open");
  document.body.classList.remove("knowledge-open");
  knowledgeToggle.setAttribute("aria-expanded", "false");
  window.setTimeout(() => {
    if (!knowledgePanel.classList.contains("is-open")) knowledgePanel.hidden = true;
  }, 180);
}

knowledgeToggle.addEventListener("click", () => {
  if (knowledgePanel.hidden) openKnowledge(); else closeKnowledge();
});
knowledgeClose.addEventListener("click", closeKnowledge);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !knowledgePanel.hidden) closeKnowledge();
});
document.addEventListener("pointerdown", (event) => {
  if (!knowledgePanel.hidden && !knowledgePanel.contains(event.target) && !knowledgeToggle.contains(event.target)) closeKnowledge();
});

function openAdminEntry() {
  if (!knowledgePanel.hidden) closeKnowledge();
  adminEntryPanel.hidden = false;
  adminEntryStatus.textContent = "";
  adminEntryStatus.className = "admin-entry-status";
  document.body.classList.add("admin-entry-open");
  window.requestAnimationFrame(() => adminEntryPanel.classList.add("is-open"));
  adminEntryToggle.setAttribute("aria-expanded", "true");
  adminEntryToken.focus();
}

function closeAdminEntry() {
  adminEntryPanel.classList.remove("is-open");
  document.body.classList.remove("admin-entry-open");
  adminEntryToggle.setAttribute("aria-expanded", "false");
  window.setTimeout(() => {
    if (!adminEntryPanel.classList.contains("is-open")) adminEntryPanel.hidden = true;
  }, 180);
}

adminEntryToggle.addEventListener("click", () => {
  if (adminEntryPanel.hidden) openAdminEntry(); else closeAdminEntry();
});
adminEntryClose.addEventListener("click", closeAdminEntry);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !adminEntryPanel.hidden) closeAdminEntry();
});
document.addEventListener("pointerdown", (event) => {
  if (!adminEntryPanel.hidden && !adminEntry.contains(event.target)) closeAdminEntry();
});

adminEntryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = adminEntryToken.value.trim();
  if (!token) {
    adminEntryStatus.className = "admin-entry-status error";
    adminEntryStatus.textContent = "请输入管理密钥";
    adminEntryToken.focus();
    return;
  }
  adminEntrySubmit.disabled = true;
  adminEntrySubmit.classList.add("is-loading");
  adminEntryStatus.className = "admin-entry-status";
  adminEntryStatus.textContent = "正在验证...";
  try {
    const response = await fetch(apiUrl("/admin/access"), {
      headers: { "X-Admin-Token": token },
    });
    if (response.status === 401) throw new Error("INVALID_TOKEN");
    if (!response.ok) throw new Error("SERVER_ERROR");
    adminEntryStatus.className = "admin-entry-status success";
    adminEntryStatus.textContent = "验证通过，正在进入...";
    const adminBase = API_BASE || window.location.origin;
    const destination = new URL("/admin", adminBase);
    destination.hash = new URLSearchParams({ access: token, return: window.location.origin }).toString();
    window.location.assign(destination.toString());
  } catch (error) {
    adminEntryStatus.className = "admin-entry-status error";
    adminEntryStatus.textContent = error.message === "INVALID_TOKEN" ? "管理密钥错误，请重新输入" : "无法连接后端，请确认服务已启动";
    adminEntryToken.select();
  } finally {
    adminEntrySubmit.disabled = false;
    adminEntrySubmit.classList.remove("is-loading");
  }
});

function escapeHtml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function inlineMarkdown(text) {
  return escapeHtml(text).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function renderMarkdown(markdown) {
  const lines = markdown.split(/\r?\n/);
  const html = [];
  let inList = false;
  let inQuote = false;
  let inTable = false;
  const closeBlocks = () => {
    if (inList) { html.push("</ul>"); inList = false; }
    if (inQuote) { html.push("</blockquote>"); inQuote = false; }
    if (inTable) { html.push("</tbody></table>"); inTable = false; }
  };
  lines.forEach((line, index) => {
    const trimmed = line.trim();
    const next = lines[index + 1]?.trim() || "";
    if (!trimmed) { closeBlocks(); return; }
    if (/^\|(.+\|)+$/.test(trimmed) && /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(next)) {
      closeBlocks();
      const headers = trimmed.split("|").slice(1, -1).map((cell) => `<th>${inlineMarkdown(cell.trim())}</th>`);
      html.push(`<table><thead><tr>${headers.join("")}</tr></thead><tbody>`); inTable = true; return;
    }
    if (inTable) {
      if (/^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(trimmed)) return;
      if (/^\|(.+\|)+$/.test(trimmed)) { const cells = trimmed.split("|").slice(1, -1).map((cell) => `<td>${inlineMarkdown(cell.trim())}</td>`); html.push(`<tr>${cells.join("")}</tr>`); return; }
      closeBlocks();
    }
    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) { closeBlocks(); const level = heading[1].length; html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`); return; }
    if (/^[-*]\s+/.test(trimmed)) { if (!inList) { closeBlocks(); html.push("<ul>"); inList = true; } html.push(`<li>${inlineMarkdown(trimmed.replace(/^[-*]\s+/, ""))}</li>`); return; }
    if (/^>\s?/.test(trimmed)) { if (!inQuote) { closeBlocks(); html.push("<blockquote>"); inQuote = true; } html.push(`<p>${inlineMarkdown(trimmed.replace(/^>\s?/, ""))}</p>`); return; }
    closeBlocks(); html.push(`<p>${inlineMarkdown(trimmed)}</p>`);
  });
  closeBlocks();
  return html.join("");
}

function renderSources(text, target = sourcesEl) {
  const matches = [...text.matchAll(/\[来源:\s*([^\];\]]+)/g)].map((match) => match[1].trim());
  target.replaceChildren(...[...new Set(matches)].map((source) => { const chip = document.createElement("span"); chip.className = "source-chip"; chip.textContent = source; return chip; }));
}

function stepDetailLines(step) {
  const detail = step.detail || {};
  if (step.type === "understand") return [`用途：${detail.usage || "未明确"}`, `面积：${detail.area ?? "未明确"}`, `目的：${detail.purpose || "未明确"}`, detail.missing?.length ? `缺失：${detail.missing.join("、")}` : ""].filter(Boolean);
  if (step.type === "plan") return [`方法：${(detail.methods || []).join("、") || "未规划"}`];
  if (step.type === "retrieve") return [`方法：${detail.method || "未明确"}`, `来源：${(detail.sources || []).join("、") || "未匹配"}`];
  if (step.type === "compute") return [`方法：${detail.method || "未明确"}`, detail.value !== null && detail.value !== undefined ? `数值：${detail.value}` : "", detail.result || "", detail.missing?.length ? `缺失：${detail.missing.join("、")}` : ""].filter(Boolean);
  if (step.type === "verify") return [detail.verification || "已完成校核。"];
  return [JSON.stringify(detail)];
}

function renderSteps(steps = []) {
  stepCountEl.textContent = steps.length ? `${steps.length} 步` : "";
  if (!steps.length) { stepsEl.className = "steps empty"; stepsEl.textContent = "暂无执行过程。"; return; }
  stepsEl.className = "steps";
  stepsEl.replaceChildren(...steps.map((step, index) => {
    const item = document.createElement("article"); item.className = `step step-${step.type || "default"}`;
    const marker = document.createElement("span"); marker.className = "step-marker"; marker.textContent = String(index + 1).padStart(2, "0");
    const body = document.createElement("div"); body.className = "step-body";
    const title = document.createElement("h3"); title.textContent = step.label || "执行步骤"; body.appendChild(title);
    stepDetailLines(step).forEach((line) => { const paragraph = document.createElement("p"); paragraph.textContent = line; body.appendChild(paragraph); });
    item.append(marker, body); return item;
  }));
}

function renderReportJson(reportJson = "") {
  if (!reportJson) { reportJsonEl.textContent = "暂无 JSON 输出。"; return; }
  try { reportJsonEl.textContent = JSON.stringify(JSON.parse(reportJson), null, 2); } catch { reportJsonEl.textContent = reportJson; }
}

function numberOrNull(id) {
  const value = document.querySelector(`#${id}`).value.trim();
  return value === "" ? null : Number(value);
}

function buildEvaluatePayload() {
  const textValue = (id) => document.querySelector(`#${id}`).value.trim();
  return {
    property_usage: textValue("property_usage"), area: numberOrNull("area"), layout: textValue("layout"), building_age: numberOrNull("building_age"),
    orientation: textValue("orientation"), floor: textValue("floor"), decoration: textValue("decoration"), location: textValue("location"),
    valuation_purpose: textValue("valuation_purpose"), valuation_date: textValue("valuation_date"), comparable_price: numberOrNull("comparable_price"),
    net_income: numberOrNull("net_income"), cap_rate: numberOrNull("cap_rate"), land_value: numberOrNull("land_value"),
    replacement_cost: numberOrNull("replacement_cost"), depreciation: numberOrNull("depreciation"),
    preset_year: numberOrNull("preset_year"), preset_sources: presetSources, preset_basis: presetBasis, note: textValue("note"),
  };
}

presetLoad.addEventListener("click", async () => {
  const district = document.querySelector("#location").value;
  const year = document.querySelector("#preset_year").value;
  if (!district || !year) {
    presetStatus.className = "is-error";
    presetStatus.textContent = "请先选择武汉区域和数据年份";
    return;
  }
  const params = new URLSearchParams({
    district,
    year,
    property_usage: document.querySelector("#property_usage").value,
  });
  const area = document.querySelector("#area").value;
  const buildingAge = document.querySelector("#building_age").value;
  if (area) params.set("area", area);
  if (buildingAge) params.set("building_age", buildingAge);
  presetLoad.disabled = true;
  presetStatus.className = "";
  presetStatus.textContent = "正在计算预设参数...";
  try {
    const response = await fetch(apiUrl(`/api/presets/wuhan?${params}`));
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "预设加载失败");
    for (const [id, field] of Object.entries(payload.fields)) {
      if (field.value !== null && field.value !== undefined) {
        document.querySelector(`#${id}`).value = field.value;
        document.querySelector(`#${id}`).title = `${field.evidence}：${field.basis}`;
      }
    }
    presetSources = payload.sources.map((source) => source.source);
    presetBasis = `${district}，${year}年，代表地价${payload.representative_grade}级，市场系数${payload.market_factor}；参数含官方基准、公式推导和可编辑估值假设。`;
    presetStatus.className = "is-ready";
    presetStatus.textContent = `${year}年 · ${district} · ${payload.representative_grade}级地价 · 已填入，悬停字段可查看口径`;
    document.querySelector(".known-data").open = true;
  } catch (error) {
    presetStatus.className = "is-error";
    presetStatus.textContent = error.message;
  } finally {
    presetLoad.disabled = false;
  }
});

copyJsonButton.addEventListener("click", async (event) => {
  event.preventDefault(); event.stopPropagation();
  const text = reportJsonEl.textContent.trim();
  if (!text || text === "暂无 JSON 输出。" || text === "等待 JSON 输出。") return;
  await navigator.clipboard.writeText(text); copyJsonButton.textContent = "已复制";
  window.setTimeout(() => { copyJsonButton.textContent = "复制"; }, 1200);
});

evaluateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const started = performance.now(); evaluateSubmit.disabled = true; evaluateSubmit.classList.add("is-loading");
  answerEl.classList.remove("empty", "report"); answerEl.textContent = "正在生成估值报告..."; sourcesEl.replaceChildren(); renderSteps([]); renderReportJson(""); elapsedEl.textContent = "";
  try {
    const controller = new AbortController(); const timeout = window.setTimeout(() => controller.abort(), 75000);
    const response = await fetch(apiUrl("/api/evaluate"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(buildEvaluatePayload()), signal: controller.signal });
    window.clearTimeout(timeout); const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || "请求失败");
    answerEl.innerHTML = renderMarkdown(payload.answer); answerEl.classList.add("report"); renderSteps(payload.steps || []); renderReportJson(payload.report_json || ""); renderSources(payload.answer); elapsedEl.textContent = `${((performance.now() - started) / 1000).toFixed(1)}s`;
  } catch (error) { answerEl.textContent = error.name === "AbortError" ? "请求超时，请稍后重试。" : `请求失败：${error.message}`; renderSteps([]); renderReportJson(""); }
  finally { evaluateSubmit.disabled = false; evaluateSubmit.classList.remove("is-loading"); }
});

const layoutUpload = document.querySelector("#layout-upload");
const layoutFile = document.querySelector("#layout-file");
const layoutInput = document.querySelector("#layout");
const layoutStatus = document.querySelector("#layout-status");
const layoutFilename = document.querySelector("#layout-filename");
const layoutDropzone = document.querySelector("#layout-dropzone");
const layoutPlaceholder = document.querySelector("#layout-placeholder");
const layoutPreview = document.querySelector("#layout-preview");
const layoutRemove = document.querySelector("#layout-remove");
let previewUrl = "";

layoutUpload.addEventListener("click", () => layoutFile.click());
layoutDropzone.addEventListener("click", () => layoutFile.click());
layoutRemove.addEventListener("click", (event) => {
  event.stopPropagation();
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = "";
  layoutPreview.removeAttribute("src");
  layoutPreview.hidden = true;
  layoutPlaceholder.hidden = false;
  layoutRemove.hidden = true;
  layoutFile.value = "";
  layoutFilename.textContent = "尚未选择图片";
  layoutStatus.textContent = "图片已移除，户型文字保留";
});

["dragenter", "dragover"].forEach((type) => layoutDropzone.addEventListener(type, (event) => {
  event.preventDefault();
  layoutDropzone.classList.add("is-dragging");
}));
["dragleave", "drop"].forEach((type) => layoutDropzone.addEventListener(type, (event) => {
  event.preventDefault();
  layoutDropzone.classList.remove("is-dragging");
}));
layoutDropzone.addEventListener("drop", (event) => analyzeLayout(event.dataTransfer.files[0]));

async function analyzeLayout(file) {
  if (!file) return;
  if (!/\.(png|jpe?g)$/i.test(file.name)) {
    layoutStatus.textContent = "请选择 PNG、JPG 或 JPEG 户型图";
    return;
  }
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  layoutPreview.src = previewUrl;
  layoutPreview.hidden = false;
  layoutPlaceholder.hidden = true;
  layoutRemove.hidden = false;
  layoutFilename.textContent = file.name;
  const originalLabel = layoutUpload.textContent;
  layoutUpload.disabled = true;
  layoutUpload.textContent = "解析中...";
  layoutStatus.textContent = "正在读取户型图";
  try {
    const data = new FormData();
    data.append("file", file);
    const response = await fetch(apiUrl("/api/analyze-layout"), { method: "POST", body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "户型图解析失败");
    layoutInput.value = payload.layout || "";
    layoutStatus.textContent = "户型描述已填入，可继续编辑";
    layoutInput.focus();
  } catch (error) {
    layoutStatus.textContent = `解析失败：${error.message}`;
  } finally {
    layoutUpload.disabled = false;
    layoutUpload.textContent = originalLabel;
    layoutFile.value = "";
  }
}

layoutFile.addEventListener("change", () => analyzeLayout(layoutFile.files[0]));

const ragForm = document.querySelector("#rag-form");
const ragQuestion = document.querySelector("#rag-question");
const ragSubmit = document.querySelector("#rag-submit");
const ragAnswer = document.querySelector("#rag-answer");
const ragSources = document.querySelector("#rag-sources");
const ragElapsed = document.querySelector("#rag-elapsed");

ragForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = ragQuestion.value.trim();
  if (!question) { ragQuestion.focus(); return; }
  const started = performance.now();
  ragSubmit.disabled = true;
  ragSubmit.classList.add("is-loading");
  ragAnswer.classList.remove("empty", "report");
  ragAnswer.textContent = "正在检索知识库...";
  ragSources.replaceChildren();
  ragElapsed.textContent = "";
  try {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 75000);
    const response = await fetch(apiUrl("/api/rag"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: controller.signal,
    });
    window.clearTimeout(timeout);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "检索失败");
    ragAnswer.innerHTML = renderMarkdown(payload.answer);
    ragAnswer.classList.add("report");
    renderSources(payload.answer, ragSources);
    ragElapsed.textContent = `${((performance.now() - started) / 1000).toFixed(1)}s`;
  } catch (error) {
    ragAnswer.textContent = error.name === "AbortError" ? "检索超时，请稍后重试。" : `检索失败：${error.message}`;
  } finally {
    ragSubmit.disabled = false;
    ragSubmit.classList.remove("is-loading");
  }
});
