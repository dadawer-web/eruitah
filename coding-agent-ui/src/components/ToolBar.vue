<script setup>
import { ref, computed } from 'vue'
import { useAgentStore } from '../stores/agent'
import CareerDashboard from './CareerDashboard.vue'
import KnowledgeGraph from './KnowledgeGraph.vue'

const store = useAgentStore()

const showGitPanel = ref(false)
const showRewindPanel = ref(false)
const showCostPanel = ref(false)
const showMcpPanel = ref(false)
const showCareerPanel = ref(false)
const showKnowledgePanel = ref(false)

const gitAction = ref('status')
const gitFilePath = ref('')
const gitCommitMsg = ref('')
const gitLogCount = ref(10)

const rewindSteps = ref(1)
const loadingTasks = ref(false)
const showRollbackDiff = ref(false)

const costInfo = computed(() => store.costInfo)
const lastRollbackInfo = computed(() => store.lastRollbackInfo)

function sendQuickTask(task) {
  store.sendTask(task)
}

function executeGitAction() {
  let task = ''
  switch (gitAction.value) {
    case 'status': task = '查看当前 git 状态'; break
    case 'diff': task = gitFilePath.value ? `查看文件 ${gitFilePath.value} 的 git diff` : '查看所有未暂存的 git diff'; break
    case 'log': task = `查看最近 ${gitLogCount.value} 条 git 日志`; break
    case 'commit':
      if (!gitCommitMsg.value) return
      task = `提交当前更改，提交信息: ${gitCommitMsg.value}`
      break
  }
  if (task) { sendQuickTask(task); showGitPanel.value = false }
}

function rollbackTask(targetTaskId) {
  store.sendSystemCommand('rollback_task', { target_task_id: targetTaskId })
  showRollbackDiff.value = true
  showRewindPanel.value = false
}

function runAutoTest() {
  if (!store.currentFile) return
  if (store.currentIsDir) {
    sendQuickTask(`对 ${store.currentFile} 目录下的所有测试文件运行自动化测试并反馈结果`)
  } else {
    sendQuickTask(`对 ${store.currentFile} 运行自动化测试并反馈结果`)
  }
}

function generateTest() {
  if (!store.currentFile) return
  if (store.currentIsDir) {
    sendQuickTask(`为 ${store.currentFile} 目录下的所有代码文件自动生成对应的测试文件并运行测试`)
  } else {
    sendQuickTask(`为 ${store.currentFile} 自动生成测试文件并运行测试`)
  }
}

function checkCoverage() {
  sendQuickTask('检查当前项目的测试覆盖率')
}

function showProjectOverview() {
  sendQuickTask('查看项目概览')
}

function showFileOutline() {
  if (!store.currentFile) return
  sendQuickTask(`查看文件 ${store.currentFile} 的大纲结构`)
}

function listCheckpoints() {
  store.sendSystemCommand('list_checkpoints')
}

function clearCheckpoints() {
  store.sendSystemCommand('clear_checkpoints')
}

function listMcpServers() {
  store.listMcpServices()
  showMcpPanel.value = true
}
</script>

