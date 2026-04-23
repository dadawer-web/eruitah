import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'

export const useAgentStore = defineStore('agent', () => {
  const ws = shallowRef(null)
  const connected = ref(false)
  const messages = ref([])
  const files = ref([])
  const basePath = ref('/tmp/eruitah-sandbox')
  const currentFile = ref(null)
  const currentCode = ref('')
  const typingQueue = ref([])
  const isTyping = ref(false)
  const isRunning = ref(false)
  const status = ref('')
  const currentTool = ref(null)
  const pendingConfirmation = ref(null)
  let rafId = null
  let editorInstance = null

  function connect() {
    if (ws.value && (ws.value.readyState === WebSocket.OPEN || ws.value.readyState === WebSocket.CONNECTING)) {
      return
    }

    const socket = new WebSocket('ws://localhost:8001/ws/coding')

    socket.onopen = () => {
      connected.value = true
      console.log('[WS] Connected to coding agent')
    }

    socket.onclose = () => {
      connected.value = false
      isRunning.value = false
      console.log('[WS] Disconnected')
      setTimeout(() => connect(), 3000)
    }

    socket.onerror = (err) => {
      console.error('[WS] Error:', err)
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
      case 'status':
        status.value = data.data || ''
        break

      case 'message':
        messages.value.push({
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
        const toolMsg = `[执行工具: ${data.tool_name}]`
        window.__xterm_write?.(`\x1b[33m${toolMsg}\x1b[0m\n`)
        if (data.args) {
          window.__xterm_write?.(`\x1b[90m${JSON.stringify(data.args, null, 2)}\x1b[0m\n`)
        }
        break

      case 'tool_end':
        currentTool.value = null
        const resultMsg = data.result || ''
        if (data.is_error) {
          window.__xterm_write?.(`\x1b[31m[错误] ${resultMsg}\x1b[0m\n`)
        } else {
          window.__xterm_write?.(`\x1b[32m${resultMsg}\x1b[0m\n`)
        }
        if (data.tool_name === 'file_edit' || data.tool_name === 'file_write') {
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
        messages.value.push({
          role: 'agent',
          content: data.data || '任务已完成',
          timestamp: Date.now(),
          isFinish: true,
        })
        fetchFileTree()
        break

      case 'error':
        isRunning.value = false
        status.value = '发生错误'
        window.__xterm_write?.(`\x1b[31m[ERROR] ${data.data}\x1b[0m\n`)
        messages.value.push({
          role: 'agent',
          content: `错误: ${data.data}`,
          timestamp: Date.now(),
          isError: true,
        })
        break

      case 'ask_user':
        messages.value.push({
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

      default:
        console.log('[WS] Unknown message type:', data.type, data)
    }
  }

  function setBasePath(path) {
    basePath.value = path
    files.value = []
    currentFile.value = null
    currentCode.value = ''
    fetchFileTree()
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
      return false
    }

    messages.value.push({
      role: 'user',
      content: task,
      timestamp: Date.now(),
    })

    const payload = {
      task: task,
      work_dir: basePath.value,
      max_turns: options.max_turns || 10,
      model: options.model,
      api_key: options.apiKey,
      base_url: options.baseUrl,
      provider: options.provider,
    }

    Object.keys(payload).forEach(key => {
      if (payload[key] === undefined || payload[key] === null) {
        delete payload[key]
      }
    })

    console.log('[WS] Sending task:', payload)
    ws.value.send(JSON.stringify(payload))
    isRunning.value = true
    status.value = 'Agent 正在思考...'
    return true
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
    currentCode,
    typingQueue,
    isTyping,
    isRunning,
    status,
    currentTool,
    pendingConfirmation,
    connect,
    disconnect,
    sendTask,
    answerQuestion,
    confirmCommand,
    setBasePath,
    fetchFileTree,
    fetchFileContent,
    registerEditor,
    unregisterEditor,
  }
})
