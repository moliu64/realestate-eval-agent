const tokenEl = document.querySelector("#token");
const fileEl = document.querySelector("#file");
const form = document.querySelector("#admin-form");
const statusEl = document.querySelector("#admin-status");
const documentsEl = document.querySelector("#documents");

const headers = () => ({ "X-Admin-Token": tokenEl.value.trim() });
const setStatus = (message) => { statusEl.textContent = message; };

async function loadDocuments() {
  const response = await fetch("/admin/documents", { headers: headers() });
  if (!response.ok) throw new Error((await response.json()).detail || "加载失败");
  const documents = await response.json();
  documentsEl.replaceChildren(...documents.map((item) => {
    const row = document.createElement("tr");
    for (const value of [item.source, item.file_type, item.updated_at]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    const action = document.createElement("td");
    const button = document.createElement("button");
    button.textContent = "删除";
    button.addEventListener("click", async () => {
      if (!window.confirm(`确定删除 ${item.source}？`)) return;
      const response = await fetch(`/admin/documents/${encodeURIComponent(item.source)}`, { method: "DELETE", headers: headers() });
      setStatus(response.ok ? "删除并重建成功。" : "删除失败。");
      if (response.ok) await loadDocuments();
    });
    action.append(button); row.append(action); return row;
  }));
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData();
  data.append("file", fileEl.files[0]);
  setStatus("正在解析并重建向量库...");
  const response = await fetch("/admin/upload", { method: "POST", headers: headers(), body: data });
  const payload = await response.json();
  setStatus(response.ok ? `已入库 ${payload.source}。` : payload.detail || "上传失败。");
  if (response.ok) { fileEl.value = ""; await loadDocuments(); }
});

tokenEl.addEventListener("change", () => loadDocuments().catch((error) => setStatus(error.message)));