<template>
  <div class="flex items-center gap-1 px-2 py-1 bg-geek-surface border-b border-geek-border overflow-x-auto">
    <div class="flex items-center gap-1 mr-2">
      <span class="text-geek-accent text-xs font-bold">◈</span>
      <span class="text-geek-text-dim text-[10px]">TOOLS</span>
    </div>

    <div v-if="store.currentTaskName" class="flex items-center gap-1 px-2 py-0.5 bg-cyan-500/10 border border-cyan-500/30 rounded text-[10px] text-cyan-400 max-w-[200px]">
      <span class="shrink-0">📦</span>
      <span class="truncate">{{ store.currentTaskName }}</span>
    </div>

    <button @click="showProjectOverview" :disabled="!store.connected || store.isRunning" class="px-2 py-1 bg-geek-bg hover:bg-geek-accent/10 text-geek-text-dim hover:text-geek-accent border border-geek-border rounded text-[10px] transition-colors disabled:opacity-30 whitespace-nowrap" title="项目概览">📋 概览</button>

    <button @click="showFileOutline" :disabled="!store.currentFile || !store.connected || store.isRunning" class="px-2 py-1 bg-geek-bg hover:bg-geek-accent/10 text-geek-text-dim hover:text-geek-accent border border-geek-border rounded text-[10px] transition-colors disabled:opacity-30 whitespace-nowrap" title="文件大纲">🗂️ 大纲</button>

    <div class="w-px h-4 bg-geek-border"></div>

    <button @click="runAutoTest" :disabled="!store.currentFile || !store.connected || store.isRunning" class="px-2 py-1 bg-geek-bg hover:bg-green-500/10 text-geek-text-dim hover:text-green-400 border border-geek-border rounded text-[10px] transition-colors disabled:opacity-30 whitespace-nowrap" title="运行测试">🧪 测试</button>

    <button @click="generateTest" :disabled="!store.currentFile || !store.connected || store.isRunning" class="px-2 py-1 bg-geek-bg hover:bg-green-500/10 text-geek-text-dim hover:text-green-400 border border-geek-border rounded text-[10px] transition-colors disabled:opacity-30 whitespace-nowrap" title="自动生成测试">✨ 生成测试</button>

    <button @click="checkCoverage" :disabled="!store.connected || store.isRunning" class="px-2 py-1 bg-geek-bg hover:bg-green-500/10 text-geek-text-dim hover:text-green-400 border border-geek-border rounded text-[10px] transition-colors disabled:opacity-30 whitespace-nowrap" title="测试覆盖率">📊 覆盖率</button>

    <div class="w-px h-4 bg-geek-border"></div>

    <button @click="showGitPanel = !showGitPanel" class="px-2 py-1 bg-geek-bg hover:bg-orange-500/10 text-geek-text-dim hover:text-orange-400 border border-geek-border rounded text-[10px] transition-colors whitespace-nowrap" :class="{ 'bg-orange-500/10 text-orange-400 border-orange-500/30': showGitPanel }" title="Git 操作">🔀 Git</button>

    <button @click="showRewindPanel = !showRewindPanel" class="px-2 py-1 bg-geek-bg hover:bg-purple-500/10 text-geek-text-dim hover:text-purple-400 border border-geek-border rounded text-[10px] transition-colors whitespace-nowrap" :class="{ 'bg-purple-500/10 text-purple-400 border-purple-500/30': showRewindPanel }" title="任务历史与回退">⏪ 任务</button>

    <button @click="showCostPanel = !showCostPanel" class="px-2 py-1 bg-geek-bg hover:bg-yellow-500/10 text-geek-text-dim hover:text-yellow-400 border border-geek-border rounded text-[10px] transition-colors whitespace-nowrap" :class="{ 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30': showCostPanel }" title="费用追踪">💰 费用</button>

    <div class="w-px h-4 bg-geek-border"></div>

    <button @click="listMcpServers" :disabled="!store.connected" class="px-2 py-1 bg-geek-bg hover:bg-blue-500/10 text-geek-text-dim hover:text-blue-400 border border-geek-border rounded text-[10px] transition-colors disabled:opacity-30 whitespace-nowrap" :class="{ 'bg-blue-500/10 text-blue-400 border-blue-500/30': showMcpPanel }" title="MCP 服务（不走 Agent）">🔌 MCP</button>

    <button @click="listCheckpoints" :disabled="!store.connected || store.isRunning" class="px-2 py-1 bg-geek-bg hover:bg-cyan-500/10 text-geek-text-dim hover:text-cyan-400 border border-geek-border rounded text-[10px] transition-colors disabled:opacity-30 whitespace-nowrap" title="检查点列表">📌 检查点</button>

    <div class="w-px h-4 bg-geek-border"></div>

    <button @click="showCareerPanel = !showCareerPanel; store.hasNewCareerAdvice = false" class="relative px-2 py-1 bg-geek-bg hover:bg-emerald-500/10 text-geek-text-dim hover:text-emerald-400 border border-geek-border rounded text-[10px] transition-colors whitespace-nowrap" :class="{ 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30': showCareerPanel }" title="职业档案 & 简历素材">
      🎓 档案
      <span v-if="store.hasNewCareerAdvice" class="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-500 rounded-full shadow-[0_0_6px_rgba(239,68,68,0.7)] animate-pulse"></span>
    </button>

    <button @click="showKnowledgePanel = !showKnowledgePanel" class="px-2 py-1 bg-geek-bg hover:bg-cyan-500/10 text-geek-text-dim hover:text-cyan-400 border border-geek-border rounded text-[10px] transition-colors whitespace-nowrap" :class="{ 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30': showKnowledgePanel }" title="知识图谱 & 技能脉络">🌳 图谱</button>

    <div class="flex-1"></div>

    <div v-if="store.isRunning" class="flex items-center gap-2">
      <div class="flex items-center gap-1 text-[10px] text-yellow-400">
        <span class="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse"></span>
        {{ store.status || '运行中' }}
      </div>
      <button @click="store.stopAgent()" class="px-2 py-0.5 bg-red-600/80 hover:bg-red-600 text-white rounded text-[10px] font-bold transition-colors flex items-center gap-1">
        <span class="text-xs">⏹</span> 停止
      </button>
    </div>
    <div v-else-if="store.connected" class="flex items-center gap-1 text-[10px] text-geek-accent">
      <span class="w-1.5 h-1.5 rounded-full bg-geek-accent"></span>
      就绪
    </div>
    <div v-else class="flex items-center gap-1 text-[10px] text-red-400">
      <span class="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse"></span>
      未连接
    </div>

    <Teleport to="body">
      <div v-if="showGitPanel" class="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center" @click.self="showGitPanel = false">
        <div class="bg-geek-surface border border-geek-border rounded-lg w-[400px] shadow-2xl">
          <div class="flex items-center justify-between px-4 py-3 border-b border-geek-border">
            <span class="text-sm font-bold text-orange-400">🔀 Git 操作</span>
            <button @click="showGitPanel = false" class="text-geek-text-dim hover:text-geek-text">×</button>
          </div>
          <div class="p-4 space-y-3">
            <div>
              <label class="text-xs text-geek-text-dim mb-1 block">操作类型</label>
              <select v-model="gitAction" class="w-full bg-geek-bg border border-geek-border rounded px-2 py-1.5 text-xs text-geek-text">
                <option value="status">查看状态</option>
                <option value="diff">查看差异</option>
                <option value="log">查看日志</option>
                <option value="commit">提交更改</option>
              </select>
            </div>
            <div v-if="gitAction === 'diff'">
              <label class="text-xs text-geek-text-dim mb-1 block">文件路径（可选）</label>
              <input v-model="gitFilePath" type="text" placeholder="留空查看所有差异" class="w-full bg-geek-bg border border-geek-border rounded px-2 py-1.5 text-xs text-geek-text placeholder-geek-text-dim focus:outline-none focus:border-geek-accent" />
            </div>
            <div v-if="gitAction === 'log'">
              <label class="text-xs text-geek-text-dim mb-1 block">日志条数</label>
              <input v-model.number="gitLogCount" type="number" min="1" max="50" class="w-full bg-geek-bg border border-geek-border rounded px-2 py-1.5 text-xs text-geek-text focus:outline-none focus:border-geek-accent" />
            </div>
            <div v-if="gitAction === 'commit'">
              <label class="text-xs text-geek-text-dim mb-1 block">提交信息</label>
              <input v-model="gitCommitMsg" type="text" placeholder="输入提交信息..." class="w-full bg-geek-bg border border-geek-border rounded px-2 py-1.5 text-xs text-geek-text placeholder-geek-text-dim focus:outline-none focus:border-geek-accent" />
            </div>
            <button @click="executeGitAction" :disabled="gitAction === 'commit' && !gitCommitMsg" class="w-full px-4 py-2 bg-orange-600/80 hover:bg-orange-600 text-white rounded text-xs font-bold transition-colors disabled:opacity-50">执行</button>
          </div>
        </div>
      </div>

      <div v-if="showRewindPanel" class="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center" @click.self="showRewindPanel = false">
        <div class="bg-geek-surface border border-geek-border rounded-lg w-[450px] shadow-2xl max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between px-4 py-3 border-b border-geek-border shrink-0">
            <span class="text-sm font-bold text-purple-400">⏪ 平行宇宙</span>
            <div class="flex items-center gap-2">
              <button @click="store.startNewTask(); showRewindPanel = false" class="text-[10px] px-2 py-0.5 bg-purple-600/60 hover:bg-purple-600 text-white rounded font-bold transition-colors">➕ 新任务</button>
              <button @click="showRewindPanel = false" class="text-geek-text-dim hover:text-geek-text">×</button>
            </div>
          </div>
          <div class="p-3 space-y-2 overflow-y-auto flex-1">
            <div class="text-[10px] text-geek-text-dim">每个任务 = 一个平行宇宙，记忆隔离、回退隔离。点击任务切换视图。</div>

            <div v-if="store.taskList.length === 0" class="text-center py-4 text-xs text-geek-text-dim italic">暂无任务记录</div>

            <div v-else class="space-y-1.5">
              <div v-for="task in store.taskList" :key="task.id"
                class="flex items-center gap-2 px-3 py-2 rounded border transition-colors cursor-pointer"
                :class="{
                  'bg-purple-500/10 border-purple-500/30': store.activeTaskId === task.id,
                  'bg-geek-bg/50 border-geek-border/50 opacity-60': task.status === 'rolled_back',
                  'bg-geek-bg border-geek-border hover:border-purple-500/30': store.activeTaskId !== task.id && task.status !== 'rolled_back',
                }"
                @click="store.switchTask(task.id); showRewindPanel = false">
                <span class="shrink-0 text-xs">{{ task.status === 'rolled_back' ? '⏪' : store.activeTaskId === task.id ? '🟢' : '⚪' }}</span>
                <div class="flex-1 min-w-0">
                  <div class="text-xs text-geek-text truncate">{{ task.title }}</div>
                  <div class="text-[10px] text-geek-text-dim">{{ new Date(task.created_at).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) }}</div>
                </div>
                <button v-if="task.status === 'active' && store.activeTaskId !== task.id"
                  @click.stop="rollbackTask(task.id)"
                  class="shrink-0 px-2 py-0.5 bg-red-600/60 hover:bg-red-600 text-white rounded text-[10px] font-bold transition-colors"
                  title="回退此任务">⏪</button>
                <span v-else-if="task.status === 'rolled_back'" class="shrink-0 text-[10px] text-geek-text-dim">已撤销</span>
                <span v-else-if="store.activeTaskId === task.id" class="shrink-0 text-[10px] text-purple-400">当前</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="showCostPanel" class="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center" @click.self="showCostPanel = false">
        <div class="bg-geek-surface border border-geek-border rounded-lg w-[400px] shadow-2xl">
          <div class="flex items-center justify-between px-4 py-3 border-b border-geek-border">
            <span class="text-sm font-bold text-yellow-400">💰 费用追踪</span>
            <button @click="showCostPanel = false" class="text-geek-text-dim hover:text-geek-text">×</button>
          </div>
          <div class="p-4 space-y-3">
            <div v-if="costInfo" class="space-y-2">
              <div class="flex justify-between text-xs">
                <span class="text-geek-text-dim">总费用</span>
                <span class="text-yellow-400 font-bold">${{ costInfo.total_cost?.toFixed(4) || '0.0000' }}</span>
              </div>
              <div class="flex justify-between text-xs">
                <span class="text-geek-text-dim">预算上限</span>
                <span class="text-geek-text">${{ costInfo.budget_limit?.toFixed(2) || '5.00' }}</span>
              </div>
              <div class="flex justify-between text-xs">
                <span class="text-geek-text-dim">剩余预算</span>
                <span :class="(costInfo.remaining || 5) < 1 ? 'text-red-400' : 'text-green-400'">${{ costInfo.remaining?.toFixed(4) || '5.0000' }}</span>
              </div>
              <div class="flex justify-between text-xs">
                <span class="text-geek-text-dim">API 调用次数</span>
                <span class="text-geek-text">{{ costInfo.api_calls || 0 }}</span>
              </div>
              <div class="flex justify-between text-xs">
                <span class="text-geek-text-dim">Token 消耗</span>
                <span class="text-geek-text">{{ costInfo.total_tokens?.toLocaleString() || 0 }}</span>
              </div>
              <div class="w-full bg-geek-bg rounded-full h-2 mt-2">
                <div class="h-2 rounded-full transition-all" :class="(costInfo.usage_percent || 0) > 80 ? 'bg-red-500' : (costInfo.usage_percent || 0) > 50 ? 'bg-yellow-500' : 'bg-green-500'" :style="{ width: Math.min(costInfo.usage_percent || 0, 100) + '%' }"></div>
              </div>
              <div class="text-[10px] text-geek-text-dim text-center">{{ (costInfo.usage_percent || 0).toFixed(1) }}% 预算已使用</div>
            </div>
            <div v-else class="text-xs text-geek-text-dim text-center py-4">暂无费用数据，发送任务后将自动追踪</div>
          </div>
        </div>
      </div>

      <div v-if="showMcpPanel" class="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center" @click.self="showMcpPanel = false">
        <div class="bg-geek-surface border border-geek-border rounded-lg w-[500px] shadow-2xl max-h-[70vh] flex flex-col">
          <div class="flex items-center justify-between px-4 py-3 border-b border-geek-border shrink-0">
            <span class="text-sm font-bold text-blue-400">🔌 MCP 服务</span>
            <div class="flex items-center gap-2">
              <button @click="listMcpServers" class="text-[10px] px-2 py-0.5 bg-blue-600/60 hover:bg-blue-600 text-white rounded font-bold transition-colors">🔄 刷新</button>
              <button @click="showMcpPanel = false" class="text-geek-text-dim hover:text-geek-text">×</button>
            </div>
          </div>
          <div class="p-4 overflow-y-auto flex-1">
            <div v-if="store.mcpServices" class="text-xs text-geek-text whitespace-pre-wrap font-mono leading-relaxed">{{ store.mcpServices }}</div>
            <div v-else class="text-xs text-geek-text-dim text-center py-4">点击「刷新」获取 MCP 服务列表</div>
          </div>
          <div class="px-4 py-2 border-t border-geek-border shrink-0">
            <div class="text-[10px] text-geek-text-dim">⚡ 此操作直接查询后端，不经过 Agent（零 Token 消耗）</div>
          </div>
        </div>
      </div>

      <div v-if="showRollbackDiff && lastRollbackInfo" class="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center" @click.self="showRollbackDiff = false">
        <div class="bg-geek-surface border border-geek-border rounded-lg w-[600px] shadow-2xl max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between px-4 py-3 border-b border-geek-border shrink-0">
            <span class="text-sm font-bold text-purple-400">⏪ 回退审计日志 (Diff Audit)</span>
            <div class="flex items-center gap-2">
              <button @click="showRollbackDiff = false" class="text-geek-text-dim hover:text-geek-text">×</button>
            </div>
          </div>
          <div class="p-4 overflow-y-auto flex-1 space-y-3">
            <div v-if="lastRollbackInfo.diff_audit" class="text-xs text-geek-text whitespace-pre-wrap font-mono leading-relaxed bg-geek-bg/50 p-3 rounded border border-geek-border/50">{{ lastRollbackInfo.diff_audit }}</div>
            <div v-if="lastRollbackInfo.reverted_files && lastRollbackInfo.reverted_files.length > 0" class="space-y-1">
              <div class="text-xs font-bold text-geek-text-dim mb-2">📂 撤销的文件变更:</div>
              <div v-for="f in lastRollbackInfo.reverted_files" :key="f.file" class="flex items-center gap-2 text-xs px-2 py-1 rounded" :class="f.status === 'M' ? 'bg-yellow-500/10 text-yellow-400' : f.status === 'A' ? 'bg-red-500/10 text-red-400' : f.status === 'D' ? 'bg-blue-500/10 text-blue-400' : 'bg-geek-bg text-geek-text-dim'">
                <span>{{ f.icon }}</span>
                <span class="font-mono w-12 shrink-0">{{ f.status_label }}</span>
                <span class="font-mono truncate">{{ f.file }}</span>
              </div>
            </div>
            <div v-if="lastRollbackInfo.detailed_diff" class="mt-3">
              <div class="text-xs font-bold text-geek-text-dim mb-2">📝 详细 Diff:</div>
              <pre class="text-[10px] font-mono leading-relaxed bg-geek-bg p-3 rounded border border-geek-border/50 overflow-x-auto max-h-[300px] overflow-y-auto whitespace-pre-wrap"><code>{{ lastRollbackInfo.detailed_diff }}</code></pre>
            </div>
          </div>
          <div class="px-4 py-2 border-t border-geek-border shrink-0">
            <div class="text-[10px] text-geek-text-dim">⏪ 回退前自动捕获的 Git Diff 审计日志，确保操作透明可追溯</div>
          </div>
        </div>
      </div>
    </Teleport>

    <CareerDashboard :visible="showCareerPanel" @close="showCareerPanel = false" />
    <KnowledgeGraph :visible="showKnowledgePanel" @close="showKnowledgePanel = false" />
  </div>
</template>
