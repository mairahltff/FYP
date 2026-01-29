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
    // Block app when auth is open
    app.style.pointerEvents = "none";
    app.style.userSelect = "none";
    app.style.opacity = "0.4";
  } else {
    // Enable app after login
    app.style.pointerEvents = "auto";
    app.style.userSelect = "auto";
    app.style.opacity = "1";
  }
}

// =============================
// MAIN APP
// =============================
document.addEventListener("DOMContentLoaded", () => {
  let currentUserId = (window.getCurrentUserId ? window.getCurrentUserId() : (window.currentUserId || "user"));

  // 🔐 Initial auth UI sync
  syncAuthUI();

  // Ensure login/signup fields are empty on load
  if (typeof window.resetAuthForms === "function") {
    window.resetAuthForms();
  }

  // -----------------------------
  // SCREEN NAVIGATION HELPERS
  // -----------------------------
  function showScreen(screenId) {
    if (isAuthBlocked()) return;

    document.querySelectorAll(".screen").forEach(s =>
      s.classList.remove("active")
    );

    document.getElementById(screenId)?.classList.add("active");

    // Toggle home-only mode (hide sidebar, center hero)
    const appEl = document.querySelector('.app');
    if (appEl) {
      if (screenId === 'screen-home') {
        appEl.classList.add('home-only');
        // Clear sidebar highlight since Home isn't a sidebar tab
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      } else {
        appEl.classList.remove('home-only');
      }
    }
  }

  function setNavActive(target) {
    document.querySelectorAll(".nav-item").forEach(n =>
      n.classList.remove("active")
    );
    if (target) target.classList.add("active");
  }

  // -----------------------------
  // HISTORY VIEW (BACKEND FETCH)
  // -----------------------------
  async function loadHistory() {
    const container = document.querySelector("#screen-history .history-list");
    if (!container) return;
    container.innerHTML = "";

    try {
      const res = await fetch(`/history?user_id=${encodeURIComponent(currentUserId)}`);
      const data = await res.json();
      if (!data.success || !Array.isArray(data.history) || !data.history.length) {
        const empty = document.createElement("div");
        empty.className = "history-empty";
        empty.textContent = "No history yet.";
        container.appendChild(empty);
        return;
      }

      data.history.forEach(item => {
        const card = document.createElement("div");
        card.className = "history-card";
        card.dataset.id = item.id;
        const ts = item.timestamp ? new Date(item.timestamp).toLocaleString() : "";
        card.innerHTML = `
          <div class="history-row"><span class="label">Q:</span><span class="value">${escapeHtml(item.query)}</span></div>
          <div class="history-row answer-collapsed" data-collapsed="true"><span class="label">A:</span><span class="value">${escapeHtml(item.answer)}</span></div>
          <div class="history-meta">
            <span>${ts}</span>
            <div class="history-actions-row">
              <button class="btn-link view-full">View full answer →</button>
              <button class="btn-link delete-btn">Delete</button>
            </div>
          </div>
          <div class="confirm-box">
            <div class="confirm-text">Delete this entry?</div>
            <button class="btn-link btn-muted cancel-delete">Cancel</button>
            <button class="btn-link btn-danger confirm-delete">Delete</button>
          </div>
        `;
        container.appendChild(card);
      });

      // Wire up actions
      container.querySelectorAll('.view-full').forEach(btn => {
        btn.addEventListener('click', () => {
          const card = btn.closest('.history-card');
          const ans = card.querySelector('.answer-collapsed');
          const collapsed = ans.dataset.collapsed === 'true';
          if (collapsed) {
            ans.classList.remove('answer-collapsed');
            ans.dataset.collapsed = 'false';
            btn.textContent = 'Collapse answer ↑';
          } else {
            ans.classList.add('answer-collapsed');
            ans.dataset.collapsed = 'true';
            btn.textContent = 'View full answer →';
          }
        });
      });

      container.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const card = btn.closest('.history-card');
          const box = card.querySelector('.confirm-box');
          box.classList.add('active');
        });
      });
      container.querySelectorAll('.cancel-delete').forEach(btn => {
        btn.addEventListener('click', () => {
          const card = btn.closest('.history-card');
          card.querySelector('.confirm-box').classList.remove('active');
        });
      });
      container.querySelectorAll('.confirm-delete').forEach(btn => {
        btn.addEventListener('click', async () => {
          const card = btn.closest('.history-card');
          const id = card.dataset.id;
          try {
            const res = await fetch('/history/delete', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ id, user_id: currentUserId })
            });
            const json = await res.json();
            if (json.success) {
              card.remove();
              if (!container.children.length) {
                const empty = document.createElement('div');
                empty.className = 'history-empty';
                empty.textContent = 'No history yet.';
                container.appendChild(empty);
              }
            }
          } catch (err) { console.error(err); }
        });
      });
    } catch (err) {
      const empty = document.createElement("div");
      empty.className = "history-empty";
      empty.textContent = "Failed to load history.";
      container.appendChild(empty);
      console.error(err);
    }
  }

  // -----------------------------
  // INITIALIZE CHAT SCREENS
  // -----------------------------
  ["healthcare"].forEach(id => {
    const box = document.getElementById(id + "-messages");
    if (box) {
      box.innerHTML = "";
      addMessage(id, "bot", "Upload a document first, then ask your questions.");
    }
  });

  // -----------------------------
  // CHAT INPUT HANDLING (RAG SAFE)
  // -----------------------------
  document.querySelectorAll(".chat-input-row").forEach(form => {
    // Upload button triggers hidden file input
    const fileInput = form.querySelector("input[type='file']");
    const plusBtn = form.querySelector(".upload-btn");
    if (plusBtn && fileInput) {
      plusBtn.addEventListener("click", () => fileInput.click());
      fileInput.addEventListener("change", () => {
        if (fileInput.files && fileInput.files.length) {
          form.requestSubmit();
        }
      });
    }
    form.addEventListener("submit", async e => {
      e.preventDefault();

      // Prevent double submits (e.g., rapid clicks or duplicate events)
      if (form.dataset.inProgress === "true") return;

      const input = form.querySelector("input[type='text']");
      const fileInput = form.querySelector("input[type='file']");
      const btn = form.querySelector("button[type='submit']");
      const chatId = form.dataset.chat;

      const question = input.value.trim();
      // Clear input immediately to avoid showing repeated text while generating
      if (question) {
        input.value = "";
        input.setAttribute("value", "");
        input.blur();
      }
      const file = fileInput?.files[0];
      if (!question && !file) return;

      input.disabled = true;
      btn.disabled = true;
      btn.textContent = "Processing…";
      form.dataset.inProgress = "true";

      try {
        if (file) {
          // Ensure a single uploading indicator with spinner
          const container = document.getElementById(chatId + "-messages");
          // Clean up any stray plain-text 'Uploading document...' messages
          if (container) {
            container.querySelectorAll(".message.bot").forEach(n => {
              const txt = (n.textContent || "").toLowerCase().replace(/\s+/g, " ").trim();
              if (txt.includes("uploading document")) {
                n.remove();
              }
            });
          }
          let uploading = container?.querySelector(".message.bot.uploading");
          if (!uploading && container) {
            uploading = document.createElement("div");
            uploading.className = "message bot uploading";
            uploading.innerHTML = '<span class="spinner inline"></span> Uploading document...';
            container.appendChild(uploading);
            container.scrollTop = container.scrollHeight;
          } else if (uploading) {
            uploading.innerHTML = '<span class="spinner inline"></span> Uploading document...';
          }

          const fd = new FormData();
          fd.append("file", file);
          fd.append("user_id", currentUserId);

          const up = await fetch("/upload_docs", {
            method: "POST",
            body: fd
          });
          const upJson = await up.json();
          if (!upJson.success) throw new Error(upJson.message);

          // Update the same uploading placeholder to success
          if (uploading) {
            uploading.classList.remove("uploading");
            uploading.textContent = "Successfully uploaded document";
          } else {
            addMessage(chatId, "bot", "Successfully uploaded document");
          }
        }

        if (question) {
          addMessage(chatId, "user", question);

          addMessage(chatId, "bot", "Synthesizing answer from document context...");

          const res = await fetch("/query_rag", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: question, user_id: currentUserId })
          });

          const result = await res.json();
          if (!result.success) throw new Error(result.answer);

          const answerText = typeof result.answer === 'string' ? result.answer : String(result.answer || '');
          let tail = '';
          if (result.confidence) {
            tail += `<br><br><strong>Confidence score:</strong><br>${escapeHtml(String(result.confidence))}<br>`;
          }
          if (Array.isArray(result.sources) && result.sources.length) {
            tail += "<br><strong>Sources:</strong><br>" + result.sources.map(s => `• ${escapeHtml(String(s))}`).join("<br>");
          }

          // Type out the answer smoothly, then append metadata
          typeLastBotMessage(chatId, answerText, tail);
        }
      } catch (err) {
        // If upload placeholder exists, show error there; else generic
        const container = document.getElementById(chatId + "-messages");
        const uploading = container?.querySelector(".message.bot.uploading");
        if (uploading) {
          uploading.classList.remove("uploading");
          uploading.textContent = "Upload failed. Please try again.";
        } else {
          updateLastBotMessage(chatId, "An error occurred while answering.");
        }
        console.error(err);
      } finally {
        input.value = "";
        if (fileInput) fileInput.value = "";
        input.disabled = false;
        btn.disabled = false;
        btn.textContent = "▶";
        delete form.dataset.inProgress;
      }
    });
  });

  // -----------------------------
  // NAVIGATION
  // -----------------------------
  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => {
      if (isAuthBlocked()) return;
      const target = item.dataset.target;
      if (!target) return;
      showScreen(target);
      setNavActive(item);
      if (target === "screen-history") loadHistory();
    });
  });

  // Header no longer navigates to Home; Home is shown only post-login

  document.getElementById("btn-start-chat")?.addEventListener("click", () => {
    showScreen("screen-healthcare");
    setNavActive(document.querySelector('[data-target="screen-healthcare"]'));
  });

  // Delete all history
  document.getElementById('history-clear')?.addEventListener('click', async () => {
    if (isAuthBlocked()) return;
    const ok = window.confirm('Delete all history?');
    if (!ok) return;
    try {
      const res = await fetch('/history/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: currentUserId })
      });
      const json = await res.json();
      if (json.success) {
        const container = document.querySelector('#screen-history .history-list');
        if (container) {
          container.innerHTML = '';
          const empty = document.createElement('div');
          empty.className = 'history-empty';
          empty.textContent = 'No history yet.';
          container.appendChild(empty);
        }
      }
    } catch (err) { console.error(err); }
  });

  // -----------------------------
  // AUTH EVENT → ENABLE APP
  // -----------------------------
  document.addEventListener("userChanged", () => {
    currentUserId = (window.getCurrentUserId ? window.getCurrentUserId() : (window.currentUserId || "user"));
    syncAuthUI();
    // After sign in, show Home first
    showScreen("screen-home");
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  });

  // -----------------------------
  // CHAT HELPERS
  // -----------------------------
  function addMessage(chatId, sender, html) {
    const container = document.getElementById(chatId + "-messages");
    if (!container) return;
    const normalized = (typeof html === "string" ? html : "").toLowerCase().replace(/\s+/g, " ").trim();
    if (sender === "bot" && normalized.includes("uploading document")) {
      container.querySelectorAll(".message.bot").forEach(n => {
        const txt = (n.textContent || "").toLowerCase().replace(/\s+/g, " ").trim();
        if (txt.includes("uploading document")) n.remove();
      });
      let uploading = container.querySelector(".message.bot.uploading");
      if (!uploading) {
        uploading = document.createElement("div");
        uploading.className = "message bot uploading";
        uploading.innerHTML = '<span class="spinner inline"></span> Uploading document...';
        container.appendChild(uploading);
        container.scrollTop = container.scrollHeight;
      } else {
        uploading.innerHTML = '<span class="spinner inline"></span> Uploading document...';
      }
      return;
    }
    const msg = document.createElement("div");
    msg.className = "message " + sender;
    msg.innerHTML = html;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
  }

  // util: escape HTML
  function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function updateLastBotMessage(chatId, html) {
    const container = document.getElementById(chatId + "-messages");
    if (!container) return;
    const bots = container.querySelectorAll(".message.bot");
    if (bots.length) bots[bots.length - 1].innerHTML = html;
  }

  // Smooth typing effect for the most recent bot message
  function typeLastBotMessage(chatId, text, afterHtml = '') {
    const container = document.getElementById(chatId + "-messages");
    if (!container) return;
    const bots = container.querySelectorAll(".message.bot");
    const target = bots[bots.length - 1];
    if (!target) return;

    // Prepare a typing container
    target.innerHTML = "<strong>Answer:</strong><br><span class=\"typing-area\"></span>";
    const area = target.querySelector('.typing-area');
    if (!area) return;

    const chars = String(text || '');
    let i = 0;
    const speed = 12; // ms per char; tweak for feel

    function step() {
      if (i >= chars.length) {
        // Append tail (confidence, sources) once typing completes
        if (afterHtml) target.innerHTML = target.innerHTML + afterHtml;
        return;
      }
      const ch = chars[i++];
      if (ch === '\n') {
        area.innerHTML += '<br>';
      } else {
        area.innerHTML += escapeHtml(ch);
      }
      container.scrollTop = container.scrollHeight;
      setTimeout(step, speed);
    }
    step();
  }
});

