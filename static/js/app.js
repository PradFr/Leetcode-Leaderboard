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

/* Theme Toggle & Initialization */
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('theme-toggle');
  if (toggle) {
    const currentTheme = localStorage.getItem('theme') || 'light';
    if (currentTheme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
      toggle.checked = true;
    } else {
      document.documentElement.removeAttribute('data-theme');
      toggle.checked = false;
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

  const mobileToggle = document.getElementById('mobile-sidebar-toggle');
  const sidebar = document.querySelector('.sidebar');
  if (mobileToggle && sidebar) {
    mobileToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      sidebar.classList.toggle('open');
    });
    document.addEventListener('click', (e) => {
      if (window.innerWidth <= 768 && sidebar.classList.contains('open') && !sidebar.contains(e.target) && e.target !== mobileToggle) {
        sidebar.classList.remove('open');
      }
    });
  }

  initLeaderboardSearchAndSort();
  initExportModal();
});

/* ── Leaderboard Live Search & Dynamic Sorting ───────────────────── */
function initLeaderboardSearchAndSort() {
  const searchInput = document.getElementById('leaderboard-search');
  const clearBtn = document.getElementById('search-clear-btn');
  const sortDropdown = document.getElementById('sort-dropdown');
  const table = document.querySelector('table[data-leaderboard-table], table[data-sortable]');
  
  if (!table) return;
  const tbody = table.querySelector('tbody');
  if (!tbody) return;

  function filterTable() {
    const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
    if (clearBtn) {
      clearBtn.style.display = query.length > 0 ? 'block' : 'none';
    }
    
    const rows = tbody.querySelectorAll('tr[data-student-row], tr:not(.empty-search-row)');
    let visibleCount = 0;
    
    rows.forEach(row => {
      const name = (row.querySelector('.display-name-text')?.textContent || '').toLowerCase();
      const reg = (row.querySelector('.display-reg-text')?.textContent || '').toLowerCase();
      const user = (row.querySelector('[data-leetcode-user]')?.textContent || row.textContent || '').toLowerCase();
      
      const match = !query || name.includes(query) || reg.includes(query) || user.includes(query);
      if (match) {
        row.style.display = '';
        visibleCount++;
      } else {
        row.style.display = 'none';
      }
    });

    // Handle empty search state
    let emptyRow = tbody.querySelector('.empty-search-row');
    if (visibleCount === 0 && query.length > 0) {
      if (!emptyRow) {
        emptyRow = document.createElement('tr');
        emptyRow.className = 'empty-search-row';
        emptyRow.innerHTML = `<td colspan="10" style="text-align:center; padding:32px; color:var(--text-secondary);">
          <div style="font-size:1.8rem; margin-bottom:8px;">🔍</div>
          <div style="font-weight:600;">No matching students found</div>
          <div style="font-size:0.8rem; color:var(--text-muted);">Try searching with a different term</div>
        </td>`;
        tbody.appendChild(emptyRow);
      } else {
        emptyRow.style.display = '';
      }
    } else if (emptyRow) {
      emptyRow.style.display = 'none';
    }
    
    if (window.updateExportRangeBounds) {
      window.updateExportRangeBounds();
    }
  }

  if (searchInput) {
    searchInput.addEventListener('input', filterTable);
  }
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      searchInput.value = '';
      filterTable();
      searchInput.focus();
    });
  }

  function sortTableByColumn(colKey, asc = false) {
    const rows = [...tbody.querySelectorAll('tr[data-student-row], tr:not(.empty-search-row)')];
    
    rows.sort((a, b) => {
      let av = a.dataset[colKey] ?? '';
      let bv = b.dataset[colKey] ?? '';
      
      if (!av) av = a.querySelector(`[data-col="${colKey}"]`)?.dataset.val ?? '';
      if (!bv) bv = b.querySelector(`[data-col="${colKey}"]`)?.dataset.val ?? '';
      
      const an = parseFloat(av), bn = parseFloat(bv);
      if (!isNaN(an) && !isNaN(bn)) {
        return asc ? an - bn : bn - an;
      }
      return asc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });

    rows.forEach((r, idx) => {
      tbody.appendChild(r);
      const rankBadge = r.querySelector('.rank-badge, td:first-child');
      if (rankBadge && rankBadge.classList.contains('rank-badge')) {
        rankBadge.textContent = idx + 1;
        rankBadge.className = `rank-badge rank-${idx + 1 <= 3 ? idx + 1 : 'n'}`;
      }
    });

    filterTable();
  }

  if (sortDropdown) {
    sortDropdown.addEventListener('change', (e) => {
      const val = e.target.value;
      if (val === 'points') sortTableByColumn('points', false);
      else if (val === 'total') sortTableByColumn('total', false);
      else if (val === 'easy') sortTableByColumn('easy', false);
      else if (val === 'med') sortTableByColumn('med', false);
      else if (val === 'hard') sortTableByColumn('hard', false);
      else if (val === 'rank') sortTableByColumn('rank', true);
    });
  }
}

