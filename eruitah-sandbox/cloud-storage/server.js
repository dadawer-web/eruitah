const express = require('express');
const multer = require('multer');
const cors = require('cors');
const path = require('path');
const fs = require('fs-extra');
const mime = require('mime-types');

const app = express();
const PORT = 3000;
const UPLOADS_DIR = path.join(__dirname, 'uploads');
const DATA_FILE = path.join(__dirname, 'data.json');

// Ensure directories and data file exist
fs.ensureDirSync(UPLOADS_DIR);
if (!fs.existsSync(DATA_FILE)) {
  fs.writeJsonSync(DATA_FILE, { files: [], folders: [] });
}

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));
app.use('/uploads', express.static(UPLOADS_DIR));

// Multer config - simple storage
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const folderPath = req.query.path ? path.join(UPLOADS_DIR, req.query.path) : UPLOADS_DIR;
    fs.ensureDirSync(folderPath);
    cb(null, folderPath);
  },
  filename: (req, file, cb) => {
    cb(null, file.originalname);
  }
});
const upload = multer({ storage, limits: { fileSize: 500 * 1024 * 1024 } });

// Helper: get folder contents
function getFolderContents(folderPath = '') {
  const data = fs.readJsonSync(DATA_FILE);
  const prefix = folderPath ? folderPath + '/' : '';
  const depth = folderPath ? folderPath.split('/').length : 0;

  const folders = data.folders.filter(f => {
    if (folderPath === '') return f.path.split('/').length === 1;
    return f.path.startsWith(prefix) && f.path.split('/').length === depth + 1;
  }).map(f => ({ ...f, type: 'folder', name: f.name || f.path.split('/').pop() }));

  const files = data.files.filter(f => {
    if (folderPath === '') return !f.path.includes('/');
    return f.path.startsWith(prefix) && f.path.replace(prefix, '').split('/').length === 1;
  }).map(f => ({ ...f, type: 'file' }));

  return [...folders, ...files];
}

