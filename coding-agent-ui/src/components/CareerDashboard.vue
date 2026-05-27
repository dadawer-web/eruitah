<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useAgentStore } from '../stores/agent'
import * as echarts from 'echarts'

const store = useAgentStore()

const props = defineProps({
  visible: Boolean
})
const emit = defineEmits(['close'])

const records = ref([])
const loading = ref(false)
const exportMsg = ref('')
const serverLoading = ref(false)
const serverError = ref('')
const serverProfile = ref(null)

let radarChart = null
const radarContainer = ref(null)

const hasServerData = computed(() => {
  if (!serverProfile.value) return false
  const p = serverProfile.value
  return (p.resumeHighlight || p.resume_highlight || '').length > 0
    || (p.learningAdvice || p.learning_advice || '').length > 0
    || (p.nextSuggestion || p.next_suggestion || '').length > 0
    || (p.extractedSkills || p.extracted_skills || p.skills || []).length > 0
})

const allSkills = computed(() => {
  const all = new Set()
  if (serverProfile.value) {
    const srv = serverProfile.value.extractedSkills || serverProfile.value.extracted_skills || serverProfile.value.skills || []
    srv.forEach(s => all.add(s))
  }
  records.value.forEach(r => {
    (r.extracted_skills || r.skills || []).forEach(s => all.add(s))
  })
  return [...all].sort()
})

const skillBadges = computed(() => allSkills.value)

const totalHighlights = computed(() => records.value.filter(r => r.resume_highlight).length)

const resumeHighlightText = computed(() => {
  return serverProfile.value?.resumeHighlight || serverProfile.value?.resume_highlight || ''
})

const nextSuggestionText = computed(() => {
  return serverProfile.value?.nextSuggestion || serverProfile.value?.next_suggestion || serverProfile.value?.learningAdvice || serverProfile.value?.learning_advice || ''
})

function _hashCode(str) {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i)
    hash |= 0
  }
  return hash
}

const GRAPH_COLORS = [
  { fill: 'rgba(56, 189, 248, 0.55)', border: '#38bdf8', glow: 'rgba(56, 189, 248, 0.8)' },
  { fill: 'rgba(129, 140, 248, 0.50)', border: '#818cf8', glow: 'rgba(129, 140, 248, 0.8)' },
  { fill: 'rgba(52, 211, 153, 0.50)', border: '#34d399', glow: 'rgba(52, 211, 153, 0.8)' },
  { fill: 'rgba(251, 191, 36, 0.45)', border: '#fbbf24', glow: 'rgba(251, 191, 36, 0.7)' },
  { fill: 'rgba(244, 114, 182, 0.45)', border: '#f472b6', glow: 'rgba(244, 114, 182, 0.7)' },
  { fill: 'rgba(167, 139, 250, 0.50)', border: '#a78bfa', glow: 'rgba(167, 139, 250, 0.8)' },
]

function initRadarChart() {
  if (!radarContainer.value) return

  if (radarChart) {
    radarChart.dispose()
    radarChart = null
  }

  radarChart = echarts.init(radarContainer.value, null, { renderer: 'canvas' })

  const skills = allSkills.value
  if (skills.length === 0) {
    radarChart.setOption({
      backgroundColor: 'transparent',
      graphic: [{
        type: 'text',
        left: 'center',
        top: 'center',
        style: {
          text: '🔒 完成任务后解锁技能星图',
          fill: '#737373',
          fontSize: 13,
          fontFamily: 'system-ui',
        }
      }]
    }, true)
    return
  }

  const nodes = skills.map((name, idx) => {
    const h = Math.abs(_hashCode(name))
    const size = 40 + (h % 41)
    const colorSet = GRAPH_COLORS[idx % GRAPH_COLORS.length]
    return {
      name,
      symbolSize: size,
      category: idx % GRAPH_COLORS.length,
      itemStyle: {
        color: new echarts.graphic.RadialGradient(0.3, 0.3, 1, [
          { offset: 0, color: colorSet.border },
          { offset: 1, color: colorSet.fill },
        ]),
        borderColor: colorSet.border,
        borderWidth: 2,
        shadowColor: colorSet.glow,
        shadowBlur: 16,
      },
      label: {
        show: true,
        formatter: '{b}',
        color: '#ffffff',
        fontSize: name.length > 6 ? 10 : 12,
        fontWeight: 'bold',
        fontFamily: 'Microsoft YaHei, sans-serif',
        textShadowColor: 'rgba(0, 0, 0, 0.6)',
        textShadowBlur: 4,
      },
    }
  })

  radarChart.setOption({
    backgroundColor: 'transparent',
    animation: true,
    animationDuration: 1200,
    animationEasing: 'elasticOut',
    series: [{
      type: 'graph',
      layout: 'force',
      data: nodes,
      links: [],
      categories: GRAPH_COLORS.map((c, i) => ({ name: 'cat' + i })),
      roam: true,
      draggable: true,
      force: {
        repulsion: 220,
        edgeLength: [60, 120],
        gravity: 0.08,
        friction: 0.6,
        layoutAnimation: true,
      },
      emphasis: {
        focus: 'adjacency',
        itemStyle: {
          shadowBlur: 30,
          borderWidth: 3,
        },
        label: {
          fontSize: 14,
        },
      },
      tooltip: {
        show: true,
        backgroundColor: 'rgba(10, 10, 10, 0.9)',
        borderColor: '#1e3a8a',
        borderWidth: 1,
        textStyle: {
          color: '#e2e8f0',
          fontSize: 12,
          fontFamily: 'Microsoft YaHei, sans-serif',
        },
        formatter: (params) => {
          if (!params.data || !params.data.name) return ''
          return `<span style="color:#38bdf8;font-weight:bold">⚡ ${params.data.name}</span>`
        },
      },
    }],
  }, true)
}

