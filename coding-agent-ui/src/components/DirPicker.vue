<script setup>
import { ref, watch, onMounted } from 'vue'
import { useAgentStore } from '../stores/agent'

const props = defineProps({
  visible: Boolean,
})

const emit = defineEmits(['close', 'select'])

const store = useAgentStore()
const currentPath = ref('/')
const folders = ref([])
const loading = ref(false)
const error = ref('')
const history = ref(['/'])

async function browse(path) {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetch(`http://localhost:8001/api/v1/browse?path=${encodeURIComponent(path)}`)
    if (resp.ok) {
      const data = await resp.json()
      folders.value = data.folders || []
      currentPath.value = data.current_path || path
      if (data.error) {
        error.value = data.error
      }
    }
  } catch (e) {
    error.value = '无法连接到服务器'
  } finally {
    loading.value = false
  }
}

function goInto(folder) {
  history.value.push(folder.path)
  browse(folder.path)
}

function goBack() {
  if (history.value.length > 1) {
    history.value.pop()
    const prevPath = history.value[history.value.length - 1]
    browse(prevPath)
  }
}

function goToRoot() {
  history.value = ['/']
  browse('/')
}

function selectCurrent() {
  emit('select', currentPath.value)
  emit('close')
}

function close() {
  emit('close')
}

watch(() => props.visible, (visible) => {
  if (visible) {
    browse(currentPath.value)
  }
})

onMounted(() => {
  if (props.visible) {
    browse(currentPath.value)
  }
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
      @click.self="close"
    >
      <div class="bg-geek-surface border border-geek-border rounded-lg w-[500px] max-h-[70vh] flex flex-col shadow-2xl">
        <div class="flex items-center justify-between px-4 py-3 border-b border-geek-border">
          <span class="text-sm font-bold text-geek-accent">选择工作目录</span>
          <button
            @click="close"
            class="text-geek-text-dim hover:text-geek-text text-lg leading-none"
          >×</button>
        </div>

        <div class="flex items-center gap-2 px-4 py-2 border-b border-geek-border bg-geek-bg">
          <button
            @click="goToRoot"
            class="px-2 py-1 text-xs bg-geek-border rounded hover:bg-geek-accent/20 transition-colors"
            title="根目录"
          >/</button>
          <button
            @click="goBack"
            :disabled="history.length <= 1"
            class="px-2 py-1 text-xs bg-geek-border rounded hover:bg-geek-accent/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="返回上级"
          >←</button>
          <div class="flex-1 text-xs text-geek-text-dim truncate">
            {{ currentPath }}
          </div>
        </div>

        <div class="flex-1 overflow-y-auto p-2 min-h-[200px]">
          <div v-if="loading" class="flex items-center justify-center py-8">
            <span class="text-geek-text-dim text-xs">加载中...</span>
          </div>
          <div v-else-if="error" class="px-4 py-8 text-center">
            <span class="text-red-400 text-xs">{{ error }}</span>
          </div>
          <div v-else-if="folders.length === 0" class="px-4 py-8 text-center">
            <span class="text-geek-text-dim text-xs">此目录没有子文件夹</span>
          </div>
          <div v-else class="space-y-1">
            <div
              v-for="folder in folders"
              :key="folder.path"
              @click="goInto(folder)"
              @dblclick="selectCurrent"
              class="flex items-center gap-2 px-3 py-2 rounded cursor-pointer hover:bg-geek-accent/10 transition-colors"
            >
              <span class="text-sm">📁</span>
              <span class="text-xs text-geek-text truncate">{{ folder.name }}</span>
            </div>
          </div>
        </div>

        <div class="flex items-center justify-between px-4 py-3 border-t border-geek-border">
          <span class="text-[10px] text-geek-text-dim">双击文件夹进入，点击选择按钮确认</span>
          <div class="flex gap-2">
            <button
              @click="close"
              class="px-3 py-1.5 text-xs bg-geek-border rounded hover:bg-geek-border/80 transition-colors"
            >取消</button>
            <button
              @click="selectCurrent"
              class="px-3 py-1.5 text-xs bg-geek-accent text-black font-bold rounded hover:bg-geek-accent-dim transition-colors"
            >选择此目录</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
