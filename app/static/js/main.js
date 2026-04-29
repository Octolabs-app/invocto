/**
 * main.js — Shared vanilla JavaScript for Tax-Ready Invoice
 *
 * Loaded on every page via base.html.
 * Page-specific JS lives in the {% block scripts %} of each template.
 */

// ── Auto-close flash messages after 4 seconds ─────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  const flashes = document.querySelectorAll("[data-flash]");
  flashes.forEach(el => {
    setTimeout(() => {
      el.style.transition = "opacity 0.4s";
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 400);
    }, 4000);
  });

  // ── Close modals on backdrop click ─────────────────────────────────────
  document.querySelectorAll("[id$='Modal']").forEach(modal => {
    modal.addEventListener("click", e => {
      if (e.target === modal) {
        modal.classList.add("hidden");
      }
    });
  });

  // ── Escape key closes any open modal ───────────────────────────────────
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      document.querySelectorAll("[id$='Modal']:not(.hidden)").forEach(modal => {
        modal.classList.add("hidden");
      });
    }
  });

  // ── Confirm before any delete form submission (extra safety) ───────────
  document.querySelectorAll("form[data-confirm]").forEach(form => {
    form.addEventListener("submit", e => {
      const msg = form.dataset.confirm || "Are you sure?";
      if (!confirm(msg)) e.preventDefault();
    });
  });
});

/**
 * Helper: format a number as currency string
 * @param {number} amount
 * @param {string} currency
 * @returns {string}
 */
function formatCurrency(amount, currency = "USD") {
  return `${currency} ${parseFloat(amount).toFixed(2)}`;
}
