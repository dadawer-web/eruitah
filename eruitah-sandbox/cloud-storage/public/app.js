const API = '';
let currentPath = '';
let currentView = 'grid';
let allItems = [];

// DOM elements
const fileGrid = document.getElementById('fileGrid');
const emptyState = document.getElementById('emptyState');
const breadcrumb = document.getElementById('breadcrumb');
const searchInput = document.getElementById('searchInput');
const fileInput = document.getElementById('fileInput');
const toastContainer = document.getElementById('toastContainer');

// Init
document.addEventListener('DOMContentLoaded', () => {
  loadFiles();
  loadStats();
  bindEvents();
});

function bindEvents() {
  document.getElementById('btnUpload').onclick = () => document.getElementById('uploadModal').style.display = 'flex';
  document.getElementById('btnNewFolder').onclick = createFolder;
  document.getElementById('btnViewGrid').onclick = () => setView('grid');
  document.getElementById('btnViewList').onclick = () => setView('list');
  fileInput.onchange = handleUpload;

  // Upload drop zone
  const drop = document.getElementById('uploadDrop');
  drop.onclick = () => fileInput.click();
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('dragover'); };
  drop.ondragleave = () => drop.classList.remove('dragover');
  drop.ondrop = (e) => {
    e.preventDefault();
    drop.classList.remove('dragover');
    if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
  };

  // Global drag-drop
  document.body.ondragover = (e) => e.preventDefault();
  document.body.ondrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
  };

  // Close modals
  document.querySelectorAll('.close-modal').forEach(btn => {
    btn.onclick = () => document.getElementById(btn.dataset.modal).style.display = 'none';
  });
  document.querySelectorAll('.modal').forEach(modal => {
    modal.onclick = (e) => { if (e.target === modal) modal.style.display = 'none'; };
  });

  // Search
  searchInput.oninput = () => renderFiles();

  // Nav items
  document.querySelectorAll('.nav-item').forEach(item => {
    item.onclick = (e) => {
      e.preventDefault();
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      item.classList.add('active');
      if (item.dataset.action === 'files') {
        navigateTo('');
      }
    };
  });

  // Close context menu on click
  document.onclick = () => {
    const menu = document.querySelector('.context-menu');
    if (menu) menu.remove();
  };
}

async function loadFiles(path) {
  if (path !== undefined) currentPath = path;
  try {
    const res = await fetch(`${API}/api/files?path=${encodeURIComponent(currentPath)}`);
    const data = await res.json();
    if (data.success) {
      allItems = data.items;
      renderFiles();
      updateBreadcrumb();
    }
  } catch (err) {
    showToast('Failed to load files', 'error');
  }
}

async function loadStats() {
  try {
    const res = await fetch(`${API}/api/stats`);
    const data = await res.json();
    if (data.success) {
      document.getElementById('fileCount').textContent = data.totalFiles;
      document.getElementById('folderCount').textContent = data.totalFolders;
      const pct = (data.usedSpace / data.maxSpace * 100).toFixed(1);
      document.getElementById('storageFill').style.width = `${Math.min(pct, 100)}%`;
      document.getElementById('storageText').textContent = `${formatSize(data.usedSpace)} / 1 GB`;
    }
  } catch (err) {}
}

function renderFiles() {
  const query = searchInput.value.toLowerCase();
  let items = allItems;
  if (query) {
    items = items.filter(i => i.name.toLowerCase().includes(query));
  }

  if (items.length === 0) {
    fileGrid.innerHTML = '';
    emptyState.style.display = 'block';
    return;
  }
  emptyState.style.display = 'none';

  // Sort: folders first, then by name
  items.sort((a, b) => {
    if (a.type === 'folder' && b.type !== 'folder') return -1;
    if (a.type !== 'folder' && b.type === 'folder') return 1;
    return a.name.localeCompare(b.name);
  });

  fileGrid.className = currentView === 'list' ? 'file-grid list-view' : 'file-grid';

  fileGrid.innerHTML = items.map(item => {
    const icon = getIcon(item);
    if (currentView === 'list') {
      return `
        <div class="file-card list-item" data-id="${item.id}" data-type="${item.type}" oncontextmenu="showContextMenu(event, '${item.id}', '${item.type}')">
          <span class="file-icon ${icon.cls}">${icon.html}</span>
          <div class="file-info">
            <div class="file-name">${item.name}</div>
            <div class="file-meta">${item.type === 'file' ? formatSize(item.size) : '文件夹'}</div>
          </div>
          <div class="file-actions">
            ${item.type === 'file' ? `<button onclick="event.stopPropagation(); previewFile('${item.id}', '${item.name}')" title="预览"><i class="fas fa-eye"></i></button>` : ''}
            <button onclick="event.stopPropagation(); renameItem('${item.id}', '${item.type}')" title="重命名"><i class="fas fa-pen"></i></button>
            <button onclick="event.stopPropagation(); deleteItem('${item.id}', '${item.type}')" title="删除"><i class="fas fa-trash"></i></button>
          </div>
        </div>`;
    }
    return `
      <div class="file-card" data-id="${item.id}" data-type="${item.type}" ondblclick="${item.type === 'folder' ? `navigateTo('${item.path}')` : `previewFile('${item.id}', '${item.name}')`}" oncontextmenu="showContextMenu(event, '${item.id}', '${item.type}')">
        <div class="file-actions-bar">
          ${item.type === 'file' ? `<button onclick="event.stopPropagation(); previewFile('${item.id}', '${item.name}')" title="预览"><i class="fas fa-eye"></i></button>` : ''}
          <button onclick="event.stopPropagation(); renameItem('${item.id}', '${item.type}')" title="重命名"><i class="fas fa-pen"></i></button>
          <button onclick="event.stopPropagation(); deleteItem('${item.id}', '${item.type}')" title="删除"><i class="fas fa-trash"></i></button>
        </div>
        <span class="file-icon ${icon.cls}">${icon.html}</span>
        <div class="file-name">${item.name}</div>
        <div class="file-meta">${item.type === 'file' ? formatSize(item.size) : ''}</div>
      </div>`;
  }).join('');
}

