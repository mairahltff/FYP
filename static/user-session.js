// Patch: Always preserve guest state and set window.userId for uploads and chat
// This script should be loaded after firebase-auth.js and before upload-spinner.js

document.addEventListener('DOMContentLoaded', function() {
  // Set window.userId based on Firebase auth or guest session
  function setUserIdFromAuth() {
    const isGuest = sessionStorage.getItem('chatly-guest') === '1';
    if (isGuest) {
      window.userId = 'guest';
    } else if (window.auth && window.auth.currentUser) {
      window.userId = window.auth.currentUser.uid;
    }
  }

  // Listen for userChanged event (dispatched in firebase-auth.js)
  window.addEventListener('userChanged', function(e) {
    if (e.detail && e.detail.userId) {
      window.userId = e.detail.userId;
    }
  });

  // Set on load
  setUserIdFromAuth();

  // Also update on auth state changes
  if (window.auth) {
    window.auth.onAuthStateChanged && window.auth.onAuthStateChanged(function(user) {
      setUserIdFromAuth();
    });
  }

  // Defensive: update userId before every upload or chat
  window.getCurrentUserId = function() {
    const isGuest = sessionStorage.getItem('chatly-guest') === '1';
    if (isGuest) return 'guest';
    if (window.auth && window.auth.currentUser) return window.auth.currentUser.uid;
    return 'guest';
  };
});

window.isGuestUser = function () {
  return sessionStorage.getItem('chatly-guest') === '1';
};

