/* ── Avatar colour generator ─────────────────────────────── */
const AVATAR_PALETTE = [
  ['#ffa116','#000'], ['#58a6ff','#000'], ['#3fb950','#000'],
  ['#a371f7','#000'], ['#79c0ff','#000'], ['#d2a8ff','#000'],
];

function avatarStyle(name = '') {
  const idx = [...name].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_PALETTE.length;
  const [bg, color] = AVATAR_PALETTE[idx];
  return `background:${bg};color:${color};`;
}

document.querySelectorAll('[data-avatar]').forEach(el => {
  const name = el.dataset.avatar || '?';
  el.style.cssText += avatarStyle(name);
  el.textContent = name.charAt(0).toUpperCase();
});

/* ── Modal helpers ───────────────────────────────────────── */
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('open');
}
function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('open');
}

document.querySelectorAll('[data-open-modal]').forEach(btn => {
  btn.addEventListener('click', () => openModal(btn.dataset.openModal));
});

document.querySelectorAll('[data-close-modal]').forEach(btn => {
  btn.addEventListener('click', () => closeModal(btn.dataset.closeModal));
});

document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
  backdrop.addEventListener('click', e => {
    if (e.target === backdrop) backdrop.classList.remove('open');
  });
});

/* ── Copy to clipboard ────────────────────────────────────── */
function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = '✓ Copied';
    btn.style.color = 'var(--green)';
    setTimeout(() => {
      btn.innerHTML = orig;
      btn.style.color = '';
    }, 2000);
  });
}

document.querySelectorAll('[data-copy]').forEach(btn => {
  btn.addEventListener('click', () => copyToClipboard(btn.dataset.copy, btn));
});

/* ── Flash message auto-dismiss ──────────────────────────── */
document.querySelectorAll('.alert[data-auto-dismiss]').forEach(alert => {
  const ms = parseInt(alert.dataset.autoDismiss) || 4000;
  setTimeout(() => {
    alert.style.transition = 'opacity 0.4s ease, max-height 0.4s ease';
    alert.style.opacity = '0';
    alert.style.maxHeight = '0';
    alert.style.overflow = 'hidden';
    alert.style.padding = '0';
    alert.style.marginBottom = '0';
    setTimeout(() => alert.remove(), 400);
  }, ms);
});

/* ── Refresh stats button with spinner ───────────────────── */
async function refreshStats(url, btn) {
  btn.disabled = true;
  const orig = btn.innerHTML;
  btn.innerHTML = '<span class="spinner"></span> Refreshing…';
  try {
    const res = await fetch(url, { method: 'POST' });
    const data = await res.json();
    if (data.success || data.refreshed !== undefined) {
      window.location.reload();
    } else {
      showToast(data.error || 'Refresh failed.', 'error');
    }
  } catch {
    showToast('Network error. Please try again.', 'error');
  } finally {
    btn.innerHTML = orig;
    btn.disabled = false;
  }
}

/* ── Simple toast ─────────────────────────────────────────── */
function showToast(msg, type = 'info') {
  const toast = document.createElement('div');
  const colors = { error: 'var(--red)', success: 'var(--green)', info: 'var(--blue)', warning: 'var(--accent)' };
  toast.style.cssText = `
    position:fixed;bottom:24px;right:24px;z-index:9999;
    background:var(--bg-card);border:1px solid var(--border);
    color:${colors[type] || colors.info};
    padding:10px 16px;border-radius:8px;
    font-size:0.85rem;font-family:var(--font-sans);
    box-shadow:var(--shadow-md);
    animation:slideUp 0.3s ease;
  `;
  toast.textContent = msg;
  const style = document.createElement('style');
  style.textContent = '@keyframes slideUp{from{transform:translateY(12px);opacity:0}to{transform:translateY(0);opacity:1}}';
  document.head.appendChild(style);
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
}

/* ── Sortable table ───────────────────────────────────────── */
document.querySelectorAll('table[data-sortable]').forEach(table => {
  const headers = table.querySelectorAll('th[data-sort]');
  headers.forEach(th => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      const tbody = table.querySelector('tbody');
      const rows = [...tbody.querySelectorAll('tr')];
      const asc = th.dataset.sortDir !== 'asc';
      th.dataset.sortDir = asc ? 'asc' : 'desc';
      headers.forEach(h => h.querySelector('.sort-icon')?.remove());
      const icon = document.createElement('span');
      icon.className = 'sort-icon';
      icon.style.marginLeft = '4px';
      icon.textContent = asc ? '↑' : '↓';
      th.appendChild(icon);

      const idx = [...th.parentElement.children].indexOf(th);
      rows.sort((a, b) => {
        const av = a.cells[idx]?.dataset.val ?? a.cells[idx]?.textContent.trim() ?? '';
        const bv = b.cells[idx]?.dataset.val ?? b.cells[idx]?.textContent.trim() ?? '';
        const an = parseFloat(av), bn = parseFloat(bv);
        if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
        return asc ? av.localeCompare(bv) : bv.localeCompare(av);
      });
      rows.forEach(r => tbody.appendChild(r));
    });
  });
});

/* ── Verify page: auto-poll ──────────────────────────────── */
if (document.getElementById('verify-pending-page')) {
  let pollCount = 0;
  const interval = setInterval(async () => {
    try {
      const res = await fetch('/check-verified');
      const data = await res.json();
      if (data.verified) {
        clearInterval(interval);
        window.location.href = data.redirect || '/';
      }
    } catch {}
    if (++pollCount > 60) clearInterval(interval); // stop after 5 min
  }, 5000);
}
