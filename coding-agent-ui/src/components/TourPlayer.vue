<script setup>
import { computed } from 'vue'
import { useAgentStore } from '../stores/agent'

const store = useAgentStore()

const isVisible = computed(() => store.tourSteps.length > 0)
const currentStep = computed(() => store.tourActiveStep)
const currentIdx = computed(() => store.tourActiveIdx)
const totalSteps = computed(() => store.tourSteps.length)
const hasPrev = computed(() => currentIdx.value > 0)
const hasNext = computed(() => currentIdx.value < totalSteps.value - 1)
const progressPercent = computed(() => {
  if (totalSteps.value <= 1) return 100
  return Math.round(((currentIdx.value + 1) / totalSteps.value) * 100)
})

function handlePrev() {
  store.tourPrev()
}

function handleNext() {
  store.tourNext()
}

function handleClose() {
  store.stopTour()
}
</script>

<template>
  <Transition name="tour-slide">
    <div
      v-if="isVisible"
      class="fixed right-6 top-1/2 -translate-y-1/2 z-50 w-[480px] max-h-[85vh] flex flex-col pointer-events-auto"
    >
      <div
        class="bg-gray-900/95 backdrop-blur-md border border-gray-700 shadow-2xl rounded-xl text-gray-200 overflow-hidden flex flex-col max-h-[85vh]"
      >
        <div
          class="absolute bottom-0 left-0 h-[2px] transition-all duration-300 ease-out"
          :style="{
            width: progressPercent + '%',
            background: 'linear-gradient(90deg, #3b82f6, #60a5fa, #93c5fd)',
            boxShadow: '0 0 8px rgba(59, 130, 246, 0.5)',
          }"
        ></div>

        <div class="flex items-center justify-between px-6 pt-5 pb-3">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-lg flex items-center justify-center text-sm bg-blue-500/10 border border-blue-500/25">
              🗺️
            </div>
            <div>
              <div class="text-sm font-medium text-gray-100">代码导览</div>
              <div class="text-[11px] font-mono text-gray-500">
                步骤 <span class="text-blue-400">{{ currentIdx + 1 }}</span> / {{ totalSteps }}
              </div>
            </div>
          </div>

          <button
            @click="handleClose"
            class="w-7 h-7 rounded-lg flex items-center justify-center transition-all duration-150 hover:bg-red-900/30 border border-gray-700/50 text-gray-500 hover:text-red-400"
            title="关闭导览"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div v-if="currentStep" class="px-6 pb-4 flex flex-col flex-1 min-h-0">
          <div class="flex items-center gap-2 mb-3 min-w-0">
            <span
              class="text-[11px] font-mono px-2 py-0.5 rounded-md shrink-0 bg-blue-500/10 border border-blue-500/20 text-blue-300"
            >{{ currentStep.function }}</span>
            <span class="text-[11px] text-gray-500 truncate">{{ currentStep.file }}</span>
            <span
              v-if="currentStep.start_line"
              class="text-[10px] font-mono shrink-0 text-gray-600"
            >L{{ currentStep.start_line }}-L{{ currentStep.end_line }}</span>
          </div>

          <div class="flex-1 overflow-y-auto pr-2 text-[13px] leading-relaxed text-gray-300 mb-4">
            {{ currentStep.explanation }}
          </div>

          <div class="flex items-center gap-2 shrink-0">
            <button
              @click="handlePrev"
              :disabled="!hasPrev"
              class="flex-1 h-9 rounded-lg flex items-center justify-center gap-1.5 transition-all duration-150 text-[12px] font-medium"
              :class="hasPrev
                ? 'bg-gray-800 border border-gray-600 text-gray-200 hover:bg-gray-700 hover:border-gray-500 cursor-pointer'
                : 'bg-gray-800/50 border border-gray-700/50 text-gray-600 cursor-not-allowed'"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
              上一步
            </button>
            <button
              @click="handleNext"
              :disabled="!hasNext"
              class="flex-1 h-9 rounded-lg flex items-center justify-center gap-1.5 transition-all duration-150 text-[12px] font-medium"
              :class="hasNext
                ? 'bg-blue-600/80 border border-blue-500/50 text-white hover:bg-blue-500/80 hover:border-blue-400/50 cursor-pointer'
                : 'bg-gray-800/50 border border-gray-700/50 text-gray-600 cursor-not-allowed'"
            >
              下一步
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.tour-slide-enter-active {
  transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.tour-slide-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 1, 1);
}
.tour-slide-enter-from {
  opacity: 0;
  transform: translateX(30px) translateY(-50%);
}
.tour-slide-leave-to {
  opacity: 0;
  transform: translateX(20px) translateY(-50%);
}
</style>
