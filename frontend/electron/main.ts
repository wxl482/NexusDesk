import { app, BrowserWindow, ipcMain, dialog, shell, nativeImage } from 'electron'
import path from 'path'
import { PythonBackendManager } from './python-manager'

// 构建与资源根目录配置
process.env.DIST = path.join(__dirname, '../dist')
process.env.VITE_PUBLIC = app.isPackaged ? process.env.DIST : path.join(process.env.DIST, '../public')

let win: BrowserWindow | null = null
const preload = path.join(__dirname, 'preload.js')
const pythonManager = PythonBackendManager.getInstance()

/**
 * 设置应用程序图标（兼顾 Windows、Linux 窗口图标与 macOS Dock 程序坞图标）
 */
function setupAppIcon(): string {
  const iconPath = path.join(process.env.VITE_PUBLIC || path.join(__dirname, '../public'), 'icon.png')
  
  // macOS 环境下动态设置 Dock 图标
  if (process.platform === 'darwin' && app.dock) {
    try {
      const icnsPath = path.resolve(__dirname, '../build/icon.icns')
      const dockIcon = nativeImage.createFromPath(icnsPath)
      if (!dockIcon.isEmpty()) {
        app.dock.setIcon(dockIcon)
      } else {
        const pngIcon = nativeImage.createFromPath(iconPath)
        if (!pngIcon.isEmpty()) {
          app.dock.setIcon(pngIcon)
        }
      }
    } catch (err) {
      console.error('[Electron] 设置 macOS Dock 图标失败:', err)
    }
  }

  return iconPath
}

/**
 * 创建应用主桌面窗口
 */
function createWindow() {
  const iconPath = setupAppIcon()
  win = new BrowserWindow({
    title: 'NexusDesk',
    icon: iconPath,
    width: 1280,
    height: 860,
    minWidth: 1024,
    minHeight: 700,
    titleBarStyle: 'hidden', // 采用 macOS 原生无边框现代沉浸式标题栏
    trafficLightPosition: { x: 18, y: 20 }, // 垂直完美居中于高度 56px (h-14) 的顶部栏
    webPreferences: {
      preload,
      nodeIntegration: false,
      contextIsolation: true, // 启用上下文隔离，确保渲染进程安全
    },
  })

  // 外部链接通过系统默认浏览器打开
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      shell.openExternal(url)
    }
    return { action: 'deny' }
  })

  // 异步唤醒 Python 后端子进程
  pythonManager.start().then((ready) => {
    if (ready) {
      console.log('Python 后端已就绪！')
      win?.webContents.send('backend-status', { running: true, port: pythonManager.getPort() })
    }
  })

  // 开发环境下加载 Vite 实时热重载服务，生产环境下加载 dist 打包静态资源
  if (process.env.VITE_DEV_SERVER_URL) {
    win.loadURL(process.env.VITE_DEV_SERVER_URL)
  } else {
    const distPath = process.env.DIST || path.join(__dirname, '../dist')
    win.loadFile(path.join(distPath, 'index.html'))
  }
}

// 所有窗口关闭时的生命周期事件
app.on('window-all-closed', () => {
  // 安全停止后端服务
  pythonManager.stop()
  if (process.platform !== 'darwin') {
    app.quit()
    win = null
  }
})

// 应用彻底退出前确保子进程销毁
app.on('before-quit', () => {
  pythonManager.stop()
})

// macOS 点击 Dock 图标唤醒主窗口
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

// ==========================================
// IPC 进程间通信通道注册
// ==========================================

// 获取当前 Python 后端的运行状态
ipcMain.handle('get-backend-status', async () => {
  const isHealthy = await pythonManager.checkHealth()
  return {
    running: isHealthy,
    port: pythonManager.getPort(),
  }
})

// 弹出系统原生文件选择对话框
ipcMain.handle('open-file-dialog', async () => {
  if (!win) return null
  const result = await dialog.showOpenDialog(win, {
    properties: ['openFile'],
    filters: [
      { name: '文档与代码', extensions: ['txt', 'md', 'pdf', 'docx', 'py', 'json', 'csv'] }
    ]
  })
  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0]
  }
  return null
})

// 在系统默认外部浏览器中打开链接
ipcMain.handle('open-external', async (_, url: string) => {
  if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
    await shell.openExternal(url)
  }
})

// Electron 初始化就绪后创建窗口
app.whenReady().then(createWindow)
