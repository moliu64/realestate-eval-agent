/* Shared, dependency-free UI primitives: toast notifications and a glass confirm dialog.
   Loaded by both the valuation workspace and the knowledge admin page. */
(() => {
  "use strict";

  const TOAST_ICONS = {
    success: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.2 4.2L19 7"/></svg>',
    error: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16.4h.01"/></svg>',
    warning: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10.3 4 2.7 17.2A1.8 1.8 0 0 0 4.3 20h15.4a1.8 1.8 0 0 0 1.6-2.8L13.7 4a1.9 1.9 0 0 0-3.4 0Z"/><path d="M12 9v4.5M12 16.6h.01"/></svg>',
    info: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.6h.01"/></svg>',
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function toastRegion() {
    let region = document.querySelector("#toast-region");
    if (!region) {
      region = document.createElement("div");
      region.id = "toast-region";
      region.className = "toast-region";
      region.setAttribute("role", "status");
      region.setAttribute("aria-live", "polite");
      document.body.append(region);
    }
    return region;
  }

  function toast(message, kind = "info", options = {}) {
    if (!message) return null;
    const region = toastRegion();
    const type = ["success", "error", "warning", "info"].includes(kind) ? kind : "info";
    const item = document.createElement("div");
    item.className = `toast toast-${type}`;
    item.setAttribute("role", type === "error" ? "alert" : "status");

    const icon = document.createElement("span");
    icon.className = "toast-icon";
    icon.innerHTML = TOAST_ICONS[type];

    const body = document.createElement("span");
    body.className = "toast-message";
    body.textContent = String(message);

    item.append(icon, body);
    region.append(item);

    let dismissed = false;
    const dismiss = () => {
      if (dismissed) return;
      dismissed = true;
      window.clearTimeout(timer);
      item.classList.add("is-leaving");
      window.setTimeout(() => item.remove(), 240);
    };
    const timer = window.setTimeout(dismiss, Number(options.duration) || (type === "error" ? 5200 : 3400));
    item.addEventListener("click", dismiss);
    return { dismiss };
  }

  let activeConfirm = null;

  function confirmDialog(options = {}) {
    const backdrop = document.querySelector("#confirm-dialog");
    if (!backdrop) return Promise.resolve(false);
    const panel = backdrop.querySelector(".dialog");
    const titleEl = backdrop.querySelector("#confirm-title");
    const copyEl = backdrop.querySelector("#confirm-copy");
    const okButton = backdrop.querySelector("#confirm-ok");
    const cancelButton = backdrop.querySelector("#confirm-cancel");
    if (!panel || !titleEl || !copyEl || !okButton || !cancelButton) {
      return Promise.resolve(false);
    }

    if (activeConfirm) {
      activeConfirm.close(false);
    }

    const previousFocus = document.activeElement;
    titleEl.textContent = options.title || "请确认操作";
    copyEl.textContent = options.message || "";
    okButton.textContent = options.confirmText || "确认";
    cancelButton.textContent = options.cancelText || "取消";
    const danger = options.danger !== false;
    okButton.classList.toggle("button-danger", danger);
    okButton.classList.toggle("button-primary", !danger);

    return new Promise((resolve) => {
      const onKeydown = (event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          close(false);
          return;
        }
        if (event.key !== "Tab") return;
        const focusables = [cancelButton, okButton];
        const index = focusables.indexOf(document.activeElement);
        event.preventDefault();
        const next = event.shiftKey
          ? focusables[(index <= 0 ? focusables.length : index) - 1]
          : focusables[(index + 1) % focusables.length];
        next.focus();
      };
      const onBackdropClick = (event) => {
        if (event.target === backdrop) close(false);
      };
      const close = (value) => {
        backdrop.hidden = true;
        document.body.classList.remove("dialog-open");
        document.removeEventListener("keydown", onKeydown, true);
        backdrop.removeEventListener("click", onBackdropClick);
        okButton.removeEventListener("click", onConfirm);
        cancelButton.removeEventListener("click", onCancel);
        activeConfirm = null;
        if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
        resolve(value);
      };
      const onConfirm = () => close(true);
      const onCancel = () => close(false);

      activeConfirm = { close };
      backdrop.hidden = false;
      document.body.classList.add("dialog-open");
      document.addEventListener("keydown", onKeydown, true);
      backdrop.addEventListener("click", onBackdropClick);
      okButton.addEventListener("click", onConfirm);
      cancelButton.addEventListener("click", onCancel);
      window.setTimeout(() => cancelButton.focus(), 30);
    });
  }

  window.UI = { toast, confirm: confirmDialog, escapeHtml };
})();
