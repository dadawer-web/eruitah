<script setup>
import { ref, computed } from 'vue'
import { useAgentStore } from '../stores/agent'

const store = useAgentStore()

const showCostPanel = ref(false)
const showMcpPanel = ref(false)

const costInfo = computed(() => store.costInfo)

function sendQuickTask(task) {
  store.sendTask(task)
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

    <button @click="showCostPanel = !showCostPanel" class="px-2 py-1 bg-geek-bg hover:bg-yellow-500/10 text-geek-text-dim hover:text-yellow-400 border border-geek-border rounded text-[10px] transition-colors whitespace-nowrap" :class="{ 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30': showCostPanel }" title="费用追踪">💰 费用</button>

    <button @click="listMcpServers" :disabled="!store.connected" class="px-2 py-1 bg-geek-bg hover:bg-blue-500/10 text-geek-text-dim hover:text-blue-400 border border-geek-border rounded text-[10px] transition-colors disabled:opacity-30 whitespace-nowrap" :class="{ 'bg-blue-500/10 text-blue-400 border-blue-500/30': showMcpPanel }" title="MCP 服务（不走 Agent）">🔌 MCP</button>

    <div class="w-px h-4 bg-geek-border"></div>

    <button
      @click="store.generateGraph()"
      :disabled="!store.connected || store.codeGraphLoading"
      class="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm text-gray-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
      :class="{ 'bg-gray-600': store.codeGraphVisible }"
      title="解析项目架构图"
    >
      <svg v-if="!store.codeGraphLoading" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="2" />
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
      </svg>
      <svg v-else class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round" />
      </svg>
      <span>{{ store.codeGraphLoading ? '解析中...' : '架构图' }}</span>
    </button>

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
    </Teleport>
  </div>
</template>
