<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import { useAgentStore } from './stores/agent'
import FileTree from './components/FileTree.vue'
import ChatPanel from './components/ChatPanel.vue'
import CodeEditor from './components/CodeEditor.vue'
import TerminalPanel from './components/TerminalPanel.vue'
import ToolBar from './components/ToolBar.vue'
import TaskList from './components/TaskList.vue'
import PixelPet from './components/PixelPet.vue'

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
  <div class="w-screen h-screen flex flex-col bg-geek-bg overflow-hidden">
    <ToolBar />

    <div class="flex-1 flex min-h-0">
      <aside class="w-1/4 min-w-[250px] max-w-[400px] flex flex-col border-r border-geek-border">
        <div class="h-1/3 min-h-0 overflow-hidden">
          <TaskList />
        </div>
        <div class="h-1/3 min-h-0 overflow-hidden border-t border-geek-border">
          <FileTree />
        </div>
        <div class="h-1/3 min-h-0 overflow-hidden border-t border-geek-border">
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
    </div>

    <Teleport to="body">
      <div
        v-if="store.pendingConfirmation"
        class="fixed inset-0 bg-black/70 flex items-center justify-center z-[100]"
      >
        <div class="bg-geek-surface border border-yellow-500/50 rounded-lg w-[450px] max-h-[90vh] flex flex-col shadow-2xl">
          <div class="flex items-center gap-2 px-4 py-3 border-b border-geek-border bg-yellow-900/20 shrink-0">
            <span class="text-yellow-400 text-lg">⚠️</span>
            <span class="text-sm font-bold text-yellow-400">命令需要授权</span>
          </div>
          <div class="p-4 overflow-y-auto">
            <div class="text-xs text-geek-text-dim mb-2">Agent 尝试执行以下命令：</div>
            <div class="bg-geek-bg border border-geek-border rounded p-3 mb-3 max-h-[40vh] overflow-y-auto">
              <code class="text-xs text-geek-accent break-all whitespace-pre-wrap">{{ store.pendingConfirmation.command }}</code>
            </div>
            <div class="text-xs text-geek-text-dim mb-1">原因：</div>
            <div class="text-xs text-yellow-300 mb-4">{{ store.pendingConfirmation.reason }}</div>
            <div class="flex gap-2 sticky bottom-0">
              <button
                @click="store.confirmCommand(false)"
                class="flex-1 px-4 py-2 bg-red-900/50 text-red-300 border border-red-500/30 rounded text-xs font-bold hover:bg-red-900/70 transition-colors"
              >拒绝执行</button>
              <button
                @click="store.confirmCommand(true)"
                class="flex-1 px-4 py-2 bg-geek-accent text-black rounded text-xs font-bold hover:bg-geek-accent-dim transition-colors"
              >授权执行</button>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="store.contextCompact"
        class="fixed top-14 right-4 px-4 py-3 bg-cyan-900/80 border border-cyan-500/50 rounded-lg text-xs text-cyan-300 z-50 max-w-[350px] shadow-xl"
      >
        <div class="font-bold mb-1">🧠 上下文已压缩</div>
        <div class="text-cyan-200/80">{{ store.contextCompact.reason }}</div>
        <div class="text-cyan-200/60 mt-1">剩余消息: {{ store.contextCompact.remaining_messages }} 条</div>
      </div>
    </Teleport>

    <PixelPet />
  </div>
</template>
