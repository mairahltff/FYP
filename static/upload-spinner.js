// Add a circular spinner next to the upload button during file upload
// Hide the spinner when upload completes or fails
// This script is loaded after the main script.js

document.addEventListener('DOMContentLoaded', function() {
  const uploadInput = document.getElementById('file-upload');
  const uploadBtn = document.querySelector('.upload-btn');
  if (!uploadInput || !uploadBtn) return;

  // Create spinner element
  const spinner = document.createElement('span');
  spinner.className = 'spinner upload-spinner';
  spinner.style.display = 'none';
  spinner.style.marginLeft = '8px';
  uploadBtn.parentNode.insertBefore(spinner, uploadBtn.nextSibling);

  // Intercept form submit for upload
  const form = uploadInput.closest('form');
  if (!form) return;

  form.addEventListener('submit', function(e) {
    if (!uploadInput.files.length) return;
    e.preventDefault();
    spinner.style.display = 'inline-block';
    uploadBtn.disabled = true;

    // Show upload status bubble
    const statusBubble = document.getElementById('upload-status-bubble');
    if (statusBubble) {
      statusBubble.textContent = 'Uploading document...';
      statusBubble.style.display = 'block';
      // Match chat bot message style
      statusBubble.style.background = '#10233b';
      statusBubble.style.color = '#fff';
    }

    const file = uploadInput.files[0];
    const formData = new FormData();
    formData.append('file', file);
    // Add user_id using robust getter
    const userId = (window.getCurrentUserId && window.getCurrentUserId()) || window.userId || 'guest';
    formData.append('user_id', userId);

    fetch('/upload_docs', {
      method: 'POST',
      body: formData
    })
    .then(res => res.json())
    .then(data => {
      spinner.style.display = 'none';
      uploadBtn.disabled = false;
      uploadInput.value = '';
      if (statusBubble) {
        if (data.success) {
          statusBubble.textContent = 'Successfully Uploaded';
          statusBubble.style.background = '#10233b';
          statusBubble.style.color = '#1dd1a1';
        } else {
          statusBubble.textContent = 'Upload failed: ' + (data.message || 'Unknown error');
          statusBubble.style.background = '#fab1a0';
          statusBubble.style.color = '#b71c1c';
        }
        setTimeout(() => { statusBubble.style.display = 'none'; }, 3000);
      }
    })
    .catch(() => {
      spinner.style.display = 'none';
      uploadBtn.disabled = false;
      if (statusBubble) {
        statusBubble.textContent = 'Upload failed.';
        statusBubble.style.background = '#fab1a0';
        statusBubble.style.color = '#b71c1c';
        setTimeout(() => { statusBubble.style.display = 'none'; }, 3000);
      }
    });
  });
});
