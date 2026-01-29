import { createUserWithEmailAndPassword, fetchSignInMethodsForEmail, signInWithEmailAndPassword, signOut } from "https://www.gstatic.com/firebasejs/12.8.0/firebase-auth.js";

// =============================
// AUTH / UI GUARDS
// =============================
function isAuthBlocked() {
  const authModal = document.getElementById("auth-modal");
  return authModal && authModal.classList.contains("active");
}

// =============================
// MAIN APP
// =============================
document.addEventListener("DOMContentLoaded", () => {
  let currentUserId = window.currentUserId || "user";

  // Navigation/UI is handled centrally in static/script.js

  // -----------------------------
  // SIDEBAR EMAIL + LOGOUT (SIMPLE)
  // -----------------------------
  const emailEl = document.getElementById("sidebar-user-email");
  const logoutBtn = document.getElementById("sidebar-logout");

  function updateSidebarUserEmail() {
    const email = window.auth?.currentUser?.email;
    if (emailEl) emailEl.textContent = email || "Signed in securely";
    if (logoutBtn) logoutBtn.style.display = email ? "inline" : "none";
  }

  logoutBtn?.addEventListener("click", async () => {
    try {
      if (window.auth) await signOut(window.auth);
    } catch (e) {
      console.error(e);
    }
    // Show sign-in modal again (no page refresh)
    const modal = document.getElementById("auth-modal");
    modal?.classList.add("active");
    if (typeof window.showLoginForm === "function") window.showLoginForm();
    // Let the app reset to Home via existing handler
    const evt = new CustomEvent("userChanged", { detail: { userId: null } });
    document.dispatchEvent(evt);
    updateSidebarUserEmail();
  });

  // Keep the email in sync when auth changes are broadcast (login/signup)
  document.addEventListener("userChanged", updateSidebarUserEmail);
  updateSidebarUserEmail();


  // (chat helper functions removed; see static/script.js)

  // =============================
  // SIGNUP HANDLERS (CLIENT ONLY)
  // =============================
  const signupBtn = document.getElementById("signup-btn");
  const signupEmail = document.getElementById("signup-email");
  const signupPass = document.getElementById("signup-password");
  const signupPass2 = document.getElementById("signup-confirm-password");
  const signupError = document.getElementById("signup-error");

  function meetsRequirements(pw) {
    return {
      length: pw.length >= 8,
      upper: /[A-Z]/.test(pw),
      lower: /[a-z]/.test(pw),
      number: /\d/.test(pw)
    };
  }

  function updateRequirementUI(pw) {
    const reqs = meetsRequirements(pw);
    const map = {
      length: document.getElementById("req-length"),
      upper: document.getElementById("req-uppercase"),
      lower: document.getElementById("req-lowercase"),
      number: document.getElementById("req-number")
    };
    Object.keys(map).forEach(k => {
      const el = map[k];
      if (!el) return;
      el.classList.toggle("met", !!reqs[k]);
    });
  }

  // Live updates as user types password
  const updatePwIndicators = (val) => updateRequirementUI(val || "");
  signupPass?.addEventListener("input", (e) => updatePwIndicators(e.target.value));
  signupPass?.addEventListener("keyup", (e) => updatePwIndicators(e.target.value));
  // Confirm password mismatch indicator
  signupPass2?.addEventListener("input", () => {
    if (!signupPass || !signupPass2) return;
    const mismatch = (signupPass.value || "") !== (signupPass2.value || "");
    signupPass2.classList.toggle("input-error", mismatch);
  });
  // Initialize indicators if field has prefilled value
  if (signupPass && signupPass.value) updateRequirementUI(signupPass.value);

  // Attempt to create user, surface email-in-use
  signupBtn?.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!window.auth) return;

    const email = (signupEmail?.value || "").trim();
    const pw = signupPass?.value || "";
    const pw2 = signupPass2?.value || "";

    if (signupError) signupError.textContent = "";

    // Basic requirements
    const reqs = meetsRequirements(pw);
    if (!(reqs.length && reqs.upper && reqs.lower && reqs.number)) {
      if (signupError) signupError.textContent = "Please meet all password requirements.";
      return;
    }
    if (pw !== pw2) {
      if (signupError) signupError.textContent = "Passwords do not match.";
      return;
    }

    try {
      const methods = await fetchSignInMethodsForEmail(window.auth, email);
      if (methods && methods.length) {
        if (signupError) signupError.textContent = "email has already registered";
        return;
      }

      await createUserWithEmailAndPassword(window.auth, email, pw);

      // Success feedback
      if (signupError) {
        signupError.textContent = "Account created successfully.";
        signupError.style.color = "#1dd1a1"; // accent green
      }

      const modal = document.getElementById("auth-modal");
      modal?.classList.remove("active");
      const evt = new CustomEvent("userChanged", { detail: { userId: window.auth.currentUser?.uid } });
      document.dispatchEvent(evt);
    } catch (err) {
      const message = (err && err.code === "auth/email-already-in-use")
        ? "email has already registered"
        : "Signup failed. Please try again.";
      if (signupError) signupError.textContent = message;
      console.error(err);
    }
  });

  // =============================
  // LOGIN HANDLER
  // =============================
  const loginForm = document.getElementById("login-form");
  const loginEmail = document.getElementById("login-email");
  const loginPassword = document.getElementById("login-password");
  const loginError = document.getElementById("login-error");

  loginForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!window.auth) return;

    const email = (loginEmail?.value || "").trim();
    const pw = loginPassword?.value || "";

    if (loginError) loginError.textContent = "";

    // Client-side validation
    if (!email || !pw) {
      if (loginError) loginError.textContent = "Please fill out this field.";
      return;
    }

    try {
      await signInWithEmailAndPassword(window.auth, email, pw);

      const modal = document.getElementById("auth-modal");
      modal?.classList.remove("active");

      // Navigate to Home screen; user can press Start Chat
      const evt = new CustomEvent("userChanged", { detail: { userId: window.auth.currentUser?.uid } });
      document.dispatchEvent(evt);
      // No fallback direct navigation to Chat
    } catch (err) {
      if (loginError) loginError.textContent = "Please fill out this field.";
      console.error(err);
    }
  });

  // (no logout button; default auth flow remains)
});