// API: List folder contents
app.get('/api/files', (req, res) => {
  try {
    const folderPath = req.query.path || '';
    const items = getFolderContents(folderPath);
    res.json({ success: true, items, currentPath: folderPath });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// API: Upload files
app.post('/api/upload', upload.array('files', 20), (req, res) => {
  try {
    const data = fs.readJsonSync(DATA_FILE);
    const results = [];
    
    for (const file of req.files) {
      const filePath = req.query.path ? `${req.query.path}/${file.originalname}` : file.originalname;
      const existing = data.files.findIndex(f => f.path === filePath);
      
      // Get actual file size from disk
      const fullPath = path.join(UPLOADS_DIR, filePath);
      const stats = fs.statSync(fullPath);
      
      if (existing !== -1) {
        data.files[existing].size = stats.size;
        data.files[existing].updatedAt = new Date().toISOString();
        results.push({ name: file.originalname, size: stats.size, path: filePath, updated: true });
      } else {
        data.files.push({
          id: Date.now().toString() + Math.random().toString(36).substr(2, 9),
          name: file.originalname,
          path: filePath,
          size: stats.size,
          mimeType: file.mimetype,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString()
        });
        results.push({ name: file.originalname, size: stats.size, path: filePath });
      }
    }
    
    fs.writeJsonSync(DATA_FILE, data, { spaces: 2 });
    res.json({ success: true, files: results, message: `${results.length} file(s) uploaded` });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// API: Create folder
app.post('/api/folders', (req, res) => {
  try {
    const { name } = req.body;
    const parentPath = req.query.path || '';
    const folderPath = parentPath ? `${parentPath}/${name}` : name;
    const data = fs.readJsonSync(DATA_FILE);
    if (data.folders.find(f => f.path === folderPath)) {
      return res.status(409).json({ success: false, error: 'Folder already exists' });
    }
    const newFolder = {
      id: Date.now().toString() + Math.random().toString(36).substr(2, 9),
      name,
      path: folderPath,
      createdAt: new Date().toISOString()
    };
    data.folders.push(newFolder);
    fs.writeJsonSync(DATA_FILE, data, { spaces: 2 });
    fs.ensureDirSync(path.join(UPLOADS_DIR, folderPath));
    res.json({ success: true, folder: newFolder });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// API: Download file
app.get('/api/download/:id', (req, res) => {
  try {
    const data = fs.readJsonSync(DATA_FILE);
    const file = data.files.find(f => f.id === req.params.id);
    if (!file) return res.status(404).json({ success: false, error: 'File not found' });
    const filePath = path.join(UPLOADS_DIR, file.path);
    if (!fs.existsSync(filePath)) return res.status(404).json({ success: false, error: 'File missing on disk' });
    res.setHeader('Content-Disposition', `attachment; filename="${encodeURIComponent(file.name)}"`);
    res.setHeader('Content-Type', file.mimeType || 'application/octet-stream');
    fs.createReadStream(filePath).pipe(res);
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// API: Delete file or folder
app.delete('/api/delete', (req, res) => {
  try {
    const { type, id } = req.body;
    const data = fs.readJsonSync(DATA_FILE);
    if (type === 'file') {
      const idx = data.files.findIndex(f => f.id === id);
      if (idx === -1) return res.status(404).json({ success: false, error: 'File not found' });
      const filePath = path.join(UPLOADS_DIR, data.files[idx].path);
      if (fs.existsSync(filePath)) fs.removeSync(filePath);
      data.files.splice(idx, 1);
    } else if (type === 'folder') {
      const idx = data.folders.findIndex(f => f.id === id);
      if (idx === -1) return res.status(404).json({ success: false, error: 'Folder not found' });
      const folderPath = data.folders[idx].path;
      const dirPath = path.join(UPLOADS_DIR, folderPath);
      if (fs.existsSync(dirPath)) fs.removeSync(dirPath);
      data.files = data.files.filter(f => !f.path.startsWith(folderPath + '/'));
      data.folders = data.folders.filter(f => !f.path.startsWith(folderPath + '/') && f.id !== id);
    }
    fs.writeJsonSync(DATA_FILE, data, { spaces: 2 });
    res.json({ success: true, message: `${type} deleted` });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// API: Rename file or folder
app.patch('/api/rename', (req, res) => {
  try {
    const { type, id, newName } = req.body;
    const data = fs.readJsonSync(DATA_FILE);
    if (type === 'file') {
      const file = data.files.find(f => f.id === id);
      if (!file) return res.status(404).json({ success: false, error: 'File not found' });
      const dir = path.dirname(file.path);
      const newPath = dir === '.' ? newName : `${dir}/${newName}`;
      const oldFull = path.join(UPLOADS_DIR, file.path);
      const newFull = path.join(UPLOADS_DIR, newPath);
      if (fs.existsSync(oldFull)) fs.renameSync(oldFull, newFull);
      file.name = newName;
      file.path = newPath;
      file.updatedAt = new Date().toISOString();
    } else if (type === 'folder') {
      const folder = data.folders.find(f => f.id === id);
      if (!folder) return res.status(404).json({ success: false, error: 'Folder not found' });
      const parentDir = path.dirname(folder.path);
      const newPath = parentDir === '.' ? newName : `${parentDir}/${newName}`;
      const oldFull = path.join(UPLOADS_DIR, folder.path);
      const newFull = path.join(UPLOADS_DIR, newPath);
      if (fs.existsSync(oldFull)) fs.renameSync(oldFull, newFull);
      const oldPrefix = folder.path;
      data.files = data.files.map(f => {
        if (f.path.startsWith(oldPrefix + '/')) {
          f.path = newPath + f.path.slice(oldPrefix.length);
        }
        return f;
      });
      data.folders = data.folders.map(f => {
        if (f.path.startsWith(oldPrefix + '/')) {
          f.path = newPath + f.path.slice(oldPrefix.length);
        }
        return f;
      });
      folder.name = newName;
      folder.path = newPath;
    }
    fs.writeJsonSync(DATA_FILE, data, { spaces: 2 });
    res.json({ success: true, message: `${type} renamed` });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// API: Storage stats
app.get('/api/stats', (req, res) => {
  try {
    const data = fs.readJsonSync(DATA_FILE);
    const totalSize = data.files.reduce((sum, f) => sum + (f.size || 0), 0);
    res.json({
      success: true,
      totalFiles: data.files.length,
      totalFolders: data.folders.length,
      totalSize,
      usedSpace: totalSize,
      maxSpace: 1024 * 1024 * 1024
    });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`Cloud Storage running at http://localhost:${PORT}`);
});
