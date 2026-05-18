import { WebContainer } from '@webcontainer/api'

let _instance = null
let _bootPromise = null
let _previewUrl = null
let _onPreviewUrlCallbacks = []
let _onServerReadyCallbacks = []

class WebContainerManager {
  constructor() {
    if (_instance) {
      return _instance
    }
    this._container = null
    this._booted = false
    this._previewUrl = null
    this._runningProcess = null
    this._onOutput = null
    this._onPreviewUrl = null
    this._onServerReady = null
    this._onError = null
    _instance = this
  }

  static getInstance() {
    if (!_instance) {
      _instance = new WebContainerManager()
    }
    return _instance
  }

  async boot() {
    if (this._booted && this._container) {
      return this._container
    }

    if (_bootPromise) {
      return _bootPromise
    }

    _bootPromise = this._doBoot()
    try {
      return await _bootPromise
    } catch (err) {
      _bootPromise = null
      throw err
    }
  }

  async _doBoot() {
    this._container = await WebContainer.boot()

    this._container.on('server-ready', (port, url) => {
      this._previewUrl = url
      _previewUrl = url
      console.log(`[WebContainer] 🟢 Server ready on port ${port}: ${url}`)
      if (typeof this._onServerReady === 'function') {
        this._onServerReady(port, url)
      }
      if (typeof this._onPreviewUrl === 'function') {
        this._onPreviewUrl(url)
      }
      _onServerReadyCallbacks.forEach(cb => cb(port, url))
      _onPreviewUrlCallbacks.forEach(cb => cb(url))
    })

    this._booted = true
    console.log('[WebContainer] ✅ Booted successfully')
    return this._container
  }

  async mountFiles(fileTree) {
    const container = await this.boot()

    if (!fileTree || typeof fileTree !== 'object') {
      throw new Error('fileTree must be a non-null object')
    }

    await container.mount(fileTree)
    console.log(
      '[WebContainer] 📁 Files mounted:',
      Object.keys(fileTree).length,
      'top-level entries'
    )
  }

  async runCommand(cmd, args = [], options = {}) {
    const container = await this.boot()

    if (this._runningProcess) {
      try {
        this._runningProcess.kill()
      } catch (e) {
        // ignore
      }
      this._runningProcess = null
    }

    const process = await container.spawn(cmd, args, {
      cwd: options.cwd || undefined,
      env: options.env || undefined,
    })

    this._runningProcess = process

    process.output.pipeTo(
      new WritableStream({
        write: (data) => {
          if (typeof this._onOutput === 'function') {
            this._onOutput(data)
          }
          if (typeof options.onOutput === 'function') {
            options.onOutput(data)
          }
        },
      })
    )

    const exitCode = await process.exit

    this._runningProcess = null

    return {
      exitCode,
      success: exitCode === 0,
    }
  }

  async installDependencies() {
    return this.runCommand('npm', ['install'], {
      onOutput: (data) => {
        console.log('[WebContainer] npm install:', data)
      },
    })
  }

  async startDevServer() {
    return this.runCommand('npm', ['run', 'dev'], {
      onOutput: (data) => {
        console.log('[WebContainer] dev server:', data)
      },
    })
  }

  async runScript(scriptName) {
    return this.runCommand('npm', ['run', scriptName], {
      onOutput: (data) => {
        console.log(`[WebContainer] npm run ${scriptName}:`, data)
      },
    })
  }

  getPreviewUrl() {
    return this._previewUrl || _previewUrl
  }

  isBooted() {
    return this._booted
  }

  getContainer() {
    return this._container
  }

  onOutput(callback) {
    this._onOutput = callback
  }

  onPreviewUrl(callback) {
    this._onPreviewUrl = callback
    if (this._previewUrl) {
      callback(this._previewUrl)
    }
  }

  onServerReady(callback) {
    this._onServerReady = callback
  }

  onError(callback) {
    this._onError = callback
  }

  async killRunningProcess() {
    if (this._runningProcess) {
      try {
        this._runningProcess.kill()
      } catch (e) {
        // ignore
      }
      this._runningProcess = null
    }
  }

  async teardown() {
    await this.killRunningProcess()
    this._previewUrl = null
    _previewUrl = null
    this._onOutput = null
    this._onPreviewUrl = null
    this._onServerReady = null
    this._onError = null
    _onPreviewUrlCallbacks = []
    _onServerReadyCallbacks = []
    console.log('[WebContainer] 🛑 Torn down')
  }

  static resetInstance() {
    if (_instance) {
      _instance.teardown()
    }
    _instance = null
    _bootPromise = null
    _previewUrl = null
  }
}

export async function bootWebContainer() {
  const manager = WebContainerManager.getInstance()
  return manager.boot()
}

export async function mountFilesToContainer(fileTree) {
  const manager = WebContainerManager.getInstance()
  return manager.mountFiles(fileTree)
}

export async function runCommandInContainer(cmd, args, options) {
  const manager = WebContainerManager.getInstance()
  return manager.runCommand(cmd, args, options)
}

export async function installAndRun(fileTree, runScript = 'dev') {
  const manager = WebContainerManager.getInstance()

  await manager.mountFiles(fileTree)

  const installResult = await manager.installDependencies()
  if (!installResult.success) {
    throw new Error(`npm install failed with exit code ${installResult.exitCode}`)
  }

  const devResult = await manager.runScript(runScript)
  return devResult
}

export function getWebContainerPreviewUrl() {
  return _previewUrl
}

export { WebContainerManager }
