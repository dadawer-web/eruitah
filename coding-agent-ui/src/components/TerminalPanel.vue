<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { useAgentStore } from '../stores/agent'

const store = useAgentStore()
let terminalIdCounter = 0

const terminals = ref([])
const activeTerminalId = ref(null)
const terminalRefs = ref({})

function createTerminal() {
  terminalIdCounter++
  const id = terminalIdCounter
  const terminal = {
    id,
    name: `终端 ${id}`,
    ws: null,
    connected: false,
    instance: null,
    fitAddon: null,
  }
  terminals.value.push(terminal)
  activeTerminalId.value = id
  
  nextTick(() => {
    initTerminalInstance(id)
  })
  
  return id
}

function initTerminalInstance(id) {
  const term = terminals.value.find(t => t.id === id)
  if (!term) return
  
  const container = terminalRefs.value[id]
  if (!container) return

  try {
    term.instance = new Terminal({
      theme: {
        background: '#0a0a0a',
        foreground: '#d4d4d4',
        cursor: '#00ff88',
        cursorAccent: '#0a0a0a',
        selectionBackground: '#264f78',
        black: '#0a0a0a',
        red: '#ff5555',
        green: '#00ff88',
        yellow: '#f1fa8c',
        blue: '#6272a4',
        magenta: '#ff79c6',
        cyan: '#8be9fd',
        white: '#d4d4d4',
        brightBlack: '#555555',
        brightRed: '#ff6e6e',
        brightGreen: '#69ff94',
        brightYellow: '#ffffa5',
        brightBlue: '#d6acff',
        brightMagenta: '#ff92df',
        brightCyan: '#a4ffff',
        brightWhite: '#ffffff',
      },
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace",
      fontSize: 12,
      lineHeight: 1.3,
      cursorBlink: true,
      cursorStyle: 'bar',
      scrollback: 10000,
      allowTransparency: true,
      convertEol: true,
    })

    term.fitAddon = new FitAddon()
    term.instance.loadAddon(term.fitAddon)
    term.instance.open(container)
    
    try {
      term.fitAddon.fit()
    } catch (e) {}

    term.instance.onData((data) => {
      if (term.ws && term.ws.readyState === WebSocket.OPEN) {
        term.ws.send(JSON.stringify({ type: 'input', data }))
      }
    })

    term.instance.onResize(({ cols, rows }) => {
      if (term.ws && term.ws.readyState === WebSocket.OPEN) {
        term.ws.send(JSON.stringify({ type: 'resize', cols, rows }))
      }
    })

    term.instance.writeln('\x1b[32m◈ Coding Agent Terminal\x1b[0m')
    term.instance.writeln('\x1b[90m点击"连接"按钮开始交互式会话...\x1b[0m')
    term.instance.writeln('')
  } catch (e) {
    console.error('Failed to initialize terminal:', e)
  }
}

function connectTerminal(id) {
  const term = terminals.value.find(t => t.id === id)
  if (!term || !term.instance) return
  
  if (term.ws && term.ws.readyState === WebSocket.OPEN) {
    return
  }

  const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  term.ws = new WebSocket(`${wsProto}//${location.host}/ws/terminal`)

  term.ws.onopen = () => {
    term.connected = true
    term.instance.writeln(`\x1b[33m[系统] 正在启动 ${term.name}...\x1b[0m`)
    
    term.ws.send(JSON.stringify({
      type: 'start',
      work_dir: store.basePath,
      cols: term.instance.cols,
      rows: term.instance.rows,
    }))
  }

  term.ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'output') {
        term.instance.write(data.data)
      } else if (data.type === 'started') {
        term.instance.writeln(`\x1b[32m[系统] ${term.name} 已启动 (PID: ${data.data.pid})\x1b[0m`)
        term.instance.writeln('')
      } else if (data.type === 'error') {
        term.instance.writeln(`\x1b[31m[错误] ${data.data}\x1b[0m`)
      }
    } catch (e) {
      term.instance.write(event.data)
    }
  }

  term.ws.onclose = () => {
    term.connected = false
    term.instance.writeln('\r\n\x1b[33m[系统] 终端连接已断开\x1b[0m')
  }

  term.ws.onerror = () => {
    term.connected = false
    term.instance.writeln('\r\n\x1b[31m[错误] 终端连接失败\x1b[0m')
  }
}

function disconnectTerminal(id) {
  const term = terminals.value.find(t => t.id === id)
  if (!term || !term.ws) return
  
  term.ws.close()
  term.ws = null
  term.connected = false
  term.instance.writeln('\r\n\x1b[33m[系统] 已断开终端连接\x1b[0m')
}

function clearTerminal(id) {
  const term = terminals.value.find(t => t.id === id)
  if (term && term.instance) {
    term.instance.clear()
  }
}

