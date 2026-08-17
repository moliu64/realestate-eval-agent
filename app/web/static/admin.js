const API_BASE = (window.APP_API_BASE || "").replace(/\/$/, "");
const apiUrl = (path) => `${API_BASE}${path}`;

const tokenEl = document.querySelector("#token");
const fileEl = document.querySelector("#file");
const titleEl = document.querySelector("#document-title");
const categoryEl = document.querySelector("#category");
const form = document.querySelector("#admin-form");
const statusEl = document.querySelector("#admin-status");
const documentsEl = document.querySelector("#documents");
const documentCount = document.querySelector("#document-count");
const previewButton = document.querySelector("#preview-upload");
const uploadButton = document.querySelector("#upload-document");
const loadButton = document.querySelector("#load-documents");
const previewEl = document.querySelector("#chunk-preview");
const previewMeta = document.querySelector("#preview-meta");
const adminBack = document.querySelector(".admin-back");

const entryParams = new URLSearchParams(window.location.hash.slice(1));
const transferredToken = entryParams.get("access") || "";
const returnOrigin = entryParams.get("return") || "";
tokenEl.value = transferredToken || sessionStorage.getItem("admin-token") || "";
if (transferredToken) sessionStorage.setItem("admin-token", transferredToken);
if (/^https?:\/\/[^/]+$/i.test(returnOrigin)) adminBack.href = returnOrigin;
if (window.location.hash) window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
const headers = () => ({ "X-Admin-Token": tokenEl.value.trim() });

function setStatus(message, kind = "") {
  statusEl.className = `admin-status ${kind}`.trim();
  statusEl.textContent = message;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function requireToken() {
  if (!tokenEl.value.trim()) {
    tokenEl.focus();
    throw new Error("请先输入管理凭证");
  }
  sessionStorage.setItem("admin-token", tokenEl.value.trim());
}

function renderPreview(payload) {
  previewMeta.textContent = `${payload.characters} 字符 · ${payload.chunk_count} 片段`;
  previewEl.className = "chunk-preview";
  previewEl.replaceChildren(...payload.chunks.map((chunk) => {
    const item = document.createElement("article");
    item.className = "chunk-item";
    const head = document.createElement("div");
    head.className = "chunk-head";
    head.textContent = `片段 ${chunk.index + 1} · ${chunk.characters} 字 · 与上一片重叠 ${chunk.overlap_chars} 字`;
    const text = document.createElement("p");
    text.textContent = chunk.text;
    item.append(head, text);
    return item;
  }));
}

async function previewFile() {
  requireToken();
  if (!fileEl.files[0]) throw new Error("请选择文档文件");
  const data = new FormData();
  data.append("file", fileEl.files[0]);
  previewButton.disabled = true;
  setStatus("正在解析文档并生成切片预览...");
  try {
    const response = await fetch(apiUrl("/admin/preview"), { method: "POST", headers: headers(), body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "预览失败");
    renderPreview(payload);
    setStatus("切分预览已生成，请确认内容后入库。", "success");
  } finally {
    previewButton.disabled = false;
  }
}

async function loadDocuments() {
  requireToken();
  loadButton.disabled = true;
  try {
    const response = await fetch(apiUrl("/admin/documents"), { headers: headers() });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "加载失败");
    documentCount.textContent = `${payload.length} 份`;
    documentsEl.className = "document-list";
    documentsEl.replaceChildren(...payload.map(renderDocument));
    if (!payload.length) {
      documentsEl.className = "document-list empty";
      documentsEl.textContent = "知识库暂无文档。";
    }
    setStatus(`知识库已连接，共 ${payload.length} 份文档。`, "success");
  } finally {
    loadButton.disabled = false;
  }
}

function renderDocument(item) {
  const card = document.createElement("article");
  card.className = "document-item";
  const info = document.createElement("div");
  info.className = "document-info";
  const category = document.createElement("span");
  category.className = "document-category";
  category.textContent = item.category;
  const name = document.createElement("strong");
  name.textContent = item.source;
  const meta = document.createElement("small");
  meta.textContent = `${item.file_type.toUpperCase()} · ${formatBytes(item.size)} · ${item.updated_at.replace("T", " ")}`;
  info.append(category, name, meta);
  const actions = document.createElement("div");
  actions.className = "document-actions";
  const preview = document.createElement("button");
  preview.className = "secondary-action";
  preview.type = "button";
  preview.textContent = "查看切片";
  preview.addEventListener("click", () => previewStoredDocument(item.source).catch((error) => setStatus(error.message, "error")));
  const remove = document.createElement("button");
  remove.className = "danger-action";
  remove.type = "button";
  remove.textContent = "删除";
  remove.addEventListener("click", () => deleteDocument(item.source).catch((error) => setStatus(error.message, "error")));
  actions.append(preview, remove);
  card.append(info, actions);
  return card;
}

async function previewStoredDocument(source) {
  setStatus(`正在读取 ${source}...`);
  const response = await fetch(apiUrl(`/admin/documents/${encodeURIComponent(source)}`), { headers: headers() });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "预览失败");
  renderPreview(payload);
  document.querySelector(".admin-preview").scrollIntoView({ behavior: "smooth", block: "start" });
  setStatus(`已显示 ${source} 的切片。`, "success");
}

async function deleteDocument(source) {
  if (!window.confirm(`确定删除“${source}”并重建知识库？`)) return;
  setStatus("正在删除并重建向量库...");
  const response = await fetch(apiUrl(`/admin/documents/${encodeURIComponent(source)}`), { method: "DELETE", headers: headers() });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "删除失败");
  setStatus(`已删除 ${source}，当前向量片段 ${payload.vector_count} 条。`, "success");
  await loadDocuments();
}

fileEl.addEventListener("change", () => {
  const file = fileEl.files[0];
  if (file && !titleEl.value.trim()) titleEl.value = file.name.replace(/\.[^.]+$/, "").replace(/^[^_]+_/, "");
});

previewButton.addEventListener("click", () => previewFile().catch((error) => setStatus(error.message, "error")));
loadButton.addEventListener("click", () => loadDocuments().catch((error) => setStatus(error.message, "error")));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    requireToken();
    const data = new FormData();
    data.append("file", fileEl.files[0]);
    data.append("category", categoryEl.value);
    data.append("title", titleEl.value.trim());
    uploadButton.disabled = true;
    setStatus("正在解析文档并重建向量库...");
    const response = await fetch(apiUrl("/admin/upload"), { method: "POST", headers: headers(), body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "上传失败");
    setStatus(`${payload.replaced ? "已更新" : "已入库"} ${payload.source}，当前向量片段 ${payload.vector_count} 条。`, "success");
    fileEl.value = "";
    titleEl.value = "";
    await loadDocuments();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    uploadButton.disabled = false;
  }
});

if (transferredToken) {
  loadDocuments().catch((error) => setStatus(error.message, "error"));
}
