function wrapSelection(textarea, before, after) {
  const start = textarea.selectionStart || 0;
  const end = textarea.selectionEnd || 0;
  const value = textarea.value || "";
  const selected = value.substring(start, end) || "";
  const next = value.substring(0, start) + before + selected + after + value.substring(end);
  textarea.value = next;
  const cursor = start + before.length;
  textarea.setSelectionRange(cursor, cursor + selected.length);
  textarea.focus();
}

function renderMarkdown(source) {
  const raw = source || "";
  if (window.marked) {
    window.marked.setOptions({ breaks: true });
    const parsed = window.marked.parse(raw);
    if (window.DOMPurify) return window.DOMPurify.sanitize(parsed);
    return parsed;
  }
  return raw.replaceAll("\n", "<br />");
}

function setupMarkdownEditor() {
  const textarea = document.getElementById("discussionBody");
  const preview = document.getElementById("discussionPreview");
  if (!textarea || !preview) return;

  const render = () => {
    preview.innerHTML = renderMarkdown(textarea.value);
  };

  render();
  textarea.addEventListener("input", render);

  document.querySelectorAll(".editor-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.md;
      if (!action) return;
      if (action === "bold") wrapSelection(textarea, "**", "**");
      if (action === "italic") wrapSelection(textarea, "*", "*");
      if (action === "underline") wrapSelection(textarea, "<u>", "</u>");
      if (action === "link") {
        const url = window.prompt("URL del enlace");
        if (!url) return;
        wrapSelection(textarea, "[", `](${url})`);
      }
      render();
    });
  });
}

function setupLinks() {
  const addBtn = document.getElementById("addDiscussionLink");
  const list = document.getElementById("discussionLinks");
  if (!addBtn || !list) return;
  addBtn.addEventListener("click", () => {
    const input = document.createElement("input");
    input.type = "url";
    input.name = "links[]";
    input.placeholder = "https://ejemplo.com/fuente";
    list.appendChild(input);
  });
}

function setupImageUploads() {
  const input = document.querySelector('input[name="images"]');
  const status = document.getElementById("discussionImageStatus");
  const previewList = document.getElementById("discussionImagePreviewList");
  if (!input || !previewList) return;

  const maxFiles = parseInt(input.dataset.maxFiles || "3", 10);
  const maxMb = parseInt(input.dataset.maxMb || "2", 10);
  const allowedExt = (input.dataset.allowedExt || "jpg,jpeg,png,webp,heic")
    .split(",")
    .map((ext) => ext.trim().toLowerCase())
    .filter(Boolean);
  const maxBytes = maxMb * 1024 * 1024;

  const showError = (message) => {
    if (!status) return;
    status.textContent = message;
  };

  const renderPreviews = () => {
    if (!input.files || input.files.length === 0) {
      previewList.innerHTML = "";
      return;
    }
    previewList.innerHTML = Array.from(input.files)
      .map((file, idx) => {
        const url = URL.createObjectURL(file);
        return `
          <div class="image-preview-card">
            <img src="${url}" alt="Vista previa ${idx + 1}" />
            <label class="image-caption">
              Descripción corta (opcional)
              <input type="text" name="image_captions[]" maxlength="255" placeholder="${file.name}" />
            </label>
          </div>
        `;
      })
      .join("");
  };

  input.addEventListener("change", () => {
    if (!input.files) return;
    if (input.files.length > maxFiles) {
      showError(`Máximo ${maxFiles} imágenes por envío.`);
      input.value = "";
      renderPreviews();
      return;
    }
    for (const file of Array.from(input.files)) {
      const name = file.name || "";
      const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
      if (!allowedExt.includes(ext)) {
        showError(`Formato no permitido: ${ext || "desconocido"}.`);
        input.value = "";
        renderPreviews();
        return;
      }
      if (file.size > maxBytes) {
        showError(`Cada imagen debe ser <= ${maxMb}MB.`);
        input.value = "";
        renderPreviews();
        return;
      }
    }
    if (status) status.textContent = "";
    renderPreviews();
  });
}

function setupVotes() {
  document.querySelectorAll(".vote-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const type = btn.dataset.type;
      const id = btn.dataset.id;
      const value = parseInt(btn.dataset.value, 10);
      if (!type || !id || !value) return;
      const url =
        type === "post"
          ? `/api/discusiones/${id}/vote`
          : `/api/discusiones/comentarios/${id}/vote`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value }),
      });
      const data = await res.json();
      if (!data) return;
      const scoreEl =
        type === "post"
          ? document.getElementById(`post-score-${id}`)
          : document.getElementById(`comment-score-${id}`);
      if (scoreEl && typeof data.score !== "undefined") {
        scoreEl.textContent = data.score;
      }
    });
  });
}

function setupLoadingButtons() {
  const form = document.querySelector(".discussion-form");
  if (form) {
    form.addEventListener("submit", () => {
      const submit = form.querySelector('button[type="submit"]');
      if (!submit) return;
      submit.disabled = true;
      submit.dataset.loading = "true";
      submit.textContent = "Publicando...";
    });
  }
  const commentForm = document.querySelector(".comment-form");
  if (commentForm) {
    commentForm.addEventListener("submit", () => {
      const submit = commentForm.querySelector('button[type="submit"]');
      if (!submit) return;
      submit.disabled = true;
      submit.dataset.loading = "true";
      submit.textContent = "Enviando...";
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  setupMarkdownEditor();
  setupLinks();
  setupImageUploads();
  setupVotes();
  setupLoadingButtons();
});
