<script setup>
import { ref, nextTick, watch, computed } from 'vue'
import { useAgentStore } from '../stores/agent'

const store = useAgentStore()
const inputText = ref('')
const chatContainer = ref(null)
const showHistory = ref(true)
const expandedThoughts = ref({})
const useSwarm = ref(false)
const pendingImages = ref([])
const fileInput = ref(null)

const pendingQuestions = computed(() => {
  return store.messages.filter(m => m.isQuestion && !m.answered)
})

watch(() => store.messages.length, async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
})

function handleSend() {
  const text = inputText.value.trim()
  if (!text && !pendingImages.value.length) return
  const pendingQuestion = pendingQuestions.value[0]
  if (pendingQuestion) {
    store.answerQuestion(pendingQuestion.questionId, text)
  } else {
    const images = pendingImages.value.map(img => img.base64)
    store.sendTask(text || '请分析上传的图片', { use_swarm: useSwarm.value, images })
  }
  inputText.value = ''
  pendingImages.value = []
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function formatTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function handleUndoToTurn(turn, taskId) {
  store.previewRollback(taskId, 1, turn)
}

function toggleThought(idx) {
  expandedThoughts.value[idx] = !expandedThoughts.value[idx]
}

function getMsgType(msg) {
  if (msg.msgType === 'agent_state') return 'agent_state'
  if (msg.msgType === 'system_alert') return 'system_alert'
  if (msg.msgType === 'context_update') return 'context_update'
  if (msg.isChat) return 'chat'
  if (msg.isError) return 'error'
  if (msg.isFinish) return 'finish'
  if (msg.isQuestion) return 'question'
  return 'default'
}

function addImageFile(file) {
  if (!file || !file.type.startsWith('image/')) return
  if (pendingImages.value.length >= 5) return
  const reader = new FileReader()
  reader.onload = (e) => {
    const base64 = e.target.result
    pendingImages.value.push({
      id: Date.now() + Math.random(),
      name: file.name,
      dataUrl: base64,
      base64: base64.split(',')[1] || base64,
    })
  }
  reader.readAsDataURL(file)
}

function removeImage(index) {
  pendingImages.value.splice(index, 1)
}

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileSelect(e) {
  const files = e.target.files
  if (files) {
    Array.from(files).forEach(addImageFile)
  }
  e.target.value = ''
}

function handlePaste(e) {
  const items = e.clipboardData?.items
  if (!items) return
  let hasImage = false
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      hasImage = true
      const file = item.getAsFile()
      if (file) addImageFile(file)
    }
  }
}
</script>