function handleResize() {
  if (radarChart) {
    radarChart.resize()
  }
}

function loadRecords() {
  loading.value = true
  try {
    const raw = localStorage.getItem('career_history')
    if (raw) {
      records.value = JSON.parse(raw)
    }
  } catch (e) {
    records.value = []
  }
  loading.value = false
}

async function fetchServerData() {
  if (!store.userId) return
  serverLoading.value = true
  serverError.value = ''
  try {
    const resp = await fetch(`/api/v1/career-advice/profile?userId=${store.userId}`)
    if (resp.ok) {
      const data = await resp.json()
      serverProfile.value = data
      if (data.resumeHighlight || data.resume_highlight || data.skills || data.nextSuggestion || data.next_suggestion) {
        const newRecord = {
          skills: data.skills || data.extractedSkills || data.extracted_skills || '',
          resume_highlight: data.resumeHighlight || data.resume_highlight || '',
          learning_advice: data.learningAdvice || data.learning_advice || '',
          next_suggestion: data.nextSuggestion || data.next_suggestion || '',
          extracted_skills: data.extractedSkills || data.extracted_skills || [],
          timestamp: Date.now(),
          source: 'server',
        }
        const serverIdx = records.value.findIndex(r => r.source === 'server')
        if (serverIdx >= 0) {
          records.value.splice(serverIdx, 1, newRecord)
        } else if (newRecord.resume_highlight) {
          records.value.unshift(newRecord)
        }
        try {
          localStorage.setItem('career_history', JSON.stringify(records.value.slice(0, 500)))
        } catch (e) {}
      }
    } else {
      serverError.value = `服务端返回 ${resp.status}`
    }
  } catch (e) {
    serverError.value = e.message || '网络请求失败'
    console.log('[CareerDashboard] Server fetch failed (non-blocking):', e.message)
  }
  serverLoading.value = false
}

watch(() => props.visible, async (val) => {
  if (val) {
    loadRecords()
    await fetchServerData()
    await nextTick()
    initRadarChart()
  }
})

watch(allSkills, async () => {
  if (props.visible) {
    await nextTick()
    initRadarChart()
  }
})

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (radarChart) {
    radarChart.dispose()
    radarChart = null
  }
})

