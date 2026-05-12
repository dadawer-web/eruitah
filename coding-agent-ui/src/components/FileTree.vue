<script setup>
import { ref, computed, reactive } from 'vue'
import { useAgentStore } from '../stores/agent'
import DirPicker from './DirPicker.vue'

const store = useAgentStore()
const showDirPicker = ref(false)
const expandedMap = reactive({})

function isActiveFile(nodePath) {
  if (!store.activeContextFiles.length) return false
  return store.activeContextFiles.some(f => {
    if (f === nodePath) return true
    if (f.endsWith(nodePath)) return true
    if (nodePath.endsWith(f)) return true
    const normF = f.startsWith('/') ? f.slice(1) : f
    const normP = nodePath.startsWith('/') ? nodePath.slice(1) : nodePath
    return normF === normP
  })
}

const tree = computed(() => {
  const root = { name: '/', children: [], isDir: true }
  const files = store.files || []
  for (const file of files) {
    const parts = file.split('/').filter(Boolean)
    let node = root
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      const isFile = i === parts.length - 1
      let child = node.children.find(c => c.name === part)
      if (!child) {
        const nodePath = parts.slice(0, i + 1).join('/')
        child = {
          name: part,
          path: nodePath,
          isDir: !isFile,
          children: [],
          get expanded() {
            return !!expandedMap[nodePath]
          },
          set expanded(val) {
            expandedMap[nodePath] = val
          }
        }
        node.children.push(child)
      }
      node = child
    }
  }
  return root.children
})

function toggle(node) {
  node.expanded = !node.expanded
}

function openFile(node) {
  store.setCurrentItem(node.path, node.isDir)
  if (node.isDir) {
    toggle(node)
  }
}

function onDirSelect(path) {
  store.setBasePath(path)
}

function getFileIcon(node) {
  if (node.isDir) return node.expanded ? '📂' : '📁'
  const ext = node.name.split('.').pop()
  const iconMap = {
    js: '🟨', ts: '🔷', vue: '💚', py: '🐍', json: '📋',
    css: '🎨', html: '🌐', md: '📝', sh: '⚙️', yml: '⚙️',
    yaml: '⚙️', toml: '⚙️', rs: '🦀', go: '🔵', java: '☕',
    txt: '📄', log: '📋', xml: '📋', sql: '🗃️', env: '🔐',
    gitignore: '📝', dockerfile: '🐳', makefile: '⚙️',
  }
  return iconMap[ext.toLowerCase()] || '📄'
}

const flatTree = computed(() => {
  const result = []
  function flatten(nodes, depth = 0) {
    for (const node of nodes) {
      result.push({ node, depth })
      if (node.isDir && node.expanded && node.children.length) {
        flatten(node.children, depth + 1)
      }
    }
  }
  flatten(tree.value)
  return result
})
</script>

<template>
  <div class="h-full flex flex-col bg-geek-surface">
    <div class="px-3 py-2 text-xs font-bold text-geek-accent uppercase tracking-wider border-b border-geek-border flex items-center gap-2">
      <span>◈</span> Explorer
    </div>

    <div class="px-2 py-2 border-b border-geek-border">
      <div class="flex gap-1">
        <div
          class="flex-1 bg-geek-bg border border-geek-border rounded px-2 py-1 text-xs text-geek-text-dim truncate cursor-pointer hover:border-geek-accent transition-colors"
          @click="showDirPicker = true"
          title="点击选择目录"
        >
          {{ store.basePath || '点击选择工作目录' }}
        </div>
        <button
          @click="showDirPicker = true"
          class="px-2 py-1 bg-geek-accent/10 text-geek-accent border border-geek-accent/30 rounded text-xs hover:bg-geek-accent/20 transition-colors"
          title="浏览目录"
        >
          📂
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto px-1 py-1 text-xs">
      <div
        v-for="item in flatTree"
        :key="item.node.path"
        class="flex items-center gap-1.5 px-2 py-1 rounded cursor-pointer transition-all duration-200"
        :class="{
          'bg-geek-border': store.currentFile === item.node.path,
          'agent-active-file': isActiveFile(item.node.path) && store.currentFile !== item.node.path,
        }"
        :style="{ paddingLeft: `${8 + item.depth * 12}px` }"
        @click="openFile(item.node)"
      >
        <span v-if="isActiveFile(item.node.path) && !item.node.isDir" class="text-xs agent-eye">👁️</span>
        <span v-else class="text-xs">{{ getFileIcon(item.node) }}</span>
        <span
          class="truncate"
          :class="{
            'text-geek-text': item.node.isDir,
            'text-geek-text-dim': !item.node.isDir && !isActiveFile(item.node.path),
            'agent-active-filename': isActiveFile(item.node.path),
          }"
        >{{ item.node.name }}</span>
      </div>
      <div v-if="!flatTree.length" class="px-3 py-4 text-geek-text-dim text-xs italic text-center">
        <div v-if="store.basePath">空目录或路径不存在</div>
        <div v-else class="cursor-pointer hover:text-geek-accent" @click="showDirPicker = true">点击上方选择工作目录</div>
      </div>
    </div>

    <DirPicker
      :visible="showDirPicker"
      @close="showDirPicker = false"
      @select="onDirSelect"
    />
  </div>
</template>

<style scoped>
.agent-active-file {
  background: rgba(0, 255, 136, 0.06);
  border: 1px solid rgba(0, 255, 136, 0.15);
  box-shadow: 0 0 8px rgba(0, 255, 136, 0.08), inset 0 0 6px rgba(0, 255, 136, 0.04);
}

.agent-active-file:hover {
  background: rgba(0, 255, 136, 0.12);
  border-color: rgba(0, 255, 136, 0.3);
}

.agent-active-filename {
  color: #4ade80;
  font-weight: 600;
  text-shadow: 0 0 6px rgba(74, 222, 128, 0.3);
}

.agent-eye {
  animation: eye-pulse 2s ease-in-out infinite;
}

@keyframes eye-pulse {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.15); }
}
</style>
