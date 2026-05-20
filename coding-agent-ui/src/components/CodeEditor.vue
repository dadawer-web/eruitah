<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useAgentStore } from '../stores/agent'

const store = useAgentStore()
const editorContainer = ref(null)
let editor = null
let monacoInstance = null

function getLanguage(filename) {
  if (!filename) return 'plaintext'
  const ext = filename.split('.').pop().toLowerCase()
  const langMap = {
    js: 'javascript', jsx: 'javascript', ts: 'typescript', tsx: 'typescript',
    vue: 'html', py: 'python', rs: 'rust', go: 'go', java: 'java',
    html: 'html', css: 'css', scss: 'scss', less: 'less',
    json: 'json', yml: 'yaml', yaml: 'yaml', toml: 'ini',
    md: 'markdown', sh: 'shell', bash: 'shell', sql: 'sql',
    xml: 'xml', svg: 'xml', c: 'c', cpp: 'cpp', h: 'c',
  }
  return langMap[ext] || 'plaintext'
}

function getRunCommand(filename) {
  if (!filename) return null
  const ext = filename.split('.').pop().toLowerCase()
  const cmdMap = {
    py: 'python3',
    js: 'node',
    ts: 'npx ts-node',
    sh: 'bash',
    bash: 'bash',
    rb: 'ruby',
    go: 'go run',
    rs: 'cargo run',
    java: 'java',
    c: 'gcc -o main && ./main',
    cpp: 'g++ -o main && ./main',
  }
  return cmdMap[ext] ? `${cmdMap[ext]} ${filename}` : null
}

function handleRunCode() {
  if (!store.currentFile) {
    window.__xterm_write?.('\r\n\x1b[31m[错误] 请先打开一个文件\x1b[0m\r\n')
    return
  }

  const cmd = getRunCommand(store.currentFile)
  if (!cmd) {
    window.__xterm_write?.(`\r\n\x1b[31m[错误] 未知文件类型，无法运行: ${store.currentFile}\x1b[0m\r\n`)
    return
  }

  if (!store.ws || store.ws.readyState !== WebSocket.OPEN) {
    window.__xterm_write?.('\r\n\x1b[31m[错误] WebSocket 未连接，无法运行！\x1b[0m\r\n')
    return
  }

  window.__xterm_write?.('\r\n\x1b[33m[系统提示] 正在执行命令...\x1b[0m\r\n')
  window.__xterm_write?.(`\x1b[36m$ ${cmd}\x1b[0m\r\n`)

  store.ws.send(JSON.stringify({
    task: cmd,
    work_dir: store.basePath,
    max_turns: 1,
  }))
}

onMounted(async () => {
  const monaco = await import('monaco-editor')
  monacoInstance = monaco

  if (!editorContainer.value) {
    console.error('[CodeEditor] editorContainer ref is null, skipping editor creation')
    return
  }

  self.MonacoEnvironment = {
    getWorkerUrl: function (moduleId, label) {
      return `data:text/javascript;charset=utf-8,${encodeURIComponent(`
        self.MonacoEnvironment = { baseUrl: '/' };
        importScripts('https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs/base/worker/workerMain.js');
      `)}`
    }
  }

  monaco.editor.defineTheme('geek-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '6A9955', fontStyle: 'italic' },
      { token: 'keyword', foreground: '00FF88' },
      { token: 'string', foreground: 'CE9178' },
      { token: 'number', foreground: 'B5CEA8' },
      { token: 'type', foreground: '4EC9B0' },
    ],
    colors: {
      'editor.background': '#0a0a0a',
      'editor.foreground': '#d4d4d4',
      'editor.lineHighlightBackground': '#1a1a1a',
      'editor.selectionBackground': '#264f78',
      'editorCursor.foreground': '#00ff88',
      'editorLineNumber.foreground': '#333333',
      'editorLineNumber.activeForeground': '#00ff88',
      'editor.inactiveSelectionBackground': '#1a1a1a',
      'editorIndentGuide.background': '#1a1a1a',
      'editorIndentGuide.activeBackground': '#2a2a2a',
    },
  })

  try {
    editor = monaco.editor.create(editorContainer.value, {
      value: store.currentCode || '// Waiting for agent...\n',
      language: getLanguage(store.currentFile),
      theme: 'geek-dark',
      fontSize: 13,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace",
      fontLigatures: true,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      smoothScrolling: true,
      cursorBlinking: 'smooth',
      cursorSmoothCaretAnimation: 'on',
      renderLineHighlight: 'all',
      padding: { top: 8 },
      automaticLayout: true,
      wordWrap: 'on',
      tabSize: 2,
      bracketPairColorization: { enabled: true },
      guides: { bracketPairs: true, indentation: true },
    })

    store.registerEditor(editor)
  } catch (e) {
    console.error('[CodeEditor] Failed to create Monaco editor:', e)
  }
})

watch(() => store.currentFile, (newFile) => {
  if (editor && monacoInstance && newFile) {
    const model = editor.getModel()
    if (model) {
      monacoInstance.editor.setModelLanguage(model, getLanguage(newFile))
    }
  }
})

