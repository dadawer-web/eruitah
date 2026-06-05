import { defineStore } from 'pinia'
import { ref, shallowRef, computed, nextTick } from 'vue'
import { WebContainerManager } from '../utils/webcontainerManager'

const LAST_PATH_KEY = 'coding-agent-last-path'

function getLastPath() {
  try {
    return localStorage.getItem(LAST_PATH_KEY) || '/tmp/eruitah-sandbox'
  } catch {
    return '/tmp/eruitah-sandbox'
  }
}

function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export const useAgentStore = defineStore('agent', () => {
  const ws = shallowRef(null)
  const connected = ref(false)
  const messages = ref([])
  const files = ref([])
  const basePath = ref(getLastPath())
  const originalBasePath = ref(getLastPath())
  const pendingBaseTaskId = ref('')
  const mcpServices = ref('')
  const currentFile = ref(null)
  const currentIsDir = ref(false)
  const currentCode = ref('')
  const openFiles = ref([])
  const activeFileIdx = ref(0)
  const diagnostics = ref([])
  const typingQueue = ref([])
  const isTyping = ref(false)
  const isRunning = ref(false)
  const status = ref('')
  const currentTool = ref(null)
  const pendingConfirmation = ref(null)
  const mermaidDiagrams = ref([])
  const activeMermaidIdx = ref(-1)
  const costInfo = ref(null)
  const lastRollbackInfo = ref(null)
  const contextCompact = ref(null)
  const assistantText = ref('')
  const currentTaskId = ref(null)
  const currentTaskName = ref('')
  const petStatus = ref('IDLE')
  const agentState = ref(null)
  const activeContextFiles = ref([])
  const systemAlerts = ref([])
  const checkpointList = ref([])

  const toasts = ref([])
  let toastIdCounter = 0

  const taskList = ref([])
  const taskMessages = ref({})
  const activeTaskId = ref(null)
  const autoApprove = ref(false)

  try {
    localStorage.removeItem('eruitah_tasks')
  } catch {}

  const historyStates = ref([])
  const rollbackPreview = ref(null)
  const checkpointView = ref(null)

  const wcPreviewUrl = ref(null)
  const wcStatus = ref('idle')
  const wcError = ref(null)
  const wcOutputBuffer = ref([])
  const wcShowPreview = ref(false)

  const selectedSkills = ref([])
  const architectureVisible = ref(false)
  const architectureData = ref({ nodes: [], edges: [] })
  const codeGraphVisible = ref(false)
  const codeGraphData = ref({ nodes: [], edges: [] })
  const codeGraphLoading = ref(false)

  const tourSteps = ref([])
  const tourActiveIdx = ref(-1)
  const tourActiveNodeId = ref(null)

  const tourActiveStep = computed(() => {
    if (tourActiveIdx.value < 0 || tourActiveIdx.value >= tourSteps.value.length) return null
    return tourSteps.value[tourActiveIdx.value]
  })

  let _wcManager = null
  let _wcOutputUnsubscribe = null

  let rafId = null
  let editorInstance = null
  const userId = ref(null)
  const sessionId = ref(generateUUID())
  const hasNewCareerAdvice = ref(false)
  const careerAdviceData = ref(null)
  let wsRetryCount = 0
  const WS_MAX_RETRY = 20

  function _initUserId() {
    const params = new URLSearchParams(window.location.search)
    const fromUrl = params.get('user_id') || params.get('userId')
    if (fromUrl) {
      userId.value = parseInt(fromUrl, 10) || null
      if (userId.value) {
        try { localStorage.setItem('eruitah_user_id', String(userId.value)) } catch {}
      }
      return
    }
    try {
      const stored = localStorage.getItem('eruitah_user_id')
      if (stored) {
        userId.value = parseInt(stored, 10) || null
      }
    } catch {}
    if (!userId.value) {
      userId.value = 1
      console.warn('[Auth] user_id 未指定，默认使用 1。请通过 URL 参数 ?user_id=xxx 传入真实用户 ID')
    }
  }
  _initUserId()

  function _initSessionId() {
    try {
      const stored = localStorage.getItem('eruitah_session_id')
      if (stored) {
        sessionId.value = stored
      } else {
        sessionId.value = generateUUID()
        try { localStorage.setItem('eruitah_session_id', sessionId.value) } catch {}
      }
    } catch {
      sessionId.value = generateUUID()
    }
  }
  _initSessionId()

  function newSession() {
    sessionId.value = generateUUID()
    try { localStorage.setItem('eruitah_session_id', sessionId.value) } catch {}
    messages.value = []
    activeTaskId.value = null
    currentTaskId.value = null
    currentTaskName.value = ''
    historyStates.value = []
  }

  function _injectIdentity(payload) {
    payload.user_id = userId.value
    payload.session_id = sessionId.value
    return payload
  }

  function pushMessage(msg) {
    messages.value.push(msg)
    const tid = activeTaskId.value
    if (tid) {
      if (!taskMessages.value[tid]) {
        taskMessages.value[tid] = []
      }
      if (taskMessages.value[tid] !== messages.value) {
        taskMessages.value[tid].push(msg)
      }
    }
  }

  function connect() {
    if (ws.value && (ws.value.readyState === WebSocket.OPEN || ws.value.readyState === WebSocket.CONNECTING)) {
      return
    }

    const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const uid = userId.value || 0
    const socket = new WebSocket(`${wsProto}//${location.host}/ws/simple-ide?user_id=${uid}`)

    socket.onopen = () => {
      connected.value = true
      wsRetryCount = 0
      console.log('[WS] Connected to coding agent')
      fetchTaskRegistry()
    }

    socket.onclose = () => {
      connected.value = false
      isRunning.value = false
      activeTaskId.value = null
      currentTaskId.value = null
      currentTaskName.value = ''
      wsRetryCount++
      if (wsRetryCount <= WS_MAX_RETRY) {
        const delay = Math.min(1000 * wsRetryCount, 5000)
        console.log(`[WS] Disconnected, retry ${wsRetryCount}/${WS_MAX_RETRY} in ${delay}ms`)
        setTimeout(() => connect(), delay)
      } else {
        console.warn('[WS] Max retries reached, giving up. Click to reconnect.')
      }
    }

    socket.onerror = (err) => {
      console.warn('[WS] Connection error - backend may not be running on port 8001')
    }

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleMessage(data)
      } catch (e) {
        console.error('[WS] Failed to parse message:', e)
      }
    }

    ws.value = socket
  }

  function handleMessage(data) {
    console.log('[WS] Received:', data.type, data)

    switch (data.type) {
      case 'agent_status':
        petStatus.value = data.status || 'IDLE'
        break

      case 'agent_state':
        agentState.value = { status: data.status || '', data: data.data || '' }
        if (data.status === 'thinking') {
          petStatus.value = 'THINKING'
        } else if (data.status === 'searching') {
          petStatus.value = 'SEARCHING'
        }
        messages.value.push({
          role: 'agent',
          content: data.data || '',
          timestamp: Date.now(),
          msgType: 'agent_state',
          agentStatus: data.status || '',
        })
        break

      case 'context_update':
        if (data.files && Array.isArray(data.files)) {
          const existing = new Set(activeContextFiles.value)
          for (const f of data.files) {
            if (f && !existing.has(f)) {
              existing.add(f)
            }
          }
          activeContextFiles.value = Array.from(existing).slice(-20)
          messages.value.push({
            role: 'agent',
            content: '',
            timestamp: Date.now(),
            msgType: 'context_update',
            files: data.files,
          })
        }
        break

      case 'chat':
        break

      case 'NOTIFY_CAREER_UPDATE':
        hasNewCareerAdvice.value = true
        careerAdviceData.value = {
          skills: data.skills || '',
          resumeHighlight: data.resume_highlight || data.resumeHighlight || '',
          learningAdvice: data.learning_advice || data.learningAdvice || '',
          nextSuggestion: data.next_suggestion || data.nextSuggestion || '',
          extractedSkills: data.extracted_skills || data.extractedSkills || [],
          timestamp: Date.now(),
        }
        try {
          const history = JSON.parse(localStorage.getItem('career_history') || '[]')
          history.unshift({
            skills: data.skills || '',
            resume_highlight: data.resume_highlight || data.resumeHighlight || '',
            learning_advice: data.learning_advice || data.learningAdvice || '',
            next_suggestion: data.next_suggestion || data.nextSuggestion || '',
            extracted_skills: data.extracted_skills || data.extractedSkills || [],
            timestamp: Date.now(),
          })
          localStorage.setItem('career_history', JSON.stringify(history.slice(0, 500)))
        } catch (e) {}
        console.log('[WS] Career advice notification received')
        break

      case 'system_alert':
        systemAlerts.value.push({
          content: data.content || '',
          timestamp: Date.now(),
        })
        messages.value.push({
          role: 'agent',
          content: data.content || '',
          timestamp: Date.now(),
          msgType: 'system_alert',
        })
        window.__xterm_write?.(`\x1b[33m[系统拦截] ${data.content}\x1b[0m\n`)
        setTimeout(() => {
          const idx = systemAlerts.value.findIndex(a => a.content === data.content && a.timestamp === Date.now())
          if (idx !== -1) systemAlerts.value.splice(idx, 1)
        }, 8000)
        break

      case 'sdd_status':
        messages.value.push({
          role: 'agent',
          content: data.message || '',
          timestamp: Date.now(),
          msgType: 'sdd_status',
          sddPhase: data.phase || '',
          sddStep: data.step || 0,
          sddTotal: data.total_steps || 0,
          sddRetry: data.retry || 0,
        })
        window.__xterm_write?.(`\x1b[35m[SDD] ${data.message}\x1b[0m\n`)
        break

      case 'sdd_review_approved':
        messages.value.push({
          role: 'agent',
          content: data.review_output || '审查通过',
          timestamp: Date.now(),
          msgType: 'sdd_review',
          sddApproved: true,
          sddStep: data.step || 0,
        })
        window.__xterm_write?.(`\x1b[32m[SDD] ✅ 审查通过 - 步骤 ${data.step}\x1b[0m\n`)
        break

      case 'sdd_review_rejected':
        messages.value.push({
          role: 'agent',
          content: data.review_output || '审查拒绝',
          timestamp: Date.now(),
          msgType: 'sdd_review',
          sddApproved: false,
          sddStep: data.step || 0,
        })
        window.__xterm_write?.(`\x1b[31m[SDD] ❌ 审查拒绝 - 步骤 ${data.step} (第 ${data.retry} 次)\x1b[0m\n`)
        break

      case 'sdd_plan_ready':
        window.__xterm_write?.(`\x1b[36m[SDD] 📋 任务计划已就绪: ${data.total_steps} 个步骤\x1b[0m\n`)
        break

      case 'sdd_loop_start':
        window.__xterm_write?.(`\x1b[35m[SDD] 🤖 多智能体协作模式启动\x1b[0m\n`)
        break

      case 'sdd_loop_end':
        window.__xterm_write?.(`\x1b[35m[SDD] 🏁 多智能体协作完成\x1b[0m\n`)
        break

      case 'status':
        status.value = data.data || ''
        if (data.data && data.data.includes('思考')) {
          petStatus.value = 'THINKING'
        }
        break

      case 'task_started':
        const realTaskId = data.task_id || ''
        const realTaskName = data.task_name || ''
        const realWorkDir = data.work_dir || ''

        const oldActiveId = activeTaskId.value
        if (oldActiveId && oldActiveId !== realTaskId && taskMessages.value[oldActiveId]) {
          taskMessages.value[realTaskId] = taskMessages.value[oldActiveId]
          delete taskMessages.value[oldActiveId]

          const oldEntry = taskList.value.find(t => t.id === oldActiveId)
          if (oldEntry) {
            oldEntry.id = realTaskId
            oldEntry.title = realTaskName || oldEntry.title
          }
        }

        currentTaskId.value = realTaskId
        currentTaskName.value = realTaskName
        activeTaskId.value = realTaskId

        if (realWorkDir) {
          basePath.value = realWorkDir
        }

        if (!taskMessages.value[realTaskId]) {
          taskMessages.value[realTaskId] = []
        }

        const existingTask = taskList.value.find(t => t.id === realTaskId)
        if (!existingTask) {
          taskList.value.unshift({
            id: realTaskId,
            title: realTaskName || '新任务',
            status: 'active',
            created_at: Date.now(),
            updated_at: Date.now(),
            workDir: realWorkDir,
          })
        } else {
          existingTask.workDir = realWorkDir
        }

        messages.value = taskMessages.value[realTaskId] || []
        fetchFileTree()
        if (data.checkpoints) {
          historyStates.value = data.checkpoints.map(cp => ({
            turn: cp.turn,
            task_id: realTaskId,
            tool: cp.description || '',
            summary: cp.description || `第 ${cp.turn} 轮`,
            diff_stat: cp.diff_stat || '',
            code_diff: cp.code_diff || '',
            timestamp: cp.timestamp * 1000,
            git_commit: cp.git_commit || '',
          }))
        } else {
          historyStates.value = []
        }
        console.log('[WS] Task started:', realTaskId, realTaskName, 'worktree:', realWorkDir)
        break

      case 'task_rolled_back':
        const rolledTask = taskList.value.find(t => t.id === data.task_id)
        if (rolledTask) {
          rolledTask.status = 'rolled_back'
        }
        if (activeTaskId.value === data.task_id) {
          currentTaskName.value = ''
          currentTaskId.value = ''
          historyStates.value = []
        }
        if (data.diff_audit) {
          addSystemMessage(`⚠️ 已成功触发物理回退 (Time Travel)\n${data.diff_audit}`)
        }
        if (data.reverted_files && data.reverted_files.length > 0) {
          lastRollbackInfo.value = {
            task_id: data.task_id,
            reverted_files: data.reverted_files,
            diff_audit: data.diff_audit,
            detailed_diff: data.detailed_diff,
          }
        }
        fetchFileTree()
        break

      case 'task_deleted':
        const deletedId = data.task_id
        taskList.value = taskList.value.filter(t => t.id !== deletedId)
        delete taskMessages.value[deletedId]
        if (activeTaskId.value === deletedId) {
          activeTaskId.value = null
          currentTaskId.value = null
          currentTaskName.value = ''
          messages.value = []
        }
        console.log('[WS] Task deleted:', deletedId)
        break

      case 'task_switched':
        activeTaskId.value = data.task_id
        currentTaskId.value = data.task_id
        currentTaskName.value = data.summary || ''
        status.value = '任务已切换'
        if (data.work_dir) {
          basePath.value = data.work_dir
        }
        if (!taskMessages.value[data.task_id]) {
          taskMessages.value[data.task_id] = []
        }
        messages.value = taskMessages.value[data.task_id]
        if (data.checkpoints) {
          historyStates.value = data.checkpoints.map(cp => ({
            turn: cp.turn,
            task_id: data.task_id,
            tool: cp.description || '',
            summary: cp.description || `第 ${cp.turn} 轮`,
            diff_stat: cp.diff_stat || '',
            code_diff: cp.code_diff || '',
            timestamp: cp.timestamp * 1000,
            git_commit: cp.git_commit || '',
          }))
        } else {
          historyStates.value = []
        }
        window.__xterm_write?.(`\x1b[36m[任务切换] ${data.summary || ''}\x1b[0m\n`)
        fetchFileTree()
        break

      case 'message':
        pushMessage({
          role: 'agent',
          content: data.content || data.data || '',
          timestamp: Date.now(),
        })
        break

      case 'tool_start':
        currentTool.value = {
          name: data.tool_name,
          args: data.args || {},
        }
        if (data.tool_name && (data.tool_name.includes('file_edit') || data.tool_name.includes('file_write') || data.tool_name.includes('bash'))) {
          petStatus.value = 'WRITING'
        }
        const toolMsg = `[执行工具: ${data.tool_name}]`
        window.__xterm_write?.(`\x1b[33m${toolMsg}\x1b[0m\n`)
        if (data.args) {
          window.__xterm_write?.(`\x1b[90m${JSON.stringify(data.args, null, 2)}\x1b[0m\n`)
        }
        break

      case 'tool_end':
        currentTool.value = null
        if (data.is_error) {
          petStatus.value = 'ERROR'
        }
        const resultMsg = data.result || ''
        if (data.is_error) {
          window.__xterm_write?.(`\x1b[31m[错误] ${resultMsg}\x1b[0m\n`)
        } else {
          window.__xterm_write?.(`\x1b[32m${resultMsg}\x1b[0m\n`)
        }
        if (data.tool_name && (data.tool_name === 'file_edit' || data.tool_name === 'file_write' || data.tool_name.startsWith('file_edit'))) {
          fetchFileTree()
        }
        if (data.diagnostics && data.diagnostics.length > 0) {
          diagnostics.value = data.diagnostics
        } else if (data.is_error) {
          diagnostics.value = []
        }
        break

      case 'typing':
        if (data.content) {
          enqueueTyping(data.content)
        }
        break

      case 'terminal':
        if (data.content) {
          window.__xterm_write?.(data.content)
        }
        break

      case 'open_file':
        if (data.file) {
          currentFile.value = data.file
          if (data.content !== undefined) {
            currentCode.value = data.content
          }
          const openIdx1 = openFiles.value.findIndex(f => f.path === data.file)
          if (openIdx1 >= 0) {
            activeFileIdx.value = openIdx1
            if (data.content !== undefined) openFiles.value[openIdx1].code = data.content
          } else {
            openFiles.value.push({ path: data.file, code: data.content || '' })
            activeFileIdx.value = openFiles.value.length - 1
          }
          if (data.content !== undefined && editorInstance) {
            const model = editorInstance.getModel()
            if (model) model.setValue(data.content)
          }
        }
        break

      case 'file_updated':
        if (data.file_name) {
          currentFile.value = data.file_name
          if (data.new_code !== undefined) {
            currentCode.value = data.new_code
          }
          const openIdx2 = openFiles.value.findIndex(f => f.path === data.file_name)
          if (openIdx2 >= 0) {
            activeFileIdx.value = openIdx2
            if (data.new_code !== undefined) openFiles.value[openIdx2].code = data.new_code
          } else {
            openFiles.value.push({ path: data.file_name, code: data.new_code || '' })
            activeFileIdx.value = openFiles.value.length - 1
          }
          if (data.new_code !== undefined && editorInstance) {
            const model = editorInstance.getModel()
            if (model) {
              model.setValue(data.new_code)
            }
          }
        }
        fetchFileTree()
        break

      case 'finish':
        isRunning.value = false
        status.value = '任务完成'
        petStatus.value = 'DONE'
        systemAlerts.value = []
        agentState.value = null
        activeContextFiles.value = []
        setTimeout(() => { petStatus.value = 'IDLE' }, 5000)
        pushMessage({
          role: 'agent',
          content: data.data || '任务已完成',
          timestamp: Date.now(),
          isFinish: true,
        })
        if (activeTaskId.value) {
          const finishedTask = taskList.value.find(t => t.id === activeTaskId.value)
          if (finishedTask) {
            finishedTask.status = 'completed'
          }
        }
        if (data.checkpoints && activeTaskId.value) {
          historyStates.value = data.checkpoints.map(cp => ({
            turn: cp.turn,
            task_id: activeTaskId.value,
            tool: cp.description || '',
            summary: cp.description || `第 ${cp.turn} 轮`,
            diff_stat: cp.diff_stat || '',
            code_diff: cp.code_diff || '',
            timestamp: cp.timestamp * 1000,
            git_commit: cp.git_commit || '',
          }))
        }
        activeTaskId.value = null
        currentTaskId.value = null
        currentTaskName.value = ''
        fetchFileTree()
        break

      case 'stopped':
        isRunning.value = false
        status.value = '已停止'
        petStatus.value = 'IDLE'
        systemAlerts.value = []
        agentState.value = null
        activeContextFiles.value = []
        pushMessage({
          role: 'agent',
          content: data.data || 'Agent 已停止',
          timestamp: Date.now(),
          isSystem: true,
        })
        window.__xterm_write?.(`\x1b[33m[停止] ${data.data || 'Agent 已停止'}\x1b[0m\n`)
        if (activeTaskId.value) {
          const stoppedTask = taskList.value.find(t => t.id === activeTaskId.value)
          if (stoppedTask) {
            stoppedTask.status = 'stopped'
          }
        }
        activeTaskId.value = null
        currentTaskId.value = null
        currentTaskName.value = ''
        break

      case 'error':
        isRunning.value = false
        status.value = '发生错误'
        petStatus.value = 'ERROR'
        agentState.value = null
        activeContextFiles.value = []
        setTimeout(() => {
          petStatus.value = 'IDLE'
          systemAlerts.value = []
        }, 8000)
        window.__xterm_write?.(`\x1b[31m[ERROR] ${data.data}\x1b[0m\n`)
        pushMessage({
          role: 'agent',
          content: `错误: ${data.data}`,
          timestamp: Date.now(),
          isError: true,
        })
        if (activeTaskId.value) {
          const errorTask = taskList.value.find(t => t.id === activeTaskId.value)
          if (errorTask) {
            errorTask.status = 'error'
          }
        }
        activeTaskId.value = null
        currentTaskId.value = null
        currentTaskName.value = ''
        break

      case 'refresh_tree':
        fetchFileTree()
        break

      case 'diagnostics':
        if (data.diagnostics && data.diagnostics.length > 0) {
          diagnostics.value = data.diagnostics
        } else {
          diagnostics.value = []
        }
        break

      case 'ask_user':
        pushMessage({
          role: 'agent',
          content: data.data?.question || data.question || '请回答问题',
          timestamp: Date.now(),
          questionId: data.data?.question_id || data.question_id,
          isQuestion: true,
        })
        break

      case 'command_confirmation':
        pendingConfirmation.value = {
          confirmationId: data.data?.confirmation_id,
          command: data.data?.command,
          reason: data.data?.reason,
        }
        window.__xterm_write?.(`\x1b[33m[需要授权] ${data.data?.command}\x1b[0m\n`)
        window.__xterm_write?.(`\x1b[90m原因: ${data.data?.reason}\x1b[0m\n`)
        break

      case 'refresh_tree':
      case 'file_changed':
        fetchFileTree()
        if (data.file) {
          currentFile.value = data.file
        }
        break

      case 'assistant':
        assistantText.value = data.data || ''
        pushMessage({
          role: 'agent',
          content: data.data || '',
          timestamp: Date.now(),
          isChat: true,
        })
        break

      case 'checkpoint_list':
        checkpointList.value = data.data || []
        break

      case 'checkpoints_updated':
        if (data.task_id === activeTaskId.value && data.checkpoints) {
          historyStates.value = data.checkpoints.map(cp => ({
            turn: cp.turn,
            task_id: data.task_id,
            tool: cp.description || '',
            summary: cp.description || `第 ${cp.turn} 轮`,
            diff_stat: cp.diff_stat || '',
            code_diff: cp.code_diff || '',
            timestamp: cp.timestamp * 1000,
            git_commit: cp.git_commit || '',
          }))
        }
        break

      case 'checkpoint_created':
        if (data.session_id && data.session_id === activeTaskId.value) {
          const existing = historyStates.value.findIndex(h => h.turn === data.turn)
          if (existing === -1) {
            historyStates.value.push({
              turn: data.turn,
              task_id: data.session_id,
              tool: data.description || '',
              summary: data.description || `第 ${data.turn} 轮`,
              diff_stat: data.diff_stat || '',
              code_diff: data.code_diff || '',
              timestamp: Date.now(),
              git_commit: data.git_commit || '',
            })
          } else {
            const entry = historyStates.value[existing]
            entry.tool = data.description || entry.tool
            entry.summary = data.description || entry.summary
            if (data.diff_stat) entry.diff_stat = data.diff_stat
            if (data.code_diff) entry.code_diff = data.code_diff
            if (data.git_commit) entry.git_commit = data.git_commit
          }
        }
        break

      case 'rollback_preview':
        rollbackPreview.value = {
          task_id: data.task_id,
          target_turn: data.target_turn,
          target_description: data.target_description,
          target_git_commit: data.target_git_commit,
          removed_turns: data.removed_turns || [],
          removed_descriptions: data.removed_descriptions || [],
          reverted_files: data.reverted_files || [],
          stat_summary: data.stat_summary || '',
          detailed_diff: data.detailed_diff || '',
          diff_report: data.diff_report || '',
          diff_lines: data.diff_lines || [],
          commits_being_reverted: data.commits_being_reverted || '',
        }
        break

      case 'checkpoint_view':
        checkpointView.value = {
          task_id: data.task_id,
          turn: data.turn,
          timestamp: data.timestamp,
          description: data.description,
          git_commit: data.git_commit,
          diff_stat: data.diff_stat,
          changed_files: data.changed_files || [],
          detailed_diff: data.detailed_diff || '',
          diff_lines: data.diff_lines || [],
          code_diff: data.code_diff || '',
        }
        break

      case 'graph_data':
        codeGraphData.value = data.data || { nodes: [], edges: [] }
        codeGraphLoading.value = false
        break

      case 'code_tour_data':
        if (Array.isArray(data.data) && data.data.length > 0) {
          _startTour(data.data)
        }
        break

      case 'system_msg':
        pushMessage({
          role: 'agent',
          content: data.content || '',
          timestamp: Date.now(),
          isSystem: true,
        })
        if (data.content) {
          window.__xterm_write?.(`\x1b[36m[系统] ${data.content}\x1b[0m\n`)
        }
        break

      case 'cost_update':
        costInfo.value = data.data || null
        break

      case 'context_compact':
        contextCompact.value = data.data || null
        window.__xterm_write?.(`\x1b[36m[上下文压缩] ${data.data?.reason || ''}\x1b[0m\n`)
        window.__xterm_write?.(`\x1b[90m剩余消息: ${data.data?.remaining_messages || 0}\x1b[0m\n`)
        setTimeout(() => { contextCompact.value = null }, 5000)
        break

      case 'task_merged':
        const mergedTaskId = data.task_id
        const mergedEntry = taskList.value.find(t => t.id === mergedTaskId)
        if (mergedEntry) {
          mergedEntry.status = 'merged'
        }
        if (activeTaskId.value === mergedTaskId) {
          basePath.value = originalBasePath.value
          fetchFileTree()
        }
        console.log('[WS] Task merged to main:', mergedTaskId)
        break

      case 'task_conflict':
        const conflictTaskId = data.task_id
        const conflictEntry = taskList.value.find(t => t.id === conflictTaskId)
        if (conflictEntry) {
          conflictEntry.status = 'conflict'
          conflictEntry.conflictFiles = data.conflict_files || []
        }
        console.warn('[WS] Task has merge conflicts:', conflictTaskId, data.conflict_files)
        break

      case 'task_step_rolled_back':
        const rolledBackTaskId = data.task_id
        const rolledBackEntry = taskList.value.find(t => t.id === rolledBackTaskId)
        if (rolledBackEntry && taskMessages.value[rolledBackTaskId]) {
          const trimCount = (data.steps_rolled_back || 1) * 2
          const msgs = taskMessages.value[rolledBackTaskId]
          if (msgs.length > trimCount) {
            taskMessages.value[rolledBackTaskId] = msgs.slice(0, -trimCount)
          }
          if (activeTaskId.value === rolledBackTaskId) {
            messages.value = taskMessages.value[rolledBackTaskId]
          }
        }
        if (data.diff_audit) {
          addSystemMessage(`⚠️ 已成功触发步骤回退 (Step Rollback)\n${data.diff_audit}`)
        }
        if (data.reverted_files && data.reverted_files.length > 0) {
          lastRollbackInfo.value = {
            task_id: data.task_id,
            reverted_files: data.reverted_files,
            diff_audit: data.diff_audit,
            detailed_diff: data.detailed_diff,
          }
        }
        fetchFileTree()
        break

      case 'task_reverted':
        const revertedTaskId = data.task_id
        const revertedEntry = taskList.value.find(t => t.id === revertedTaskId)
        if (revertedEntry) {
          revertedEntry.status = 'reverted'
        }
        if (activeTaskId.value === revertedTaskId) {
          basePath.value = originalBasePath.value
          fetchFileTree()
        }
        console.log('[WS] Task reverted on main:', revertedTaskId)
        break

      case 'mcp_services':
        mcpServices.value = data.data || ''
        console.log('[WS] MCP services listed')
        break

      case 'webcontainer_artifacts':
        console.log('[WS] 🌐 WebContainer artifacts received:', data.task_id, 'files:', data.file_count)
        _handleWebContainerArtifacts(data)
        break

      case 'artifacts_ready':
        console.log('[WS] 📦 Artifacts ready:', data.execution_env, 'files:', data.file_count)
        break

      case 'swarm_loop_start':
        status.value = data.data || ''
        if (data.role === 'coder') {
          petStatus.value = 'WRITING'
        } else if (data.role === 'reviewer') {
          petStatus.value = 'REVIEWING'
        }
        messages.value.push({
          role: 'agent',
          content: data.data || '',
          timestamp: Date.now(),
          msgType: 'system_alert',
        })
        break

      case 'swarm_phase_change':
        status.value = data.data || ''
        if (data.role === 'reviewer') {
          petStatus.value = 'REVIEWING'
        } else if (data.role === 'coder') {
          petStatus.value = 'WRITING'
        }
        messages.value.push({
          role: 'agent',
          content: data.data || '',
          timestamp: Date.now(),
          msgType: 'system_alert',
        })
        break

      case 'swarm_rejected':
        status.value = data.data || ''
        petStatus.value = 'WRITING'
        messages.value.push({
          role: 'agent',
          content: `❌ Reviewer 打回重写！意见：${data.reviewer_feedback || ''}`,
          timestamp: Date.now(),
          msgType: 'system_alert',
        })
        break

      case 'swarm_result':
        if (data.result) {
          const r = data.result
          status.value = r.status || ''
        }
        break

      default:
        console.log('[WS] Unknown message type:', data.type, data)
    }
  }

  function setBasePath(path) {
    basePath.value = path
    originalBasePath.value = path
    files.value = []
    currentFile.value = null
    currentIsDir.value = false
    currentCode.value = ''
    try {
      localStorage.setItem(LAST_PATH_KEY, path)
    } catch {}
    fetchFileTree()
  }

  function setCurrentItem(path, isDir = false) {
    currentFile.value = path
    currentIsDir.value = isDir
    diagnostics.value = []
    if (!isDir) {
      const existing = openFiles.value.findIndex(f => f.path === path)
      if (existing >= 0) {
        activeFileIdx.value = existing
      } else {
        openFiles.value.push({ path, code: '' })
        activeFileIdx.value = openFiles.value.length - 1
      }
      fetchFileContent(path)
    }
  }

  function switchToFile(idx) {
    if (idx < 0 || idx >= openFiles.value.length) return
    activeFileIdx.value = idx
    const file = openFiles.value[idx]
    currentFile.value = file.path
    currentCode.value = file.code
    diagnostics.value = []
    if (editorInstance) {
      const model = editorInstance.getModel()
      if (model) {
        model.setValue(file.code || '')
      }
    }
  }

  function closeFile(idx) {
    if (idx < 0 || idx >= openFiles.value.length) return
    openFiles.value.splice(idx, 1)
    if (openFiles.value.length === 0) {
      currentFile.value = null
      currentCode.value = ''
      activeFileIdx.value = 0
      if (editorInstance) {
        const model = editorInstance.getModel()
        if (model) model.setValue('')
      }
      return
    }
    if (activeFileIdx.value >= openFiles.value.length) {
      activeFileIdx.value = openFiles.value.length - 1
    } else if (activeFileIdx.value > idx) {
      activeFileIdx.value--
    } else if (activeFileIdx.value === idx) {
      activeFileIdx.value = Math.min(idx, openFiles.value.length - 1)
    }
    switchToFile(activeFileIdx.value)
  }

  async function fetchTaskRegistry() {
    try {
      const uid = userId.value || 0
      const resp = await fetch(`/api/v1/task-registry?user_id=${uid}`)
      if (!resp.ok) {
        console.warn('[API] fetchTaskRegistry HTTP error:', resp.status)
        return
      }
      const data = await resp.json()
      console.log('[API] fetchTaskRegistry response:', JSON.stringify(data).slice(0, 500))

      let backendTasks = []
      if (Array.isArray(data)) {
        backendTasks = data
      } else if (data && Array.isArray(data.tasks)) {
        backendTasks = data.tasks
      } else if (data && Array.isArray(data.data)) {
        backendTasks = data.data
      } else if (data && typeof data === 'object') {
        const vals = Object.values(data)
        if (vals.length > 0 && vals.every(v => typeof v === 'object' && v !== null)) {
          backendTasks = vals.map((v, i) => {
            if (!v.task_id && !v.id) {
              v.task_id = Object.keys(data)[i]
            }
            return v
          })
        } else {
          const possibleArray = vals.find(v => Array.isArray(v))
          if (possibleArray) backendTasks = possibleArray
        }
      }

      console.log('[API] fetchTaskRegistry extracted tasks count:', backendTasks.length)

      // 最小映射：只补齐前端模板需要的别名，其余字段原样透传（不丢弃任何后端字段）
      taskList.value = backendTasks.map(t => ({
        ...t,
        id: t.task_id || t.id,
        title: t.summary || t.title || '未命名任务',
        baseTaskId: t.base_task_id || t.baseTaskId || '',
        workDir: t.work_dir || t.workDir || '',
        mergeCommitHash: t.merge_commit_hash || t.mergeCommitHash || '',
      })).sort((a, b) => {
        const ta = a.created_at ? new Date(a.created_at).getTime() : 0
        const tb = b.created_at ? new Date(b.created_at).getTime() : 0
        return tb - ta
      })
    } catch (e) {
      console.error('[API] fetchTaskRegistry error:', e)
    }
  }

  function showToast(message, type = 'info', duration = 3000) {
    const id = ++toastIdCounter
    toasts.value.push({ id, message, type, duration })
    if (duration > 0) {
      setTimeout(() => removeToast(id), duration)
    }
    return id
  }

  function removeToast(id) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  async function fetchFileTree() {
    try {
      const uid = userId.value || 0
      const resp = await fetch(`/api/v1/files?path=${encodeURIComponent(basePath.value)}&user_id=${uid}`)
      if (resp.ok) {
        const data = await resp.json()
        files.value = data.files || []
      }
    } catch (e) {
      console.error('[API] Failed to fetch file tree:', e)
    }
  }

  async function fetchFileContent(relativePath) {
    try {
      const fullPath = basePath.value + '/' + relativePath
      const uid = userId.value || 0
      const resp = await fetch(`/api/v1/file?path=${encodeURIComponent(fullPath)}&user_id=${uid}`)
      if (resp.ok) {
        const data = await resp.json()
        currentFile.value = relativePath
        currentCode.value = data.content || ''
        const openIdx = openFiles.value.findIndex(f => f.path === relativePath)
        if (openIdx >= 0) {
          openFiles.value[openIdx].code = currentCode.value
        }
        if (editorInstance) {
          const model = editorInstance.getModel()
          if (model) {
            model.setValue(currentCode.value)
          }
        }
      }
    } catch (e) {
      console.error('[API] Failed to fetch file content:', e)
    }
  }

  function enqueueTyping(content) {
    const chars = Array.from(content)
    typingQueue.value.push(...chars)
    if (!isTyping.value) {
      startTypingLoop()
    }
  }

  function startTypingLoop() {
    if (isTyping.value) return
    isTyping.value = true

    const tick = () => {
      if (typingQueue.value.length === 0) {
        isTyping.value = false
        rafId = null
        return
      }

      const batchSize = Math.min(3, typingQueue.value.length)
      const charsToInsert = typingQueue.value.splice(0, batchSize)
      const text = charsToInsert.join('')

      if (editorInstance) {
        const position = editorInstance.getPosition()
        editorInstance.executeEdits('agent-typing', [{
          range: {
            startLineNumber: position.lineNumber,
            startColumn: position.column,
            endLineNumber: position.lineNumber,
            endColumn: position.column,
          },
          text,
          forceMoveMarkers: true,
        }])

        const newLineCount = (text.match(/\n/g) || []).length
        let newLine, newCol
        if (newLineCount > 0) {
          newLine = position.lineNumber + newLineCount
          const lastNewlineIdx = text.lastIndexOf('\n')
          newCol = text.length - lastNewlineIdx
        } else {
          newLine = position.lineNumber
          newCol = position.column + text.length
        }

        editorInstance.setPosition({ lineNumber: newLine, column: newCol })
        editorInstance.revealPositionInCenter({ lineNumber: newLine, column: newCol })
      }

      rafId = requestAnimationFrame(tick)
    }

    rafId = requestAnimationFrame(tick)
  }

  function registerEditor(editor) {
    editorInstance = editor
  }

  function unregisterEditor() {
    editorInstance = null
    if (rafId) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
    isTyping.value = false
    typingQueue.value = []
  }

  function addMermaidDiagram(title, svg) {
    const existing = mermaidDiagrams.value.findIndex(d => d.title === title)
    if (existing >= 0) {
      mermaidDiagrams.value[existing].svg = svg
      activeMermaidIdx.value = existing
    } else {
      mermaidDiagrams.value.push({ title, svg, id: Date.now() })
      activeMermaidIdx.value = mermaidDiagrams.value.length - 1
    }
  }

  function removeMermaidDiagram(idx) {
    mermaidDiagrams.value.splice(idx, 1)
    if (activeMermaidIdx.value >= mermaidDiagrams.value.length) {
      activeMermaidIdx.value = mermaidDiagrams.value.length - 1
    }
  }

  function closeMermaidView() {
    activeMermaidIdx.value = -1
  }

  function sendTask(task, options = {}) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Not connected, cannot send task')
      pushMessage({
        role: 'agent',
        content: '⚠️ WebSocket 未连接，正在尝试重连...请稍后重试',
        timestamp: Date.now(),
        isSystem: true,
      })
      if (!ws.value || ws.value.readyState === WebSocket.CLOSED) {
        connect()
      }
      return false
    }

    const isNewTask = !activeTaskId.value || options.forceNewTask

    if (isNewTask) {
      const tempId = 'task_' + Math.random().toString(36).substr(2, 9)
      taskMessages.value[tempId] = [{ role: 'user', content: task, timestamp: Date.now() }]
      taskList.value.unshift({
        id: tempId,
        title: task.substring(0, 30) + (task.length > 30 ? '...' : ''),
        status: 'active',
        created_at: Date.now(),
        updated_at: Date.now(),
      })
      activeTaskId.value = tempId
      currentTaskId.value = tempId
      currentTaskName.value = task.substring(0, 30) + (task.length > 30 ? '...' : '')
      messages.value = taskMessages.value[tempId]

      const allSkills = [...new Set([
        ...selectedSkills.value,
        ...(options.skills || []),
      ])]

      const payload = _injectIdentity({
        type: 'chat_new_task',
        task: task,
        work_dir: basePath.value,
        max_turns: options.max_turns || 30,
        model: options.model,
        api_key: options.apiKey,
        base_url: options.baseUrl,
        provider: options.provider,
        base_task_id: options.base_task_id || pendingBaseTaskId.value || '',
        auto_approve: autoApprove.value,
        use_swarm: options.use_swarm || false,
        images: options.images && options.images.length ? options.images : undefined,
        skills: allSkills.length ? allSkills : undefined,
      })

      pendingBaseTaskId.value = ''

      Object.keys(payload).forEach(key => {
        if (payload[key] === undefined || payload[key] === null) {
          delete payload[key]
        }
      })

      console.log('[WS] Sending new task:', payload)
      ws.value.send(JSON.stringify(payload))
      selectedSkills.value = []
    } else {
      if (!taskMessages.value[activeTaskId.value]) {
        taskMessages.value[activeTaskId.value] = []
      }
      taskMessages.value[activeTaskId.value].push({ role: 'user', content: task, timestamp: Date.now() })
      messages.value = taskMessages.value[activeTaskId.value]

      const payload = _injectIdentity({
        type: 'chat_continue',
        task: task,
        work_dir: basePath.value,
        max_turns: options.max_turns || 30,
        task_id: activeTaskId.value,
        model: options.model,
        api_key: options.apiKey,
        base_url: options.baseUrl,
        provider: options.provider,
        auto_approve: autoApprove.value,
        use_swarm: options.use_swarm || false,
      })

      Object.keys(payload).forEach(key => {
        if (payload[key] === undefined || payload[key] === null) {
          delete payload[key]
        }
      })

      console.log('[WS] Sending continue task:', payload)
      ws.value.send(JSON.stringify(payload))
    }

    isRunning.value = true
    status.value = 'Agent 正在思考...'
    return true
  }

  function sendSystemCommand(action, params = {}) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Not connected, cannot send system command')
      return false
    }

    const payload = _injectIdentity({
      type: 'system_command',
      action: action,
      task_id: currentTaskId.value || undefined,
      work_dir: basePath.value,
      ...params,
    })

    Object.keys(payload).forEach(key => {
      if (payload[key] === undefined || payload[key] === null) {
        delete payload[key]
      }
    })

    console.log('[WS] Sending system command:', payload)
    ws.value.send(JSON.stringify(payload))
    return true
  }

  function stopAgent() {
    if (!isRunning.value) {
      console.warn('[WS] Agent is not running')
      return false
    }
    console.log('[WS] Sending stop command')
    return sendSystemCommand('stop_agent')
  }

  async function deleteTask(taskId) {
    if (!taskId) return false
    try {
      const taskTitle = taskList.value.find(t => t.id === taskId)?.title || taskId
      taskList.value = taskList.value.filter(t => t.id !== taskId)
      delete taskMessages.value[taskId]
      if (activeTaskId.value === taskId) {
        activeTaskId.value = null
        currentTaskId.value = null
        currentTaskName.value = ''
        messages.value = []
      }
      const sent = sendSystemCommand('delete_task', { target_task_id: taskId })
      if (sent) {
        await new Promise(resolve => setTimeout(resolve, 1500))
        await fetchTaskRegistry()
      }
      showToast(`🗑️ 任务「${taskTitle.slice(0, 20)}」已删除`, 'success')
      return true
    } catch (e) {
      console.error('[Store] deleteTask error:', e)
      showToast('❌ 删除任务失败: ' + (e.message || '未知错误'), 'error')
      await fetchTaskRegistry()
      return false
    }
  }

  function mergeTask(taskId, force = false) {
    if (!taskId) return false
    return sendSystemCommand('merge_task', { target_task_id: taskId, force })
  }

  function rollbackStep(taskId, steps = 1) {
    if (!taskId) return false
    return sendSystemCommand('rollback_task', { target_task_id: taskId, steps })
  }

  function previewRollback(taskId, steps = 1, toTurn = null) {
    if (!taskId) return false
    const params = { target_task_id: taskId, steps }
    if (toTurn !== null) {
      params.to_turn = toTurn
    }
    return sendSystemCommand('preview_rollback', params)
  }

  function confirmRollback(taskId, steps = 1) {
    rollbackPreview.value = null
    return rollbackStep(taskId, steps)
  }

  function dismissRollbackPreview() {
    rollbackPreview.value = null
  }

  function viewCheckpoint(taskId, turn) {
    if (!taskId) return false
    return sendSystemCommand('view_checkpoint', { target_task_id: taskId, turn })
  }

  function dismissCheckpointView() {
    checkpointView.value = null
  }

  function revertMergedTask(taskId) {
    if (!taskId) return false
    return sendSystemCommand('revert_merged_task', { target_task_id: taskId })
  }

  async function _handleWebContainerArtifacts(data) {
    const vfs = data.vfs
    if (!vfs || typeof vfs !== 'object') {
      wcError.value = '无效的 VFS 数据'
      wcStatus.value = 'error'
      return
    }

    try {
      wcStatus.value = 'booting'
      wcError.value = null
      wcOutputBuffer.value = []
      window.__xterm_write?.('\x1b[36m[WebContainer] 🚀 正在启动浏览器内 Node.js 环境...\x1b[0m\n')

      _wcManager = WebContainerManager.getInstance()

      _wcManager.onOutput((output) => {
        wcOutputBuffer.value.push(output)
        if (wcOutputBuffer.value.length > 500) {
          wcOutputBuffer.value = wcOutputBuffer.value.slice(-300)
        }
        window.__xterm_write?.(output)
      })

      _wcManager.onPreviewUrl((url) => {
        wcPreviewUrl.value = url
        wcShowPreview.value = true
        window.__xterm_write?.(`\x1b[32m[WebContainer] 🟢 预览服务已就绪: ${url}\x1b[0m\n`)
      })

      _wcManager.onServerReady((port, url) => {
        wcStatus.value = 'running'
        console.log(`[WebContainer] Server ready: port=${port}, url=${url}`)
      })

      await _wcManager.boot()
      wcStatus.value = 'mounting'
      window.__xterm_write?.('\x1b[36m[WebContainer] 📁 正在挂载文件到虚拟文件系统...\x1b[0m\n')

      await _wcManager.mountFiles(vfs)
      wcStatus.value = 'installing'
      window.__xterm_write?.('\x1b[36m[WebContainer] 📦 正在执行 npm install...\x1b[0m\n')

      const installResult = await _wcManager.installDependencies()
      if (!installResult.success) {
        wcError.value = `npm install 失败 (exit code: ${installResult.exitCode})`
        wcStatus.value = 'error'
        window.__xterm_write?.(`\x1b[31m[WebContainer] ❌ npm install 失败\x1b[0m\n`)
        return
      }

      wcStatus.value = 'starting'
      window.__xterm_write?.('\x1b[36m[WebContainer] 🏃 正在启动开发服务器 (npm run dev)...\x1b[0m\n')

      _wcManager.startDevServer()
    } catch (err) {
      console.error('[WebContainer] Error:', err)
      wcError.value = err.message || String(err)
      wcStatus.value = 'error'
      window.__xterm_write?.(`\x1b[31m[WebContainer] ❌ 启动失败: ${err.message}\x1b[0m\n`)
    }
  }

  function stopWebContainer() {
    if (_wcManager) {
      _wcManager.killRunningProcess()
      wcStatus.value = 'idle'
      wcShowPreview.value = false
      window.__xterm_write?.('\x1b[33m[WebContainer] 🛑 开发服务器已停止\x1b[0m\n')
    }
  }

  function closeWebContainerPreview() {
    wcShowPreview.value = false
  }

  function openWebContainerPreview() {
    if (wcPreviewUrl.value) {
      wcShowPreview.value = true
    }
  }

  function resetWebContainer() {
    if (_wcManager) {
      _wcManager.teardown()
      _wcManager = null
    }
    wcPreviewUrl.value = null
    wcStatus.value = 'idle'
    wcError.value = null
    wcOutputBuffer.value = []
    wcShowPreview.value = false
  }

  function addSystemMessage(content) {
    messages.value.push({
      role: 'system',
      content: content,
      timestamp: Date.now(),
    })
  }

  function listMcpServices() {
    return sendSystemCommand('list_mcp_services')
  }

  async function switchTask(taskId) {
    if (activeTaskId.value === taskId) return
    activeTaskId.value = taskId
    const task = taskList.value.find(t => t.id === taskId)
    if (task) {
      currentTaskId.value = taskId
      currentTaskName.value = task.title
    }
    if (!taskMessages.value[taskId]) {
      taskMessages.value[taskId] = []
    }
    if (taskMessages.value[taskId].length === 0) {
      try {
        const uid = userId.value || 0
        const resp = await fetch(`/api/v1/tasks/${encodeURIComponent(taskId)}/messages?user_id=${uid}`)
        if (resp.ok) {
          const data = await resp.json()
          const backendMsgs = data.messages || []
          if (backendMsgs.length > 0) {
            taskMessages.value[taskId] = backendMsgs
          }
        }
      } catch (e) {
        console.error('[API] fetchTaskMessages error:', e)
      }
    }
    messages.value = taskMessages.value[taskId]
    sendSystemCommand('switch_task', { target_task_id: taskId })
  }

  function startNewTask() {
    activeTaskId.value = null
    currentTaskId.value = null
    currentTaskName.value = ''
    messages.value = []
    basePath.value = originalBasePath.value
    pendingBaseTaskId.value = ''
    fetchFileTree()
  }

  function prepareNewTaskBasedOn(taskId) {
    activeTaskId.value = null
    currentTaskId.value = null
    currentTaskName.value = ''
    messages.value = []
    basePath.value = originalBasePath.value
    pendingBaseTaskId.value = taskId
    fetchFileTree()
  }

  function answerQuestion(questionId, answer) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Not connected, cannot answer question')
      return false
    }

    ws.value.send(JSON.stringify(_injectIdentity({
      type: 'user_answer',
      question_id: questionId,
      answer: answer,
    })))

    const msgIndex = messages.value.findIndex(m => m.questionId === questionId)
    if (msgIndex !== -1) {
      messages.value[msgIndex].answered = true
      messages.value[msgIndex].answer = answer
    }

    return true
  }

  function confirmCommand(approved) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Not connected, cannot confirm command')
      return false
    }

    if (!pendingConfirmation.value) {
      console.warn('[WS] No pending confirmation')
      return false
    }

    ws.value.send(JSON.stringify(_injectIdentity({
      type: 'command_confirm',
      confirmation_id: pendingConfirmation.value.confirmationId,
      approved: approved,
    })))

    window.__xterm_write?.(`\x1b[36m[用户${approved ? '已授权' : '拒绝'}] ${pendingConfirmation.value.command}\x1b[0m\n`)
    pendingConfirmation.value = null
    return true
  }

  function disconnect() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    unregisterEditor()
  }

  function _startTour(steps) {
    if (!Array.isArray(steps) || steps.length === 0) return
    tourSteps.value = steps
    tourActiveIdx.value = 0
    _applyTourStep(steps[0])
  }

  function _applyTourStep(step) {
    if (!step) return
    const relPath = step.file || ''
    const funcName = step.function || ''
    tourActiveNodeId.value = funcName ? `${relPath}::${funcName}` : relPath
  }

  return {
    ws,
    connected,
    messages,
    files,
    basePath,
    currentFile,
    currentIsDir,
    currentCode,
    openFiles,
    activeFileIdx,
    switchToFile,
    closeFile,
    diagnostics,
    typingQueue,
    isTyping,
    isRunning,
    status,
    currentTool,
    pendingConfirmation,
    mermaidDiagrams,
    activeMermaidIdx,
    addMermaidDiagram,
    removeMermaidDiagram,
    closeMermaidView,
    costInfo,
    contextCompact,
    mcpServices,
    lastRollbackInfo,
    assistantText,
    petStatus,
    agentState,
    activeContextFiles,
    systemAlerts,
    checkpointList,
    taskList,
    taskMessages,
    activeTaskId,
    autoApprove,
    userId,
    sessionId,
    hasNewCareerAdvice,
    careerAdviceData,
    newSession,
    historyStates,
    rollbackPreview,
    checkpointView,
    connect,
    disconnect,
    sendTask,
    sendSystemCommand,
    stopAgent,
    deleteTask,
    mergeTask,
    rollbackStep,
    previewRollback,
    confirmRollback,
    dismissRollbackPreview,
    viewCheckpoint,
    dismissCheckpointView,
    revertMergedTask,
    listMcpServices,
    switchTask,
    startNewTask,
    prepareNewTaskBasedOn,
    answerQuestion,
    confirmCommand,
    setBasePath,
    setCurrentItem,
    fetchFileTree,
    fetchFileContent,
    fetchTaskRegistry,
    toasts,
    showToast,
    removeToast,
    registerEditor,
    unregisterEditor,
    wcPreviewUrl,
    wcStatus,
    wcError,
    wcOutputBuffer,
    wcShowPreview,
    stopWebContainer,
    closeWebContainerPreview,
    openWebContainerPreview,
    resetWebContainer,
    selectedSkills,
    architectureVisible,
    architectureData,
    showArchitecture(data) {
      architectureData.value = data || { nodes: [], edges: [] }
      architectureVisible.value = true
    },
    hideArchitecture() {
      architectureVisible.value = false
    },
    codeGraphVisible,
    codeGraphLoading,
    codeGraphData,
    tourSteps,
    tourActiveIdx,
    tourActiveNodeId,
    tourActiveStep,
    showCodeGraph(data) {
      codeGraphData.value = data || { nodes: [], edges: [] }
      codeGraphVisible.value = true
    },
    hideCodeGraph() {
      codeGraphVisible.value = false
    },
    generateGraph() {
      if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
        return false
      }
      codeGraphLoading.value = true
      codeGraphVisible.value = true
      codeGraphData.value = { nodes: [], edges: [] }
      const payload = _injectIdentity({
        type: 'system_command',
        action: 'generate_graph',
        work_dir: basePath.value,
      })
      ws.value.send(JSON.stringify(payload))
      return true
    },

    startTour(steps) {
      _startTour(steps)
    },

    tourNext() {
      if (tourActiveIdx.value < 0 || tourActiveIdx.value >= tourSteps.value.length - 1) return
      tourActiveIdx.value++
      _applyTourStep(tourSteps.value[tourActiveIdx.value])
    },

    tourPrev() {
      if (tourActiveIdx.value <= 0) return
      tourActiveIdx.value--
      _applyTourStep(tourSteps.value[tourActiveIdx.value])
    },

    stopTour() {
      tourSteps.value = []
      tourActiveIdx.value = -1
      tourActiveNodeId.value = null
    },
  }
})