/* ── Admin Export Modal & Validation Controller ─────────────────── */
function initExportModal() {
  const modal = document.getElementById('modal-export');
  if (!modal) return;

  const rangeAllRadio = document.getElementById('export-range-all');
  const rangeCustomRadio = document.getElementById('export-range-custom');
  const rangeInputsBox = document.getElementById('export-range-inputs-box');
  const fromInput = document.getElementById('export-from-pos');
  const toInput = document.getElementById('export-to-pos');
  const totalCountSpan = document.getElementById('export-total-count-text');
  const errorAlert = document.getElementById('export-error-alert');
  const errorMsgText = document.getElementById('export-error-message');
  const exportSubmitBtn = document.getElementById('export-submit-btn');

  function getActiveRows() {
    const table = document.querySelector('table[data-leaderboard-table], table[data-sortable]');
    if (!table) return [];
    const tbody = table.querySelector('tbody');
    if (!tbody) return [];
    return [...tbody.querySelectorAll('tr:not(.empty-search-row)')].filter(r => r.style.display !== 'none');
  }

  function validateExportRange() {
    const rows = getActiveRows();
    const total = rows.length;

    if (totalCountSpan) {
      totalCountSpan.textContent = total;
    }

    if (total === 0) {
      showExportError('No students available in current list to export.');
      return false;
    }

    if (rangeAllRadio && rangeAllRadio.checked) {
      fromInput.value = 1;
      toInput.value = total;
      hideExportError();
      return true;
    }

    const fromVal = parseInt(fromInput.value, 10);
    const toVal = parseInt(toInput.value, 10);

    if (isNaN(fromVal) || isNaN(toVal)) {
      showExportError('Please enter valid position numbers.');
      return false;
    }

    if (fromVal < 1) {
      showExportError('Start position must be at least 1.');
      return false;
    }

    if (fromVal > total) {
      showExportError(`Start position (${fromVal}) exceeds maximum total students (${total}).`);
      return false;
    }

    if (toVal > total) {
      showExportError(`End position (${toVal}) exceeds maximum total students (${total}).`);
      return false;
    }

    if (fromVal > toVal) {
      showExportError(`Start position (${fromVal}) cannot be greater than End position (${toVal}).`);
      return false;
    }

    hideExportError();
    return true;
  }

  function showExportError(msg) {
    if (errorAlert && errorMsgText) {
      errorMsgText.textContent = msg;
      errorAlert.style.display = 'flex';
    }
    if (exportSubmitBtn) {
      exportSubmitBtn.disabled = true;
      exportSubmitBtn.style.opacity = '0.5';
      exportSubmitBtn.style.cursor = 'not-allowed';
    }
  }

  function hideExportError() {
    if (errorAlert) {
      errorAlert.style.display = 'none';
    }
    if (exportSubmitBtn) {
      exportSubmitBtn.disabled = false;
      exportSubmitBtn.style.opacity = '1';
      exportSubmitBtn.style.cursor = 'pointer';
    }
  }

  window.updateExportRangeBounds = function() {
    const rows = getActiveRows();
    if (totalCountSpan) totalCountSpan.textContent = rows.length;
    validateExportRange();
  };

  if (rangeAllRadio && rangeCustomRadio) {
    rangeAllRadio.addEventListener('change', () => {
      if (rangeInputsBox) rangeInputsBox.style.display = 'none';
      validateExportRange();
    });
    rangeCustomRadio.addEventListener('change', () => {
      if (rangeInputsBox) rangeInputsBox.style.display = 'flex';
      validateExportRange();
    });
  }

  if (fromInput) fromInput.addEventListener('input', validateExportRange);
  if (toInput) toInput.addEventListener('input', validateExportRange);

  document.querySelectorAll('.export-format-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.export-format-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      const radio = card.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
    });
  });

  if (exportSubmitBtn) {
    exportSubmitBtn.addEventListener('click', () => {
      if (!validateExportRange()) return;

      const rows = getActiveRows();
      const fromVal = parseInt(fromInput.value, 10);
      const toVal = parseInt(toInput.value, 10);

      const selectedRows = rows.slice(fromVal - 1, toVal);
      const formatRadio = document.querySelector('input[name="export-format"]:checked');
      const format = formatRadio ? formatRadio.value : 'xlsx';

      const exportData = selectedRows.map((r, idx) => {
        const name = r.querySelector('.display-name-text')?.textContent.trim() || 'Student';
        const reg = r.querySelector('.display-reg-text')?.textContent.trim() || 'N/A';
        const lcUser = r.querySelector('[data-leetcode-user]')?.textContent.trim() || r.dataset.lcUser || 'N/A';
        const points = parseInt(r.dataset.points || r.querySelector('[data-col="points"]')?.textContent.trim() || '0', 10);
        const totalSolved = parseInt(r.dataset.total || r.querySelector('[data-col="total"]')?.textContent.trim() || '0', 10);
        const easy = parseInt(r.dataset.easy || r.querySelector('[data-col="easy"]')?.textContent.trim() || '0', 10);
        const medium = parseInt(r.dataset.med || r.querySelector('[data-col="med"]')?.textContent.trim() || '0', 10);
        const hard = parseInt(r.dataset.hard || r.querySelector('[data-col="hard"]')?.textContent.trim() || '0', 10);
        const rank = parseInt(r.dataset.rank || r.querySelector('[data-col="rank"]')?.textContent.trim() || '0', 10);

        return {
          "Rank": fromVal + idx,
          "Student Name": name,
          "Register Number": reg,
          "LeetCode Username": lcUser,
          "Points": points,
          "Total Solved": totalSolved,
          "Easy": easy,
          "Medium": medium,
          "Hard": hard,
          "LeetCode Rank": rank || 'N/A'
        };
      });

      const classNameTitle = document.querySelector('h1, h2, .page-title')?.textContent.trim().replace(/[^a-zA-Z0-9_\-]/g, '_') || 'Leaderboard';
      const fileName = `${classNameTitle}_Positions_${fromVal}_to_${toVal}`;

      if (format === 'csv') {
        exportToCSV(exportData, `${fileName}.csv`);
      } else if (format === 'json') {
        exportToJSON(exportData, `${fileName}.json`);
      } else {
        exportToXLSX(exportData, `${fileName}.xlsx`);
      }

      closeModal('modal-export');
      showToast(`Exported positions ${fromVal} to ${toVal} successfully!`, 'success');
    });
  }
}

function exportToCSV(data, filename) {
  if (!data || !data.length) return;
  const headers = Object.keys(data[0]);
  const csvRows = [headers.join(',')];
  data.forEach(row => {
    const values = headers.map(h => {
      const escaped = ('' + (row[h] ?? '')).replace(/"/g, '""');
      return `"${escaped}"`;
    });
    csvRows.push(values.join(','));
  });
  const blob = new Blob(['\uFEFF' + csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
  triggerDownload(blob, filename);
}

function exportToJSON(data, filename) {
  const jsonStr = JSON.stringify(data, null, 2);
  const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8;' });
  triggerDownload(blob, filename);
}

function exportToXLSX(data, filename) {
  if (typeof XLSX !== 'undefined') {
    const worksheet = XLSX.utils.json_to_sheet(data);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Leaderboard");
    XLSX.writeFile(workbook, filename);
  } else {
    exportToCSV(data, filename.replace(/\.xlsx$/, '.csv'));
  }
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

