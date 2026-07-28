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

/* ── Custom UI Confirm ────────────────────────────────────── */
function uiConfirm(message, title, okText, okClass, onConfirm) {
  const m = document.getElementById('modal-confirm');
  if (!m) return;
  document.getElementById('confirm-title').textContent = title || 'Confirm Action';
  document.getElementById('confirm-message').textContent = message || 'Are you sure?';
  const okBtn = document.getElementById('confirm-ok');
  okBtn.textContent = okText || 'Yes';
  okBtn.className = 'btn w-full ' + (okClass || 'btn-primary');
  
  okBtn.onclick = () => {
    closeModal('modal-confirm');
    onConfirm();
  };
  openModal('modal-confirm');
}

/* Override forms with data-confirm */
document.addEventListener('submit', e => {
  if (e.target && e.target.hasAttribute('data-confirm')) {
    e.preventDefault();
    const msg = e.target.getAttribute('data-confirm');
    const title = e.target.getAttribute('data-confirm-title') || 'Confirm';
    const okText = e.target.getAttribute('data-confirm-ok') || 'Confirm';
    const okClass = e.target.getAttribute('data-confirm-class') || 'btn-primary';
    
    uiConfirm(msg, title, okText, okClass, () => {
      e.target.removeAttribute('data-confirm');
      e.target.submit();
      e.target.setAttribute('data-confirm', msg);
    });
  }
});

/* ── Toggle Password Visibility ───────────────────────────── */
function togglePasswordVisibility(inputId, btn) {
  const input = document.getElementById(inputId) || (btn ? btn.parentElement.querySelector('input') : null);
  if (!input) return;
  const isPassword = input.type === 'password';
  input.type = isPassword ? 'text' : 'password';
  if (btn) {
    btn.textContent = isPassword ? '👁 Hide' : '👁 Show';
  }
}

/* Theme Toggle */
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('theme-toggle');
  if (toggle) {
    const currentTheme = localStorage.getItem('theme') || 'light';
    if (currentTheme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
      toggle.checked = true;
    }
    toggle.addEventListener('change', (e) => {
      if (e.target.checked) {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
      } else {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', 'light');
      }
    });
  }
});
