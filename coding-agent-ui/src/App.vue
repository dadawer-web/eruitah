<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import { useAgentStore } from './stores/agent'
import FileTree from './components/FileTree.vue'
import ChatPanel from './components/ChatPanel.vue'
import CodeEditor from './components/CodeEditor.vue'
import TerminalPanel from './components/TerminalPanel.vue'

const store = useAgentStore()

onMounted(() => {
  store.connect()
  store.fetchFileTree()
})

onBeforeUnmount(() => {
  store.disconnect()
})
</script>

<template>
  <div class="w-screen h-screen flex bg-geek-bg overflow-hidden">
    <aside class="w-1/4 min-w-[250px] max-w-[400px] flex flex-col border-r border-geek-border">
      <div class="h-1/2 min-h-0 overflow-hidden">
        <FileTree />
      </div>
      <div class="h-1/2 min-h-0 overflow-hidden">
        <ChatPanel />
      </div>
    </aside>

    <main class="flex-1 flex flex-col min-w-0">
      <div class="h-[70%] min-h-0 overflow-hidden border-b border-geek-border">
        <CodeEditor />
      </div>
      <div class="h-[30%] min-h-0 overflow-hidden">
        <TerminalPanel />
      </div>
    </main>

    <div
      v-if="!store.connected"
      class="fixed top-3 left-3 px-3 py-1.5 bg-red-900/80 border border-red-500/50 rounded text-xs text-red-300 flex items-center gap-2 z-50"
    >
      <span class="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
      未连接
    </div>
    <div
      v-else-if="store.isRunning"
      class="fixed top-3 left-3 px-3 py-1.5 bg-yellow-900/80 border border-yellow-500/50 rounded text-xs text-yellow-300 flex items-center gap-2 z-50"
    >
      <span class="w-2 h-2 rounded-full bg-yellow-500 animate-pulse"></span>
      {{ store.status || '运行中' }}
      <span v-if="store.currentTool" class="ml-1 text-yellow-200">[{{ store.currentTool.name }}]</span>
    </div>
    <div
      v-else
      class="fixed top-3 left-3 px-3 py-1.5 bg-geek-surface border border-geek-accent/30 rounded text-xs text-geek-accent flex items-center gap-2 z-50"
    >
      <span class="w-2 h-2 rounded-full bg-geek-accent"></span>
      已连接
    </div>

    <Teleport to="body">
      <div
        v-if="store.pendingConfirmation"
        class="fixed inset-0 bg-black/70 flex items-center justify-center z-[100]"
      >
        <div class="bg-geek-surface border border-yellow-500/50 rounded-lg w-[450px] shadow-2xl">
          <div class="flex items-center gap-2 px-4 py-3 border-b border-geek-border bg-yellow-900/20">
            <span class="text-yellow-400 text-lg">⚠️</span>
            <span class="text-sm font-bold text-yellow-400">命令需要授权</span>
          </div>
          <div class="p-4">
            <div class="text-xs text-geek-text-dim mb-2">Agent 尝试执行以下命令：</div>
            <div class="bg-geek-bg border border-geek-border rounded p-3 mb-3">
              <code class="text-xs text-geek-accent break-all">{{ store.pendingConfirmation.command }}</code>
            </div>
            <div class="text-xs text-geek-text-dim mb-1">原因：</div>
            <div class="text-xs text-yellow-300 mb-4">{{ store.pendingConfirmation.reason }}</div>
            <div class="flex gap-2">
              <button
                @click="store.confirmCommand(false)"
                class="flex-1 px-4 py-2 bg-red-900/50 text-red-300 border border-red-500/30 rounded text-xs font-bold hover:bg-red-900/70 transition-colors"
              >
                拒绝执行
              </button>
              <button
                @click="store.confirmCommand(true)"
                class="flex-1 px-4 py-2 bg-geek-accent text-black rounded text-xs font-bold hover:bg-geek-accent-dim transition-colors"
              >
                授权执行
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
