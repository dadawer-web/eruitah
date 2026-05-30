<script setup>
import { onMounted, onBeforeUnmount, computed, ref, watch } from 'vue'
import { useAgentStore } from './stores/agent'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import FileTree from './components/FileTree.vue'
import ChatPanel from './components/ChatPanel.vue'
import CodeEditor from './components/CodeEditor.vue'
import TerminalPanel from './components/TerminalPanel.vue'
import ToolBar from './components/ToolBar.vue'
import TaskList from './components/TaskList.vue'
import PixelPet from './components/PixelPet.vue'

const store = useAgentStore()

const sidebarCollapsed = ref(false)
const terminalCollapsed = ref(false)
const mermaidLightbox = ref(null)

const isVisualMode = computed(() => {
  return store.selectedSkills?.includes('visual') || false
})

watch(isVisualMode, (val) => {
  if (val) {
    sidebarCollapsed.value = true
    terminalCollapsed.value = true
  }
})

const wcStatusLabel = computed(() => {
  const map = {
    idle: '',
    booting: '启动中...',
    mounting: '挂载文件...',
    installing: 'npm install...',
    starting: '启动开发服务器...',
    running: '运行中',
    error: '错误',
  }
  return map[store.wcStatus] || store.wcStatus
})

const wcStatusColor = computed(() => {
  const map = {
    idle: 'text-geek-text-dim',
    booting: 'text-yellow-400',
    mounting: 'text-cyan-400',
    installing: 'text-blue-400',
    starting: 'text-purple-400',
    running: 'text-green-400',
    error: 'text-red-400',
  }
  return map[store.wcStatus] || 'text-geek-text-dim'
})

function openMermaidLightbox(svg, title) {
  mermaidLightbox.value = { svg, title: title || 'Diagram', scale: 1 }
}

function closeMermaidLightbox() {
  mermaidLightbox.value = null
}

function zoomLightbox(delta) {
  if (!mermaidLightbox.value) return
  const next = mermaidLightbox.value.scale + delta
  mermaidLightbox.value.scale = Math.max(0.2, Math.min(5, next))
}

function handleLightboxWheel(e) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  zoomLightbox(delta)
}

onMounted(() => {
  store.connect()
  store.fetchFileTree()
  store.fetchTaskRegistry()
  window.__open_mermaid_lightbox = openMermaidLightbox
  window.__add_mermaid_tab = (title, svg) => store.addMermaidDiagram(title, svg)
})

onBeforeUnmount(() => {
  store.disconnect()
  store.resetWebContainer()
  delete window.__open_mermaid_lightbox
  delete window.__add_mermaid_tab
})
</script>