function getIcon(item) {
  if (item.type === 'folder') return { html: '<i class="fas fa-folder"></i>', cls: 'folder-icon' };
  const ext = item.name.split('.').pop().toLowerCase();
  const map = {
    'jpg|jpeg|png|gif|bmp|svg|webp': { html: '<i class="fas fa-file-image"></i>', cls: 'image-icon' },
    'mp4|avi|mov|wmv|flv|mkv': { html: '<i class="fas fa-file-video"></i>', cls: 'video-icon' },
    'mp3|wav|flac|aac|ogg': { html: '<i class="fas fa-file-audio"></i>', cls: 'audio-icon' },
    'pdf': { html: '<i class="fas fa-file-pdf"></i>', cls: 'pdf-icon' },
    'doc|docx': { html: '<i class="fas fa-file-word"></i>', cls: 'doc-icon' },
    'xls|xlsx|csv': { html: '<i class="fas fa-file-excel"></i>', cls: 'doc-icon' },
    'ppt|pptx': { html: '<i class="fas fa-file-powerpoint"></i>', cls: 'doc-icon' },
    'zip|rar|7z|tar|gz': { html: '<i class="fas fa-file-archive"></i>', cls: 'archive-icon' },
    'js|ts|py|java|c|cpp|go|rs|html|css|json|xml|yml|yaml|sh|rb': { html: '<i class="fas fa-file-code"></i>', cls: 'code-icon' },
    'txt|md|log': { html: '<i class="fas fa-file-alt"></i>', cls: 'file-icon-default' },
  };
  for (const [exts, val] of Object.entries(map)) {
    if (exts.split('|').includes(ext)) return val;
  }
  return { html: '<i class="fas fa-file"></i>', cls: 'file-icon-default' };
}

function navigateTo(path) {
  currentPath = path;
  loadFiles();
  loadStats();
  // Update nav
  document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
  document.querySelector('[data-action="files"]').classList.add('active');
}

function updateBreadcrumb() {
  const parts = currentPath ? currentPath.split('/') : [];
  let html = '<span class="crumb" onclick="navigateTo(\'\')">/</span>';
  let accumulated = '';
  parts.forEach((p, i) => {
    accumulated += (accumulated ? '/' : '') + p;
    const path = accumulated;
    html += `<span class="crumb" onclick="navigateTo('${path}')">${p}</span> /`;
  });
  breadcrumb.innerHTML = html;
}

async function handleUpload() {
  if (fileInput.files.length) uploadFiles(fileInput.files);
}

async function uploadFiles(files) {
  const modal = document.getElementById('uploadModal');
  const list = document.getElementById('uploadList');
  modal.style.display = 'flex';
  list.innerHTML = '';

  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
    list.innerHTML += `<div class="upload-item"><i class="fas fa-file"></i><span>${file.name}</span><div class="progress"><div class="progress-fill" style="width:100%"></div></div><span class="status">✓</span></div>`;
  }

  try {
    const res = await fetch(`${API}/api/upload?path=${encodeURIComponent(currentPath)}`, { method: 'POST', body: formData });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      loadFiles();
      loadStats();
    } else {
      showToast(data.error || 'Upload failed', 'error');
    }
  } catch (err) {
    showToast('Upload failed', 'error');
  }

  fileInput.value = '';
  setTimeout(() => { modal.style.display = 'none'; list.innerHTML = ''; }, 1500);
}