function exportMarkdown() {
  const lines = []
  lines.push('# 🎯 AI 职业档案 — 简历素材')
  lines.push('')
  lines.push(`> 生成时间: ${new Date().toLocaleString('zh-CN')}`)
  lines.push(`> 用户ID: ${store.userId || 'N/A'}`)
  lines.push('')

  if (skillBadges.value.length > 0) {
    lines.push('## 🏅 已掌握技能')
    lines.push('')
    skillBadges.value.forEach(s => {
      lines.push(`- \`${s}\``)
    })
    lines.push('')
  }

  if (serverProfile.value) {
    lines.push('## 🤖 AI 导师最新评估')
    lines.push('')
    if (serverProfile.value.resumeHighlight || serverProfile.value.resume_highlight) {
      lines.push(`**简历亮点 (STAR):** ${serverProfile.value.resumeHighlight || serverProfile.value.resume_highlight}`)
      lines.push('')
    }
    if (serverProfile.value.nextSuggestion || serverProfile.value.next_suggestion) {
      lines.push(`**导师进阶建议:** ${serverProfile.value.nextSuggestion || serverProfile.value.next_suggestion}`)
      lines.push('')
    }
    const srvSkills = serverProfile.value.extractedSkills || serverProfile.value.extracted_skills || []
    if (srvSkills.length > 0) {
      lines.push(`**核心技能:** ${srvSkills.map(s => '`' + s + '`').join(' ')}`)
      lines.push('')
    }
    lines.push('---')
    lines.push('')
  }

  lines.push('## 📝 项目经历与简历亮点')
  lines.push('')

  records.value.forEach((r, i) => {
    const ts = r.timestamp ? new Date(r.timestamp).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''
    lines.push(`### ${i + 1}. ${r.category || '编程实践'} ${ts ? `— ${ts}` : ''}`)
    lines.push('')
    if (r.resume_highlight) {
      lines.push(`**简历亮点 (STAR):** ${r.resume_highlight}`)
      lines.push('')
    }
    if (r.next_suggestion || r.learning_advice) {
      lines.push(`**导师建议:** ${r.next_suggestion || r.learning_advice}`)
      lines.push('')
    }
    const skills = r.extracted_skills || r.skills || []
    if (skills.length > 0) {
      lines.push(`**技术标签:** ${skills.map(s => '`' + s + '`').join(' ')}`)
      lines.push('')
    }
    lines.push('---')
    lines.push('')
  })

  const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `career_profile_user${store.userId}_${Date.now()}.md`
  a.click()
  URL.revokeObjectURL(url)
  exportMsg.value = '✅ 已导出'
  setTimeout(() => { exportMsg.value = '' }, 2000)
}
</script>

