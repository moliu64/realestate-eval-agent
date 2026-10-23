/* RealEstate Eval Agent — valuation workspace front-end.
   Single boot path: /api/auth/me -> login gate or workspace -> sessions (load once, create only when empty).
   All API paths and payload shapes are unchanged; rendering is progressively enhanced in place. */
(() => {
  "use strict";

  const API_BASE = (window.APP_API_BASE || "").replace(/\/$/, "");
  const apiUrl = (path) => `${API_BASE}${path}`;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const toast = (window.UI && window.UI.toast) || ((message) => console.info(message));
  const confirmAction = (window.UI && window.UI.confirm) || (() => Promise.resolve(false));

  const FIELD_IDS = [
    "property_usage", "area", "location", "preset_year", "valuation_purpose", "layout",
    "building_age", "orientation", "floor", "decoration",
    "comparable_price", "net_income", "cap_rate", "land_value", "replacement_cost", "depreciation",
  ];
  const REPORT_STEPS = [
    { type: "understand", short: "理解", title: "需求理解" },
    { type: "plan", short: "规划", title: "方法规划" },
    { type: "retrieve", short: "检索", title: "知识检索" },
    { type: "compute", short: "计算", title: "工具计算" },
    { type: "verify", short: "校核", title: "交叉校核" },
  ];
  const EMPTY_FILENAME = "尚未选择图片";

  const state = {
    me: null,
    session: null,
    sessions: [],
    presetSources: [],
    presetBasis: "",
    previewUrl: "",
    syncTimer: null,
    syncSequence: 0,
    lastReport: null,
  };

  /* ---------------------------------------------------------------- helpers */

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fieldText(id) {
    const field = $(`#${id}`);
    return field ? field.value.trim() : "";
  }

  function fieldNumber(id) {
    const value = fieldText(id);
    return value === "" ? null : Number(value);
  }

  function setText(id, value) {
    const node = $(`#${id}`);
    if (node) node.textContent = value;
  }

  function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value ?? "");
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(number);
  }

  function parseDate(iso) {
    if (!iso) return null;
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function formatTime(iso) {
    const date = parseDate(iso);
    if (!date) return "";
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  function formatSessionTime(iso) {
    const date = parseDate(iso);
    if (!date) return "";
    const now = new Date();
    const sameDay = date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
    return sameDay ? formatTime(iso) : date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
  }

  function setButtonBusy(button, busy) {
    if (!button) return;
    if (busy && !button.querySelector(".spinner")) {
      const spinner = document.createElement("span");
      spinner.className = "spinner";
      spinner.setAttribute("aria-hidden", "true");
      button.append(spinner);
    }
    button.disabled = busy;
    button.classList.toggle("is-loading", busy);
    button.setAttribute("aria-busy", String(busy));
  }

  function setAutosave(message, kind = "ok") {
    const node = $("#autosave-state");
    if (!node) return;
    node.textContent = message;
    node.className = `autosave autosave-${kind}`;
  }

  async function copyText(value, successMessage) {
    const textValue = String(value ?? "");
    if (!textValue) return;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(textValue);
      } else {
        const proxy = document.createElement("textarea");
        proxy.className = "clipboard-proxy";
        proxy.value = textValue;
        document.body.append(proxy);
        proxy.select();
        const copied = document.execCommand("copy");
        proxy.remove();
        if (!copied) throw new Error("copy failed");
      }
      toast(successMessage || "已复制到剪贴板", "success");
    } catch (error) {
      toast("复制失败，请手动选择文本复制", "error");
    }
  }

  /* ------------------------------------------------------------------- api */

  async function request(path, options = {}) {
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
      if (response.status === 401 && !path.startsWith("/api/auth/") && state.me) handleSessionExpired();
      throw failure;
    }
    return data;
  }

  function handleSessionExpired() {
    if (!state.me) return;
    state.me = null;
    showGate("登录状态已失效，请重新登录。");
    toast("登录状态已失效，请重新登录", "warning");
  }

  /* ------------------------------------------------------------- boot flow */

  function init() {
    bindAuthEvents();
    bindWorkspaceEvents();
    bindGlobalShortcuts();
    boot().catch((error) => {
      showGate();
      setLoginStatus(`工作台初始化失败：${error.message}`, "error");
    });
  }

  async function boot() {
    setLoginStatus("正在检查登录状态…", "muted");
    let me;
    try {
      me = await request("/api/auth/me");
    } catch (error) {
      showGate();
      setLoginStatus(`无法连接估价服务：${error.message}`, "error");
      return;
    }
    if (!me || !me.authenticated) {
      showGate();
      setLoginStatus("", "");
      return;
    }
    await enterWorkspace(me);
  }

  async function enterWorkspace(me) {
    state.me = me;
    $("#auth-gate").hidden = true;
    $("#app-shell").hidden = false;
    document.body.classList.add("is-authenticated");
    applyAccount(me);
    setLoginStatus("", "");
    setAuthView("login", { focus: false });

    try {
      state.sessions = await request("/api/sessions");
    } catch (error) {
      toast(`会话列表加载失败：${error.message}`, "error");
      renderSessions();
      return;
    }
    renderSessions();
    if (state.sessions.length) {
      await loadSession(state.sessions[0].id, { refresh: false });
    } else {
      await createSession({ refresh: false, silent: true });
    }
  }

  function showGate(message = "") {
    state.me = null;
    if (state.session) setAutosave("已同步");
    state.session = null;
    state.lastReport = null;
    $("#app-shell").hidden = true;
    $("#auth-gate").hidden = false;
    document.body.classList.remove("is-authenticated");
    resetWorkspace();
    setLoginStatus(message, message ? "error" : "");
    window.setTimeout(() => {
      const field = $("#login-username");
      if (field) field.focus({ preventScroll: true });
    }, 80);
  }

  function applyAccount(me) {
    const isAdmin = me.role === "admin";
    document.body.classList.toggle("is-admin", isAdmin);
    $("#admin-entry").hidden = !isAdmin;
    setText("account-name", me.username || "未登录");
    setText("account-role", isAdmin ? "管理员" : "估价师");
    const avatar = $("#account-avatar");
    if (avatar) {
      avatar.textContent = (me.username || "访").slice(0, 1).toUpperCase();
      avatar.classList.toggle("is-admin", isAdmin);
    }
  }

  function setAuthView(view, options = {}) {
    const loginView = view !== "register";
    $("#login-form").hidden = !loginView;
    $("#register-form").hidden = loginView;
    setLoginStatus("", "");
    setRegisterStatus("", "");
    if (options.focus !== false) {
      window.setTimeout(() => {
        const field = loginView ? $("#login-username") : $("#register-username");
        if (field) field.focus({ preventScroll: true });
      }, 40);
    }
  }

  function setLoginStatus(message, kind = "") {
    const node = $("#login-status");
    if (!node) return;
    node.textContent = message || "";
    node.className = `form-status${kind ? ` form-status-${kind}` : ""}`;
  }

  function setRegisterStatus(message, kind = "") {
    const node = $("#register-status");
    if (!node) return;
    node.textContent = message || "";
    node.className = `form-status${kind ? ` form-status-${kind}` : ""}`;
  }

  /* -------------------------------------------------------------- sessions */

  function resetWorkspace() {
    $("#session-list").replaceChildren();
    $("#message-list").replaceChildren();
    setText("session-title", "新建估价会话");
    setText("session-meta", "暂无记录");
    setText("session-count", "0");
    for (const id of FIELD_IDS) {
      const field = $(`#${id}`);
      if (field) field.value = "";
    }
    const usage = $("#property_usage");
    if (usage) usage.value = "住宅";
    const description = $("#layout-description");
    if (description) description.value = "";
    resetLayoutImage();
    resetLayoutLabels();
    $("#rag-recent").hidden = true;
    setText("bottom-rag-status", "检索结果会进入当前会话");
    setText("preset-status", "选择区域和年份后载入权威口径参数");
    state.presetSources = [];
    state.presetBasis = "";
    renderLatest(null);
    setAutosave("已同步");
  }

  async function refreshSessions() {
    try {
      state.sessions = await request("/api/sessions");
      renderSessions();
    } catch (error) {
      toast(`会话列表刷新失败：${error.message}`, "error");
    }
  }

  function renderSessions() {
    const list = $("#session-list");
    setText("session-count", String(state.sessions.length));
    if (!state.sessions.length) {
      const empty = document.createElement("p");
      empty.className = "session-empty";
      empty.textContent = "暂无会话，点击上方按钮开始。";
      list.replaceChildren(empty);
      return;
    }
    const nodes = state.sessions.map((item) => {
      const active = Boolean(state.session && item.id === state.session.id);
      const row = document.createElement("div");
      row.className = `session-row${active ? " active" : ""}`;

      const button = document.createElement("button");
      button.type = "button";
      button.className = "session-item";
      if (active) button.setAttribute("aria-current", "true");
      button.title = item.last_user_message || "暂无用户输入";

      const title = document.createElement("span");
      title.className = "session-item-title";
      title.textContent = item.last_user_message || "暂无用户输入";

      const meta = document.createElement("span");
      meta.className = "session-item-meta";
      const count = document.createElement("span");
      count.textContent = item.message_count ? `${item.message_count} 条记录` : "暂无记录";
      const time = document.createElement("span");
      time.className = "session-item-time";
      time.textContent = formatSessionTime(item.updated_at);
      meta.append(count, time);
      button.append(title, meta);
      button.addEventListener("click", () => loadSession(item.id));

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "session-delete";
      remove.title = "删除会话";
      remove.setAttribute("aria-label", `删除会话：${item.last_user_message || "暂无用户输入"}`);
      remove.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>';
      remove.addEventListener("click", (event) => {
        event.stopPropagation();
        deleteSession(item);
      });

      row.append(button, remove);
      return row;
    });
    list.replaceChildren(...nodes);
  }

  async function createSession(options = {}) {
    const button = $("#new-session");
    setButtonBusy(button, true);
    try {
      const session = await request("/api/sessions", { method: "POST" });
      applySession(session);
      if (options.refresh !== false) await refreshSessions();
      if (!options.silent) toast("已新建估价会话", "success");
    } catch (error) {
      toast(`新建会话失败：${error.message}`, "error");
    } finally {
      setButtonBusy(button, false);
    }
  }

  async function loadSession(id, options = {}) {
    if (!id) return;
    setAutosave("正在载入…", "pending");
    try {
      const session = await request(`/api/sessions/${encodeURIComponent(id)}`);
      applySession(session);
    } catch (error) {
      setAutosave("载入失败", "error");
      toast(`会话载入失败：${error.message}`, "error");
      return;
    }
    if (options.refresh !== false) await refreshSessions();
  }

  async function deleteSession(item) {
    const confirmed = await confirmAction({
      title: "删除估价会话",
      message: `将永久删除会话「${item.last_user_message || "暂无用户输入"}」及其全部报告，此操作不可撤销。`,
      confirmText: "删除会话",
      cancelText: "取消",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await request(`/api/sessions/${encodeURIComponent(item.id)}`, { method: "DELETE" });
      state.sessions = state.sessions.filter((session) => session.id !== item.id);
      if (state.session && state.session.id === item.id) {
        if (state.sessions.length) await loadSession(state.sessions[0].id, { refresh: false });
        else await createSession({ refresh: false, silent: true });
      }
      await refreshSessions();
      toast("会话已删除", "success");
    } catch (error) {
      toast(`删除会话失败：${error.message}`, "error");
    }
  }

  function applySession(session, options = {}) {
    window.clearTimeout(state.syncTimer);
    state.syncTimer = null;
    state.syncSequence += 1;
    state.session = session;
    setText("session-title", session.title || "新建估价会话");
    resetFixedFieldInputs();
    restoreFixedFields(session.fixed_fields || {});
    const fields = session.fixed_fields || {};
    state.presetSources = Array.isArray(fields.preset_sources) ? fields.preset_sources.slice() : [];
    state.presetBasis = typeof fields.preset_basis === "string" ? fields.preset_basis : "";
    const description = $("#layout-description");
    if (description) description.value = session.layout_description || "";
    if (!options.preserveLayout) {
      resetLayoutImage();
      const filename = session.layout_filename || "";
      if (filename && filename !== EMPTY_FILENAME) {
        setText("layout-filename", filename);
        setText("layout-status", "已保存解析，可重新上传覆盖");
        const placeholder = $("#layout-placeholder");
        if (placeholder) {
          const strong = placeholder.querySelector("strong");
          const small = placeholder.querySelector("small");
          if (strong) strong.textContent = "已保存户型解析";
          if (small) small.textContent = filename;
        }
      } else {
        resetLayoutLabels();
      }
    }
    renderMessages({ scrollTo: options.scrollTo });
    renderLatest(findLatestReport());
    syncRagRecent();
    updateSessionMeta();
    setAutosave("已同步");
  }

  function resetFixedFieldInputs() {
    for (const id of FIELD_IDS) {
      const field = $(`#${id}`);
      if (field) field.value = "";
    }
    const usage = $("#property_usage");
    if (usage) usage.value = "住宅";
  }

  function restoreFixedFields(fields) {
    for (const id of FIELD_IDS) {
      const value = fields[id];
      const field = $(`#${id}`);
      if (!field || value === null || value === undefined || typeof value === "object") continue;
      field.value = value;
    }
  }

  function updateSessionMeta() {
    const session = state.session;
    if (!session) {
      setText("session-meta", "暂无记录");
      return;
    }
    const count = (session.messages || []).length;
    setText("session-meta", count ? `${count} 条记录 · ${formatTime(session.updated_at)}` : "暂无记录");
  }

  function findLatestReport() {
    if (!state.session) return null;
    const messages = state.session.messages || [];
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message && message.role === "assistant" && message.kind === "report") return message;
    }
    return null;
  }

  function findLatestRagAnswer() {
    if (!state.session) return null;
    const messages = state.session.messages || [];
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message && message.kind === "rag_answer") return message;
    }
    return null;
  }

  /* -------------------------------------------------------------- markdown */

  function inlineMarkdown(raw) {
    let text = escapeHtml(raw);
    text = text.replace(/`([^`]+)`/g, '<code class="md-code">$1</code>');
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/\[来源[:：]\s*([^\]]+)\]/g, '<span class="inline-source">来源 · $1</span>');
    return text;
  }

  function renderMarkdown(markdown) {
    const source = String(markdown ?? "").replace(/\r\n?/g, "\n").trim();
    if (!source) return "";
    const lines = source.split("\n");
    const html = [];
    let paragraph = [];
    let table = [];
    let code = null;
    const listStack = [];

    const renderList = (list) => {
      const items = list.items.map((item) => {
        const children = item.children.length ? item.children.map(renderList).join("") : "";
        return `<li>${inlineMarkdown(item.text)}${children}</li>`;
      }).join("");
      return `<${list.type}>${items}</${list.type}>`;
    };
    const flushParagraph = () => {
      if (!paragraph.length) return;
      html.push(`<p>${paragraph.map(inlineMarkdown).join("<br>")}</p>`);
      paragraph = [];
    };
    const flushList = () => {
      if (!listStack.length) return;
      html.push(renderList(listStack[0]));
      listStack.length = 0;
    };
    const flushTable = () => {
      if (!table.length) return;
      const splitRow = (line) => line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((cell) => cell.trim());
      const head = splitRow(table[0]);
      const body = table.slice(2).map(splitRow);
      html.push(
        `<div class="md-table-wrap"><table><thead><tr>${head.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead>` +
          `<tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
      );
      table = [];
    };
    const flushAll = () => {
      flushParagraph();
      flushList();
      flushTable();
    };
    const isSeparator = (line) => /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(line) && line.includes("-");
    const pushListItem = (type, indent, itemText) => {
      while (listStack.length && listStack[listStack.length - 1].indent > indent) listStack.pop();
      const current = listStack[listStack.length - 1];
      if (!current) {
        listStack.push({ type, indent, items: [] });
      } else if (indent > current.indent) {
        const parentItem = current.items[current.items.length - 1];
        if (parentItem) {
          const child = { type, indent, items: [] };
          parentItem.children.push(child);
          listStack.push(child);
        } else {
          listStack.push({ type, indent, items: [] });
        }
      } else if (indent === current.indent && current.type !== type) {
        flushList();
        listStack.push({ type, indent, items: [] });
      }
      listStack[listStack.length - 1].items.push({ text: itemText, children: [] });
    };

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      if (/^\s*```/.test(line)) {
        if (code) {
          html.push(`<pre class="md-pre"><code>${escapeHtml(code.join("\n"))}</code></pre>`);
          code = null;
        } else {
          flushAll();
          code = [];
        }
        continue;
      }
      if (code) {
        code.push(line);
        continue;
      }
      if (line.includes("|") && index + 1 < lines.length && isSeparator(lines[index + 1])) {
        flushParagraph();
        flushList();
        table = [line, lines[index + 1]];
        index += 1;
        while (index + 1 < lines.length && lines[index + 1].includes("|") && lines[index + 1].trim()) {
          table.push(lines[index + 1]);
          index += 1;
        }
        flushTable();
        continue;
      }
      if (!line.trim()) {
        flushAll();
        continue;
      }
      const heading = line.match(/^\s*(#{1,6})\s+(.*)$/);
      if (heading) {
        flushAll();
        const level = Math.min(4, heading[1].length + 1);
        html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
        continue;
      }
      const unordered = line.match(/^(\s*)[-*+]\s+(.*)$/);
      if (unordered) {
        flushParagraph();
        pushListItem("ul", unordered[1].length, unordered[2]);
        continue;
      }
      const ordered = line.match(/^(\s*)(\d+)[.)、]\s+(.*)$/);
      if (ordered) {
        flushParagraph();
        pushListItem("ol", ordered[1].length, ordered[3]);
        continue;
      }
      if (/^\s*>\s?/.test(line)) {
        flushAll();
        html.push(`<blockquote>${inlineMarkdown(line.replace(/^\s*>\s?/, ""))}</blockquote>`);
        continue;
      }
      if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
        flushAll();
        html.push("<hr>");
        continue;
      }
      if (listStack.length && /^\s{2,}\S/.test(line)) {
        const top = listStack[listStack.length - 1];
        const item = top.items[top.items.length - 1];
        if (item) {
          item.text += ` ${line.trim()}`;
          continue;
        }
      }
      flushList();
      paragraph.push(line);
    }
    if (code) html.push(`<pre class="md-pre"><code>${escapeHtml(code.join("\n"))}</code></pre>`);
    flushAll();
    return html.join("");
  }

  function extractSources(markdown) {
    const sources = [];
    const pattern = /\[来源[:：]\s*([^\]]+)\]/g;
    let match;
    while ((match = pattern.exec(String(markdown ?? "")))) {
      for (const part of match[1].split(/[;；]/)) {
        const source = part.trim();
        if (source && !sources.includes(source)) sources.push(source);
      }
    }
    return sources;
  }

  function stripSources(markdown) {
    return String(markdown ?? "").replace(/\[来源[:：][^\]]*\]/g, "");
  }

  /* --------------------------------------------------------------- messages */

  function renderMessages(options = {}) {
    const list = $("#message-list");
    const messages = (state.session && state.session.messages) || [];
    if (!messages.length) {
      list.replaceChildren(createEmptyState());
      return;
    }
    const nodes = messages.map((message) => renderMessage(message));
    list.replaceChildren(...nodes);

    const scrollToAnchor = () => {
      if (options.scrollTo === "bottom") {
        list.scrollTop = list.scrollHeight;
        return;
      }
      let anchorIndex = -1;
      for (let index = messages.length - 1; index >= 0; index -= 1) {
        const message = messages[index];
        if (message && message.role === "assistant" && message.kind === "report") {
          anchorIndex = index;
          break;
        }
      }
      if (anchorIndex < 0) {
        list.scrollTop = list.scrollHeight;
        return;
      }
      if (anchorIndex > 0 && messages[anchorIndex - 1].role === "user") anchorIndex -= 1;
      const anchor = nodes[anchorIndex];
      if (!anchor) {
        list.scrollTop = list.scrollHeight;
        return;
      }
      list.scrollTop = Math.max(0, anchor.offsetTop - 8);
    };
    window.requestAnimationFrame(scrollToAnchor);
  }

  function renderMessage(message) {
    const isUser = message.role === "user";
    const isReport = message.role === "assistant" && message.kind === "report";
    const isRagAnswer = message.kind === "rag_answer";
    const isRagQuestion = message.kind === "rag_question";

    const article = document.createElement("article");
    article.className = [
      "message",
      isUser ? "message-user" : "message-assistant",
      isReport ? "message-report" : "",
      isRagAnswer ? "message-knowledge" : "",
      isRagQuestion ? "message-rag-question" : "",
    ].filter(Boolean).join(" ");

    const avatar = document.createElement("div");
    avatar.className = `message-avatar ${isRagAnswer ? "avatar-knowledge" : isReport ? "avatar-assistant" : isUser ? "avatar-user" : "avatar-assistant"}`;
    avatar.textContent = isRagAnswer ? "知" : isRagQuestion ? "问" : isReport ? "估" : "我";
    avatar.setAttribute("aria-hidden", "true");

    const main = document.createElement("div");
    main.className = "message-main";

    const role = document.createElement("div");
    role.className = "message-role";
    const roleName = document.createElement("span");
    roleName.className = "message-role-name";
    roleName.textContent = isRagAnswer ? "知识库回答" : isRagQuestion ? "知识库提问" : isReport ? "估价助手" : "你";
    role.append(roleName);
    const created = formatTime(message.created_at);
    if (created) {
      const time = document.createElement("time");
      time.className = "message-time";
      time.textContent = created;
      if (message.created_at) time.dateTime = message.created_at;
      role.append(time);
    }

    const content = document.createElement("div");
    content.className = `message-content ${isReport ? "report-answer md" : isRagAnswer ? "knowledge-answer md" : "plain-answer"}`;
    if (isUser) content.textContent = message.content;
    else content.innerHTML = renderMarkdown(message.content);
    if (isReport) content.prepend(buildReportTopbar(message));

    main.append(role, content);

    if (isRagAnswer) {
      const chips = buildSourceChips(extractSources(message.content), 8);
      if (chips) main.append(chips);
    }
    if (isReport) main.append(buildReportExtras(message));

    article.append(avatar, main);
    return article;
  }

  function buildReportTopbar(message) {
    const topbar = document.createElement("div");
    topbar.className = "report-topbar";
    const sources = collectSources(message).slice(0, 5);
    const chips = buildSourceChips(sources, 5);
    if (chips) {
      topbar.append(chips);
    } else {
      const label = document.createElement("span");
      label.className = "report-topbar-label";
      const steps = (message.steps || []).length;
      label.textContent = `估价报告${steps ? ` · ${steps} 个执行步骤` : ""}`;
      topbar.append(label);
    }
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "button button-quiet button-small";
    copy.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg><span>复制 Markdown</span>';
    copy.addEventListener("click", () => copyText(message.content, "报告 Markdown 已复制"));
    topbar.append(copy);
    return topbar;
  }

  function buildReportExtras(message) {
    const extras = document.createElement("div");
    extras.className = "report-extras";
    extras.append(buildTimeline(message.steps || []));
    extras.append(buildJsonDetails(message));
    return extras;
  }

  function buildJsonDetails(message) {
    const details = document.createElement("details");
    details.className = "json-details";
    const summary = document.createElement("summary");
    summary.textContent = "结构化 JSON";
    const pre = document.createElement("pre");
    pre.textContent = message.report_json || "暂无 JSON 输出";
    details.append(summary, pre);
    return details;
  }

  function groupStepsByType(steps) {
    const groups = new Map();
    for (const step of steps) {
      if (!step || !step.type) continue;
      if (!groups.has(step.type)) groups.set(step.type, []);
      groups.get(step.type).push(step);
    }
    return groups;
  }

  function uniqueValues(values) {
    return values.filter((value, index) => value && values.indexOf(value) === index);
  }

  function stageSummary(definition, stageSteps) {
    if (!stageSteps || !stageSteps.length) return "未执行";
    switch (definition.type) {
      case "understand": {
        const detail = stageSteps[0].detail || {};
        const parts = [detail.usage, detail.area ? `${detail.area} ㎡` : "", detail.purpose].filter(Boolean);
        return parts.join(" · ") || "已解析估价需求";
      }
      case "plan": {
        const methods = uniqueValues(stageSteps.flatMap((step) => (step.detail && step.detail.methods) || []));
        return methods.length ? methods.join(" / ") : "已完成方法规划";
      }
      case "retrieve": {
        const sources = uniqueValues(stageSteps.flatMap((step) => (step.detail && step.detail.sources) || []));
        return `${stageSteps.length} 轮检索${sources.length ? ` · ${sources.length} 个来源` : ""}`;
      }
      case "compute": {
        const methods = uniqueValues(stageSteps.map((step) => (step.detail && step.detail.method) || ""));
        return `${methods.length || stageSteps.length} 个方法已测算`;
      }
      case "verify": {
        const verification = String((stageSteps[0].detail && stageSteps[0].detail.verification) || "")
          .replace(/[#>*_`|]/g, "")
          .replace(/\s+/g, " ")
          .trim();
        return verification ? verification.slice(0, 42) : "已完成交叉校核";
      }
      default:
        return stageSteps[0].label || "已完成";
    }
  }

  function implicitUnderstandDetail() {
    const fields = (state.session && state.session.fixed_fields) || {};
    const parts = [fields.property_usage, fields.area ? `${fields.area} ㎡` : "", fields.valuation_purpose].filter(Boolean);
    return parts.length ? parts.join(" · ") : "已解析估价需求";
  }

  function buildTimeline(steps) {
    const groups = groupStepsByType(steps);
    const block = document.createElement("div");
    block.className = "report-timeline-block";
    const label = document.createElement("p");
    label.className = "report-extras-label";
    label.textContent = "执行步骤";
    const list = document.createElement("ol");
    list.className = "report-timeline";
    REPORT_STEPS.forEach((definition, index) => {
      const stageSteps = groups.get(definition.type) || [];
      const implicitUnderstand = definition.type === "understand" && stageSteps.length === 0 && steps.length > 0;
      const done = stageSteps.length > 0 || implicitUnderstand;
      const item = document.createElement("li");
      item.className = `timeline-step${done ? " is-done" : " is-skipped"}`;
      const badge = document.createElement("span");
      badge.className = "timeline-badge";
      badge.textContent = String(index + 1).padStart(2, "0");
      const body = document.createElement("span");
      body.className = "timeline-body";
      const title = document.createElement("strong");
      title.textContent = definition.title;
      const detail = document.createElement("small");
      detail.textContent = stageSteps.length ? stageSummary(definition, stageSteps) : implicitUnderstand ? implicitUnderstandDetail() : "未执行";
      body.append(title, detail);
      item.append(badge, body);
      if (stageSteps.length > 1) item.title = `${definition.title}：共 ${stageSteps.length} 个步骤`;
      list.append(item);
    });
    block.append(label, list);
    return block;
  }

  function collectSources(message) {
    const sources = [];
    for (const step of message.steps || []) {
      if (step && step.detail && Array.isArray(step.detail.sources)) {
        for (const source of step.detail.sources) {
          if (source && !sources.includes(source)) sources.push(source);
        }
      }
    }
    for (const source of extractSources(message.content)) {
      if (source && !sources.includes(source)) sources.push(source);
    }
    return sources;
  }

  function buildSourceChips(sources, limit = 6) {
    if (!sources || !sources.length) return null;
    const wrap = document.createElement("div");
    wrap.className = "source-chips";
    const label = document.createElement("span");
    label.className = "source-chips-label";
    label.textContent = "来源";
    wrap.append(label);
    sources.slice(0, limit).forEach((source) => {
      const chip = document.createElement("span");
      chip.className = "source-chip";
      chip.textContent = source;
      wrap.append(chip);
    });
    return wrap;
  }

  function createEmptyState() {
    const wrap = document.createElement("div");
    wrap.className = "conversation-empty glass-inset";
    const mark = document.createElement("span");
    mark.className = "empty-mark";
    mark.setAttribute("aria-hidden", "true");
    mark.innerHTML = '<svg viewBox="0 0 24 24"><path d="M4 20V9.5L12 4l8 5.5V20"/><path d="M9 20v-5.5h6V20"/></svg>';
    const title = document.createElement("strong");
    title.textContent = "开始一次专业估价";
    const copy = document.createElement("p");
    copy.textContent = "填写固定参数或直接描述估价需求，助手会规划方法、检索依据并生成带来源的报告。";
    const actions = document.createElement("div");
    actions.className = "empty-actions";
    const sample = document.createElement("button");
    sample.type = "button";
    sample.className = "button button-secondary button-small";
    sample.textContent = "填入示例参数";
    sample.addEventListener("click", fillSampleFields);
    const ask = document.createElement("button");
    ask.type = "button";
    ask.className = "button button-ghost button-small";
    ask.textContent = "先问知识库";
    ask.addEventListener("click", () => $("#bottom-rag-question").focus());
    actions.append(sample, ask);
    const hint = document.createElement("small");
    hint.className = "empty-hint";
    hint.textContent = "快捷键：Ctrl / ⌘ + Enter 提交当前输入";
    wrap.append(mark, title, copy, actions, hint);
    return wrap;
  }

  function fillSampleFields() {
    const sample = {
      property_usage: "住宅",
      area: 118,
      location: "武昌区",
      preset_year: "2024",
      valuation_purpose: "买卖",
      layout: "三室两厅",
      building_age: 6,
      orientation: "南北",
      floor: "中楼层 / 共18层",
      decoration: "精装",
      comparable_price: 22000,
      net_income: 100000,
      cap_rate: 0.04,
    };
    for (const [id, value] of Object.entries(sample)) {
      const field = $(`#${id}`);
      if (field) field.value = value;
    }
    const input = $("#message-input");
    if (input && !input.value.trim()) input.value = "请重点说明市场比较法的修正过程，并给出参考估值区间。";
    scheduleFixedSync();
    toast("已填入示例参数，可补充说明后生成报告", "info");
    if (input) input.focus();
  }

  function renderLatest(message) {
    state.lastReport = message || null;
    const copy = $("#latest-copy");
    if (copy) copy.disabled = !message;
    const container = $("#latest-steps");
    if (!container) return;
    if (!message) {
      const note = document.createElement("span");
      note.className = "empty-note";
      note.textContent = "生成报告后显示执行步骤";
      container.replaceChildren(note);
      setText("latest-meta", "暂无报告");
      setText("report-json", "暂无 JSON 输出");
      return;
    }
    const groups = groupStepsByType(message.steps || []);
    const totalSteps = (message.steps || []).length;
    const nodes = REPORT_STEPS.map((definition, index) => {
      const stageSteps = groups.get(definition.type) || [];
      const implicitUnderstand = definition.type === "understand" && stageSteps.length === 0 && totalSteps > 0;
      const done = stageSteps.length > 0 || implicitUnderstand;
      const row = document.createElement("div");
      row.className = `mini-step${done ? " is-done" : " is-skipped"}`;
      const badge = document.createElement("span");
      badge.className = "mini-step-index";
      badge.textContent = String(index + 1).padStart(2, "0");
      const label = document.createElement("span");
      label.className = "mini-step-label";
      label.textContent = definition.title;
      const state_ = document.createElement("span");
      state_.className = "mini-step-state";
      state_.textContent = done ? (stageSteps.length > 1 ? `${stageSteps.length} 步` : "完成") : "未执行";
      row.append(badge, label, state_);
      return row;
    });
    container.replaceChildren(...nodes);
    const steps = (message.steps || []).length;
    setText("latest-meta", `${formatTime(message.created_at)}${steps ? ` · ${steps} 步` : ""}`);
    setText("report-json", message.report_json || "暂无 JSON 输出");
  }

  function syncRagRecent() {
    const message = findLatestRagAnswer();
    const panel = $("#rag-recent");
    if (!message) {
      panel.hidden = true;
      setText("bottom-rag-status", "检索结果会进入当前会话");
      return;
    }
    updateRagRecent(message);
    setText("bottom-rag-status", "已载入最近一次检索结果");
  }

  function updateRagRecent(message) {
    const panel = $("#rag-recent");
    if (!message) {
      panel.hidden = true;
      return;
    }
    const sources = extractSources(message.content);
    const plain = stripSources(message.content)
      .replace(/^[#>*\-\s]+/gm, "")
      .replace(/\*\*/g, "")
      .replace(/\s+/g, " ")
      .trim();
    const snippet = plain.length > 150 ? `${plain.slice(0, 150)}…` : plain;
    setText("rag-recent-count", sources.length ? `${sources.length} 个来源` : "未标注来源");
    setText("rag-recent-snippet", snippet || "本次回答未返回可读摘要。");
    const chips = $("#rag-recent-chips");
    chips.replaceChildren();
    if (sources.length) {
      sources.slice(0, 4).forEach((source) => {
        const chip = document.createElement("span");
        chip.className = "source-chip";
        chip.textContent = source;
        chips.append(chip);
      });
    } else {
      const chip = document.createElement("span");
      chip.className = "source-chip source-chip-muted";
      chip.textContent = "未标注来源";
      chips.append(chip);
    }
    panel.hidden = false;
  }

  /* ------------------------------------------------------------------ sync */

  function scheduleFixedSync() {
    if (!state.session) return;
    setAutosave("待保存…", "pending");
    window.clearTimeout(state.syncTimer);
    state.syncTimer = window.setTimeout(() => {
      syncFixedFields();
    }, 400);
  }

  async function syncFixedFields() {
    if (!state.session) return;
    const sessionId = state.session.id;
    const sequence = (state.syncSequence += 1);
    setAutosave("保存中…", "pending");
    try {
      const layoutFilenameNode = $("#layout-filename");
      const layoutFilename = (layoutFilenameNode && layoutFilenameNode.textContent ? layoutFilenameNode.textContent : "").trim();
      const updated = await request(`/api/sessions/${encodeURIComponent(sessionId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fixed_fields: buildPayload(),
          layout_description: $("#layout-description").value,
          layout_filename: layoutFilename === EMPTY_FILENAME || layoutFilename === "尚未选择图片" ? "" : layoutFilename,
        }),
      });
      if (sequence === state.syncSequence && state.session && state.session.id === sessionId) {
        const messages = state.session.messages || [];
        state.session = { ...updated, messages: updated.messages || messages };
        setAutosave("已同步", "ok");
      }
    } catch (error) {
      if (sequence === state.syncSequence) {
        setAutosave("保存失败", "error");
        toast(`参数保存失败：${error.message}`, "error");
      }
    }
  }

  function buildPayload(message = "") {
    return {
      property_usage: fieldText("property_usage"),
      area: fieldNumber("area"),
      layout: fieldText("layout"),
      building_age: fieldNumber("building_age"),
      orientation: fieldText("orientation"),
      floor: fieldText("floor"),
      decoration: fieldText("decoration"),
      location: fieldText("location"),
      valuation_purpose: fieldText("valuation_purpose"),
      preset_year: fieldNumber("preset_year"),
      comparable_price: fieldNumber("comparable_price"),
      net_income: fieldNumber("net_income"),
      cap_rate: fieldNumber("cap_rate"),
      land_value: fieldNumber("land_value"),
      replacement_cost: fieldNumber("replacement_cost"),
      depreciation: fieldNumber("depreciation"),
      preset_sources: state.presetSources,
      preset_basis: state.presetBasis,
      note: message,
    };
  }

  /* --------------------------------------------------------------- actions */

  async function handleLogin(event) {
    event.preventDefault();
    const username = fieldText("login-username");
    const password = $("#login-password") ? $("#login-password").value : "";
    if (!username || !password) {
      setLoginStatus("请输入账号和密码。", "error");
      return;
    }
    const button = $("#login-submit");
    setButtonBusy(button, true);
    setLoginStatus("正在登录…", "muted");
    try {
      const me = await request("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      $("#login-form").reset();
      await enterWorkspace(me);
      toast(`欢迎回来，${me.username}`, "success");
    } catch (error) {
      setLoginStatus(error.message, "error");
    } finally {
      setButtonBusy(button, false);
    }
  }

  async function handleRegister(event) {
    event.preventDefault();
    const username = fieldText("register-username");
    const password = $("#register-password") ? $("#register-password").value : "";
    const confirmPassword = $("#register-confirm-password") ? $("#register-confirm-password").value : "";
    if (password !== confirmPassword) {
      setRegisterStatus("两次输入的密码不一致。", "error");
      return;
    }
    const button = $("#register-submit");
    setButtonBusy(button, true);
    setRegisterStatus("正在创建账号…", "muted");
    try {
      await request("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, confirm_password: confirmPassword }),
      });
      $("#register-form").reset();
      setAuthView("login", { focus: false });
      const loginUser = $("#login-username");
      if (loginUser) loginUser.value = username;
      setLoginStatus("账号已创建，请使用新账号登录。", "success");
      const passwordField = $("#login-password");
      if (passwordField) passwordField.focus({ preventScroll: true });
      toast("注册成功，请登录", "success");
    } catch (error) {
      setRegisterStatus(error.message, "error");
    } finally {
      setButtonBusy(button, false);
    }
  }

  async function handleLogout() {
    const button = $("#logout-button");
    setButtonBusy(button, true);
    try {
      await request("/api/auth/logout", { method: "POST" });
    } catch (error) {
      toast(`退出登录失败：${error.message}`, "error");
    } finally {
      setButtonBusy(button, false);
    }
    showGate();
    toast("已退出登录", "info");
  }

  async function loadPreset() {
    const district = fieldText("location");
    const year = fieldText("preset_year");
    if (!district || !year) {
      setText("preset-status", "请先选择区域和年份");
      toast("请先选择区域和年份", "warning");
      return;
    }
    if (!state.session) {
      toast("会话尚未就绪，请稍后重试", "warning");
      return;
    }
    const button = $("#preset-load");
    setButtonBusy(button, true);
    setText("preset-status", "正在载入权威预设…");
    try {
      const params = new URLSearchParams({ district, year, property_usage: fieldText("property_usage") });
      if (fieldText("area")) params.set("area", fieldText("area"));
      if (fieldText("building_age")) params.set("building_age", fieldText("building_age"));
      const data = await request(`/api/presets/wuhan?${params.toString()}`);
      let applied = 0;
      for (const [id, field] of Object.entries(data.fields || {})) {
        const input = $(`#${id}`);
        if (input && field && field.value !== null && field.value !== undefined) {
          input.value = field.value;
          applied += 1;
        }
      }
      state.presetSources = (data.sources || []).map((source) => source.source).filter(Boolean);
      state.presetBasis = `${district}，${year}年，代表地价${data.representative_grade}级；参数含官方基准、公式推导和可编辑假设。`;
      await syncFixedFields();
      const note = `${year}年 ${district} 预设已载入${applied ? ` · 更新 ${applied} 项参数` : ""}`;
      setText("preset-status", note);
      toast(note, "success");
    } catch (error) {
      setText("preset-status", `预设载入失败：${error.message}`);
      toast(`预设载入失败：${error.message}`, "error");
    } finally {
      setButtonBusy(button, false);
    }
  }

  async function submitReport(event) {
    event.preventDefault();
    if (!state.session) {
      toast("请先选择或新建估价会话", "warning");
      return;
    }
    const message = fieldText("message-input");
    if (!message) {
      toast("请补充估价内容后再生成报告", "warning");
      const input = $("#message-input");
      if (input) input.focus();
      return;
    }
    const button = $("#estimate-submit");
    setButtonBusy(button, true);
    const input = $("#message-input");
    input.value = "";
    setText("session-meta", "正在生成报告…");
    try {
      const result = await request(`/api/sessions/${encodeURIComponent(state.session.id)}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload(message)),
      });
      if (result && result.session) applySession(result.session, { preserveLayout: true });
      await refreshSessions();
      updateSessionMeta();
      toast("估值报告已生成", "success");
    } catch (error) {
      input.value = message;
      updateSessionMeta();
      toast(`报告生成失败：${error.message}`, "error");
    } finally {
      setButtonBusy(button, false);
    }
  }

  async function submitRag(event) {
    event.preventDefault();
    if (!state.session) {
      toast("会话尚未就绪，请稍后重试", "warning");
      return;
    }
    const question = fieldText("bottom-rag-question");
    if (!question) {
      toast("请输入要检索的问题", "warning");
      return;
    }
    const button = $("#bottom-rag-submit");
    setButtonBusy(button, true);
    setText("bottom-rag-status", "正在检索知识库…");
    try {
      const result = await request(`/api/sessions/${encodeURIComponent(state.session.id)}/rag`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (result && result.session) applySession(result.session, { preserveLayout: true, scrollTo: "bottom" });
      $("#bottom-rag-question").value = "";
      await refreshSessions();
      updateSessionMeta();
      const answer = (result && result.message) || findLatestRagAnswer();
      if (answer) updateRagRecent(answer);
      setText("bottom-rag-status", "检索完成 · 回答已加入当前会话");
      toast("知识库检索完成", "success");
    } catch (error) {
      setText("bottom-rag-status", `检索失败：${error.message}`);
      toast(`知识库检索失败：${error.message}`, "error");
    } finally {
      setButtonBusy(button, false);
    }
  }

  /* ---------------------------------------------------------------- layout */

  function resetLayoutImage() {
    if (state.previewUrl) {
      URL.revokeObjectURL(state.previewUrl);
      state.previewUrl = "";
    }
    const preview = $("#layout-preview");
    if (preview) {
      preview.hidden = true;
      preview.removeAttribute("src");
    }
    const remove = $("#layout-remove");
    if (remove) remove.hidden = true;
    const placeholder = $("#layout-placeholder");
    if (placeholder) placeholder.hidden = false;
    const file = $("#layout-file");
    if (file) file.value = "";
  }

  function resetLayoutLabels() {
    setText("layout-filename", EMPTY_FILENAME);
    setText("layout-status", "上传后自动解析");
    const placeholder = $("#layout-placeholder");
    if (!placeholder) return;
    placeholder.hidden = false;
    const strong = placeholder.querySelector("strong");
    const small = placeholder.querySelector("small");
    if (strong) strong.textContent = "拖入户型图";
    if (small) small.textContent = "PNG / JPG，最大 20MB";
  }

  function openLayoutPicker() {
    const file = $("#layout-file");
    if (file) file.click();
  }

  function handleLayoutFile(file) {
    if (!file) return;
    if (!/\.(png|jpe?g)$/i.test(file.name) || (file.type && !/^image\/(png|jpeg)$/i.test(file.type))) {
      toast("仅支持 PNG / JPG 格式的户型图", "warning");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      toast("户型图不能超过 20MB", "error");
      return;
    }
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = URL.createObjectURL(file);
    const preview = $("#layout-preview");
    preview.src = state.previewUrl;
    preview.hidden = false;
    const placeholder = $("#layout-placeholder");
    if (placeholder) placeholder.hidden = true;
    const remove = $("#layout-remove");
    if (remove) remove.hidden = false;
    setText("layout-filename", file.name);
    setText("layout-status", "正在解析…");
    analyzeLayout(file);
  }

  async function analyzeLayout(file) {
    const form = new FormData();
    form.append("file", file);
    setText("layout-status", "正在解析…");
    try {
      const data = await request("/api/analyze-layout", { method: "POST", body: form });
      const description = $("#layout-description");
      if (description) description.value = data.layout || "";
      setText("layout-status", "解析完成，可编辑");
      await syncFixedFields();
      toast("户型图解析完成", "success");
    } catch (error) {
      setText("layout-status", `解析失败：${error.message}`);
      toast(`户型图解析失败：${error.message}`, "error");
    }
  }

  function removeLayoutImage() {
    resetLayoutImage();
    resetLayoutLabels();
    const description = $("#layout-description");
    if (description) description.value = "";
    if (state.session) syncFixedFields();
    toast("已移除户型图", "info");
  }

  /* ---------------------------------------------------------------- events */

  function bindAuthEvents() {
    $("#login-form").addEventListener("submit", handleLogin);
    $("#register-form").addEventListener("submit", handleRegister);
    $("#show-register").addEventListener("click", () => setAuthView("register"));
    $("#show-login").addEventListener("click", () => setAuthView("login"));
  }

  function bindWorkspaceEvents() {
    $("#new-session").addEventListener("click", () => createSession());
    $("#logout-button").addEventListener("click", handleLogout);
    $("#admin-entry").addEventListener("click", () => {
      window.location.href = "/admin";
    });

    $$("#fixed-form input, #fixed-form select").forEach((field) => {
      field.addEventListener("change", scheduleFixedSync);
      if (field.tagName === "INPUT") field.addEventListener("input", scheduleFixedSync);
    });
    $("#layout-description").addEventListener("input", scheduleFixedSync);
    $("#preset-load").addEventListener("click", loadPreset);

    $("#layout-upload").addEventListener("click", openLayoutPicker);
    $("#layout-file").addEventListener("change", () => {
      const file = $("#layout-file").files[0];
      handleLayoutFile(file);
    });
    const dropzone = $("#layout-dropzone");
    dropzone.addEventListener("click", (event) => {
      if (event.target.closest("#layout-remove")) return;
      openLayoutPicker();
    });
    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openLayoutPicker();
      }
    });
    dropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragover");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragover"));
    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragover");
      const file = event.dataTransfer && event.dataTransfer.files ? event.dataTransfer.files[0] : null;
      handleLayoutFile(file);
    });
    $("#layout-remove").addEventListener("click", (event) => {
      event.stopPropagation();
      removeLayoutImage();
    });

    $("#composer-form").addEventListener("submit", submitReport);
    $("#bottom-rag-form").addEventListener("submit", submitRag);
    $("#latest-copy").addEventListener("click", () => {
      if (state.lastReport) copyText(state.lastReport.content, "报告 Markdown 已复制");
    });
  }

  function bindGlobalShortcuts() {
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || !(event.ctrlKey || event.metaKey)) return;
      const active = document.activeElement;
      if (!active || typeof active.closest !== "function") return;
      const form = active.closest("form");
      if (!form || (form.id !== "composer-form" && form.id !== "bottom-rag-form")) return;
      const submit = form.querySelector('button[type="submit"]');
      if (!submit || submit.disabled) return;
      event.preventDefault();
      form.requestSubmit();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
