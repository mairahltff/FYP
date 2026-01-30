// =============================
// AUTH / UI GUARDS
// =============================
function isAuthBlocked() {
  const authModal = document.getElementById("auth-modal");
  return authModal && authModal.classList.contains("active");
}

function syncAuthUI() {
  const app = document.querySelector(".app");
  const modal = document.getElementById("auth-modal");
  if (!app || !modal) return;

  if (modal.classList.contains("active")) {
    app.style.pointerEvents = "none";
    app.style.userSelect = "none";
    app.style.opacity = "0.4";
  } else {
    app.style.pointerEvents = "auto";
    app.style.userSelect = "auto";
    app.style.opacity = "1";
  }
}

// =============================
// MAIN APP
// =============================
document.addEventListener("DOMContentLoaded", () => {
  let currentUserId =
    (window.auth && window.auth.currentUser && window.auth.currentUser.uid)
      ? window.auth.currentUser.uid
      : "guest";

  syncAuthUI();
  if (typeof window.resetAuthForms === "function") {
    window.resetAuthForms();
  }

  // -----------------------------
  // HISTORY
  // -----------------------------
  async function loadHistory() {
    const container = document.querySelector("#screen-history .history-list");
    if (!container) return;
    container.innerHTML = "";

    try {
      const res = await fetch(`/history?user_id=${encodeURIComponent(currentUserId)}`);
      const data = await res.json();
      if (!data.success || !data.history?.length) {
        container.innerHTML = `<div class="history-empty">No history yet.</div>`;
        return;
      }

      data.history.forEach(item => {
        const card = document.createElement("div");
        card.className = "history-card";
        card.dataset.id = item.id;
        card.innerHTML = `
          <div><b>Q:</b> ${escapeHtml(item.query)}</div>
          <div><b>A:</b> ${escapeHtml(item.answer)}</div>
          <small>${item.timestamp}</small>
        `;
        container.appendChild(card);
      });
    } catch (e) {
      container.innerHTML = `<div class="history-empty">Failed to load history.</div>`;
    }
  }

  // -----------------------------
  // INIT CHAT
  // -----------------------------
  const chatBox = document.getElementById("healthcare-messages");
  if (chatBox) {
    chatBox.innerHTML = "";
    addMessage("healthcare", "bot", "Uploads are disabled on the deployed demo. You can still ask questions.");
  }

  // -----------------------------
  // CHAT INPUT
  // -----------------------------
  document.querySelectorAll(".chat-input-row").forEach(form => {
    form.addEventListener("submit", async e => {
      e.preventDefault();
      if (form.dataset.inProgress === "true") return;

      const input = form.querySelector("input[type='text']");
      const fileInput = form.querySelector("input[type='file']");
      const btn = form.querySelector("button[type='submit']");
      const chatId = form.dataset.chat;

      const question = input.value.trim();
      const file = fileInput?.files?.[0];

      // 🚫 BLOCK FILE UPLOADS (HEROKU SAFE)
      if (file) {
        addMessage(chatId, "bot", "🚫 Document uploads are disabled on this deployed demo.");
        fileInput.value = "";
        return;
      }

      if (!question) return;

      form.dataset.inProgress = "true";
      btn.disabled = true;
      btn.textContent = "Processing…";
      input.value = "";

      try {
        addMessage(chatId, "user", escapeHtml(question));
        addMessage(chatId, "bot", "Synthesizing answer…");

        const res = await fetch("/query_rag", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: question, user_id: currentUserId })
        });

        const result = await res.json();
        if (!result.success) throw new Error(result.answer);

        typeLastBotMessage(chatId, result.answer);
      } catch (err) {
        updateLastBotMessage(chatId, "An error occurred while answering.");
        console.error(err);
      } finally {
        form.dataset.inProgress = "";
        btn.disabled = false;
        btn.textContent = "▶";
      }
    });
  });

  // -----------------------------
  // NAV
  // -----------------------------
  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => {
      if (item.dataset.target === "screen-history") loadHistory();
    });
  });

  // -----------------------------
  // HELPERS
  // -----------------------------
  function addMessage(chatId, sender, html) {
    const box = document.getElementById(chatId + "-messages");
    if (!box) return;
    const msg = document.createElement("div");
    msg.className = "message " + sender;
    msg.innerHTML = html;
    box.appendChild(msg);
    box.scrollTop = box.scrollHeight;
  }

  function updateLastBotMessage(chatId, html) {
    const box = document.getElementById(chatId + "-messages");
    const bots = box?.querySelectorAll(".message.bot");
    if (bots?.length) bots[bots.length - 1].innerHTML = html;
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function typeLastBotMessage(chatId, text) {
    const box = document.getElementById(chatId + "-messages");
    const bots = box?.querySelectorAll(".message.bot");
    const target = bots?.[bots.length - 1];
    if (!target) return;

    target.innerHTML = "";
    let i = 0;
    const s = String(text || "");

    (function type() {
      if (i < s.length) {
        target.innerHTML += escapeHtml(s[i++]);
        setTimeout(type, 10);
      }
    })();
  }
});

// -----------------------------
// AUTH HELPERS
// -----------------------------
window.resetAuthForms = function () {
  ["login-email", "login-password", "signup-name", "signup-email", "signup-password", "signup-confirm-password"]
    .forEach(id => document.getElementById(id)?.value = "");
};

window.togglePassword = function (id) {
  const el = document.getElementById(id);
  if (el) el.type = el.type === "password" ? "text" : "password";
};
