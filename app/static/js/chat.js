function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function linkify(text) {
  const escaped = escapeHtml(text);
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  return escaped.replace(urlRegex, (url) => {
    return `<a href="${url}" target="_blank" rel="noopener">${url}</a>`;
  });
}

async function fetchChat() {
  const res = await fetch("/api/chat");
  return await res.json();
}

async function sendChatMessage(nickname, body) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nickname, body }),
  });
  return await res.json();
}

let initialLoad = true;
let lastSeenMessageId = 0;
let latestRenderedMessageId = 0;

function renderChat(payload) {
  const container = document.getElementById("chatMessages");
  if (!container) return [];
  const items = payload?.items || [];
  const onlineCount = payload?.online_count;
  const onlineEl = document.getElementById("chatOnlineCount");
  if (onlineEl && typeof onlineCount !== "undefined") {
    onlineEl.textContent = onlineCount;
  }

  const nearBottom =
    container.scrollHeight - container.scrollTop - container.clientHeight < 40;

  if (!items.length) {
    container.innerHTML = `<div class="chat-empty">Sin mensajes aún.</div>`;
    latestRenderedMessageId = 0;
    return [];
  }

  container.innerHTML = items
    .map((msg) => {
      const time = msg.created_at ? new Date(msg.created_at).toLocaleString("es-ES") : "";
      return `
        <div class="chat-item">
          <div class="chat-meta">
            <span class="chat-author">${escapeHtml(msg.author || "Anon")}</span>
            <span class="chat-time">${time}</span>
          </div>
          <div class="chat-body-line">${linkify(msg.body || "")}</div>
        </div>
      `;
    })
    .join("");

  latestRenderedMessageId = items.reduce((maxId, msg) => {
    const id = Number(msg?.id || 0);
    return id > maxId ? id : maxId;
  }, 0);

  if (initialLoad || nearBottom) {
    container.scrollTop = container.scrollHeight;
  }
  initialLoad = false;
  return items;
}

function isMobileView() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function setUnreadCount(unreadEl, count) {
  if (!unreadEl) return;
  const value = Math.max(0, Number(count) || 0);
  unreadEl.textContent = value > 99 ? "99+" : String(value);
  unreadEl.classList.toggle("is-hidden", value < 1);
}

function isChatOpen(widget) {
  return !!widget?.classList.contains("is-open");
}

function updateUnreadState(widget, unreadEl, items) {
  const latestId = items.reduce((maxId, msg) => {
    const id = Number(msg?.id || 0);
    return id > maxId ? id : maxId;
  }, 0);

  if (!latestId) {
    setUnreadCount(unreadEl, 0);
    return;
  }

  if (!lastSeenMessageId) {
    lastSeenMessageId = latestId;
    setUnreadCount(unreadEl, 0);
    return;
  }

  if (isChatOpen(widget)) {
    lastSeenMessageId = latestId;
    setUnreadCount(unreadEl, 0);
    return;
  }

  const unread = items.filter((msg) => Number(msg?.id || 0) > lastSeenMessageId).length;
  setUnreadCount(unreadEl, unread);
}

function markCurrentAsRead(unreadEl) {
  if (latestRenderedMessageId > 0) {
    lastSeenMessageId = latestRenderedMessageId;
  }
  setUnreadCount(unreadEl, 0);
}

document.addEventListener("DOMContentLoaded", () => {
  const widget = document.getElementById("chatWidget");
  const toggleBtn = document.getElementById("chatWidgetToggle");
  const closeBtn = document.getElementById("chatWidgetClose");
  const backdrop = document.getElementById("chatWidgetBackdrop");
  const unreadEl = document.getElementById("chatUnreadCount");
  const form = document.getElementById("chatForm");
  const nickInput = document.getElementById("chatNick");
  const messageInput = document.getElementById("chatMessage");
  const container = document.getElementById("chatMessages");

  const openChat = () => {
    if (!widget) return;
    widget.classList.add("is-open");
    widget.dataset.state = "open";
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");
    if (isMobileView()) {
      if (backdrop) backdrop.hidden = false;
      document.body.classList.add("chat-widget-mobile-open");
    } else if (backdrop) {
      backdrop.hidden = true;
    }
    markCurrentAsRead(unreadEl);
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
    if (messageInput) {
      messageInput.focus();
    }
  };

  const closeChat = () => {
    if (!widget) return;
    widget.classList.remove("is-open");
    widget.dataset.state = "closed";
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "false");
    if (backdrop) backdrop.hidden = true;
    document.body.classList.remove("chat-widget-mobile-open");
  };

  const syncViewportState = () => {
    if (!widget) return;
    if (!isMobileView()) {
      if (backdrop) backdrop.hidden = true;
      document.body.classList.remove("chat-widget-mobile-open");
    } else if (isChatOpen(widget) && backdrop) {
      backdrop.hidden = false;
      document.body.classList.add("chat-widget-mobile-open");
    }
  };

  const refresh = async () => {
    try {
      const payload = await fetchChat();
      const items = renderChat(payload);
      updateUnreadState(widget, unreadEl, items);
    } catch (e) {
      // no-op
    }
  };

  const bindTapOrClick = (element, handler) => {
    if (!element) return;
    let suppressClick = false;

    element.addEventListener(
      "touchend",
      (event) => {
        suppressClick = true;
        event.preventDefault();
        handler(event);
        window.setTimeout(() => {
          suppressClick = false;
        }, 350);
      },
      { passive: false }
    );

    element.addEventListener("click", (event) => {
      if (suppressClick) return;
      handler(event);
    });
  };

  bindTapOrClick(toggleBtn, () => {
    if (isChatOpen(widget)) {
      closeChat();
    } else {
      openChat();
    }
  });

  bindTapOrClick(closeBtn, () => {
    closeChat();
  });

  bindTapOrClick(backdrop, () => {
    closeChat();
  });

  if (toggleBtn) {
    toggleBtn.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      if (isChatOpen(widget)) {
        closeChat();
      } else {
        openChat();
      }
    });
  }

  window.addEventListener("resize", syncViewportState);
  window.addEventListener("hashchange", () => {
    if (window.location.hash === "#chatbox") {
      openChat();
    }
  });

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const nickname = nickInput?.value.trim() || "Anon";
      const body = messageInput?.value.trim();
      if (!body) return;
      await sendChatMessage(nickname, body);
      messageInput.value = "";
      await refresh();
      markCurrentAsRead(unreadEl);
      messageInput.focus();
    });
  }

  if (window.location.hash === "#chatbox") {
    openChat();
  } else {
    closeChat();
  }

  setUnreadCount(unreadEl, 0);
  syncViewportState();
  refresh();
  setInterval(refresh, 7000);
});
