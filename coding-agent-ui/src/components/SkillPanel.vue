<script setup>
import { useAgentStore } from '../stores/agent'

const store = useAgentStore()

const skills = [
  { id: 'sdd', label: '🤖 多智能体', desc: 'Lead→Implementer→Reviewer 三角色协作' },
  { id: 'performance', label: '⚡ 性能优化', desc: '关注大O复杂度与内存泄漏' },
  { id: 'security', label: '🛡️ 安全审计', desc: '检查越权、注入与并发漏洞' },
  { id: 'tdd', label: '🧪 TDD驱动', desc: '先写测试再写实现' },
  { id: 'doubt', label: '🤔 质疑驱动', desc: '不盲从需求，先排查隐患' },
]

function toggleSkill(id) {
  const idx = store.selectedSkills.indexOf(id)
  if (idx === -1) {
    store.selectedSkills.push(id)
  } else {
    store.selectedSkills.splice(idx, 1)
  }
}

function isActive(id) {
  return store.selectedSkills.includes(id)
}
</script>

<template>
  <div class="flex flex-wrap gap-1.5 py-1.5 px-1">
    <button
      v-for="skill in skills"
      :key="skill.id"
      @click="toggleSkill(skill.id)"
      class="group relative flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-all duration-200 border"
      :class="isActive(skill.id)
        ? 'bg-geek-accent/15 text-geek-accent border-geek-accent/40 shadow-[0_0_8px_rgba(0,255,136,0.1)]'
        : 'bg-geek-bg text-geek-text-dim border-geek-border hover:border-geek-accent/30 hover:text-geek-text'"
      :title="skill.desc"
    >
      <span class="transition-transform duration-200" :class="isActive(skill.id) ? 'scale-110' : ''">
        {{ skill.label }}
      </span>
      <span
        v-if="isActive(skill.id)"
        class="w-1 h-1 rounded-full bg-geek-accent animate-pulse"
      ></span>

      <div
        class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-geek-surface border border-geek-border rounded text-[10px] text-geek-text-dim whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 shadow-lg"
      >
        {{ skill.desc }}
      </div>
    </button>
  </div>
</template>
