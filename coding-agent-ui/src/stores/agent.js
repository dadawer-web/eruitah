import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'

const LAST_PATH_KEY = 'coding-agent-last-path'

function getLastPath() {
  try {
    return localStorage.getItem(LAST_PATH_KEY) || '/tmp/eruitah-sandbox'
  } catch {
    return '/tmp/eruitah-sandbox'
  }
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
  const typingQueue = ref([])
  const isTyping = ref(false)
  const isRunning = ref(false)
  const status = ref('')
  const currentTool = ref(null)
  const pendingConfirmation = ref(null)
  const costInfo = ref(null)
  const lastRollbackInfo = ref(null)
  const contextCompact = ref(null)
  const assistantText = ref('')
  const currentTaskId = ref(null)
  const currentTaskName = ref('')
  const petStatus = ref('IDLE')
  const checkpointList = ref([])

  const taskList = ref([])
  const taskMessages = ref({})
  const activeTaskId = ref(null)
  const autoApprove = ref(false)

  let rafId = null
  let editorInstance = null
  let wsRetryCount = 0
  const WS_MAX_RETRY = 20

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

    const socket = new WebSocket('ws://localhost:8001/ws/coding')

    socket.onopen = () => {
      connected.value = true
      wsRetryCount = 0
      console.log('[WS] Connected to coding agent')
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
            workDir: realWorkDir,
          })
        } else {
          existingTask.workDir = realWorkDir
        }

        messages.value = taskMessages.value[realTaskId] || []
        fetchFileTree()
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
            if (editorInstance) {
              const model = editorInstance.getModel()
              if (model) {
                model.setValue(data.content)
              }
            }
          }
        }
        break

      case 'file_updated':
        if (data.file_name) {
          currentFile.value = data.file_name
          if (data.new_code !== undefined) {
            currentCode.value = data.new_code
            if (editorInstance) {
              const model = editorInstance.getModel()
              if (model) {
                model.setValue(data.new_code)
              }
            }
          }
        }
        fetchFileTree()
        break

      case 'finish':
        isRunning.value = false
        status.value = '任务完成'
        petStatus.value = 'DONE'
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
        activeTaskId.value = null
        currentTaskId.value = null
        currentTaskName.value = ''
        fetchFileTree()
        break

      case 'stopped':
        isRunning.value = false
        status.value = '已停止'
        petStatus.value = 'IDLE'
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
        setTimeout(() => { petStatus.value = 'IDLE' }, 8000)
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
        })
        break

      case 'checkpoint_list':
        checkpointList.value = data.data || []
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
        mergedTaskId = data.task_id
        taskEntry = taskList.value.find(t => t.id === mergedTaskId)
        if (taskEntry) {
          taskEntry.status = 'merged'
        }
        if (activeTaskId.value === mergedTaskId) {
          basePath.value = originalBasePath.value
          fetchFileTree()
        }
        console.log('[WS] Task merged to main:', mergedTaskId)
        break

      case 'task_conflict':
        conflictTaskId = data.task_id
        conflictEntry = taskList.value.find(t => t.id === conflictTaskId)
        if (conflictEntry) {
          conflictEntry.status = 'conflict'
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
        revertedTaskId = data.task_id
        revertedEntry = taskList.value.find(t => t.id === revertedTaskId)
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
    if (!isDir) {
      fetchFileContent(path)
    }
  }

  async function fetchFileTree() {
    try {
      const resp = await fetch(`http://localhost:8001/api/v1/files?path=${encodeURIComponent(basePath.value)}`)
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
      const resp = await fetch(`http://localhost:8001/api/v1/file?path=${encodeURIComponent(fullPath)}`)
      if (resp.ok) {
        const data = await resp.json()
        currentFile.value = relativePath
        currentCode.value = data.content || ''
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
      })
      activeTaskId.value = tempId
      currentTaskId.value = tempId
      currentTaskName.value = task.substring(0, 30) + (task.length > 30 ? '...' : '')
      messages.value = taskMessages.value[tempId]

      const payload = {
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
      }

      pendingBaseTaskId.value = ''

      Object.keys(payload).forEach(key => {
        if (payload[key] === undefined || payload[key] === null) {
          delete payload[key]
        }
      })

      console.log('[WS] Sending new task:', payload)
      ws.value.send(JSON.stringify(payload))
    } else {
      if (!taskMessages.value[activeTaskId.value]) {
        taskMessages.value[activeTaskId.value] = []
      }
      taskMessages.value[activeTaskId.value].push({ role: 'user', content: task, timestamp: Date.now() })
      messages.value = taskMessages.value[activeTaskId.value]

      const payload = {
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
      }

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

    const payload = {
      type: 'system_command',
      action: action,
      task_id: currentTaskId.value || undefined,
      work_dir: basePath.value,
      ...params,
    }

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

  function deleteTask(taskId) {
    if (!taskId) return false
    return sendSystemCommand('delete_task', { target_task_id: taskId })
  }

  function mergeTask(taskId) {
    if (!taskId) return false
    return sendSystemCommand('merge_task', { target_task_id: taskId })
  }

  function rollbackStep(taskId, steps = 1) {
    if (!taskId) return false
    return sendSystemCommand('rollback_task', { target_task_id: taskId, steps })
  }

  function revertMergedTask(taskId) {
    if (!taskId) return false
    return sendSystemCommand('revert_merged_task', { target_task_id: taskId })
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

  function switchTask(taskId) {
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

    ws.value.send(JSON.stringify({
      type: 'user_answer',
      question_id: questionId,
      answer: answer,
    }))

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

    ws.value.send(JSON.stringify({
      type: 'command_confirm',
      confirmation_id: pendingConfirmation.value.confirmationId,
      approved: approved,
    }))

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

  return {
    ws,
    connected,
    messages,
    files,
    basePath,
    currentFile,
    currentIsDir,
    currentCode,
    typingQueue,
    isTyping,
    isRunning,
    status,
    currentTool,
    pendingConfirmation,
    costInfo,
    contextCompact,
    mcpServices,
    lastRollbackInfo,
    assistantText,
    petStatus,
    checkpointList,
    taskList,
    taskMessages,
    activeTaskId,
    autoApprove,
    connect,
    disconnect,
    sendTask,
    sendSystemCommand,
    stopAgent,
    deleteTask,
    mergeTask,
    rollbackStep,
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
    registerEditor,
    unregisterEditor,
  }
})