// -----------------------------
// AUTH FORM TOGGLES (GLOBAL)
// -----------------------------
// These are called by links in index.html to switch between
// the login and signup forms inside the auth modal.
window.resetAuthForms = function () {
  const lfEmail = document.getElementById("login-email");
  const lfPass = document.getElementById("login-password");
  const sfName = document.getElementById("signup-name");
  const sfEmail = document.getElementById("signup-email");
  const sfPass = document.getElementById("signup-password");
  const sfPass2 = document.getElementById("signup-confirm-password");

  [lfEmail, lfPass, sfName, sfEmail, sfPass, sfPass2].forEach(el => {
    if (el) {
      el.value = "";
    }
  });
};

window.showSignupForm = function () {
  const login = document.getElementById("login-form");
  const signup = document.getElementById("signup-form");
  if (!login || !signup) return;

  login.classList.remove("active");
  signup.classList.add("active");

  const err = document.getElementById("login-error");
  if (err) err.textContent = "";

  resetAuthForms();
};

window.showLoginForm = function () {
  const login = document.getElementById("login-form");
  const signup = document.getElementById("signup-form");
  if (!login || !signup) return;

  signup.classList.remove("active");
  login.classList.add("active");

  const err = document.getElementById("signup-error");
  if (err) err.textContent = "";

  resetAuthForms();
};

// Toggle password visibility for inputs
window.togglePassword = function (inputId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  input.type = input.type === "password" ? "text" : "password";
};
