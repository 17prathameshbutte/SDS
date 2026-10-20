document.addEventListener('DOMContentLoaded', function () {
  const forms = document.querySelectorAll('form');
  forms.forEach(function (form) {
    form.addEventListener('submit', function (event) {
      // Use the button that was actually clicked (e.g. Upvote vs Downvote),
      // falling back to the form's first submit button.
      const submitButton = event.submitter || form.querySelector('button[type="submit"]');
      if (!submitButton) {
        return;
      }
      // Disable AFTER the browser has collected the form data. A disabled
      // button's name/value is not sent, which used to drop the vote value.
      setTimeout(function () {
        submitButton.dataset.originalText = submitButton.textContent;
        submitButton.disabled = true;
        submitButton.textContent = 'Submitting...';
      }, 0);
    });
  });

  // If the user comes back with the browser's Back button, re-enable the buttons.
  window.addEventListener('pageshow', function (event) {
    if (!event.persisted) {
      return;
    }
    document.querySelectorAll('button[data-original-text]').forEach(function (button) {
      button.disabled = false;
      button.textContent = button.dataset.originalText;
    });
  });
});