function updateMarkers() {
  if (!editor || !monacoInstance) return
  const model = editor.getModel()
  if (!model) return

  const diags = store.diagnostics
  if (!diags || diags.length === 0) {
    monacoInstance.editor.setModelMarkers(model, 'lsp', [])
    return
  }

  const currentFilePath = store.currentFile
  const basePath = store.basePath || ''

  const markers = []
  for (const d of diags) {
    let matchesCurrentFile = false
    if (d.file) {
      const diagFile = d.file.replace(/\\/g, '/')
      const normalizedCurrent = (basePath + '/' + currentFilePath).replace(/\\/g, '/')
      const normalizedCurrent2 = currentFilePath.replace(/\\/g, '/')
      if (diagFile.endsWith(normalizedCurrent) || diagFile.endsWith(normalizedCurrent2) || diagFile === normalizedCurrent) {
        matchesCurrentFile = true
      }
    } else {
      matchesCurrentFile = true
    }

    if (!matchesCurrentFile) continue

    let severity = monacoInstance.MarkerSeverity.Info
    if (d.severity === 'error') severity = monacoInstance.MarkerSeverity.Error
    else if (d.severity === 'warning') severity = monacoInstance.MarkerSeverity.Warning

    markers.push({
      startLineNumber: d.line || 1,
      startColumn: d.column || 1,
      endLineNumber: d.endLine || d.line || 1,
      endColumn: d.endColumn || (d.column || 1) + 10,
      message: d.message || '',
      severity: severity,
      source: 'LSP',
    })
  }

  monacoInstance.editor.setModelMarkers(model, 'lsp', markers)
}

watch(() => store.diagnostics, () => {
  nextTick(() => updateMarkers())
}, { deep: true })

watch(() => store.currentFile, () => {
  nextTick(() => updateMarkers())
})

onBeforeUnmount(() => {
  store.unregisterEditor()
  if (editor) {
    editor.dispose()
    editor = null
  }
})

watch(() => store.activeMermaidIdx, (val) => {
  if (val < 0 && editor) {
    nextTick(() => {
      editor.layout()
    })
  }
})
</script>

<template>
  <div class="h-full w-full flex flex-col bg-geek-bg">
    <!-- Tab 栏 -->
    <div class="flex items-center bg-[#1e1e1e] border-b border-gray-700 overflow-x-auto shrink-0 shadow-sm z-10 relative font-mono">
      <div class="flex items-center min-w-0 flex-1">
        <button
          v-for="(file, fidx) in store.openFiles"
          :key="'f'+fidx"
          @click="store.switchToFile(fidx); store.closeMermaidView()"
          class="flex items-center gap-1.5 px-3 py-1.5 text-xs border-b-2 transition-colors whitespace-nowrap text-gray-300"
          :class="store.activeMermaidIdx < 0 && store.activeFileIdx === fidx
            ? 'border-blue-500 text-blue-400 bg-[#252526]'
            : 'border-transparent text-gray-500 hover:text-gray-300'"
        >
          <span class="text-blue-400">📄</span>
          <span>{{ file.path?.split('/').pop() || file.path }}</span>
          <span
            @click.stop="store.closeFile(fidx)"
            class="ml-1 text-gray-600 hover:text-red-400 transition-colors text-[10px] cursor-pointer"
          >✕</span>
        </button>
        <button
          v-for="(diag, idx) in store.mermaidDiagrams"
          :key="'m'+idx"
          @click="store.activeMermaidIdx = idx"
          class="flex items-center gap-1.5 px-3 py-1.5 text-xs border-b-2 transition-colors whitespace-nowrap text-gray-300"
          :class="store.activeMermaidIdx === idx
            ? 'border-violet-500 text-violet-400 bg-[#252526]'
            : 'border-transparent text-gray-500 hover:text-gray-300'"
        >
          <span>📊</span>
          <span>{{ diag.title }}</span>
          <span
            @click.stop="store.removeMermaidDiagram(idx)"
            class="ml-1 text-gray-600 hover:text-red-400 transition-colors text-[10px] cursor-pointer"
          >✕</span>
        </button>
      </div>
      <div class="flex items-center gap-2 px-2 shrink-0">
        <span v-if="store.diagnostics && store.diagnostics.length > 0" class="text-[10px] px-1.5 py-0.5 rounded-full bg-red-900/30 text-red-400 border border-red-800/50">
          {{ store.diagnostics.filter(d => d.severity === 'error').length }} 错误
        </span>
        <button
          @click="handleRunCode"
          :disabled="!store.currentFile || !store.connected"
          class="px-3 py-1 bg-green-700/80 hover:bg-green-600 text-green-100 rounded text-xs font-bold transition-colors flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
          title="运行当前文件"
        >
          <span>▶</span>
          <span>运行</span>
        </button>
      </div>
    </div>
    <!-- 编辑器 / Mermaid 预览 -->
    <div v-show="store.activeMermaidIdx >= 0 && store.mermaidDiagrams[store.activeMermaidIdx]" class="flex-1 min-h-0 overflow-auto bg-gradient-to-br from-[#0f172a] to-[#1e1b4b] p-6">
      <div class="mermaid-editor-view" v-html="store.mermaidDiagrams[store.activeMermaidIdx]?.svg || ''"></div>
    </div>
    <div v-show="store.activeMermaidIdx < 0" ref="editorContainer" class="flex-1 min-h-0"></div>
  </div>
</template>