<template>
  <div class="h-full flex bg-geek-surface">
    <!-- 左侧: Chat 主区域 -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- Chat 标题栏 -->
      <div class="px-4 py-2.5 border-b border-geek-border flex items-center gap-3 bg-geek-bg/30">
        <span class="text-xs font-bold text-geek-accent tracking-wider">◈ CHAT</span>
        <span v-if="store.isRunning" class="text-[10px] text-yellow-400 animate-pulse">{{ store.status || '运行中...' }}</span>
        <span v-else-if="store.currentTool" class="text-[10px] text-blue-400">执行: {{ store.currentTool.name }}</span>
        <div class="ml-auto flex items-center gap-2">
          <button
            @click="showHistory = !showHistory"
            class="text-[10px] px-2 py-1 rounded border transition-colors"
            :class="showHistory
              ? 'bg-geek-accent/10 text-geek-accent border-geek-accent/30'
              : 'text-geek-text-dim border-geek-border hover:text-geek-text'"
            :title="showHistory ? '隐藏操作历史' : '显示操作历史'"
          >
            {{ showHistory ? '◈ 历史 ON' : '◇ 历史 OFF' }}
          </button>
        </div>
      </div>

      <!-- Chat 消息区 -->
      <div ref="chatContainer" class="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        <template v-for="(msg, idx) in store.messages" :key="idx">

          <!-- ═══ agent_state: thinking 深度推理折叠面板 ═══ -->
          <div v-if="getMsgType(msg) === 'agent_state' && msg.agentStatus === 'thinking'" class="thinking-panel">
            <button
              @click="toggleThought(idx)"
              class="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg bg-blue-950/40 border border-blue-500/20 hover:border-blue-500/40 transition-all group"
            >
              <span class="text-sm breathing-icon">🧠</span>
              <span class="text-[11px] font-medium text-blue-300/90 flex-1 text-left truncate">
                {{ expandedThoughts[idx] ? '🧠 Agent 推理过程' : '🧠 Agent 正在推演逻辑...' }}
              </span>
              <svg
                class="w-3.5 h-3.5 text-blue-400/60 transition-transform duration-200"
                :class="{ 'rotate-180': expandedThoughts[idx] }"
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            <Transition name="expand">
              <div v-if="expandedThoughts[idx]" class="mt-1.5 px-3 py-2.5 rounded-lg bg-geek-bg/60 border border-blue-500/10 backdrop-blur-sm">
                <div class="text-[10px] text-blue-200/50 leading-relaxed whitespace-pre-wrap">{{ msg.content }}</div>
              </div>
            </Transition>
          </div>

          <!-- ═══ agent_state: searching 搜索徽章 ═══ -->
          <div v-else-if="getMsgType(msg) === 'agent_state' && msg.agentStatus === 'searching'" class="flex items-center gap-2 py-1">
            <div class="search-badge">
              <span class="text-xs animate-pulse">🔍</span>
              <span class="text-[10px] font-medium text-cyan-300/90 truncate max-w-[200px]">{{ msg.content }}</span>
            </div>
          </div>

          <!-- ═══ system_alert 系统拦截卡片 ═══ -->
          <div v-else-if="getMsgType(msg) === 'system_alert'" class="alert-card">
            <div class="flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-amber-950/30 border border-amber-500/25 backdrop-blur-sm">
              <span class="text-sm mt-0.5 shrink-0">🛡️</span>
              <div class="flex-1 min-w-0">
                <div class="text-[10px] font-bold text-amber-400/80 mb-0.5">系统自愈</div>
                <div class="text-[10px] text-amber-200/60 leading-relaxed">{{ msg.content }}</div>
              </div>
            </div>
          </div>

          <!-- ═══ context_update 活跃文件徽章 ═══ -->
          <div v-else-if="getMsgType(msg) === 'context_update'" class="flex items-center gap-1.5 flex-wrap py-0.5">
            <span class="text-[10px] text-geek-text-dim">📂</span>
            <span
              v-for="f in (msg.files || [])"
              :key="f"
              class="context-file-tag"
            >{{ f }}</span>
          </div>

          <!-- ═══ chat 结构化回复 ═══ -->
          <div v-else-if="getMsgType(msg) === 'chat'" class="text-xs leading-relaxed group">
            <div class="flex items-center gap-2 mb-1.5">
              <span class="font-bold text-[11px] text-emerald-400">▸ Agent</span>
              <span class="text-geek-text-dim text-[10px]">{{ formatTime(msg.timestamp) }}</span>
              <span class="text-[10px] bg-emerald-900/40 text-emerald-400/80 px-1.5 py-0.5 rounded">回复</span>
            </div>
            <div class="chat-content-block pl-4 border-l-2 border-emerald-500/30 whitespace-pre-wrap break-words text-geek-text/90">
              {{ msg.content }}
            </div>
          </div>

          <!-- ═══ error 错误消息 ═══ -->
          <div v-else-if="getMsgType(msg) === 'error'" class="text-xs leading-relaxed group">
            <div class="flex items-center gap-2 mb-1">
              <span class="font-bold text-[11px] text-red-400">▸ Agent</span>
              <span class="text-geek-text-dim text-[10px]">{{ formatTime(msg.timestamp) }}</span>
              <span class="text-[10px] bg-red-900/50 text-red-400 px-1.5 py-0.5 rounded">错误</span>
              <button
                v-if="store.activeTaskId && idx > 0"
                @click="handleUndoToTurn(Math.ceil(idx / 2), store.activeTaskId)"
                class="ml-auto opacity-0 group-hover:opacity-100 transition-opacity text-[10px] px-2 py-0.5 rounded bg-red-900/30 text-red-400 border border-red-500/30 hover:bg-red-900/50 hover:border-red-500/50"
                title="撤销至此消息之前的状态"
              >⏪ 撤销至此</button>
            </div>
            <div class="pl-4 border-l-2 border-red-500/30 whitespace-pre-wrap break-words text-red-300/80">
              {{ msg.content }}
            </div>
          </div>

          <!-- ═══ finish 完成消息 ═══ -->
          <div v-else-if="getMsgType(msg) === 'finish'" class="text-xs leading-relaxed">
            <div class="flex items-center gap-2 mb-1">
              <span class="font-bold text-[11px] text-green-400">▸ Agent</span>
              <span class="text-geek-text-dim text-[10px]">{{ formatTime(msg.timestamp) }}</span>
              <span class="text-[10px] bg-green-900/50 text-green-400 px-1.5 py-0.5 rounded">完成</span>
            </div>
            <div class="pl-4 border-l-2 border-green-500/30 whitespace-pre-wrap break-words text-green-300/80">
              {{ msg.content }}
            </div>
          </div>

          <!-- ═══ question 待回答消息 ═══ -->
          <div v-else-if="getMsgType(msg) === 'question'" class="text-xs leading-relaxed">
            <div class="flex items-center gap-2 mb-1">
              <span class="font-bold text-[11px] text-yellow-400">▸ Agent</span>
              <span class="text-geek-text-dim text-[10px]">{{ formatTime(msg.timestamp) }}</span>
              <span v-if="!msg.answered" class="text-[10px] bg-yellow-900/50 text-yellow-400 px-1.5 py-0.5 rounded animate-pulse">待回答</span>
            </div>
            <div class="pl-4 border-l-2 border-yellow-500/30 whitespace-pre-wrap break-words text-geek-text">
              {{ msg.content }}
            </div>
            <div v-if="!msg.answered" class="mt-1 pl-4 text-yellow-400 text-[10px]">
              ↑ 请在下方输入框回答此问题
            </div>
            <div v-if="msg.answered" class="mt-1 pl-4 text-green-400 text-[10px]">
              已回答: {{ msg.answer }}
            </div>
          </div>

          <!-- ═══ default: 用户消息 & 普通Agent消息 ═══ -->
          <div v-else class="text-xs leading-relaxed group" :class="{ 'text-geek-accent': msg.role === 'user' }">
            <div class="flex items-center gap-2 mb-1">
              <span
                class="font-bold text-[11px]"
                :class="msg.role === 'user' ? 'text-geek-accent' : 'text-blue-400'"
              >
                {{ msg.role === 'user' ? '▸ You' : '▸ Agent' }}
              </span>
              <span class="text-geek-text-dim text-[10px]">{{ formatTime(msg.timestamp) }}</span>
              <button
                v-if="msg.role === 'agent' && store.activeTaskId && idx > 0"
                @click="handleUndoToTurn(Math.ceil(idx / 2), store.activeTaskId)"
                class="ml-auto opacity-0 group-hover:opacity-100 transition-opacity text-[10px] px-2 py-0.5 rounded bg-red-900/30 text-red-400 border border-red-500/30 hover:bg-red-900/50 hover:border-red-500/50"
                title="撤销至此消息之前的状态"
              >⏪ 撤销至此</button>
            </div>
            <div class="whitespace-pre-wrap break-words pl-4 border-l-2 border-geek-border/50 text-geek-text">
              {{ msg.content }}
            </div>
          </div>

        </template>
        <div v-if="!store.messages.length" class="text-geek-text-dim text-xs italic py-8 text-center">
          {{ store.activeTaskId ? '在当前任务下继续追问...' : '发送任务给 AI Agent 开始编程...' }}
        </div>
      </div>

      <!-- 输入区 -->
      <div class="p-3 border-t border-geek-border bg-geek-bg/20">
        <div class="text-[10px] text-geek-text-dim mb-1.5 truncate" v-if="pendingQuestions.length">
          ⚠️ 有 {{ pendingQuestions.length }} 个问题等待回答
        </div>

        <!-- 图片预览区 -->
        <div v-if="pendingImages.length" class="flex gap-2 mb-2 flex-wrap">
          <div
            v-for="(img, idx) in pendingImages"
            :key="img.id"
            class="relative group rounded-lg overflow-hidden border border-geek-accent/30 bg-geek-bg/50"
          >
            <img :src="img.dataUrl" class="w-16 h-16 object-cover" :alt="img.name" />
            <button
              @click="removeImage(idx)"
              class="absolute top-0.5 right-0.5 w-4 h-4 rounded-full bg-red-900/80 text-red-300 text-[9px] flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-800"
            >✕</button>
            <div class="absolute bottom-0 inset-x-0 bg-black/60 text-[8px] text-geek-text-dim px-1 py-0.5 truncate">
              {{ img.name }}
            </div>
          </div>
          <div
            v-if="pendingImages.length < 5"
            class="w-16 h-16 rounded-lg border border-dashed border-geek-border hover:border-geek-accent/50 flex items-center justify-center cursor-pointer transition-colors"
            @click="triggerFileInput"
          >
            <span class="text-geek-text-dim text-lg">+</span>
          </div>
        </div>

        <input
          ref="fileInput"
          type="file"
          accept="image/*"
          multiple
          class="hidden"
          @change="handleFileSelect"
        />

        <div class="flex gap-2 items-center">
          <button
            @click="triggerFileInput"
            class="px-2 py-2 rounded text-xs border transition-colors shrink-0"
            :class="pendingImages.length
              ? 'bg-geek-accent/10 text-geek-accent border-geek-accent/30'
              : 'bg-geek-bg/50 text-geek-text-dim border-geek-border hover:text-geek-text hover:border-geek-accent/30'"
            title="上传图片（UML图/架构图/草图）"
          >
            🖼️
          </button>
          <input
            v-model="inputText"
            @keydown="handleKeydown"
            @paste="handlePaste"
            type="text"
            :placeholder="pendingQuestions.length ? '回答问题...' : (store.activeTaskId ? '在当前任务下追问...' : (pendingImages.length ? '描述你想对图片做什么...' : '描述你想要的功能，开启新任务...'))"
            class="flex-1 bg-geek-bg border border-geek-border rounded px-3 py-2 text-xs text-geek-text placeholder-geek-text-dim focus:outline-none focus:border-geek-accent transition-colors"
            :disabled="store.isRunning && !pendingQuestions.length"
          />
          <button
            @click="handleSend"
            :disabled="store.isRunning && !pendingQuestions.length"
            class="px-4 py-2 bg-geek-accent/10 text-geek-accent border border-geek-accent/30 rounded text-xs font-bold hover:bg-geek-accent/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ pendingQuestions.length ? '回答' : '发送' }}
          </button>
          <button
            @click="useSwarm = !useSwarm"
            class="px-2.5 py-2 rounded text-xs font-bold border transition-colors whitespace-nowrap"
            :class="useSwarm
              ? 'bg-purple-900/30 text-purple-400 border-purple-500/40 hover:bg-purple-900/50'
              : 'bg-geek-bg/50 text-geek-text-dim border-geek-border hover:text-geek-text hover:border-geek-accent/30'"
            :title="useSwarm ? '🧠 深度研发模式：Coder-Reviewer 对抗博弈，代码经过严格审查' : '⚡ 闪电模式：单体 Agent 极速响应'"
          >
            {{ useSwarm ? '🧠 深度' : '⚡ 极速' }}
          </button>
          <button
            @click="store.autoApprove = !store.autoApprove"
            class="px-2.5 py-2 rounded text-xs font-bold border transition-colors whitespace-nowrap"
            :class="store.autoApprove
              ? 'bg-red-900/30 text-red-400 border-red-500/40 hover:bg-red-900/50'
              : 'bg-green-900/20 text-green-400 border-green-500/30 hover:bg-green-900/40'"
            :title="store.autoApprove ? '自动执行模式：危险命令将自动放行' : '安全模式：危险命令需人工确认'"
          >
            {{ store.autoApprove ? '🚀 免确认' : '🛡️ 需确认' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 右侧: 操作历史面板 -->
    <Transition name="slide">
      <div
        v-if="showHistory && store.historyStates.length > 0"
        class="w-64 border-l border-geek-border flex flex-col bg-geek-bg/40"
      >
        <!-- 历史面板标题 -->
        <div class="px-3 py-2.5 border-b border-geek-border flex items-center gap-2 bg-geek-bg/30">
          <span class="text-xs font-bold text-geek-accent tracking-wider">◈ TIMELINE</span>
          <span class="text-[10px] text-geek-text-dim ml-auto">{{ store.historyStates.length }} 步</span>
        </div>

        <!-- 历史条目列表 -->
        <div class="flex-1 overflow-y-auto py-2 px-2 space-y-1">
          <div
            v-for="(entry, idx) in store.historyStates"
            :key="idx"
            class="group relative rounded-lg px-3 py-2 hover:bg-geek-surface/80 transition-colors border border-transparent hover:border-geek-border/50"
          >
            <!-- 时间线连接线 -->
            <div class="absolute left-[18px] top-0 bottom-0 w-px bg-geek-border/30 -z-10" v-if="idx < store.historyStates.length - 1"></div>

            <div class="flex items-start gap-2.5">
              <!-- Turn 编号圆点 -->
              <div class="flex-shrink-0 w-5 h-5 rounded-full bg-geek-accent/20 border border-geek-accent/40 flex items-center justify-center">
                <span class="text-[9px] font-bold text-geek-accent">{{ entry.turn }}</span>
              </div>

              <!-- 内容 -->
              <div class="flex-1 min-w-0">
                <div class="text-[10px] text-geek-text truncate leading-tight">
                  {{ entry.summary || entry.tool || `第 ${entry.turn} 轮` }}
                </div>
                <div v-if="entry.diff_stat" class="text-[9px] text-geek-text-dim/70 truncate mt-0.5 font-mono">
                  {{ entry.diff_stat }}
                </div>
                <div class="flex items-center gap-1.5 mt-1">
                  <span class="text-[9px] text-geek-text-dim">{{ formatTime(entry.timestamp) }}</span>
                  <span v-if="entry.git_commit" class="text-[9px] font-mono text-blue-400/60">{{ entry.git_commit.substring(0, 7) }}</span>
                </div>
              </div>

              <!-- 操作按钮 -->
              <div class="flex-shrink-0 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  @click="store.viewCheckpoint(entry.task_id, entry.turn)"
                  class="w-6 h-6 rounded flex items-center justify-center bg-blue-900/20 text-blue-400 border border-blue-500/20 hover:bg-blue-900/40 hover:border-blue-500/40"
                  title="查看此步骤的代码变更"
                >
                  <span class="text-[10px]">👁</span>
                </button>
                <button
                  @click="store.previewRollback(entry.task_id, store.historyStates.length - idx)"
                  class="w-6 h-6 rounded flex items-center justify-center bg-red-900/20 text-red-400 border border-red-500/20 hover:bg-red-900/40 hover:border-red-500/40"
                  title="预览回退到此步骤"
                >
                  <span class="text-[10px]">⏪</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 可视化对比弹窗 -->
    <Teleport to="body">
      <div
        v-if="store.rollbackPreview"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
        @click.self="store.dismissRollbackPreview()"
      >
        <div class="bg-geek-surface border border-geek-border rounded-xl shadow-2xl w-[90vw] max-w-4xl max-h-[85vh] flex flex-col overflow-hidden">
          <!-- 弹窗头部 -->
          <div class="px-5 py-4 border-b border-geek-border flex items-center justify-between bg-geek-bg/30">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg bg-red-900/30 border border-red-500/30 flex items-center justify-center">
                <span class="text-base">⏪</span>
              </div>
              <div>
                <h3 class="text-sm font-bold text-geek-accent">时光机回退预览</h3>
                <p class="text-[10px] text-geek-text-dim mt-0.5">
                  回退到第 {{ store.rollbackPreview.target_turn }} 轮
                  <span v-if="store.rollbackPreview.target_description"> — {{ store.rollbackPreview.target_description }}</span>
                  <span v-if="store.rollbackPreview.target_git_commit" class="font-mono ml-1 text-blue-400">{{ store.rollbackPreview.target_git_commit.substring(0, 8) }}</span>
                </p>
              </div>
            </div>
            <button
              @click="store.dismissRollbackPreview()"
              class="text-geek-text-dim hover:text-geek-text text-lg px-2"
            >
              ✕
            </button>
          </div>

          <!-- 弹窗内容 -->
          <div class="flex-1 overflow-y-auto p-5 space-y-5">
            <!-- 将撤销的提交 -->
            <div v-if="store.rollbackPreview.commits_being_reverted" class="space-y-2">
              <h4 class="text-[10px] font-bold text-geek-accent uppercase tracking-wider">📝 将撤销的提交</h4>
              <pre class="text-[10px] font-mono bg-geek-bg p-3 rounded-lg border border-geek-border/50 text-geek-text whitespace-pre-wrap">{{ store.rollbackPreview.commits_being_reverted }}</pre>
            </div>

            <!-- 将撤销的文件 -->
            <div v-if="store.rollbackPreview.reverted_files.length > 0" class="space-y-2">
              <h4 class="text-[10px] font-bold text-geek-accent uppercase tracking-wider">📂 将撤销的文件变更</h4>
              <div class="space-y-1">
                <div
                  v-for="(file, idx) in store.rollbackPreview.reverted_files"
                  :key="idx"
                  class="flex items-center gap-2.5 text-xs px-3 py-1.5 bg-geek-bg/50 rounded-lg border border-geek-border/30"
                >
                  <span>{{ file.icon }}</span>
                  <span
                    class="font-bold text-[10px]"
                    :class="{
                      'text-yellow-400': file.status === 'M',
                      'text-red-400': file.status === 'A',
                      'text-blue-400': file.status === 'D',
                    }"
                  >{{ file.status_label }}</span>
                  <code class="text-geek-text font-mono text-[10px]">{{ file.file }}</code>
                </div>
              </div>
            </div>

            <!-- 变更统计 -->
            <div v-if="store.rollbackPreview.stat_summary" class="space-y-2">
              <h4 class="text-[10px] font-bold text-geek-accent uppercase tracking-wider">📊 变更统计</h4>
              <pre class="text-[10px] font-mono bg-geek-bg p-3 rounded-lg border border-geek-border/50 text-geek-text whitespace-pre-wrap">{{ store.rollbackPreview.stat_summary }}</pre>
            </div>

            <!-- 代码差异详情 -->
            <div v-if="store.rollbackPreview.diff_lines.length > 0" class="space-y-2">
              <h4 class="text-[10px] font-bold text-geek-accent uppercase tracking-wider">
                🔍 代码差异详情
              </h4>
              <div class="flex items-center gap-3 text-[10px] text-geek-text-dim mb-1">
                <span class="flex items-center gap-1"><span class="inline-block w-3 h-3 rounded bg-red-900/30 border border-red-500/30"></span> AI 添加的代码（将被删除）</span>
                <span class="flex items-center gap-1"><span class="inline-block w-3 h-3 rounded bg-green-900/30 border border-green-500/30"></span> AI 删除的代码（将被恢复）</span>
              </div>
              <div class="bg-geek-bg rounded-lg border border-geek-border/50 overflow-hidden">
                <div class="max-h-[400px] overflow-y-auto font-mono text-[10px] leading-[20px]">
                  <template v-for="(line, idx) in store.rollbackPreview.diff_lines" :key="idx">
                    <div
                      v-if="line.type === 'header'"
                      class="px-4 py-1.5 text-blue-400 bg-blue-900/10 border-t border-geek-border/30 font-bold sticky top-0"
                    >
                      {{ line.file }} {{ line.content }}
                    </div>
                    <div
                      v-else-if="line.type === 'ai_added'"
                      class="px-4 bg-red-900/20 text-red-400 hover:bg-red-900/30"
                    >
                      <span class="text-red-500/60 select-none mr-2">-</span>{{ line.content }}
                    </div>
                    <div
                      v-else-if="line.type === 'ai_removed'"
                      class="px-4 bg-green-900/20 text-green-400 hover:bg-green-900/30"
                    >
                      <span class="text-green-500/60 select-none mr-2">+</span>{{ line.content }}
                    </div>
                    <div v-else class="px-4 text-geek-text-dim/60">
                      <span class="select-none mr-2"> </span>{{ line.content }}
                    </div>
                  </template>
                </div>
              </div>
            </div>

            <!-- 无差异时的提示 -->
            <div v-if="!store.rollbackPreview.diff_lines.length && !store.rollbackPreview.reverted_files.length" class="text-center py-8 text-geek-text-dim text-xs">
              📂 没有检测到物理文件的变更，回退仅影响 Agent 的对话记忆
            </div>
          </div>

          <!-- 弹窗底部按钮 -->
          <div class="px-5 py-4 border-t border-geek-border flex items-center justify-between bg-geek-bg/20">
            <div class="text-[10px] text-geek-text-dim">
              将撤销 {{ store.rollbackPreview.removed_turns?.length || 0 }} 个轮次的变更
            </div>
            <div class="flex gap-3">
              <button
                @click="store.dismissRollbackPreview()"
                class="px-5 py-2 text-xs font-bold rounded-lg border border-geek-border text-geek-text-dim hover:bg-geek-bg transition-colors"
              >
                取消
              </button>
              <button
                @click="store.confirmRollback(store.rollbackPreview.task_id, store.rollbackPreview.removed_turns?.length || 1)"
                class="px-5 py-2 text-xs font-bold rounded-lg bg-red-900/30 text-red-400 border border-red-500/40 hover:bg-red-900/50 hover:border-red-500/60 transition-colors"
              >
                ⏪ 确认回退
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 代码查看弹窗 -->
    <Teleport to="body">
      <div
        v-if="store.checkpointView"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
        @click.self="store.dismissCheckpointView()"
      >
        <div class="bg-geek-surface border border-geek-border rounded-xl shadow-2xl w-[90vw] max-w-4xl max-h-[85vh] flex flex-col overflow-hidden">
          <!-- 弹窗头部 -->
          <div class="px-5 py-4 border-b border-geek-border flex items-center justify-between bg-geek-bg/30">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg bg-blue-900/30 border border-blue-500/30 flex items-center justify-center">
                <span class="text-base">👁</span>
              </div>
              <div>
                <h3 class="text-sm font-bold text-geek-accent">代码变更详情</h3>
                <p class="text-[10px] text-geek-text-dim mt-0.5">
                  第 {{ store.checkpointView.turn }} 轮
                  <span v-if="store.checkpointView.description"> — {{ store.checkpointView.description }}</span>
                  <span v-if="store.checkpointView.git_commit" class="font-mono ml-1 text-blue-400">{{ store.checkpointView.git_commit.substring(0, 8) }}</span>
                </p>
              </div>
            </div>
            <button
              @click="store.dismissCheckpointView()"
              class="text-geek-text-dim hover:text-geek-text text-lg px-2"
            >
              ✕
            </button>
          </div>

          <!-- 弹窗内容 -->
          <div class="flex-1 overflow-y-auto p-5 space-y-5">
            <!-- 变更文件列表 -->
            <div v-if="store.checkpointView.changed_files.length > 0" class="space-y-2">
              <h4 class="text-[10px] font-bold text-geek-accent uppercase tracking-wider">📂 变更的文件</h4>
              <div class="space-y-1">
                <div
                  v-for="(file, idx) in store.checkpointView.changed_files"
                  :key="idx"
                  class="flex items-center gap-2.5 text-xs px-3 py-1.5 bg-geek-bg/50 rounded-lg border border-geek-border/30"
                >
                  <span>{{ file.icon }}</span>
                  <span
                    class="font-bold text-[10px]"
                    :class="{
                      'text-yellow-400': file.status === 'M',
                      'text-red-400': file.status === 'A',
                      'text-blue-400': file.status === 'D',
                    }"
                  >{{ file.status_label }}</span>
                  <code class="text-geek-text font-mono text-[10px]">{{ file.file }}</code>
                </div>
              </div>
            </div>

            <!-- 变更统计 -->
            <div v-if="store.checkpointView.diff_stat" class="space-y-2">
              <h4 class="text-[10px] font-bold text-geek-accent uppercase tracking-wider">📊 变更统计</h4>
              <pre class="text-[10px] font-mono bg-geek-bg p-3 rounded-lg border border-geek-border/50 text-geek-text whitespace-pre-wrap">{{ store.checkpointView.diff_stat }}</pre>
            </div>

            <!-- 代码差异详情 -->
            <div v-if="store.checkpointView.diff_lines.length > 0" class="space-y-2">
              <h4 class="text-[10px] font-bold text-geek-accent uppercase tracking-wider">
                🔍 AI 写的代码
              </h4>
              <div class="flex items-center gap-3 text-[10px] text-geek-text-dim mb-1">
                <span class="flex items-center gap-1"><span class="inline-block w-3 h-3 rounded bg-green-900/30 border border-green-500/30"></span> AI 新增的代码</span>
                <span class="flex items-center gap-1"><span class="inline-block w-3 h-3 rounded bg-red-900/30 border border-red-500/30"></span> AI 删除的代码</span>
              </div>
              <div class="bg-geek-bg rounded-lg border border-geek-border/50 overflow-hidden">
                <div class="max-h-[400px] overflow-y-auto font-mono text-[10px] leading-[20px]">
                  <template v-for="(line, idx) in store.checkpointView.diff_lines" :key="idx">
                    <div
                      v-if="line.type === 'header'"
                      class="px-4 py-1.5 text-blue-400 bg-blue-900/10 border-t border-geek-border/30 font-bold sticky top-0"
                    >
                      {{ line.file }} {{ line.content }}
                    </div>
                    <div
                      v-else-if="line.type === 'ai_added'"
                      class="px-4 bg-green-900/20 text-green-400 hover:bg-green-900/30"
                    >
                      <span class="text-green-500/60 select-none mr-2">+</span>{{ line.content }}
                    </div>
                    <div
                      v-else-if="line.type === 'ai_removed'"
                      class="px-4 bg-red-900/20 text-red-400 hover:bg-red-900/30"
                    >
                      <span class="text-red-500/60 select-none mr-2">-</span>{{ line.content }}
                    </div>
                    <div v-else class="px-4 text-geek-text-dim/60">
                      <span class="select-none mr-2"> </span>{{ line.content }}
                    </div>
                  </template>
                </div>
              </div>
            </div>

            <!-- 无代码变更时的提示 -->
            <div v-if="!store.checkpointView.diff_lines.length && !store.checkpointView.changed_files.length" class="text-center py-8 text-geek-text-dim text-xs">
              📂 此步骤没有检测到代码文件变更
            </div>
          </div>

          <!-- 弹窗底部 -->
          <div class="px-5 py-4 border-t border-geek-border flex items-center justify-between bg-geek-bg/20">
            <div class="text-[10px] text-geek-text-dim">
              {{ store.checkpointView.diff_stat || '无变更统计' }}
            </div>
            <button
              @click="store.dismissCheckpointView()"
              class="px-5 py-2 text-xs font-bold rounded-lg border border-geek-border text-geek-text-dim hover:bg-geek-bg transition-colors"
            >
              关闭
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
}
.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
  width: 0;
  padding: 0;
  overflow: hidden;
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}
.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
}
.expand-enter-to,
.expand-leave-from {
  opacity: 1;
  max-height: 500px;
}

.breathing-icon {
  animation: breathe 2s ease-in-out infinite;
}
@keyframes breathe {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.1); }
}

.thinking-panel {
  margin: 4px 0;
}

.search-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 9999px;
  background: rgba(6, 182, 212, 0.08);
  border: 1px solid rgba(6, 182, 212, 0.2);
  backdrop-filter: blur(4px);
}

.alert-card {
  margin: 4px 0;
}

.context-file-tag {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  background: rgba(0, 255, 136, 0.06);
  border: 1px solid rgba(0, 255, 136, 0.15);
  color: rgba(0, 255, 136, 0.7);
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-content-block {
  background: rgba(16, 185, 129, 0.03);
  border-radius: 0 6px 6px 0;
  padding: 6px 10px;
}
</style>
