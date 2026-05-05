<script setup>
import { ref, nextTick, watch, computed } from 'vue'
import { useAgentStore } from '../stores/agent'

const store = useAgentStore()
const inputText = ref('')
const chatContainer = ref(null)
const showHistory = ref(true)

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

function handleUndoToTurn(turn, taskId) {
  store.previewRollback(taskId, 1, turn)
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
        <div
          v-for="(msg, idx) in store.messages"
          :key="idx"
          class="text-xs leading-relaxed group"
          :class="{
            'text-geek-accent': msg.role === 'user',
            'text-geek-text': msg.role === 'agent' && !msg.isError,
            'text-red-400': msg.isError,
            'text-green-400': msg.isFinish,
          }"
        >
          <div class="flex items-center gap-2 mb-1">
            <span
              class="font-bold text-[11px]"
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
            <span v-if="msg.isFinish" class="text-[10px] bg-green-900/50 text-green-400 px-1.5 py-0.5 rounded">完成</span>
            <span v-if="msg.isError" class="text-[10px] bg-red-900/50 text-red-400 px-1.5 py-0.5 rounded">错误</span>
            <span v-if="msg.isQuestion && !msg.answered" class="text-[10px] bg-yellow-900/50 text-yellow-400 px-1.5 py-0.5 rounded">待回答</span>
            <button
              v-if="msg.role === 'agent' && !msg.isError && !msg.isFinish && store.activeTaskId && idx > 0"
              @click="handleUndoToTurn(Math.ceil(idx / 2), store.activeTaskId)"
              class="ml-auto opacity-0 group-hover:opacity-100 transition-opacity text-[10px] px-2 py-0.5 rounded bg-red-900/30 text-red-400 border border-red-500/30 hover:bg-red-900/50 hover:border-red-500/50"
              title="撤销至此消息之前的状态"
            >
              ⏪ 撤销至此
            </button>
          </div>
          <div class="whitespace-pre-wrap break-words pl-4 border-l-2 border-geek-border/50">
            {{ msg.content }}
          </div>
          <div v-if="msg.isQuestion && !msg.answered" class="mt-1 pl-4 text-yellow-400 text-[10px]">
            ↑ 请在下方输入框回答此问题
          </div>
          <div v-if="msg.answered" class="mt-1 pl-4 text-green-400 text-[10px]">
            已回答: {{ msg.answer }}
          </div>
        </div>
        <div v-if="!store.messages.length" class="text-geek-text-dim text-xs italic py-8 text-center">
          {{ store.activeTaskId ? '在当前任务下继续追问...' : '发送任务给 AI Agent 开始编程...' }}
        </div>
      </div>

      <!-- 输入区 -->
      <div class="p-3 border-t border-geek-border bg-geek-bg/20">
        <div class="text-[10px] text-geek-text-dim mb-1.5 truncate" v-if="pendingQuestions.length">
          ⚠️ 有 {{ pendingQuestions.length }} 个问题等待回答
        </div>
        <div class="flex gap-2 items-center">
          <input
            v-model="inputText"
            @keydown="handleKeydown"
            type="text"
            :placeholder="pendingQuestions.length ? '回答问题...' : (store.activeTaskId ? '在当前任务下追问...' : '描述你想要的功能，开启新任务...')"
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
</style>
