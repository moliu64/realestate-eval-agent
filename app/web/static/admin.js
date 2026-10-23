/* Knowledge-base admin front-end.
   Authorisation is cookie + role based (`GET /admin/access`); the legacy X-Admin-Token
   input and sessionStorage hand-off have been removed. API paths are unchanged. */
(() => {
  "use strict";

  const API_BASE = (window.APP_API_BASE || "").replace(/\/$/, "");
  const apiUrl = (path) => `${API_BASE}${path}`;
  const $ = (selector) => document.querySelector(selector);
  const toast = (window.UI && window.UI.toast) || ((message) => console.info(message));
  const confirmAction = (window.UI && window.UI.confirm) || (() => Promise.resolve(false));

  const statusEl = $("#admin-status");
  const statusText = $("#admin-status-text");
  const statusDot = $("#admin-status-dot");
  const adminContent = $("#admin-content");
  const adminGate = $("#admin-gate");
  const adminGateCopy = $("#admin-gate-copy");
  const adminAccount = $("#admin-account");
  const adminAccountName = $("#admin-account-name");
  const fileEl = $("#file");
  const titleEl = $("#document-title");
  const categoryEl = $("#category");
  const form = $("#admin-form");
  const documentsEl = $("#documents");
  const documentCount = $("#document-count");
  const previewButton = $("#preview-upload");
  const uploadButton = $("#upload-document");
  const retryButton = $("#admin-retry");
  const previewEl = $("#chunk-preview");
  const previewMeta = $("#preview-meta");

  const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
  const ALLOWED_EXTENSIONS = /\.(md|txt|csv|pdf|docx|png|jpe?g)$/i;
  const state = { authorized: false, documents: [] };

  function setStatus(message, kind = "") {
    statusEl.className = `admin-status glass-inset${kind ? ` is-${kind}` : ""}`;
    statusText.textContent = message;
  }

  function setBusy(button, busy) {
    if (!button) return;
    button.disabled = busy;
    button.classList.toggle("is-loading", busy);
    button.setAttribute("aria-busy", String(busy));
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  async function requestJson(path, options = {}) {
    const response = await fetch(apiUrl(path), { credentials: "include", ...options });
    const raw = await response.text();
    let data = null;
    if (raw) {
      try {
        data = JSON.parse(raw);
      } catch (error) {
        data = null;
      }
    }
    if (!response.ok) {
      const detail = data && (data.detail || data.message);
      const message = typeof detail === "string" && detail ? detail : `请求失败（HTTP ${response.status}）`;
      const failure = new Error(message);
      failure.status = response.status;
      throw failure;
    }
    return data;
  }

  function showWorkspace(username) {
    state.authorized = true;
    if (adminGate) adminGate.hidden = true;
    if (adminContent) adminContent.hidden = false;
    if (adminAccount) adminAccount.hidden = false;
    if (adminAccountName) adminAccountName.textContent = username || "管理员";
    document.body.classList.add("is-admin");
  }

  function showGate(message) {
    state.authorized = false;
    if (adminContent) adminContent.hidden = true;
    if (adminGate) adminGate.hidden = false;
    if (adminGateCopy && message) adminGateCopy.textContent = message;
    if (adminAccount) adminAccount.hidden = true;
    document.body.classList.remove("is-admin");
  }

  function handleError(error, context) {
    const unauthorized = error.status === 401 || error.status === 403;
    if (unauthorized) {
      const message = error.status === 403
        ? "当前账号没有管理员权限，无法管理知识库。请使用管理员账号登录后重试。"
        : "登录状态已失效，请重新登录后再试。";
      showGate(message);
      toast("管理员权限校验失败", "error");
      return;
    }
    setStatus(`${context}：${error.message}`, "error");
    toast(`${context}：${error.message}`, "error");
  }

  async function checkAccess(options = {}) {
    setStatus("正在校验管理员权限…");
    try {
      const access = await requestJson("/admin/access");
      showWorkspace(access.username);
      if (!options.silent) toast("已连接知识库", "success");
      await loadDocuments({ silent: true });
      return true;
    } catch (error) {
      handleError(error, "权限校验失败");
      return false;
    }
  }

  async function loadDocuments(options = {}) {
    try {
      const payload = await requestJson("/admin/documents");
      state.documents = Array.isArray(payload) ? payload : [];
      renderDocuments(state.documents);
      setStatus(`知识库已连接，共 ${state.documents.length} 份文档。`, "success");
      return state.documents;
    } catch (error) {
      handleError(error, "文档加载失败");
      if (!options.silent) {
        documentsEl.className = "document-list empty";
        documentsEl.textContent = "文档加载失败，请稍后重试。";
      }
      return [];
    }
  }

  function renderDocuments(items) {
    documentCount.textContent = `${items.length} 份`;
    if (!items.length) {
      documentsEl.className = "document-list empty";
      documentsEl.textContent = "知识库暂无文档。";
      return;
    }
    documentsEl.className = "document-list";
    documentsEl.replaceChildren(...items.map(renderDocument));
  }

  function renderDocument(item) {
    const card = document.createElement("article");
    card.className = "document-item";

    const info = document.createElement("div");
    info.className = "document-info";
    const category = document.createElement("span");
    category.className = "document-category";
    category.textContent = item.category || "未分类";
    const name = document.createElement("strong");
    name.textContent = item.source || "未命名文档";
    const meta = document.createElement("small");
    meta.textContent = `${String(item.file_type || "").toUpperCase()} · ${formatBytes(item.size)} · ${String(item.updated_at || "").replace("T", " ")}`;
    info.append(category, name, meta);

    const actions = document.createElement("div");
    actions.className = "document-actions";
    const preview = document.createElement("button");
    preview.type = "button";
    preview.className = "button button-secondary";
    preview.textContent = "查看切片";
    preview.addEventListener("click", () => {
      previewStoredDocument(item.source).catch((error) => handleError(error, "切片预览失败"));
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger-action";
    remove.textContent = "删除";
    remove.addEventListener("click", () => {
      deleteDocument(item.source).catch((error) => handleError(error, "删除失败"));
    });
    actions.append(preview, remove);
    card.append(info, actions);
    return card;
  }

  function renderPreview(payload) {
    previewMeta.textContent = `${payload.characters} 字符 · ${payload.chunk_count} 片段`;
    previewEl.className = "chunk-preview";
    const chunks = Array.isArray(payload.chunks) ? payload.chunks : [];
    if (!chunks.length) {
      previewEl.className = "chunk-preview empty";
      previewEl.textContent = "该文档没有可预览的切片。";
      return;
    }
    previewEl.replaceChildren(...chunks.map((chunk) => {
      const item = document.createElement("article");
      item.className = "chunk-item";
      const head = document.createElement("div");
      head.className = "chunk-head";
      head.textContent = `片段 ${Number(chunk.index) + 1} · ${chunk.characters} 字 · 与上一片重叠 ${chunk.overlap_chars} 字`;
      const text = document.createElement("p");
      text.textContent = chunk.text;
      item.append(head, text);
      return item;
    }));
  }

  function validateFile() {
    const file = fileEl.files[0];
    if (!file) {
      toast("请选择需要入库的文档", "warning");
      return null;
    }
    if (!ALLOWED_EXTENSIONS.test(file.name)) {
      toast("仅支持 md、txt、csv、pdf、docx、png、jpg、jpeg 文件", "warning");
      return null;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      toast("文件不能超过 20MB", "error");
      return null;
    }
    return file;
  }

  async function previewFile() {
    if (!state.authorized) {
      toast("管理员权限尚未就绪，请稍后重试", "warning");
      return;
    }
    const file = validateFile();
    if (!file) return;
    const data = new FormData();
    data.append("file", file);
    setBusy(previewButton, true);
    setStatus("正在解析文档并生成切片预览…");
    try {
      const payload = await requestJson("/admin/preview", { method: "POST", body: data });
      renderPreview(payload);
      setStatus("切分预览已生成，请确认内容后入库。", "success");
      toast("切分预览已生成", "success");
    } catch (error) {
      handleError(error, "预览失败");
    } finally {
      setBusy(previewButton, false);
    }
  }

  async function previewStoredDocument(source) {
    setStatus(`正在读取 ${source} 的切片…`);
    const payload = await requestJson(`/admin/documents/${encodeURIComponent(source)}`);
    renderPreview(payload);
    const previewCard = document.querySelector(".admin-preview");
    if (previewCard) previewCard.scrollIntoView({ behavior: "smooth", block: "start" });
    setStatus(`已显示 ${source} 的切片。`, "success");
  }

  async function uploadDocument(event) {
    event.preventDefault();
    if (!state.authorized) {
      toast("管理员权限尚未就绪，请稍后重试", "warning");
      return;
    }
    const file = validateFile();
    if (!file) return;
    const title = titleEl.value.trim();
    if (!title) {
      titleEl.focus();
      toast("请填写文档中文标题", "warning");
      return;
    }
    const data = new FormData();
    data.append("file", file);
    data.append("category", categoryEl.value);
    data.append("title", title);
    setBusy(uploadButton, true);
    setStatus("正在解析文档并重建向量库…");
    try {
      const payload = await requestJson("/admin/upload", { method: "POST", body: data });
      const action = payload.replaced ? "已更新" : "已入库";
      setStatus(`${action} ${payload.source}，当前向量片段 ${payload.vector_count} 条。`, "success");
      toast(`${action} ${payload.source}`, "success");
      fileEl.value = "";
      titleEl.value = "";
      await loadDocuments({ silent: true });
    } catch (error) {
      handleError(error, "入库失败");
    } finally {
      setBusy(uploadButton, false);
    }
  }

  async function deleteDocument(source) {
    const confirmed = await confirmAction({
      title: "删除知识库文档",
      message: `将永久删除「${source}」并重建向量库，此操作不可撤销。`,
      confirmText: "删除文档",
      cancelText: "取消",
      danger: true,
    });
    if (!confirmed) return;
    setStatus("正在删除文档并重建向量库…");
    try {
      const payload = await requestJson(`/admin/documents/${encodeURIComponent(source)}`, { method: "DELETE" });
      setStatus(`已删除 ${source}，当前向量片段 ${payload.vector_count} 条。`, "success");
      toast("文档已删除", "success");
      await loadDocuments({ silent: true });
    } catch (error) {
      handleError(error, "删除失败");
    }
  }

  function bindEvents() {
    fileEl.addEventListener("change", () => {
      const file = fileEl.files[0];
      if (file && !titleEl.value.trim()) {
        titleEl.value = file.name.replace(/\.[^.]+$/, "").replace(/^[^_]+_/, "");
      }
    });
    previewButton.addEventListener("click", () => {
      previewFile().catch((error) => handleError(error, "预览失败"));
    });
    form.addEventListener("submit", uploadDocument);
    retryButton.addEventListener("click", () => {
      checkAccess().catch((error) => handleError(error, "权限校验失败"));
    });
  }

  bindEvents();
  checkAccess().catch((error) => handleError(error, "权限校验失败"));
})();