function closeTerminal(id) {
  const index = terminals.value.findIndex(t => t.id === id)
  if (index === -1) return
  
  const term = terminals.value[index]
  
  if (term.ws) {
    term.ws.close()
    term.ws = null
  }
  
  if (term.instance) {
    try {
      term.instance.dispose()
    } catch (e) {
      console.warn('Dispose terminal error:', e)
    }
    term.instance = null
  }
  
  term.fitAddon = null
  term.connected = false
  
  if (terminals.value.length === 1) {
    return
  }
  
  terminals.value.splice(index, 1)
  
  if (activeTerminalId.value === id) {
    activeTerminalId.value = terminals.value[0].id
  }
}

function switchTerminal(id) {
  activeTerminalId.value = id
  nextTick(() => {
    const term = terminals.value.find(t => t.id === id)
    if (term && term.fitAddon) {
      try {
        term.fitAddon.fit()
      } catch (e) {}
    }
  })
}

function getActiveTerminal() {
  return terminals.value.find(t => t.id === activeTerminalId.value)
}

onMounted(() => {
  createTerminal()
  
  window.__xterm_write = (data) => {
    const term = getActiveTerminal()
    if (term && term.instance) {
      term.instance.write(data)
    }
  }

  window.__xterm_clear = () => {
    const term = getActiveTerminal()
    if (term && term.instance) {
      term.instance.clear()
    }
  }
})

watch(() => store.basePath, () => {
  terminals.value.forEach(term => {
    if (term.connected && term.ws) {
      term.ws.close()
      term.ws = null
      term.connected = false
      if (term.instance) {
        term.instance.writeln('\x1b[33m[系统] 工作目录已更改，请重新连接终端\x1b[0m')
      }
    }
  })
})

onBeforeUnmount(() => {
  window.__xterm_write = undefined
  window.__xterm_clear = undefined
  terminals.value.forEach(term => {
    if (term.ws) {
      term.ws.close()
      term.ws = null
    }
    if (term.instance) {
      try {
        term.instance.dispose()
      } catch (e) {
        // ignore dispose errors
      }
      term.instance = null
    }
    term.fitAddon = null
  })
  terminals.value = []
})
</script>

<template>
  <div class="h-full w-full flex flex-col bg-geek-bg">
    <div class="flex flex-col bg-geek-surface border-b border-geek-border">
      <div class="flex items-center px-2 py-1 gap-1 overflow-x-auto">
        <div
          v-for="term in terminals"
          :key="term.id"
          @click="switchTerminal(term.id)"
          class="flex items-center gap-1 px-2 py-1 rounded text-xs cursor-pointer transition-colors whitespace-nowrap"
          :class="activeTerminalId === term.id 
            ? 'bg-geek-accent/20 text-geek-accent border border-geek-accent/30' 
            : 'bg-geek-bg text-geek-text-dim hover:bg-geek-border border border-transparent'"
        >
          <span class="w-1.5 h-1.5 rounded-full" :class="term.connected ? 'bg-green-400' : 'bg-gray-500'"></span>
          <span>{{ term.name }}</span>
          <button
            v-if="terminals.length > 1"
            @click.stop="closeTerminal(term.id)"
            class="ml-1 text-geek-text-dim hover:text-red-400 transition-colors"
          >×</button>
        </div>
        <button
          @click="createTerminal"
          class="px-2 py-1 text-geek-text-dim hover:text-geek-accent text-xs transition-colors"
          title="新建终端"
        >+</button>
      </div>
      
      <div class="flex items-center justify-between px-3 py-1">
        <div class="flex items-center gap-2">
          <span class="text-geek-text-dim text-xs">{{ store.basePath }}</span>
        </div>
        <div class="flex items-center gap-1">
          <template v-if="getActiveTerminal()?.connected">
            <button
              @click="disconnectTerminal(activeTerminalId)"
              class="px-2 py-0.5 bg-red-600/80 hover:bg-red-600 text-white rounded text-[10px] font-bold transition-colors"
              title="断开连接"
            >
              断开
            </button>
          </template>
          <template v-else>
            <button
              @click="connectTerminal(activeTerminalId)"
              class="px-2 py-0.5 bg-green-600/80 hover:bg-green-600 text-white rounded text-[10px] font-bold transition-colors"
              title="连接终端"
            >
              连接
            </button>
          </template>
          <button
            @click="clearTerminal(activeTerminalId)"
            class="px-2 py-0.5 bg-geek-border hover:bg-geek-accent/20 text-geek-text-dim hover:text-geek-accent rounded text-[10px] transition-colors"
            title="清屏"
          >
            清屏
          </button>
        </div>
      </div>
    </div>
    
    <div class="flex-1 min-h-0 relative">
      <div
        v-for="term in terminals"
        :key="term.id"
        :ref="el => terminalRefs[term.id] = el"
        class="absolute inset-0 p-1"
        :class="activeTerminalId === term.id ? 'block' : 'hidden'"
      ></div>
    </div>
  </div>
</template>
