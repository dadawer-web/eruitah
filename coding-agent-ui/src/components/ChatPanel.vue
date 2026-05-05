<script setup>
import { ref, nextTick, watch, computed } from 'vue'
import { useAgentStore } from '../stores/agent'

const store = useAgentStore()
const inputText = ref('')
const chatContainer = ref(null)

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
  if (!text) return

  const pendingQuestion = pendingQuestions.value[0]
  if (pendingQuestion) {
    store.answerQuestion(pendingQuestion.questionId, text)
  } else {
    store.sendTask(text)
  }
  inputText.value = ''
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
</script>

<template>
  <div class="h-full flex flex-col bg-geek-surface border-t border-geek-border">
    <div class="px-3 py-2 text-xs font-bold text-geek-accent uppercase tracking-wider border-b border-geek-border flex items-center gap-2">
      <span>◈</span> Chat
      <span v-if="store.isRunning" class="ml-auto text-yellow-400 animate-pulse text-[10px]">{{ store.status || '运行中...' }}</span>
      <span v-else-if="store.currentTool" class="ml-auto text-blue-400 text-[10px]">执行: {{ store.currentTool.name }}</span>
    </div>

    <div ref="chatContainer" class="flex-1 overflow-y-auto px-3 py-2 space-y-2">
      <div
        v-for="(msg, idx) in store.messages"
        :key="idx"
        class="text-xs leading-relaxed"
        :class="{
          'text-geek-accent': msg.role === 'user',
          'text-geek-text': msg.role === 'agent' && !msg.isError,
          'text-red-400': msg.isError,
          'text-green-400': msg.isFinish,
        }"
      >
        <div class="flex items-center gap-2 mb-1">
          <span
            class="font-bold"
            :class="{
              'text-geek-accent': msg.role === 'user',
              'text-blue-400': msg.role === 'agent' && !msg.isError && !msg.isFinish,
              'text-red-400': msg.isError,
              'text-green-400': msg.isFinish,
            }"
          >
            {{ msg.role === 'user' ? '▸ You' : '▸ Agent' }}
          </span>
          <span class="text-geek-text-dim text-[10px]">{{ formatTime(msg.timestamp) }}</span>
          <span v-if="msg.isFinish" class="text-[10px] bg-green-900/50 text-green-400 px-1 rounded">完成</span>
          <span v-if="msg.isError" class="text-[10px] bg-red-900/50 text-red-400 px-1 rounded">错误</span>
          <span v-if="msg.isQuestion && !msg.answered" class="text-[10px] bg-yellow-900/50 text-yellow-400 px-1 rounded">待回答</span>
        </div>
        <div class="whitespace-pre-wrap break-words pl-4 border-l-2 border-geek-border">
          {{ msg.content }}
        </div>
        <div v-if="msg.isQuestion && !msg.answered" class="mt-1 pl-4 text-yellow-400 text-[10px]">
          ↑ 请在下方输入框回答此问题
        </div>
        <div v-if="msg.answered" class="mt-1 pl-4 text-green-400 text-[10px]">
          已回答: {{ msg.answer }}
        </div>
      </div>
      <div v-if="!store.messages.length" class="text-geek-text-dim text-xs italic py-4 text-center">
        {{ store.activeTaskId ? '在当前任务下继续追问...' : '发送任务给 AI Agent 开始编程...' }}
      </div>
    </div>

    <div class="p-2 border-t border-geek-border">
      <div class="text-[10px] text-geek-text-dim mb-1 truncate" v-if="pendingQuestions.length">
        ⚠️ 有 {{ pendingQuestions.length }} 个问题等待回答
      </div>
      <div class="flex gap-2 items-center">
        <input
          v-model="inputText"
          @keydown="handleKeydown"
          type="text"
          :placeholder="pendingQuestions.length ? '回答问题...' : (store.activeTaskId ? '在当前任务下追问...' : '描述你想要的功能，开启新任务...')"
          class="flex-1 bg-geek-bg border border-geek-border rounded px-3 py-1.5 text-xs text-geek-text placeholder-geek-text-dim focus:outline-none focus:border-geek-accent transition-colors"
          :disabled="store.isRunning && !pendingQuestions.length"
        />
        <button
          @click="handleSend"
          :disabled="store.isRunning && !pendingQuestions.length"
          class="px-3 py-1.5 bg-geek-accent/10 text-geek-accent border border-geek-accent/30 rounded text-xs font-bold hover:bg-geek-accent/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ pendingQuestions.length ? '回答' : '发送' }}
        </button>
        <button
          @click="store.autoApprove = !store.autoApprove"
          class="px-2 py-1.5 rounded text-xs font-bold border transition-colors whitespace-nowrap"
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
</template>
