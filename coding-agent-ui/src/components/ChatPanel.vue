<script setup>
import { ref, nextTick, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { useAgentStore } from '../stores/agent'
import { splitByMermaid, renderMermaid } from '../utils/mermaidRenderer'

const store = useAgentStore()
const inputText = ref('')
const chatContainer = ref(null)
const showHistory = ref(true)
const expandedThoughts = ref({})
const useSwarm = ref(false)
const pendingImages = ref([])
const fileInput = ref(null)
const inputEl = ref(null)

const CAPABILITIES = [
  { id: 'sdd', icon: '🤖', label: '多智能体开发', desc: 'Lead→Implementer→Reviewer 三角色协作', skill: 'sdd' },
  { id: 'plan', icon: '🤔', label: 'PM需求澄清', desc: '深度理解需求再动手', skill: 'doubt' },
  { id: 'tdd', icon: '🧪', label: 'TDD测试驱动', desc: '先写测试再写实现', skill: 'tdd' },
  { id: 'debugging', icon: '🐛', label: '深度排障', desc: '系统化定位 Bug：复现→隔离→假设→验证', skill: 'debugging' },
  { id: 'visual', icon: '🎨', label: '视觉头脑风暴', desc: 'Mermaid 图表驱动的架构设计与创意发散', skill: 'visual' },
  { id: 'security', icon: '🛡️', label: '安全审计', desc: '检查越权、注入与并发漏洞', skill: 'security' },
  { id: 'performance', icon: '⚡', label: '性能优化', desc: '测量→定位→优化→验证', skill: 'performance' },
]

const SLASH_COMMANDS = [
  { id: 'plan', slash: '/plan', icon: '🤔', label: 'PM需求澄清', desc: '深度理解需求再动手', skill: 'doubt' },
  { id: 'sdd', slash: '/sdd', icon: '🤖', label: '多智能体开发', desc: 'Lead→Implementer→Reviewer 三角色协作', skill: 'sdd' },
  { id: 'tdd', slash: '/tdd', icon: '🧪', label: 'TDD测试驱动', desc: '先写测试再写实现', skill: 'tdd' },
  { id: 'debugging', slash: '/debug', icon: '🐛', label: '深度排障', desc: '系统化定位 Bug', skill: 'debugging' },
  { id: 'visual', slash: '/visual', icon: '🎨', label: '视觉头脑风暴', desc: 'Mermaid 图表驱动的创意发散', skill: 'visual' },
  { id: 'review', slash: '/review', icon: '🛡️', label: '专家代码审查', desc: '安全+性能双维度审计', skill: 'security' },
  { id: 'perf', slash: '/perf', icon: '⚡', label: '性能优化专家', desc: '测量→定位→优化→验证', skill: 'performance' },
]

const showCapMenu = ref(false)
const showSlashMenu = ref(false)
const slashFilter = ref('')
const slashSelectedIdx = ref(0)
const activeTags = ref([])

function toggleCapability(cap) {
  const existing = activeTags.value.find(t => t.id === cap.id)
  if (existing) {
    activeTags.value = activeTags.value.filter(t => t.id !== cap.id)
  } else {
    activeTags.value.push({ id: cap.id, icon: cap.icon, label: cap.label, skill: cap.skill })
  }
}

function isCapActive(cap) {
  return activeTags.value.some(t => t.id === cap.id)
}

const activeCapCount = computed(() => activeTags.value.length)

const filteredCommands = computed(() => {
  if (!slashFilter.value) return SLASH_COMMANDS
  const q = slashFilter.value.toLowerCase()
  return SLASH_COMMANDS.filter(c =>
    c.slash.includes(q) || c.label.toLowerCase().includes(q) || c.desc.toLowerCase().includes(q)
  )
})

function onInputChange() {
  const text = inputText.value
  const cursorPos = inputEl.value?.selectionStart ?? text.length
  const textBeforeCursor = text.substring(0, cursorPos)

  const match = textBeforeCursor.match(/(?:^|\s)\/(\S*)$/)
  if (match) {
    slashFilter.value = match[1]
    slashSelectedIdx.value = 0
    showSlashMenu.value = true
  } else {
    showSlashMenu.value = false
    slashFilter.value = ''
  }
}

function selectCommand(cmd) {
  showSlashMenu.value = false
  slashFilter.value = ''

  const cursorPos = inputEl.value?.selectionStart ?? inputText.value.length
  const textBeforeCursor = inputText.value.substring(0, cursorPos)
  const textAfterCursor = inputText.value.substring(cursorPos)

  const match = textBeforeCursor.match(/(?:^|\s)\/\S*$/)
  if (match) {
    const before = textBeforeCursor.substring(0, match.index)
    inputText.value = before + textAfterCursor
  }

  if (!activeTags.value.find(t => t.id === cmd.id)) {
    activeTags.value.push({ id: cmd.id, icon: cmd.icon, label: cmd.label, skill: cmd.skill })
  }

  nextTick(() => {
    inputEl.value?.focus()
  })
}

function removeTag(tagId) {
  activeTags.value = activeTags.value.filter(t => t.id !== tagId)
}

function closeCapMenu(e) {
  if (showCapMenu.value && !e.target.closest('.cap-menu-zone')) {
    showCapMenu.value = false
  }
}

onMounted(() => document.addEventListener('click', closeCapMenu))
onBeforeUnmount(() => document.removeEventListener('click', closeCapMenu))

function onSlashKeydown(e) {
  if (!showSlashMenu.value) return

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    slashSelectedIdx.value = Math.min(slashSelectedIdx.value + 1, filteredCommands.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    slashSelectedIdx.value = Math.max(slashSelectedIdx.value - 1, 0)
  } else if (e.key === 'Enter' && filteredCommands.value.length > 0) {
    e.preventDefault()
    selectCommand(filteredCommands.value[slashSelectedIdx.value])
  } else if (e.key === 'Escape') {
    e.preventDefault()
    showSlashMenu.value = false
  }
}

function handleKeydown(e) {
  if (onSlashKeydown(e)) return
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

const pendingQuestions = computed(() => {
  return store.messages.filter(m => m.isQuestion && !m.answered)
})

watch(() => store.messages.length, async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
  for (let i = 0; i < store.messages.length; i++) {
    const msg = store.messages[i]
    if (!_processedTourMsgs.has(i)) {
      const tourData = isCodeTourContent(msg.content)
      if (tourData && !store.tourSteps.length) {
        _processedTourMsgs.add(i)
        store.startTour(tourData)
      }
    }
  }
})

function handleSend() {
  const text = inputText.value.trim()
  if (!text && !pendingImages.value.length && !activeTags.value.length) return
  const pendingQuestion = pendingQuestions.value[0]
  if (pendingQuestion) {
    store.answerQuestion(pendingQuestion.questionId, text)
  } else {
    const images = pendingImages.value.map(img => img.base64)
    const skills = activeTags.value.map(t => t.skill)
    store.sendTask(text || '请分析上传的图片', { use_swarm: useSwarm.value, images, skills })
  }
  inputText.value = ''
  pendingImages.value = []
  activeTags.value = []
}

function formatTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

const mermaidCache = new Map()

async function renderMsgContent(content) {
  if (!content || typeof content !== 'string') return content
  const parts = splitByMermaid(content)
  if (parts.length === 1 && parts[0].type === 'text') return null

  const htmlParts = []
  for (const part of parts) {
    if (part.type === 'mermaid') {
      const cacheKey = part.code
      let svg
      if (mermaidCache.has(cacheKey)) {
        svg = mermaidCache.get(cacheKey)
      } else {
        svg = await renderMermaid(part.code)
        mermaidCache.set(cacheKey, svg)
      }
      htmlParts.push(
        `<div class="mermaid-chart">` +
        `<button class="mermaid-expand-btn" onclick="window.__open_mermaid_lightbox&&window.__open_mermaid_lightbox(this.parentElement.querySelector('svg')?.outerHTML||'','Diagram')" title="全屏放大">⛶</button>` +
        svg +
        `</div>`
      )
      if (window.__add_mermaid_tab) {
        const title = `Architecture ${window.__mermaid_counter = (window.__mermaid_counter || 0) + 1}`
        window.__add_mermaid_tab(title, svg)
      }
    } else {
      const escaped = part.content
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
      htmlParts.push(`<div class="mermaid-text">${escaped}</div>`)
    }
  }
  return htmlParts.join('')
}

const renderedMessages = ref({})

watch(
  () => store.messages.length,
  async () => {
    for (let i = 0; i < store.messages.length; i++) {
      const msg = store.messages[i]
      if (msg.content && typeof msg.content === 'string' && msg.content.includes('```mermaid')) {
        if (!renderedMessages.value[i]) {
          const html = await renderMsgContent(msg.content)
          if (html) renderedMessages.value[i] = html
        }
      }
    }
  },
  { immediate: true },
)

function handleUndoToTurn(turn, taskId) {
  store.previewRollback(taskId, 1, turn)
}

function toggleThought(idx) {
  expandedThoughts.value[idx] = !expandedThoughts.value[idx]
}

function getMsgType(msg) {
  if (msg.msgType === 'sdd_status') return 'sdd_status'
  if (msg.msgType === 'sdd_review') return 'sdd_review'
  if (msg.msgType === 'agent_state') return 'agent_state'
  if (msg.msgType === 'system_alert') return 'system_alert'
  if (msg.msgType === 'context_update') return 'context_update'
  if (msg.isChat && isCodeTourContent(msg.content)) return 'code_tour'
  if (msg.isChat) return 'chat'
  if (msg.isError) return 'error'
  if (msg.isFinish) return 'finish'
  if (msg.isQuestion) return 'question'
  if (!msg.isChat && !msg.isError && !msg.isFinish && !msg.isQuestion && isCodeTourContent(msg.content)) return 'code_tour'
  return 'default'
}

const _processedTourMsgs = new Set()

function isCodeTourContent(content) {
  if (!content || typeof content !== 'string') return null
  let text = content.trim()
  const fenceMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?\s*```/)
  if (fenceMatch) {
    text = fenceMatch[1].trim()
  }
  const bracketStart = text.indexOf('[')
  const bracketEnd = text.lastIndexOf(']')
  if (bracketStart === -1 || bracketEnd === -1 || bracketEnd <= bracketStart) return null
  const jsonCandidate = text.substring(bracketStart, bracketEnd + 1)
  try {
    const parsed = JSON.parse(jsonCandidate)
    if (
      Array.isArray(parsed) &&
      parsed.length > 0 &&
      parsed.every(item =>
        typeof item === 'object' &&
        item !== null &&
        'step' in item &&
        'file' in item &&
        'function' in item
      )
    ) {
      return parsed
    }
  } catch {
    return null
  }
  return null
}

function checkAndStartTour(msg, idx) {
  if (_processedTourMsgs.has(idx)) return
  const tourData = isCodeTourContent(msg.content)
  if (tourData) {
    _processedTourMsgs.add(idx)
    if (!store.tourSteps.length) {
      store.startTour(tourData)
    }
  }
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

          <!-- ═══ SDD 多智能体状态指示器 ═══ -->
          <div v-if="getMsgType(msg) === 'sdd_status'" class="sdd-status-card">
            <div class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg bg-violet-950/40 border border-violet-500/25 backdrop-blur-sm">
              <span class="text-sm breathing-icon">{{ msg.sddPhase === 'lead' ? '🔄' : msg.sddPhase === 'implement' ? '👨‍💻' : msg.sddPhase === 'review' ? '🕵️' : msg.sddPhase === 'fix' ? '🔧' : '🤖' }}</span>
              <div class="flex-1 min-w-0">
                <div class="text-[10px] font-bold text-violet-400/80 mb-0.5">
                  SDD · {{ msg.sddPhase === 'lead' ? 'Lead Agent' : msg.sddPhase === 'implement' ? 'Implementer' : msg.sddPhase === 'review' ? 'Reviewer' : msg.sddPhase === 'fix' ? 'Implementer (修复)' : '多智能体' }}
                  <span v-if="msg.sddStep" class="text-violet-300/50 ml-1">步骤 {{ msg.sddStep }}/{{ msg.sddTotal }}</span>
                  <span v-if="msg.sddRetry && msg.sddRetry > 0" class="text-amber-400/60 ml-1">第 {{ msg.sddRetry }} 次审查</span>
                </div>
                <div class="text-[10px] text-violet-200/60 leading-relaxed">{{ msg.content }}</div>
              </div>
              <div v-if="msg.sddPhase === 'implement'" class="flex gap-0.5">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400/40 animate-pulse" style="animation-delay:0.2s"></span>
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400/20 animate-pulse" style="animation-delay:0.4s"></span>
              </div>
              <div v-else-if="msg.sddPhase === 'review'" class="flex gap-0.5">
                <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
                <span class="w-1.5 h-1.5 rounded-full bg-amber-400/40 animate-pulse" style="animation-delay:0.2s"></span>
                <span class="w-1.5 h-1.5 rounded-full bg-amber-400/20 animate-pulse" style="animation-delay:0.4s"></span>
              </div>
            </div>
          </div>

          <!-- ═══ SDD 审查结果指示器 ═══ -->
          <div v-else-if="getMsgType(msg) === 'sdd_review'" class="sdd-review-card">
            <div class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg border backdrop-blur-sm"
              :class="msg.sddApproved
                ? 'bg-emerald-950/30 border-emerald-500/25'
                : 'bg-red-950/30 border-red-500/25'"
            >
              <span class="text-sm">{{ msg.sddApproved ? '✅' : '❌' }}</span>
              <div class="flex-1 min-w-0">
                <div class="text-[10px] font-bold mb-0.5"
                  :class="msg.sddApproved ? 'text-emerald-400/80' : 'text-red-400/80'"
                >
                  {{ msg.sddApproved ? '审查通过' : '审查拒绝 · 打回修改' }}
                  <span v-if="msg.sddStep" class="ml-1 opacity-50">步骤 {{ msg.sddStep }}</span>
                </div>
                <div class="text-[10px] leading-relaxed"
                  :class="msg.sddApproved ? 'text-emerald-200/60' : 'text-red-200/60'"
                >{{ msg.content }}</div>
              </div>
            </div>
          </div>

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

          <!-- ═══ code_tour 代码导览卡片 ═══ -->
          <div v-if="getMsgType(msg) === 'code_tour'" class="code-tour-card" :data-idx="idx">
            <div
              class="flex items-center gap-3 px-4 py-3 rounded-lg border backdrop-blur-sm"
              style="background: rgba(5, 46, 22, 0.3); border-color: rgba(52, 211, 153, 0.25);"
            >
              <div class="w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0"
                style="background: rgba(52, 211, 153, 0.1); border: 1px solid rgba(52, 211, 153, 0.3);">
                🗺️
              </div>
              <div class="flex-1 min-w-0">
                <div class="text-[11px] font-bold" style="color: #34d399;">
                  源码级导览已生成
                </div>
                <div class="text-[10px] mt-0.5" style="color: #6ee7b7; opacity: 0.7;">
                  为您生成了源码级导览，请在底部控制台点击播放查看
                </div>
              </div>
              <button
                @click="checkAndStartTour(msg, idx)"
                class="shrink-0 px-3 py-1.5 rounded-lg text-[10px] font-bold transition-all duration-200"
                style="background: rgba(52, 211, 153, 0.12); border: 1px solid rgba(52, 211, 153, 0.35); color: #34d399;"
                @mouseenter="$event.target.style.background='rgba(52,211,153,0.22)'"
                @mouseleave="$event.target.style.background='rgba(52,211,153,0.12)'"
              >
                ▶ 播放导览
              </button>
            </div>
          </div>

          <!-- ═══ chat 结构化回复 ═══ -->
          <div v-else-if="getMsgType(msg) === 'chat'" class="text-xs leading-relaxed group">
            <div class="flex items-center gap-2 mb-1.5">
              <span class="font-bold text-[11px] text-emerald-400">▸ Agent</span>
              <span class="text-geek-text-dim text-[10px]">{{ formatTime(msg.timestamp) }}</span>
              <span class="text-[10px] bg-emerald-900/40 text-emerald-400/80 px-1.5 py-0.5 rounded">回复</span>
            </div>
            <div v-if="renderedMessages[idx]" class="chat-content-block pl-4 border-l-2 border-emerald-500/30 text-geek-text/90" v-html="renderedMessages[idx]"></div>
            <div v-else class="chat-content-block pl-4 border-l-2 border-emerald-500/30 whitespace-pre-wrap break-words text-geek-text/90">
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
            <div v-if="renderedMessages[idx]" class="pl-4 border-l-2 border-geek-border/50 text-geek-text" v-html="renderedMessages[idx]"></div>
            <div v-else class="whitespace-pre-wrap break-words pl-4 border-l-2 border-geek-border/50 text-geek-text">
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

        <!-- 已激活技能 Tag -->
        <div v-if="activeTags.length" class="flex flex-wrap gap-1 mb-2">
          <template v-for="tag in activeTags" :key="tag.id">
            <span
              class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-geek-accent/15 text-geek-accent border border-geek-accent/30 select-none whitespace-nowrap"
            >
              {{ tag.icon }} {{ tag.label }}
              <button
                @click="removeTag(tag.id)"
                class="ml-0.5 text-geek-accent/50 hover:text-red-400 transition-colors"
              >✕</button>
            </span>
          </template>
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

        <div class="flex gap-2 items-center relative">
          <!-- ⚡ 技能矩阵下拉菜单 -->
          <div class="relative cap-menu-zone">
            <button
              @click="showCapMenu = !showCapMenu"
              class="px-2 py-2 rounded text-xs font-bold border transition-all duration-200 shrink-0"
              :class="activeCapCount > 0
                ? 'bg-violet-900/30 text-violet-400 border-violet-500/40 shadow-[0_0_10px_rgba(139,92,246,0.15)]'
                : 'bg-geek-bg/50 text-geek-text-dim border-geek-border hover:text-geek-text hover:border-violet-500/30'"
              title="技能矩阵"
            >
              ⚡ {{ activeCapCount > 0 ? activeCapCount : '' }}
            </button>
            <Transition name="slash-menu">
              <div
                v-if="showCapMenu"
                class="absolute bottom-full left-0 mb-1 w-72 bg-geek-surface border border-geek-border rounded-lg shadow-xl shadow-black/50 z-50 overflow-hidden backdrop-blur-sm"
              >
                <div class="px-3 py-2 border-b border-geek-border/50 bg-geek-bg/30 flex items-center justify-between">
                  <span class="text-[10px] text-geek-accent font-bold tracking-widest">⚡ CAPABILITIES</span>
                  <span class="text-[9px] text-geek-text-dim">已激活 {{ activeCapCount }}</span>
                </div>
                <div class="py-0.5 max-h-[280px] overflow-y-auto">
                  <button
                    v-for="cap in CAPABILITIES"
                    :key="cap.id"
                    @click="toggleCapability(cap)"
                    class="w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors"
                    :class="isCapActive(cap)
                      ? 'bg-violet-500/10 text-violet-300'
                      : 'text-geek-text hover:bg-geek-bg/50'"
                  >
                    <span class="text-sm shrink-0">{{ cap.icon }}</span>
                    <div class="flex-1 min-w-0">
                      <div class="text-[11px] font-bold" :class="isCapActive(cap) ? 'text-violet-300' : ''">{{ cap.label }}</div>
                      <div class="text-[9px] text-geek-text-dim truncate">{{ cap.desc }}</div>
                    </div>
                    <span
                      v-if="isCapActive(cap)"
                      class="w-2 h-2 rounded-full bg-violet-400 animate-pulse shrink-0"
                    ></span>
                  </button>
                </div>
              </div>
            </Transition>
          </div>

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
          <div class="flex-1 relative">
            <div
              class="flex items-center gap-1 bg-geek-bg border border-geek-border rounded px-3 py-2 focus-within:border-geek-accent transition-colors min-h-[32px] flex-wrap"
            >
              <template v-for="tag in activeTags" :key="tag.id">
                <span
                  class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-geek-accent/15 text-geek-accent border border-geek-accent/30 select-none whitespace-nowrap"
                >
                  {{ tag.icon }} {{ tag.label }}
                  <button
                    @click="removeTag(tag.id)"
                    class="ml-0.5 text-geek-accent/50 hover:text-red-400 transition-colors"
                  >✕</button>
                </span>
              </template>
              <input
                ref="inputEl"
                v-model="inputText"
                @keydown="handleKeydown"
                @input="onInputChange"
                @paste="handlePaste"
                type="text"
                :placeholder="activeTags.length ? '继续输入任务描述...' : (pendingQuestions.length ? '回答问题...' : (store.activeTaskId ? '在当前任务下追问...' : (pendingImages.length ? '描述你想对图片做什么...' : '描述你想要的功能，输入 / 开启技能...')))"
                class="flex-1 bg-transparent border-none outline-none text-xs text-geek-text placeholder-geek-text-dim min-w-[120px]"
                :disabled="store.isRunning && !pendingQuestions.length"
              />
            </div>

            <Transition name="slash-menu">
              <div
                v-if="showSlashMenu && filteredCommands.length"
                class="absolute bottom-full left-0 mb-1 w-64 bg-geek-surface border border-geek-border rounded-lg shadow-xl shadow-black/40 z-50 overflow-hidden backdrop-blur-sm"
              >
                <div class="px-2.5 py-1.5 border-b border-geek-border/50 bg-geek-bg/30">
                  <span class="text-[9px] text-geek-text-dim font-bold tracking-wider">⚡ 斜杠指令</span>
                </div>
                <div class="py-0.5 max-h-[200px] overflow-y-auto">
                  <button
                    v-for="(cmd, idx) in filteredCommands"
                    :key="cmd.id"
                    @click="selectCommand(cmd)"
                    @mouseenter="slashSelectedIdx = idx"
                    class="w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors"
                    :class="idx === slashSelectedIdx
                      ? 'bg-geek-accent/10 text-geek-accent'
                      : 'text-geek-text hover:bg-geek-bg/50'"
                  >
                    <span class="text-sm shrink-0">{{ cmd.icon }}</span>
                    <div class="flex-1 min-w-0">
                      <div class="text-[11px] font-bold">{{ cmd.slash }}</div>
                      <div class="text-[9px] text-geek-text-dim truncate">{{ cmd.desc }}</div>
                    </div>
                    <span
                      v-if="idx === slashSelectedIdx"
                      class="text-[9px] text-geek-accent/60 border border-geek-accent/20 rounded px-1 py-0.5"
                    >↵</span>
                  </button>
                </div>
              </div>
            </Transition>
          </div>
          <button
            @click="useSwarm = !useSwarm"
            class="px-2 py-2 rounded text-xs font-bold border transition-colors whitespace-nowrap shrink-0"
            :class="useSwarm
              ? 'bg-purple-900/30 text-purple-400 border-purple-500/40 shadow-[0_0_8px_rgba(139,92,246,0.15)]'
              : 'bg-geek-bg/50 text-geek-text-dim border-geek-border hover:text-geek-text hover:border-purple-500/30'"
            :title="useSwarm ? '🧠 深度模式：Coder-Reviewer 对抗博弈' : '⚡ 极速模式：单体 Agent'"
          >
            {{ useSwarm ? '🧠' : '⚡' }}
          </button>
          <button
            @click="store.autoApprove = !store.autoApprove"
            class="px-2 py-2 rounded text-xs font-bold border transition-colors whitespace-nowrap shrink-0"
            :class="store.autoApprove
              ? 'bg-red-900/30 text-red-400 border-red-500/40 hover:bg-red-900/50'
              : 'bg-green-900/20 text-green-400 border-green-500/30 hover:bg-green-900/40'"
            :title="store.autoApprove ? '自动执行模式：危险命令将自动放行' : '安全模式：危险命令需人工确认'"
          >
            {{ store.autoApprove ? '🚀' : '🛡️' }}
          </button>
          <button
            @click="handleSend"
            :disabled="store.isRunning && !pendingQuestions.length"
            class="px-4 py-2 bg-geek-accent/10 text-geek-accent border border-geek-accent/30 rounded text-xs font-bold hover:bg-geek-accent/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
          >
            {{ pendingQuestions.length ? '回答' : '发送' }}
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

.code-tour-card {
  margin: 4px 0;
  animation: tour-card-in 0.3s ease-out;
}

@keyframes tour-card-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.slash-menu-enter-active,
.slash-menu-leave-active {
  transition: all 0.15s ease;
}
.slash-menu-enter-from,
.slash-menu-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>

<style>
.mermaid-chart {
  margin: 10px 0;
  padding: 16px;
  background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
  border: 1px solid rgba(124, 58, 237, 0.25);
  border-radius: 8px;
  overflow-x: auto;
  position: relative;
}

.mermaid-chart::before {
  content: '◈ Mermaid';
  position: absolute;
  top: 6px;
  right: 10px;
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: rgba(167, 139, 250, 0.4);
  letter-spacing: 1px;
  text-transform: uppercase;
}

.mermaid-expand-btn {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 10;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(124, 58, 237, 0.15);
  border: 1px solid rgba(124, 58, 237, 0.3);
  border-radius: 4px;
  color: rgba(167, 139, 250, 0.7);
  font-size: 12px;
  cursor: pointer;
  opacity: 0;
  transition: all 0.2s;
}

.mermaid-chart:hover .mermaid-expand-btn {
  opacity: 1;
}

.mermaid-expand-btn:hover {
  background: rgba(124, 58, 237, 0.3);
  color: #c4b5fd;
}

.mermaid-chart svg {
  max-width: 100%;
  height: auto;
}

.mermaid-chart .node rect,
.mermaid-chart .node circle,
.mermaid-chart .node polygon {
  stroke-width: 1.5px;
}

.mermaid-chart .edgeLabel {
  font-size: 11px;
}

.mermaid-chart .label {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px;
}

.mermaid-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.mermaid-error {
  padding: 8px 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
  color: #fca5a5;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
}
</style>