<template>
  <div class="w-screen h-screen flex flex-col bg-geek-bg overflow-hidden">
    <ToolBar />

    <div class="flex-1 flex min-h-0">
      <Splitpanes class="default-theme" @resized="() => {}">
        <!-- ═══ 左侧边栏 ═══ -->
        <Pane
          v-if="!sidebarCollapsed"
          :size="25"
          :min-size="15"
          :max-size="40"
        >
          <div class="h-full flex flex-col bg-geek-bg">
            <div class="h-1/3 min-h-0 overflow-hidden">
              <TaskList />
            </div>
            <div class="h-1/3 min-h-0 overflow-hidden border-t border-geek-border">
              <FileTree />
            </div>
            <div class="h-1/3 min-h-0 overflow-hidden border-t border-geek-border">
              <ChatPanel />
            </div>
          </div>
        </Pane>

        <!-- ═══ 主工作区 ═══ -->
        <Pane :size="sidebarCollapsed ? 100 : 75">
          <div class="h-full flex flex-col bg-geek-bg">
            <Splitpanes horizontal class="default-theme">
              <!-- 编辑器区域 -->
              <Pane
                :size="terminalCollapsed ? 100 : 70"
                :min-size="30"
              >
                <div class="h-full flex min-h-0">
                  <Splitpanes class="default-theme">
                    <Pane
                      :size="store.wcShowPreview ? 50 : 100"
                      :min-size="30"
                    >
                      <div class="h-full flex flex-col min-w-0">
                        <div class="flex items-center gap-1 px-2 py-1 border-b border-gray-700 bg-[#1e1e1e] shrink-0">
                          <button
                            @click="sidebarCollapsed = !sidebarCollapsed"
                            class="px-1.5 py-0.5 text-[10px] text-gray-500 hover:text-blue-400 transition-colors rounded"
                            :title="sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'"
                          >{{ sidebarCollapsed ? '◧' : '◨' }}</button>
                          <button
                            @click="terminalCollapsed = !terminalCollapsed"
                            class="px-1.5 py-0.5 text-[10px] text-gray-500 hover:text-blue-400 transition-colors rounded"
                            :title="terminalCollapsed ? '展开终端' : '折叠终端'"
                          >{{ terminalCollapsed ? '⬒' : '⬓' }}</button>
                          <span class="text-[9px] text-gray-600 ml-auto">编辑器</span>
                        </div>
                        <div class="flex-1 min-h-0 overflow-hidden">
                          <CodeEditor />
                        </div>
                      </div>
                    </Pane>

                    <Pane
                      v-if="store.wcShowPreview"
                      :size="50"
                      :min-size="20"
                    >
                      <div class="h-full flex flex-col min-w-0 bg-geek-bg">
                        <div class="flex items-center justify-between px-3 py-1.5 border-b border-geek-border bg-geek-surface shrink-0">
                          <div class="flex items-center gap-2">
                            <span class="text-xs font-bold text-geek-accent">🌐 实时预览</span>
                            <span
                              v-if="wcStatusLabel"
                              class="text-[10px] px-1.5 py-0.5 rounded bg-geek-bg border border-geek-border"
                              :class="wcStatusColor"
                            >{{ wcStatusLabel }}</span>
                          </div>
                          <div class="flex items-center gap-1">
                            <button
                              v-if="store.wcPreviewUrl"
                              @click="navigator.clipboard?.writeText(store.wcPreviewUrl)"
                              class="px-1.5 py-0.5 text-[10px] text-geek-text-dim hover:text-geek-accent transition-colors"
                              title="复制预览 URL"
                            >📋</button>
                            <button
                              @click="store.stopWebContainer()"
                              class="px-1.5 py-0.5 text-[10px] text-red-400 hover:text-red-300 transition-colors"
                              title="停止服务"
                            >⏹</button>
                            <button
                              @click="store.closeWebContainerPreview()"
                              class="px-1.5 py-0.5 text-[10px] text-geek-text-dim hover:text-geek-accent transition-colors"
                              title="关闭预览"
                            >✕</button>
                          </div>
                        </div>

                        <div class="flex-1 min-h-0 relative">
                          <div
                            v-if="store.wcStatus !== 'running' && store.wcStatus !== 'error'"
                            class="absolute inset-0 flex items-center justify-center bg-geek-bg/80 z-10"
                          >
                            <div class="text-center">
                              <div class="text-2xl mb-2">
                                <span v-if="store.wcStatus === 'booting'">🚀</span>
                                <span v-else-if="store.wcStatus === 'mounting'">📁</span>
                                <span v-else-if="store.wcStatus === 'installing'">📦</span>
                                <span v-else-if="store.wcStatus === 'starting'">🏃</span>
                                <span v-else>⏳</span>
                              </div>
                              <div class="text-xs text-geek-text-dim">{{ wcStatusLabel }}</div>
                            </div>
                          </div>

                          <div
                            v-if="store.wcError"
                            class="absolute inset-0 flex items-center justify-center bg-geek-bg/90 z-10"
                          >
                            <div class="text-center max-w-[80%]">
                              <div class="text-2xl mb-2">❌</div>
                              <div class="text-xs text-red-400 mb-2">WebContainer 启动失败</div>
                              <div class="text-[10px] text-geek-text-dim break-all">{{ store.wcError }}</div>
                              <button
                                @click="store.resetWebContainer()"
                                class="mt-3 px-3 py-1 bg-geek-accent text-black rounded text-[10px] font-bold hover:bg-geek-accent-dim transition-colors"
                              >重试</button>
                            </div>
                          </div>

                          <iframe
                            v-if="store.wcPreviewUrl"
                            :src="store.wcPreviewUrl"
                            class="w-full h-full border-0 bg-white"
                            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-downloads"
                            allow="cross-origin-isolated"
                          ></iframe>

                          <div
                            v-if="!store.wcPreviewUrl && store.wcStatus === 'running'"
                            class="absolute inset-0 flex items-center justify-center"
                          >
                            <div class="text-xs text-geek-text-dim">等待 server-ready 事件...</div>
                          </div>
                        </div>
                      </div>
                    </Pane>
                  </Splitpanes>
                </div>
              </Pane>

              <!-- 终端区域 -->
              <Pane
                v-if="!terminalCollapsed"
                :size="30"
                :min-size="10"
              >
                <div class="h-full overflow-hidden">
                  <TerminalPanel />
                </div>
              </Pane>
            </Splitpanes>
          </div>
        </Pane>
      </Splitpanes>
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

      <div
        v-if="store.systemAlerts.length > 0"
        class="fixed top-14 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2 items-center"
      >
        <div
          v-for="(alert, idx) in store.systemAlerts.slice(-3)"
          :key="alert.timestamp + idx"
          class="px-4 py-2 bg-amber-900/90 border border-amber-500/50 rounded-lg text-xs text-amber-300 shadow-xl max-w-[500px] animate-pulse"
        >
          🛡️ {{ alert.content }}
        </div>
      </div>

      <div
        v-if="store.agentState && store.isRunning"
        class="fixed bottom-24 right-5 px-3 py-2 bg-geek-surface/95 border border-geek-border rounded-lg text-xs z-50 max-w-[280px] shadow-xl backdrop-blur-sm"
      >
        <div class="flex items-center gap-2 mb-1">
          <span v-if="store.agentState.status === 'thinking'" class="text-blue-400">🤔</span>
          <span v-else-if="store.agentState.status === 'searching'" class="text-cyan-400">🔍</span>
          <span v-else class="text-geek-accent">◈</span>
          <span class="text-geek-text-dim font-bold">{{ store.agentState.status === 'thinking' ? '深度推理' : store.agentState.status === 'searching' ? '代码检索' : store.agentState.status }}</span>
        </div>
        <div class="text-geek-text-dim truncate">{{ store.agentState.data }}</div>
      </div>

      <div
        v-if="store.activeContextFiles.length > 0 && store.isRunning"
        class="fixed bottom-24 right-[300px] px-3 py-2 bg-geek-surface/95 border border-geek-border rounded-lg text-xs z-50 max-w-[500px] shadow-xl backdrop-blur-sm"
      >
        <div class="text-geek-text-dim font-bold mb-1">📂 活跃文件</div>
        <div class="flex flex-wrap gap-1">
          <span
            v-for="f in store.activeContextFiles.slice(-8)"
            :key="f"
            :title="f"
            class="px-1.5 py-0.5 bg-geek-bg border border-geek-border rounded text-[10px] text-geek-accent whitespace-nowrap"
          >{{ f }}</span>
        </div>
      </div>

      <!-- ═══ Mermaid Lightbox 全屏放大 ═══ -->

      <!-- ═══ Toast 通知 ═══ -->
      <div
        v-if="store.toasts.length > 0"
        class="fixed bottom-6 left-1/2 -translate-x-1/2 z-[150] flex flex-col gap-2 items-center pointer-events-none"
      >
        <TransitionGroup name="toast">
          <div
            v-for="toast in store.toasts"
            :key="toast.id"
            class="px-4 py-2 rounded-lg text-xs shadow-xl pointer-events-auto cursor-pointer backdrop-blur-sm"
            :class="{
              'bg-emerald-900/90 border border-emerald-500/50 text-emerald-300': toast.type === 'success',
              'bg-red-900/90 border border-red-500/50 text-red-300': toast.type === 'error',
              'bg-blue-900/90 border border-blue-500/50 text-blue-300': toast.type === 'info',
              'bg-amber-900/90 border border-amber-500/50 text-amber-300': toast.type === 'warning',
            }"
            @click="store.removeToast(toast.id)"
          >{{ toast.message }}</div>
        </TransitionGroup>
      </div>

      <Transition name="lightbox">
        <div
          v-if="mermaidLightbox"
          class="fixed inset-0 z-[200] flex items-center justify-center bg-black/85 backdrop-blur-sm"
          @click.self="closeMermaidLightbox"
          @keydown.escape="closeMermaidLightbox"
        >
          <div class="relative w-[95vw] h-[92vh] flex flex-col">
            <div class="flex items-center justify-between px-4 py-2 bg-geek-surface border-b border-geek-border rounded-t-lg shrink-0">
              <div class="flex items-center gap-3">
                <span class="text-xs font-bold text-violet-400">◈ {{ mermaidLightbox.title }}</span>
                <span class="text-[10px] text-geek-text-dim">{{ Math.round(mermaidLightbox.scale * 100) }}%</span>
              </div>
              <div class="flex items-center gap-2">
                <button @click="zoomLightbox(-0.2)" class="px-2 py-1 text-xs text-geek-text-dim hover:text-geek-accent border border-geek-border rounded transition-colors">−</button>
                <button @click="mermaidLightbox.scale = 1" class="px-2 py-1 text-xs text-geek-text-dim hover:text-geek-accent border border-geek-border rounded transition-colors">1:1</button>
                <button @click="zoomLightbox(0.2)" class="px-2 py-1 text-xs text-geek-text-dim hover:text-geek-accent border border-geek-border rounded transition-colors">+</button>
                <span class="text-geek-text-dim text-[10px] mx-2">|</span>
                <button @click="closeMermaidLightbox" class="px-2 py-1 text-xs text-red-400 hover:text-red-300 border border-red-500/30 rounded transition-colors">ESC</button>
              </div>
            </div>
            <div
              class="flex-1 min-h-0 overflow-auto bg-gradient-to-br from-[#0f172a] to-[#1e1b4b] rounded-b-lg p-8"
              @wheel.prevent="handleLightboxWheel"
            >
              <div
                class="origin-center transition-transform duration-150"
                :style="{ transform: `scale(${mermaidLightbox.scale})` }"
                v-html="mermaidLightbox.svg"
              ></div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <PixelPet />
  </div>
</template>

<style>
.lightbox-enter-active,
.lightbox-leave-active {
  transition: all 0.25s ease;
}
.lightbox-enter-from,
.lightbox-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

.toast-enter-active {
  transition: all 0.3s ease-out;
}
.toast-leave-active {
  transition: all 0.2s ease-in;
}
.toast-enter-from {
  opacity: 0;
  transform: translateY(16px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
.toast-move {
  transition: transform 0.2s ease;
}
</style>