async function createFolder() {
  const name = prompt('请输入文件夹名称:');
  if (!name) return;
  try {
    const res = await fetch(`${API}/api/folders?path=${encodeURIComponent(currentPath)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (data.success) {
      showToast('文件夹创建成功', 'success');
      loadFiles();
      loadStats();
    } else {
      showToast(data.error || '创建失败', 'error');
    }
  } catch (err) {
    showToast('创建失败', 'error');
  }
}

async function deleteItem(id, type) {
  if (!confirm(`确定要删除此${type === 'file' ? '文件' : '文件夹'}吗？`)) return;
  try {
    const res = await fetch(`${API}/api/delete`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, id })
    });
    const data = await res.json();
    if (data.success) {
      showToast('删除成功', 'success');
      loadFiles();
      loadStats();
    } else {
      showToast(data.error || '删除失败', 'error');
    }
  } catch (err) {
    showToast('删除失败', 'error');
  }
}

async function renameItem(id, type) {
  const newName = prompt('请输入新名称:');
  if (!newName) return;
  try {
    const res = await fetch(`${API}/api/rename`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, id, newName })
    });
    const data = await res.json();
    if (data.success) {
      showToast('重命名成功', 'success');
      loadFiles();
    } else {
      showToast(data.error || '重命名失败', 'error');
    }
  } catch (err) {
    showToast('重命名失败', 'error');
  }
}

async function previewFile(id, name) {
  const ext = name.split('.').pop().toLowerCase();
  const previewBody = document.getElementById('previewBody');
  const previewName = document.getElementById('previewName');
  const previewDownload = document.getElementById('previewDownload');

  previewName.textContent = name;
  previewDownload.href = `${API}/api/download/${id}`;

  const imgExts = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'];
  const textExts = ['txt', 'md', 'json', 'js', 'ts', 'py', 'java', 'c', 'cpp', 'go', 'rs', 'html', 'css', 'xml', 'yml', 'yaml', 'sh', 'rb', 'log', 'csv', 'tsv'];

  if (imgExts.includes(ext)) {
    previewBody.innerHTML = `<img src="${API}/uploads/${currentPath ? currentPath + '/' : ''}${name}" alt="${name}">`;
  } else if (textExts.includes(ext)) {
    try {
      const res = await fetch(`${API}/uploads/${currentPath ? currentPath + '/' : ''}${name}`);
      const text = await res.text();
      previewBody.innerHTML = `<pre class="preview-text">${escapeHtml(text)}</pre>`;
    } catch {
      previewBody.innerHTML = '<div class="no-preview"><i class="fas fa-exclamation-circle"></i><p>无法加载文件内容</p></div>';
    }
  } else {
    previewBody.innerHTML = '<div class="no-preview"><i class="fas fa-eye-slash"></i><p>此文件类型不支持预览</p><p style="margin-top:8px;font-size:12px">请下载后查看</p></div>';
  }

  document.getElementById('previewModal').style.display = 'flex';
}

function showContextMenu(e, id, type) {
  e.preventDefault();
  e.stopPropagation();
  document.querySelector('.context-menu')?.remove();

  const menu = document.createElement('div');
  menu.className = 'context-menu';
  menu.style.left = `${e.clientX}px`;
  menu.style.top = `${e.clientY}px`;

  const item = allItems.find(i => i.id === id);
  let html = '';
  if (type === 'folder') {
    html += `<div class="context-menu-item" onclick="navigateTo('${item.path}')"><i class="fas fa-folder-open"></i> 打开</div>`;
  } else {
    html += `<div class="context-menu-item" onclick="previewFile('${id}', '${item.name}')"><i class="fas fa-eye"></i> 预览</div>`;
    html += `<div class="context-menu-item" onclick="window.location='${API}/api/download/${id}'"><i class="fas fa-download"></i> 下载</div>`;
  }
  html += `<div class="context-menu-divider"></div>`;
  html += `<div class="context-menu-item" onclick="renameItem('${id}', '${type}')"><i class="fas fa-pen"></i> 重命名</div>`;
  html += `<div class="context-menu-item danger" onclick="deleteItem('${id}', '${type}')"><i class="fas fa-trash"></i> 删除</div>`;

  menu.innerHTML = html;
  document.body.appendChild(menu);

  // Adjust position if off-screen
  const rect = menu.getBoundingClientRect();
  if (rect.right > window.innerWidth) menu.style.left = `${window.innerWidth - rect.width - 5}px`;
  if (rect.bottom > window.innerHeight) menu.style.top = `${window.innerHeight - rect.height - 5}px`;
}

function setView(view) {
  currentView = view;
  renderFiles();
}

function formatSize(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (bytes >= 1024 && i < 3) { bytes /= 1024; i++; }
  return `${bytes.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icon = type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle';
  toast.innerHTML = `<i class="fas fa-${icon}"></i> ${message}`;
  toastContainer.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}
