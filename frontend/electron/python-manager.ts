import { ChildProcess, spawn, execSync } from 'child_process'
import path from 'path'
import http from 'http'
import { app } from 'electron'

/**
 * Python 后端子进程生命周期守护管理器（单例模式）。
 * 职责：
 * 1. 自动探测 Python 虚拟环境与 backend/main.py 启动脚本。
 * 2. 在 Electron 启动时唤醒 FastAPI 后端，并重定向标准输出/错误流。
 * 3. 轮询健康探针 (/health) 确认后端完全在线。
 * 4. 在桌面应用退出时平滑安全地终止 (SIGTERM/SIGKILL) Python 子进程，防止孤儿进程残留。
 */
export class PythonBackendManager {
  private static instance: PythonBackendManager
  private process: ChildProcess | null = null
  private port: number = 8000
  private isRunning: boolean = false

  private constructor() {}

  public static getInstance(): PythonBackendManager {
    if (!PythonBackendManager.instance) {
      PythonBackendManager.instance = new PythonBackendManager()
    }
    return PythonBackendManager.instance
  }

  /** 获取后端服务监听的端口号 */
  public getPort(): number {
    return this.port
  }

  /** 获取后端运行状态 */
  public getStatus(): { running: boolean; port: number } {
    return {
      running: this.isRunning,
      port: this.port,
    }
  }

  /**
   * 探测并解析 Python 解释器二进制路径
   */
  private findPythonPath(): string {
    const isDev = !app.isPackaged
    if (isDev) {
      // 本地开发环境：定位至 backend/venv/bin/python3
      const devVenvPython = path.resolve(__dirname, '../../backend/venv/bin/python3')
      return devVenvPython
    }
    // 生产打包环境：定位至安装包内置 resources 资源目录
    return path.join(process.resourcesPath, 'backend', 'venv', 'bin', 'python3')
  }

  /**
   * 探测并解析后端启动入口脚本路径
   */
  private findBackendEntry(): string {
    const isDev = !app.isPackaged
    if (isDev) {
      return path.resolve(__dirname, '../../backend/main.py')
    }
    return path.join(process.resourcesPath, 'backend', 'main.py')
  }

  /**
   * 强力释放被异常残留或挂死僵尸进程占用的端口
   */
  public freePortIfOccupied(): void {
    try {
      if (process.platform === 'win32') {
        const output = execSync(`netstat -ano | findstr :${this.port}`, { encoding: 'utf-8' })
        const lines = output.split('\n')
        for (const line of lines) {
          const parts = line.trim().split(/\s+/)
          const pid = parts[parts.length - 1]
          if (pid && !isNaN(Number(pid)) && Number(pid) > 0) {
            execSync(`taskkill /F /PID ${pid} 2>nul || exit 0`, { stdio: 'ignore' })
          }
        }
      } else {
        // macOS / Linux: 查找并强制杀死占用此端口的残留死进程
        execSync(`lsof -ti :${this.port} | xargs kill -9 2>/dev/null || true`, { stdio: 'ignore' })
      }
    } catch (_) {}
  }

  /**
   * 启动 Python FastAPI 后端服务并执行就绪探活
   */
  public async start(): Promise<boolean> {
    if (this.isRunning) {
      return true
    }

    // 检查指定端口是否已有存活的后端服务，有则复用，避免重复拉起
    const alreadyAlive = await this.checkHealth()
    if (alreadyAlive) {
      console.log(`[PythonManager] 检测到端口 ${this.port} 已有运行中的健康后端服务，直接复用。`)
      this.isRunning = true
      return true
    }

    // 若端口被异常挂死的僵尸进程占用，自动释放端口确保启动成功
    this.freePortIfOccupied()
    await new Promise((res) => setTimeout(res, 300))

    const pythonBin = this.findPythonPath()
    const scriptPath = this.findBackendEntry()
    const backendCwd = path.dirname(scriptPath)

    console.log(`[PythonManager] 正在启动 Python 后端: ${pythonBin} ${scriptPath} 端口: ${this.port}`)

    const isDev = !app.isPackaged
    try {
      this.process = spawn(pythonBin, [scriptPath, '--port', String(this.port), isDev ? '--reload' : '--no-reload'], {
        cwd: backendCwd,
        detached: process.platform !== 'win32', // 创建独立进程组，退出时整组销毁
        env: {
          ...process.env,
          PYTHONUNBUFFERED: '1', // 禁用标准流缓冲，确保日志实时捕获
          KMP_DUPLICATE_LIB_OK: 'TRUE', // 解决 macOS 下 Milvus-Lite 与 NumPy/PyTorch OpenMP 双重初始化冲突崩溃 (OMP: Error #15)
          OMP_NUM_THREADS: '1',
        },
        stdio: ['ignore', 'pipe', 'pipe'],
      })

      // 实时转发 Python 标准输出日志
      this.process.stdout?.on('data', (data) => {
        console.log(`[Python 控制台输出]: ${data.toString().trim()}`)
      })

      // 实时转发 Python 错误与异常日志
      this.process.stderr?.on('data', (data) => {
        console.error(`[Python 错误输出]: ${data.toString().trim()}`)
      })

      // 监听子进程退出事件
      this.process.on('close', (code) => {
        console.log(`[PythonManager] Python 子进程退出，退出码: ${code}`)
        this.isRunning = false
        this.process = null
      })

      // 轮询探活健康接口 /health（最多等待 15 秒）
      const maxRetries = 30
      for (let i = 0; i < maxRetries; i++) {
        await new Promise((res) => setTimeout(res, 500))
        if (await this.checkHealth()) {
          console.log(`[PythonManager] Python 后端服务在端口 ${this.port} 健康就绪！`)
          this.isRunning = true
          return true
        }
      }

      console.warn(`[PythonManager] 健康检查超时（15秒），但子进程存活中。`)
      this.isRunning = true
      return true
    } catch (err) {
      console.error(`[PythonManager] 启动 Python 后端发生严重异常:`, err)
      return false
    }
  }

  /**
   * 检查 FastAPI 后端 /health 接口是否正常响应 HTTP 200
   */
  public checkHealth(): Promise<boolean> {
    return new Promise((resolve) => {
      const req = http.get(`http://127.0.0.1:${this.port}/health`, (res) => {
        if (res.statusCode === 200) {
          resolve(true)
        } else {
          resolve(false)
        }
      })
      req.on('error', () => {
        resolve(false)
      })
      req.setTimeout(1000, () => {
        req.destroy()
        resolve(false)
      })
    })
  }

  /**
   * 优雅安全关闭 Python 子进程
   */
  public stop(): void {
    if (this.process && this.process.pid) {
      console.log(`[PythonManager] 正在安全终止 Python 子进程组 (PID: ${this.process.pid})...`)
      try {
        if (process.platform !== 'win32') {
          process.kill(-this.process.pid, 'SIGTERM')
        } else {
          this.process.kill('SIGTERM')
        }
      } catch (e) {
        try {
          if (process.platform !== 'win32') {
            process.kill(-this.process.pid, 'SIGKILL')
          } else {
            this.process.kill('SIGKILL')
          }
        } catch (_) {}
      }
      this.freePortIfOccupied()
      this.process = null
      this.isRunning = false
    }
  }
}
