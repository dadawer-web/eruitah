<script setup>
import { ref, onMounted, computed } from 'vue'
import { useAgentStore } from '../stores/agent'

const store = useAgentStore()
const expandedTaskId = ref(null)
const taskCommits = ref({})

const deletingTaskIds = ref(new Set())

async function fetchTasks() {
  await store.fetchTaskRegistry()
}

function switchTask(task) {
  const taskId = task.id || task.task_id
  if (store.activeTaskId === taskId) return
  store.switchTask(taskId)
}

function rollbackTask(taskId) {
  store.sendSystemCommand('rollback_task', { target_task_id: taskId })
}

function rollbackStep(taskId, steps = 1) {
  store.rollbackStep(taskId, steps)
}

async function deleteTask(taskId) {
  if (deletingTaskIds.value.has(taskId)) return
  deletingTaskIds.value.add(taskId)
  try {
    await store.deleteTask(taskId)
  } catch (e) {
    console.error('[TaskList] deleteTask failed:', e)
  } finally {
    deletingTaskIds.value.delete(taskId)
  }
}

function mergeTask(taskId, force = false) {
  store.mergeTask(taskId, force)
}

function forceMergeTask(taskId) {
  store.mergeTask(taskId, true)
}

function abortMerge(taskId) {
  const task = store.taskList.find(t => t.id === taskId)
  if (task) {
    task.status = 'active'
    task.conflictFiles = []
  }
}

function revertMergedTask(taskId) {
  store.revertMergedTask(taskId)
}

function startNewTask() {
  store.startNewTask()
}

function startNewTaskBasedOn(taskId) {
  store.prepareNewTaskBasedOn(taskId)
}

async function toggleCommits(taskId) {
  if (expandedTaskId.value === taskId) {
    expandedTaskId.value = null
    return
  }
  expandedTaskId.value = taskId
  if (!taskCommits.value[taskId]) {
    store.sendSystemCommand('get_task_commits', { target_task_id: taskId })
  }
}

const activeTasks = computed(() => store.taskList.filter(t => t.status !== 'deleted'))

onMounted(fetchTasks)
</script>