<template>
  <Transition name="panel-slide">
    <div v-if="visible" class="fixed inset-0 z-[100] flex justify-end" @click.self="emit('close')">
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>
      <div class="relative w-[860px] max-w-[95vw] h-full bg-geek-surface border-l border-cyan-500/20 shadow-[0_0_40px_rgba(56,189,248,0.06)] flex flex-col">
        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-geek-border shrink-0">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-cyan-900/30 border border-cyan-500/30 flex items-center justify-center text-sm">🎓</div>
            <div>
              <div class="text-sm font-bold text-cyan-400">职业档案</div>
              <div class="text-[10px] text-geek-text-dim">
                AI 驱动的技能雷达 & 简历素材
                <span v-if="store.userId" class="text-cyan-500/60 ml-1">User#{{ store.userId }}</span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button @click="exportMarkdown" :disabled="records.length === 0 && !serverProfile" class="px-3 py-1.5 bg-cyan-600/40 hover:bg-cyan-600/70 text-white rounded text-[10px] font-bold transition-colors disabled:opacity-30 flex items-center gap-1 border border-cyan-500/20">
              <span>📄</span> 导出 Markdown
            </button>
            <span v-if="exportMsg" class="text-[10px] text-cyan-400">{{ exportMsg }}</span>
            <button @click="emit('close')" class="text-geek-text-dim hover:text-geek-text text-lg leading-none ml-2">×</button>
          </div>
        </div>

        <!-- Main Content -->
        <div class="flex-1 overflow-y-auto p-5">
          <!-- Loading Skeleton -->
          <div v-if="serverLoading" class="space-y-4">
            <div class="flex items-center gap-2 text-[11px] text-cyan-400 animate-pulse">
              <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" stroke-dasharray="60 30" stroke-linecap="round"/></svg>
              正在同步 AI 分析的个人档案...
            </div>
            <div class="grid grid-cols-5 gap-4">
              <div class="col-span-2 space-y-3">
                <div class="h-[400px] bg-geek-bg rounded-lg animate-pulse border border-geek-border/30"></div>
              </div>
              <div class="col-span-3 space-y-3">
                <div class="h-4 bg-geek-bg rounded w-3/4 animate-pulse"></div>
                <div class="flex gap-1.5">
                  <div class="h-5 w-16 bg-cyan-500/10 rounded animate-pulse"></div>
                  <div class="h-5 w-20 bg-cyan-500/10 rounded animate-pulse"></div>
                  <div class="h-5 w-14 bg-cyan-500/10 rounded animate-pulse"></div>
                </div>
                <div class="h-3 bg-geek-bg rounded w-full animate-pulse"></div>
                <div class="h-3 bg-geek-bg rounded w-5/6 animate-pulse"></div>
                <div class="h-3 bg-geek-bg rounded w-4/6 animate-pulse"></div>
              </div>
            </div>
          </div>

          <!-- Server Error -->
          <div v-if="serverError && !serverLoading" class="mb-4 px-3 py-2 bg-yellow-500/10 border border-yellow-500/20 rounded text-[10px] text-yellow-400">
            ⚠️ 服务端同步失败: {{ serverError }}，当前展示本地缓存数据
          </div>

          <!-- Empty State -->
          <div v-if="records.length === 0 && !hasServerData && !serverLoading" class="flex flex-col items-center justify-center py-20 text-geek-text-dim">
            <div class="text-6xl mb-4 opacity-20">📭</div>
            <div class="text-sm font-bold text-geek-text-dim/80">暂无职业档案记录</div>
            <div class="text-[10px] mt-2 text-center leading-relaxed max-w-[280px]">
              请在沙盒中完成编程任务，AI 导师将自动为您生成高亮简历
            </div>
            <div class="mt-4 px-3 py-1.5 bg-cyan-500/5 border border-cyan-500/15 rounded text-[10px] text-cyan-500/60">
              💡 每次代码审查通过后，技能星图会自动扩展
            </div>
          </div>

          <!-- Main Grid: Radar + Details -->
          <div v-if="!serverLoading && (hasServerData || records.length > 0)" class="grid grid-cols-5 gap-4">
            <!-- Left: Radar Chart (40%) -->
            <div class="col-span-2 space-y-3">
              <div class="relative bg-geek-bg/80 border border-cyan-500/10 rounded-lg overflow-hidden">
                <div class="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-500/40 to-transparent"></div>
                <div class="px-3 py-2 flex items-center justify-between border-b border-geek-border/30">
                  <div class="flex items-center gap-1.5">
                    <span class="text-[10px] text-cyan-400">⚡</span>
                    <span class="text-[10px] font-bold text-cyan-400">技能星图</span>
                  </div>
                  <span v-if="allSkills.length > 0" class="text-[9px] text-cyan-500/50 font-mono">LV.{{ allSkills.length }}</span>
                </div>
                <div ref="radarContainer" class="w-full" style="height: 400px;"></div>
              </div>

              <!-- Skill Badges below radar -->
              <div v-if="skillBadges.length > 0" class="space-y-2">
                <div class="text-[10px] font-bold text-geek-text-dim flex items-center gap-1.5">
                  <span class="text-cyan-400">🏅</span> 已解锁技能 ({{ skillBadges.length }})
                </div>
                <div class="flex flex-wrap gap-1">
                  <span v-for="skill in skillBadges" :key="skill"
                    class="px-1.5 py-0.5 bg-cyan-500/10 border border-cyan-500/20 rounded text-[9px] text-cyan-400 font-mono">
                    {{ skill }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Right: Details (60%) -->
            <div class="col-span-3 space-y-4">
              <!-- AI Evaluation Card -->
              <div v-if="hasServerData" class="bg-gradient-to-br from-cyan-900/15 to-blue-900/10 border border-cyan-500/15 rounded-lg overflow-hidden">
                <div class="absolute-0 h-px bg-gradient-to-r from-transparent via-cyan-500/30 to-transparent"></div>
                <div class="px-4 py-2.5 flex items-center gap-2 border-b border-cyan-500/10">
                  <span class="text-sm">🤖</span>
                  <span class="text-xs font-bold text-cyan-400">AI 导师最新评估</span>
                  <span class="text-[9px] px-1.5 py-0.5 bg-cyan-500/20 border border-cyan-500/30 rounded text-cyan-400 animate-pulse">LIVE</span>
                </div>
                <div class="p-4 space-y-3">
                  <!-- Resume Highlight (Markdown rendered) -->
                  <div v-if="resumeHighlightText" class="text-xs text-geek-text leading-relaxed">
                    <div class="text-cyan-400 font-bold text-[11px] mb-1.5 flex items-center gap-1">
                      <span>🚀</span> STAR 简历亮点
                    </div>
                    <div class="bg-geek-bg/50 border border-geek-border/30 rounded p-3 text-[11px] leading-relaxed whitespace-pre-wrap career-highlight">{{ resumeHighlightText }}</div>
                  </div>
                  <!-- Next Suggestion -->
                  <div v-if="nextSuggestionText" class="text-xs text-geek-text-dim leading-relaxed">
                    <div class="text-yellow-400 font-bold text-[11px] mb-1 flex items-center gap-1">
                      <span>💡</span> 导师进阶建议
                    </div>
                    <div class="bg-yellow-500/5 border border-yellow-500/10 rounded p-2.5 text-[11px] leading-relaxed">{{ nextSuggestionText }}</div>
                  </div>
                </div>
              </div>

              <!-- Timeline -->
              <div v-if="records.length > 0" class="space-y-3">
                <div class="text-xs font-bold text-geek-text-dim flex items-center gap-2">
                  <span class="text-cyan-400">📋</span> 成长时间轴 ({{ totalHighlights }} 条简历素材)
                </div>
                <div class="max-h-[320px] overflow-y-auto space-y-2 pr-1 custom-scrollbar">
                  <div v-for="(record, idx) in records" :key="idx"
                    class="relative pl-5 pb-3 border-l-2"
                    :class="idx === records.length - 1 ? 'border-cyan-500/30' : 'border-geek-border'">
                    <div class="absolute -left-[5px] top-0 w-2 h-2 rounded-full"
                      :class="idx === 0 ? 'bg-cyan-400 shadow-[0_0_6px_rgba(56,189,248,0.5)]' : 'bg-geek-text-dim'"></div>
                    <div class="bg-geek-bg/50 border border-geek-border/50 rounded-lg p-3 space-y-1.5">
                      <div class="flex items-center justify-between">
                        <div class="flex items-center gap-1.5">
                          <span class="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                            {{ record.category || '编程实践' }}
                          </span>
                          <span v-if="record.source === 'server'" class="text-[9px] px-1 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">服务端</span>
                        </div>
                        <span class="text-[10px] text-geek-text-dim font-mono">
                          {{ record.timestamp ? new Date(record.timestamp).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '' }}
                        </span>
                      </div>
                      <div v-if="record.resume_highlight" class="text-[11px] text-geek-text leading-relaxed">
                        <span class="text-cyan-400 font-bold">STAR: </span>{{ record.resume_highlight }}
                      </div>
                      <div v-if="record.next_suggestion || record.learning_advice" class="text-[11px] text-geek-text-dim leading-relaxed">
                        <span class="text-yellow-400">💡 </span>{{ record.next_suggestion || record.learning_advice }}
                      </div>
                      <div v-if="(record.extracted_skills || record.skills || []).length > 0" class="flex flex-wrap gap-1 pt-0.5">
                        <span v-for="s in (record.extracted_skills || record.skills)" :key="s"
                          class="px-1.5 py-0.5 bg-purple-500/10 border border-purple-500/20 rounded text-[9px] text-purple-400 font-mono">
                          {{ s }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="px-5 py-3 border-t border-geek-border shrink-0">
          <div class="flex items-center justify-between">
            <div class="text-[10px] text-geek-text-dim">⚡ 技能星图由 AI 深度分析驱动，简历亮点基于 STAR 法则生成</div>
            <div v-if="serverProfile" class="text-[10px] text-cyan-500/50">已同步服务端</div>
            <div v-else-if="serverError" class="text-[10px] text-yellow-500/50">本地缓存模式</div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.panel-slide-enter-active {
  transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.panel-slide-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 1, 1);
}
.panel-slide-enter-from {
  opacity: 0;
}
.panel-slide-enter-from > :nth-child(2) {
  transform: translateX(100%);
}
.panel-slide-leave-to {
  opacity: 0;
}
.panel-slide-leave-to > :nth-child(2) {
  transform: translateX(100%);
}
.panel-slide-enter-active > :nth-child(2) {
  transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.panel-slide-leave-active > :nth-child(2) {
  transition: transform 0.25s cubic-bezier(0.4, 0, 1, 1);
}

.career-highlight :deep(h2) {
  color: #38bdf8;
  font-size: 13px;
  font-weight: bold;
  margin: 8px 0 4px 0;
}
.career-highlight :deep(strong) {
  color: #67e8f9;
}
.career-highlight :deep(ul),
.career-highlight :deep(ol) {
  padding-left: 16px;
  margin: 4px 0;
}
.career-highlight :deep(li) {
  margin: 2px 0;
}
.career-highlight :deep(code) {
  color: #a78bfa;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  background: rgba(167, 139, 250, 0.1);
  padding: 0 4px;
  border-radius: 2px;
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(56, 189, 248, 0.2);
  border-radius: 2px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(56, 189, 248, 0.4);
}
</style>
