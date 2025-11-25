/**
 * dashboard.js — Unified dashboard frontend (copy-paste ready)
 *
 * Endpoints expected:
 *   GET  /api/analytics/
 *   GET  /api/files/
 *   GET  /api/user/me/
 *   POST /api/files/            (upload new file)
 *   PUT  /api/files/<id>/       (replace file via FormData with 'file' field)
 *   DELETE /api/files/<id>/     (delete file)
 *   POST /api/files/<id>/access/ (record access)
 *   POST /api/scan_shared/      (manager-only rescan)
 *   GET/POST /api/files/<id>/content/ (edit file)
 *
 * IDs expected in HTML:
 *  - #welcome-username, #total-files-kpi, #total-size-kpi
 *  - #fileTypeChart, #hot-files-list, #files-table-body
 *  - #file-upload-form, #fileInput, #upload-status
 *  - #team-members, #team-name-header, #team-count
 *  - #rescan-btn, #rescan-status
 *  - Modal ids: #fileEditModal, #fileEditTextarea, #fileEditModalTitle, #fileEditAlert, #fileEditSaveBtn
 */

(function () {
  "use strict";

  // --- Small helpers -----------------------------------------------------
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));

  function getCsrf() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || "";
  }

  function log(...args) { console.log('[dashboard]', ...args); }
  function err(...args) { console.error('[dashboard]', ...args); }

  function fmtBytes(bytes) {
    if (bytes == null) return "—";
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"','&quot;').replaceAll("'", "&#039;");
  }

  async function fetchJSON(url, opts = {}) {
    const res = await fetch(url, Object.assign({ credentials: "include", headers: { "X-Requested-With": "XMLHttpRequest" } }, opts));
    if (!res.ok) {
      const txt = await res.text().catch(()=>"");
      throw new Error(`HTTP ${res.status} ${url} ${txt}`);
    }
    return res.json();
  }

  // debounce utility
  function debounce(fn, wait = 350) {
    let t = null;
    return function(...a) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, a), wait);
    };
  }

  // --- DOM refs ----------------------------------------------------------
  const refs = {
    welcome: $("#welcome-username"),
    kpiFiles: $("#total-files-kpi"),
    kpiSize: $("#total-size-kpi"),
    fileTypeCanvas: $("#fileTypeChart"),
    hotFilesList: $("#hot-files-list"),
    filesTbody: $("#files-table-body"),
    uploadForm: $("#file-upload-form"),
    uploadInput: $("#fileInput"),
    uploadStatus: $("#upload-status"),
    teamMembers: $("#team-members"),
    teamHeader: $("#team-name-header"),
    teamCount: $("#team-count"),
    rescanBtn: $("#rescan-btn"),
    rescanStatus: $("#rescan-status")
  };

  // Chart instances
  let fileTypeChart = null;

  // Global current user store (populated by /api/user/me/)
  window.CURRENT_USER = window.CURRENT_USER || { id: null, username: null, role: null, team_id: null };

  // --- Renderers --------------------------------------------------------
  function renderFileTypeChart(dataset) {
    const canvas = refs.fileTypeCanvas;
    if (!canvas) return;
    try {
      if (fileTypeChart && fileTypeChart.destroy) fileTypeChart.destroy();

      let labels = [], values = [];
      if (Array.isArray(dataset) && dataset.length) {
        labels = dataset.map(d => d.file_type || d.label || "unknown");
        values = dataset.map(d => Number(d.count || d.value || 0));
      }
      if (!labels.length) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0,0,canvas.width,canvas.height);
        return;
      }
      const palette = ['rgba(99,102,241,0.9)','rgba(16,185,129,0.9)','rgba(59,130,246,0.9)','rgba(245,158,11,0.9)','rgba(168,85,247,0.9)'];
      const ctx = canvas.getContext('2d');
      fileTypeChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: labels.map((_,i)=>palette[i%palette.length]), borderColor:'#fff', borderWidth:1 }]},
        options: { maintainAspectRatio:false, responsive:true, cutout:'60%', plugins:{ legend:{ position:'bottom' } } }
      });
    } catch (e) {
      err('renderFileTypeChart failed', e);
    }
  }

  function renderHotFiles(list) {
    const el = refs.hotFilesList;
    if (!el) return;
    log('renderHotFiles payload', list);
    if (!Array.isArray(list) || list.length === 0) {
      el.innerHTML = `<li class="text-soft py-3 text-center">No hot files yet.</li>`;
      return;
    }
    // only show files with access_count > 1 and limit to 8
    const filtered = list.filter(f => (Number(f.access_count) || 0) > 1).slice(0, 8);
    if (!filtered.length) {
      el.innerHTML = `<li class="text-soft py-3 text-center">No hot files (low access counts).</li>`;
      return;
    }
    el.innerHTML = filtered.map(f => {
      const fname = escapeHtml(f.file_name || 'Untitled');
      const when = f.last_modified_date ? new Date(f.last_modified_date).toLocaleString() : "—";
      const accesses = Number(f.access_count || 0);
      const url = f.file_url || `/shared_files/${encodeURIComponent(f.file_name || '')}/`;
      return `
        <li class="d-flex justify-content-between align-items-start py-2 border-bottom">
          <div>
            <div class="fw-semibold"><a href="${url}" data-file-id="${f.id}" target="_blank" rel="noreferrer" class="text-decoration-none">${fname}</a></div>
            <div class="small text-soft">${escapeHtml(f.modified_by_username || 'System')} • ${when}</div>
          </div>
          <div class="text-end small text-soft"> ${accesses}</div>
        </li>
      `;
    }).join('');
  }

  function buildFileRowHtml(f) {
    const fileUrl = f.file_url || `/shared_files/${encodeURIComponent(f.file_name || "")}/`;
    const modifiedBy = f.modified_by_username || "System (external edit)";
    const modifiedOn = f.last_modified_date ? new Date(f.last_modified_date).toLocaleString() : (f.upload_date ? new Date(f.upload_date).toLocaleString() : "—");
    const accesses = f.access_count || 0;
    const size = f.size_display || fmtBytes(f.file_size || 0);
    const type = f.file_type || "—";

    const fileTeamId = f.team && (typeof f.team === "object" ? f.team.id : f.team);
    const canReplace = (window.CURRENT_USER && window.CURRENT_USER.team_id && String(window.CURRENT_USER.team_id) === String(fileTeamId));
    const canDelete = canReplace && (String(window.CURRENT_USER?.role || "").toLowerCase() === "manager");
    const canEdit = canReplace && ['txt','csv','md','py','json','html','js','css','log','docx'].includes((f.file_type||'').toLowerCase());

    const replaceHtml = canReplace ? `<label class="btn btn-sm btn-outline-secondary me-1 mb-0" style="cursor:pointer">Replace <input type="file" data-replace-id="${f.id}" style="display:none" /></label>` : "";
    const editHtml = canEdit ? `<button class="btn btn-sm btn-outline-secondary me-1 btn-edit" data-edit-id="${f.id}" data-edit-name="${escapeHtml(f.file_name)}" data-edit-ext="${escapeHtml(f.file_type)}" data-edit-size="${f.file_size || 0}">Edit</button>` : "";
    const deleteHtml = canDelete ? `<button class="btn btn-sm btn-outline-danger btn-delete" data-delete-id="${f.id}">Delete</button>` : "";

    return `
      <tr data-file-id-row="${f.id}">
        <td><a href="${fileUrl}" data-file-id="${f.id}" target="_blank" rel="noreferrer" class="text-decoration-none">${escapeHtml(f.file_name)}</a></td>
        <td>${escapeHtml(type)}</td>
        <td>${escapeHtml(size)}</td>
        <td>${escapeHtml(modifiedBy)}</td>
        <td>${escapeHtml(modifiedOn)}</td>
        <td class="col-accesses">${escapeHtml(String(accesses))}</td>
        <td class="text-end text-nowrap">
          <div class="d-flex justify-content-end gap-2">
            <a class="btn btn-sm btn-outline-primary" href="${fileUrl}" data-file-id="${f.id}" target="_blank" rel="noreferrer">View</a>
            ${editHtml}
            ${replaceHtml}
            ${deleteHtml}
          </div>
        </td>
      </tr>
    `;
  }

  function renderFilesList(files) {
    const tbody = refs.filesTbody;
    if (!tbody) return;
    if (!Array.isArray(files) || files.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">No files found.</td></tr>`;
      return;
    }
    tbody.innerHTML = files.map(buildFileRowHtml).join('');
  }

  // --- Data loaders -----------------------------------------------------
  async function loadAnalytics() {
    try {
      const data = await fetchJSON('/api/analytics/');
      log('ANALYTICS:', data);
      if (refs.kpiFiles) refs.kpiFiles.textContent = data.total_files ?? '0';
      if (refs.kpiSize) refs.kpiSize.textContent = data.total_size_display ?? fmtBytes(data.total_size || 0);
      renderFileTypeChart(data.file_type_distribution || []);
      renderHotFiles(data.hot_files || []);
    } catch (err) {
      err('loadAnalytics error', err);
    }
  }

  async function loadFiles() {
    try {
      const files = await fetchJSON('/api/files/');
      // normalize
      const normalized = (files || []).map(f => Object.assign({
        id: f.id,
        file_name: f.file_name,
        file_type: f.file_type,
        file_size: f.file_size,
        upload_date: f.upload_date,
        last_modified_date: f.last_modified_date,
        uploaded_by_username: f.uploaded_by_username,
        modified_by_username: f.modified_by_username || (f.modified_by ? (f.modified_by.username || null) : null),
        access_count: f.access_count || 0,
        team: f.team,
        file_url: f.file_url,
        size_display: f.size_display
      }, f));
      renderFilesList(normalized);
    } catch (err) {
      err('loadFiles error', err);
      if (refs.filesTbody) refs.filesTbody.innerHTML = '<tr><td colspan="7" class="text-center text-danger py-4">Failed to load files.</td></tr>';
    }
  }

  async function loadUserAndTeam() {
    try {
      const payload = await fetchJSON('/api/user/me/');
      const user = payload?.user;
      if (user) {
        window.CURRENT_USER = {
          id: user.id || null,
          username: user.username || null,
          role: (user.role || '').toLowerCase(),
          team_id: user.team_id || null
        };
        if (refs.welcome) refs.welcome.textContent = `${user.username || user.email}${user.role ? ` (${user.role})` : ''}`;
        if (refs.teamHeader) refs.teamHeader.textContent = user.team_name || 'My Team';
      } else {
        window.CURRENT_USER = { id: null, username: null, role: null, team_id: null };
      }

      const members = payload?.team_members || [];
      if (refs.teamMembers) {
        refs.teamMembers.innerHTML = members.length ? members.map(m => `
          <li class="list-group-item d-flex justify-content-between align-items-center">
            <div><div class="fw-semibold">${escapeHtml(m.username)}</div><div class="small text-soft">${escapeHtml(m.role || '')}</div></div>
          </li>`).join('') : '<li class="text-soft">You are not assigned to a team.</li>';
      }
      if (refs.teamCount) refs.teamCount.textContent = String(members.length || 0);

      // show/hide rescan button
      if (refs.rescanBtn) {
        if ((window.CURRENT_USER.role || '') === 'manager') refs.rescanBtn.style.display = 'inline-block';
        else refs.rescanBtn.style.display = 'none';
      }

      // load analytics & files
      await loadAnalytics();
      await loadFiles();
    } catch (err) {
      err('loadUserAndTeam error', err);
    }
  }

  // debounced analytics reload used after access increments, replaces many calls with one
  const debouncedReloadAnalytics = debounce(() => {
    if (typeof loadAnalytics === 'function') {
      loadAnalytics().catch(e => err('debounced loadAnalytics error', e));
    }
  }, 350);

  // --- Upload handling --------------------------------------------------
  if (refs.uploadForm) {
    refs.uploadForm.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      if (!refs.uploadInput || !refs.uploadInput.files || !refs.uploadInput.files[0]) {
        alert('Please choose a file to upload.');
        return;
      }
      const fd = new FormData();
      fd.append('file', refs.uploadInput.files[0]);
      // include team_id if available (serializer accepts team_id write-only)
      if (window.CURRENT_USER?.team_id) fd.append('team_id', window.CURRENT_USER.team_id);
      // csrf
      const csrf = getCsrf();
      if (csrf) fd.append('csrfmiddlewaretoken', csrf);

      if (refs.uploadStatus) refs.uploadStatus.innerHTML = '<div class="alert alert-info small mb-0">Uploading…</div>';
      try {
        const res = await fetch('/api/files/', { method: 'POST', credentials: 'include', body: fd });
        const txt = await res.text().catch(()=>'');
        let body = null;
        try { body = txt ? JSON.parse(txt) : null; } catch(e){ body = null; }
        if (!res.ok) {
          err('upload error body', body);
          throw new Error(body?.detail || `HTTP ${res.status}`);
        }
        if (refs.uploadStatus) refs.uploadStatus.innerHTML = '<div class="alert alert-success small mb-0">Upload successful!</div>';
        refs.uploadForm.reset();
        // refresh UI
        setTimeout(()=>{ loadFiles(); loadAnalytics(); }, 600);
      } catch (err) {
        err('upload failed', err);
        if (refs.uploadStatus) refs.uploadStatus.innerHTML = `<div class="alert alert-danger small mb-0">Upload failed: ${escapeHtml(err.message)}</div>`;
      } finally {
        setTimeout(()=>{ if (refs.uploadStatus) refs.uploadStatus.innerHTML = ''; }, 3500);
      }
    });
  }

  // --- Rescan handler (manager only) -----------------------------------
  if (refs.rescanBtn) {
    refs.rescanBtn.addEventListener('click', async function () {
      refs.rescanBtn.disabled = true;
      if (refs.rescanStatus) refs.rescanStatus.textContent = "🔄 Scanning shared folder…";
      try {
        const csrf = getCsrf();
        const res = await fetch('/api/scan_shared/', { method: 'POST', headers: { 'X-CSRFToken': csrf }, credentials: 'include' });
        const txt = await res.text().catch(()=>'');
        let body = null;
        try { body = txt ? JSON.parse(txt) : null; } catch(e){ body = null; }
        if (!res.ok) {
          const msg = body?.detail || body?.error || `HTTP ${res.status}`;
          if (refs.rescanStatus) refs.rescanStatus.textContent = `❌ Rescan failed: ${msg}`;
          err('Rescan error:', msg, 'raw:', txt);
          return;
        }
        const stats = body?.stats || { created:0, updated:0, deleted:0 };
        if (refs.rescanStatus) refs.rescanStatus.textContent = `✅ Rescan done. Created: ${stats.created}, Updated: ${stats.updated}, Deleted: ${stats.deleted}.`;
        // refresh analytics and files (rescan may change these)
        await loadAnalytics();
        await loadFiles();
      } catch (err) {
        err('Rescan failed:', err);
        if (refs.rescanStatus) refs.rescanStatus.textContent = `⚠️ Rescan failed: ${escapeHtml(err.message)}`;
      } finally {
        refs.rescanBtn.disabled = false;
        setTimeout(()=>{ if (refs.rescanStatus) refs.rescanStatus.textContent = ''; }, 6000);
      }
    });
  }

  // --- Replace (input[type=file] dynamic) --------------------------------
  document.addEventListener('change', async function (e) {
    const input = e.target;
    if (!input.matches("input[type='file'][data-replace-id]")) return;
    const fileId = input.getAttribute('data-replace-id');
    const file = input.files[0];
    if (!file) return;
    if (!confirm(`Replace existing file with "${file.name}"?`)) { input.value = ""; return; }

    const fd = new FormData();
    fd.append('file', file);
    const csrf = getCsrf();
    try {
      const res = await fetch(`/api/files/${fileId}/`, { method: 'PUT', credentials: 'include', headers: { 'X-CSRFToken': csrf }, body: fd });
      if (!res.ok) {
        const txt = await res.text().catch(()=>'');
        let body=null; try{ body = txt?JSON.parse(txt):null; }catch{} ;
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      alert('File replaced successfully.');
      await loadFiles(); await loadAnalytics();
    } catch (err) {
      err('replace error', err);
      alert('Replace failed: ' + err.message);
    } finally {
      input.value = "";
    }
  });

  // --- Delete handler (delegated) ---------------------------------------
  document.addEventListener('click', async function (e) {
    const btn = e.target.closest('.btn-delete');
    if (!btn) return;
    const fileId = btn.getAttribute('data-delete-id');
    if (!confirm('Delete this file? This cannot be undone.')) return;
    const csrf = getCsrf();
    try {
      const res = await fetch(`/api/files/${fileId}/`, { method: 'DELETE', credentials: 'include', headers: { 'X-CSRFToken': csrf } });
      if (!res.ok) {
        const txt = await res.text().catch(()=>''); let body=null; try{body = txt?JSON.parse(txt):null}catch{} ;
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      alert('File deleted.');
      await loadFiles(); await loadAnalytics();
    } catch (err) {
      err('delete error', err);
      alert('Delete failed: ' + err.message);
    }
  });

  // --- Editor: open/save modal ------------------------------------------
  const EDITABLE_EXT = ['txt','csv','md','py','json','html','js','css','log','docx'];
  const MAX_EDIT_SIZE = 2 * 1024 * 1024; // 2MB

  // modal elements (may be absent until DOM loaded)
  let editModalEl = document.getElementById('fileEditModal');
  let editTextarea = document.getElementById('fileEditTextarea');
  let editTitle = document.getElementById('fileEditModalTitle');
  let editAlert = document.getElementById('fileEditAlert');
  let editSaveBtn = document.getElementById('fileEditSaveBtn');

  let EDIT_CURRENT_FILE_ID = null;

  async function openFileEditor(fileId, fileName, fileExt, fileSize) {
    // refresh DOM refs
    editModalEl = editModalEl || document.getElementById('fileEditModal');
    editTextarea = editTextarea || document.getElementById('fileEditTextarea');
    editTitle = editTitle || document.getElementById('fileEditModalTitle');
    editAlert = editAlert || document.getElementById('fileEditAlert');
    editSaveBtn = editSaveBtn || document.getElementById('fileEditSaveBtn');

    if (!editModalEl || !editTextarea || !editTitle || !editSaveBtn) {
      console.warn('Editor modal missing in DOM.');
      alert('Editor not available (modal missing).');
      return;
    }

    const ext = (fileExt || '').toLowerCase().replace('.', '');
    if (!EDITABLE_EXT.includes(ext)) {
      alert('This file type cannot be edited in-browser.');
      return;
    }
    if (fileSize && fileSize > MAX_EDIT_SIZE) {
      alert('File too large to edit in the browser (max 2 MB).');
      return;
    }

    EDIT_CURRENT_FILE_ID = fileId;
    editTitle.textContent = `Edit — ${fileName}`;
    editAlert.innerHTML = '';
    editTextarea.value = 'Loading...';

    // show modal
    try {
      const modal = new bootstrap.Modal(editModalEl);
      modal.show();
    } catch (e) {
      console.warn('Bootstrap modal not available', e);
    }

    // fetch content
    try {
      const resp = await fetch(`/api/files/${fileId}/content/`, { credentials: 'include' });
      if (!resp.ok) {
        const body = await resp.json().catch(()=>({detail:'Failed to load'}));
        editAlert.innerHTML = `<div class="alert alert-danger small mb-2">${escapeHtml(body.detail || 'Could not load file.')}</div>`;
        editTextarea.value = '';
        return;
      }
      const payload = await resp.json();
      editTextarea.value = payload.content || '';
    } catch (err) {
      err('Failed to load file content:', err);
      editAlert.innerHTML = `<div class="alert alert-danger small mb-2">Failed to load file content.</div>`;
      editTextarea.value = '';
    }
  }

  // attach save handler once when available
  function attachEditSaveHandler() {
    editSaveBtn = editSaveBtn || document.getElementById('fileEditSaveBtn');
    if (!editSaveBtn) return;
    if (editSaveBtn.__attached) return;
    editSaveBtn.addEventListener('click', async function () {
      if (!EDIT_CURRENT_FILE_ID) return;
      const content = editTextarea.value;
      if ((new TextEncoder().encode(content)).length > MAX_EDIT_SIZE) {
        editAlert.innerHTML = `<div class="alert alert-danger small mb-2">Content too large to save.</div>`;
        return;
      }
      editSaveBtn.disabled = true;
      editAlert.innerHTML = `<div class="alert alert-info small mb-2">Saving…</div>`;
      try {
        const resp = await fetch(`/api/files/${EDIT_CURRENT_FILE_ID}/content/`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
          body: JSON.stringify({ content })
        });
        const body = await resp.json().catch(()=>({}));
        if (!resp.ok) {
          editAlert.innerHTML = `<div class="alert alert-danger small mb-2">${escapeHtml(body.detail || 'Save failed')}</div>`;
          return;
        }
        editAlert.innerHTML = `<div class="alert alert-success small mb-2">Saved successfully.</div>`;
        await loadFiles(); await loadAnalytics();
        setTimeout(()=>{ const m = bootstrap.Modal.getInstance(editModalEl); if (m) m.hide(); }, 700);
      } catch (err) {
        err('save error', err);
        editAlert.innerHTML = `<div class="alert alert-danger small mb-2">Save failed.</div>`;
      } finally {
        editSaveBtn.disabled = false;
      }
    });
    editSaveBtn.__attached = true;
  }

  // delegate: when an edit button clicked, open editor
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('.btn-edit');
    if (!btn) return;
    const id = btn.getAttribute('data-edit-id');
    const name = btn.getAttribute('data-edit-name');
    const ext = btn.getAttribute('data-edit-ext') || '';
    const size = parseInt(btn.getAttribute('data-edit-size') || '0', 10);
    openFileEditor(id, name, ext, size);
    // ensure save handler attached
    attachEditSaveHandler();
  });

  // --- Delegated access handler (intercepts clicks on links having data-file-id) ---
  document.addEventListener('click', async function (evt) {
    const a = evt.target.closest('a[data-file-id]');
    if (!a) return;
    // intercept to record access
    evt.preventDefault();
    const fileId = a.getAttribute('data-file-id');
    const href = a.href;
    const csrf = getCsrf();

    try {
      const res = await fetch(`/api/files/${fileId}/access/`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' }
      });
      const txt = await res.text().catch(()=>'');
      let body = null;
      try { body = txt ? JSON.parse(txt) : null; } catch(e) { body = null; }

      if (res.ok && body && body.access_count !== undefined) {
        // update table row cell
        const row = document.querySelector(`tr[data-file-id-row="${fileId}"]`);
        if (row) {
          const aCell = row.querySelector('.col-accesses');
          if (aCell) aCell.textContent = String(body.access_count);
        }
        // update hot-files item(s) locally (fast)
        const hotAnchors = document.querySelectorAll(`#hot-files-list a[data-file-id="${fileId}"]`);
        hotAnchors.forEach(h => {
          const li = h.closest('li');
          if (!li) return;
          const right = li.querySelector('.text-end');
          if (right) right.textContent = String(body.access_count);
        });
      } else {
        // optimistic increment fallback
        const row = document.querySelector(`tr[data-file-id-row="${fileId}"]`);
        if (row) {
          const aCell = row.querySelector('.col-accesses');
          if (aCell) {
            const cur = parseInt(aCell.textContent || '0', 10) || 0;
            aCell.textContent = String(cur + 1);
          }
        }
      }
    } catch (err) {
      err('access POST failed', err);
      // optimistic update
      const row = document.querySelector(`tr[data-file-id-row="${fileId}"]`);
      if (row) {
        const aCell = row.querySelector('.col-accesses');
        if (aCell) {
          const cur = parseInt(aCell.textContent || '0', 10) || 0;
          aCell.textContent = String(cur + 1);
        }
      }
    } finally {
      // refresh analytics/hot-files (debounced to avoid spam)
      debouncedReloadAnalytics();
      // open file in new tab/window
      try { window.open(href, '_blank'); } catch(e) { window.location = href; }
    }
  }, true);

  // --- Attach delete/replace handlers already handled above via delegation ---

  // --- Boot --------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', function () {
    // load user/team, then analytics/files will load after
    loadUserAndTeam();
    // attach modal save handler if present
    attachEditSaveHandler();
  });

})();
