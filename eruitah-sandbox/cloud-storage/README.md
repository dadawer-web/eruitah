# Cloud Storage

A simple, modern cloud storage web application built with Node.js, Express, and vanilla JavaScript.

## Features

- **File Management**: Upload, download, delete, and rename files
- **Folder Organization**: Create nested folders to organize your files
- **Drag & Drop**: Easy file upload with drag and drop support
- **File Preview**: Preview images and text files directly in the browser
- **Search**: Quickly find files with the search functionality
- **Responsive Design**: Works on desktop and mobile devices
- **Storage Stats**: Track your storage usage

## Tech Stack

- **Backend**: Node.js + Express
- **Frontend**: Vanilla JavaScript + CSS Grid
- **Storage**: Local filesystem with JSON metadata
- **Icons**: Font Awesome

## Installation

1. Install dependencies:
   ```bash
   npm install
   ```

2. Start the server:
   ```bash
   npm start
   ```

3. Open your browser and navigate to:
   ```
   http://localhost:3000
   ```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/files?path=` | List files in folder |
| POST | `/api/upload?path=` | Upload files |
| POST | `/api/folders?path=` | Create folder |
| GET | `/api/download/:id` | Download file |
| DELETE | `/api/delete` | Delete file/folder |
| PATCH | `/api/rename` | Rename file/folder |
| GET | `/api/stats` | Get storage statistics |

## File Structure

```
cloud-storage/
├── server.js          # Express server and API
├── package.json       # Dependencies
├── data.json          # File metadata storage
├── uploads/           # Uploaded files
└── public/
    ├── index.html     # Main HTML
    ├── style.css      # Styles
    └── app.js         # Frontend logic
```

## Usage

1. **Upload Files**: Click the "Upload" button or drag files into the browser
2. **Create Folders**: Click "New Folder" to organize your files
3. **Navigate**: Double-click folders to open them, use breadcrumbs to go back
4. **Preview**: Click the eye icon to preview supported file types
5. **Manage**: Right-click or hover for rename/delete options

## License

MIT