<template>
  <div class="h-full flex flex-col bg-geek-surface">
    <div class="px-3 py-2 text-xs font-bold text-geek-accent uppercase tracking-wider border-b border-geek-border flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span>◈</span> Tasks
      </div>
      <button
        @click="startNewTask"
        class="text-geek-accent hover:text-geek-accent-dim transition-colors text-sm"
        title="新建任务"
      >+</button>
    </div>

    <div class="flex-1 overflow-y-auto px-1 py-1 text-xs">
      <div
        v-for="task in activeTasks"
        :key="task.id"
        class="mb-0.5"
      >
        <div
          class="flex items-center gap-1.5 px-2 py-1.5 rounded cursor-pointer hover:bg-geek-border transition-colors group"
          :class="{
            'bg-geek-border': store.activeTaskId === task.id,
            'opacity-50': task.status === 'rolled_back',
            'border border-yellow-500/30 bg-yellow-900/10': task.status === 'conflict',
            'border border-green-500/30 bg-green-900/10': task.status === 'merged',
            'border border-orange-500/30 bg-orange-900/10': task.status === 'reverted',
          }"
          @click="switchTask(task)"
        >
          <span class="text-xs shrink-0">
            <template v-if="task.status === 'merged'">✅</template>
            <template v-else-if="task.status === 'conflict'">⚠️</template>
            <template v-else-if="task.status === 'reverted'">🚑</template>
            <template v-else-if="task.status === 'rolled_back'">⏪</template>
            <template v-else-if="store.activeTaskId === task.id">🟢</template>
            <template v-else>⚪</template>
          </span>
          <div class="flex-1 min-w-0">
            <div class="truncate text-geek-text">{{ task.title }}</div>
            <div class="flex items-center gap-1 text-[10px] text-geek-text-dim">
              <span>{{ task.created_at ? new Date(task.created_at).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) : '' }}</span>
              <span v-if="task.baseTaskId" class="text-purple-400">🔗{{ task.baseTaskId.slice(5, 13) }}</span>
            </div>
          </div>

          <span v-if="task.status === 'merged'" class="text-xs px-2 py-0.5 rounded-full bg-emerald-900/30 text-emerald-400 border border-emerald-800/50 flex-shrink-0">已合入主干</span>
          <span v-else-if="task.status === 'conflict'" class="text-xs px-2 py-0.5 rounded-full bg-yellow-900/30 text-yellow-400 border border-yellow-800/50 flex-shrink-0">冲突待解决</span>
          <span v-else-if="task.status === 'reverted'" class="text-xs px-2 py-0.5 rounded-full bg-orange-900/30 text-orange-400 border border-orange-800/50 flex-shrink-0">已 revert</span>
          <span v-else-if="task.status === 'rolled_back'" class="text-xs px-2 py-0.5 rounded-full bg-gray-900/30 text-gray-400 border border-gray-800/50 flex-shrink-0">已撤销</span>
          <span v-else-if="store.activeTaskId === task.id" class="text-xs px-2 py-0.5 rounded-full bg-purple-900/30 text-purple-400 border border-purple-800/50 flex-shrink-0">当前</span>
          <span v-else class="text-xs px-2 py-0.5 rounded-full bg-blue-900/30 text-blue-400 border border-blue-800/50 flex-shrink-0">待处理</span>

          <button
            v-if="task.status === 'conflict'"
            @click.stop="forceMergeTask(task.id)"
            class="text-yellow-400 hover:text-green-400 transition-all text-[10px] px-0.5"
            title="强制合并（以任务分支为准）"
          >⚡</button>
          <button
            v-if="task.status === 'conflict'"
            @click.stop="abortMerge(task.id)"
            class="text-yellow-400 hover:text-red-400 transition-all text-[10px] px-0.5"
            title="放弃合并"
          >✕</button>
          <button
            v-if="task.status === 'active'"
            @click.stop="rollbackStep(task.id, 1)"
            class="opacity-0 group-hover:opacity-100 text-orange-400 hover:text-orange-300 transition-all text-[10px] px-0.5"
            title="撤销 Agent 上一步"
          >⏪</button>
          <button
            v-if="task.status === 'active' && store.activeTaskId !== task.id"
            @click.stop="mergeTask(task.id)"
            class="opacity-0 group-hover:opacity-100 text-green-400 hover:text-green-300 transition-all text-[10px] px-0.5"
            title="验收并合并到主干"
          >✅</button>
          <button
            v-if="task.status === 'active'"
            @click.stop="startNewTaskBasedOn(task.id)"
            class="opacity-0 group-hover:opacity-100 text-purple-400 hover:text-purple-300 transition-all text-[10px] px-0.5"
            title="基于此任务创建新任务"
          >🔗</button>
          <button
            v-if="task.status === 'merged'"
            @click.stop="revertMergedTask(task.id)"
            class="opacity-0 group-hover:opacity-100 text-orange-400 hover:text-orange-300 transition-all text-[10px] px-0.5"
            title="撤销已发布任务 (revert)"
          >🔄</button>
          <button
            @click.stop="deleteTask(task.id)"
            :disabled="deletingTaskIds.has(task.id)"
            class="opacity-0 group-hover:opacity-100 transition-all text-[10px] px-0.5"
            :class="deletingTaskIds.has(task.id) ? 'text-geek-text-dim cursor-wait' : 'text-geek-text-dim hover:text-red-400'"
            :title="deletingTaskIds.has(task.id) ? '删除中...' : '删除此任务'"
          >{{ deletingTaskIds.has(task.id) ? '⏳' : '✕' }}</button>

          <button
            @click.stop="toggleCommits(task.id)"
            class="text-geek-text-dim hover:text-geek-accent transition-colors text-[10px] px-0.5"
            :class="{ 'text-geek-accent': expandedTaskId === task.id }"
            title="查看提交历史"
          >📋</button>
        </div>

        <div
          v-if="task.status === 'conflict'"
          class="ml-5 mr-1 mt-0.5 mb-1 border-l-2 border-yellow-700 pl-2 py-1 space-y-0.5"
        >
          <template v-if="task.conflictFiles && task.conflictFiles.length">
            <div class="text-[10px] text-yellow-400 font-bold mb-0.5">冲突文件:</div>
            <div
              v-for="file in task.conflictFiles"
              :key="file"
              class="flex items-center gap-1 text-[10px] text-yellow-300/80"
            >
              <span>⚡</span>
              <span class="truncate">{{ file }}</span>
            </div>
          </template>
          <template v-else>
            <div class="text-[10px] text-yellow-400/70 italic">合并时检测到冲突，请选择处理方式</div>
          </template>
          <div class="flex gap-2 mt-1">
            <button
              @click.stop="forceMergeTask(task.id)"
              class="text-[10px] px-1.5 py-0.5 rounded bg-yellow-900/40 text-yellow-300 hover:bg-yellow-800/60 border border-yellow-700/50 transition-colors"
            >⚡ 强制合并（以任务为准）</button>
            <button
              @click.stop="abortMerge(task.id)"
              class="text-[10px] px-1.5 py-0.5 rounded bg-gray-800/40 text-gray-400 hover:bg-gray-700/60 border border-gray-700/50 transition-colors"
            >✕ 放弃合并</button>
          </div>
        </div>

        <div
          v-if="expandedTaskId === task.id"
          class="ml-5 mr-1 mt-0.5 mb-1 border-l-2 border-geek-border pl-2 py-1 space-y-0.5"
        >
          <div
            v-for="commit in (store.checkpointList.length && expandedTaskId === task.id ? store.checkpointList : [])"
            :key="commit.hash"
            class="flex items-center gap-1 text-[10px] text-geek-text-dim hover:text-geek-text transition-colors"
          >
            <span class="text-geek-accent font-mono">{{ commit.hash }}</span>
            <span class="truncate flex-1">{{ commit.message }}</span>
            <span class="shrink-0">{{ commit.date ? commit.date.split(' ')[0] : '' }}</span>
          </div>
          <div v-if="!store.checkpointList.length" class="text-[10px] text-geek-text-dim italic">
            点击 📋 加载提交历史...
          </div>
        </div>

      </div>
      <div v-if="!activeTasks.length" class="px-3 py-4 text-geek-text-dim text-xs italic text-center">
        暂无任务，输入指令开始
      </div>
    </div>
  </div>
</template>
