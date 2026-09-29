import { app, BrowserWindow, ipcMain, dialog, shell, nativeImage, globalShortcut, clipboard, screen } from 'electron'
import path from 'path'
import { autoUpdater } from 'electron-updater'
import { PythonBackendManager } from './python-manager'

// 构建与资源根目录配置
process.env.DIST = path.join(__dirname, '../dist')
process.env.VITE_PUBLIC = app.isPackaged ? process.env.DIST : path.join(process.env.DIST, '../public')

let win: BrowserWindow | null = null
let quickBarWin: BrowserWindow | null = null
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

function getQuickBarBounds(height = 118) {
  const currentDisplay = screen.getDisplayNearestPoint(screen.getCursorScreenPoint())
  const { x: displayX, y: displayY, width: displayWidth, height: displayHeight } = currentDisplay.workArea
  const winWidth = 680
  const x = Math.round(displayX + (displayWidth - winWidth) / 2)
  const y = Math.round(displayY + displayHeight * 0.18)
  return { x, y, width: winWidth, height }
}

/**
 * 创建 Raycast / Spotlight 悬浮快捷呼出小窗 (QuickBar)
 */
function createQuickBarWindow() {
  if (quickBarWin) return

  const bounds = getQuickBarBounds(118)

  quickBarWin = new BrowserWindow({
    width: bounds.width,
    height: bounds.height,
    x: bounds.x,
    y: bounds.y,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    show: false,
    skipTaskbar: true,
    hasShadow: false,
    backgroundColor: '#00000000',
    webPreferences: {
      preload,
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  if (process.platform === 'darwin') {
    quickBarWin.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  }

  const quickUrl = process.env.VITE_DEV_SERVER_URL
    ? `${process.env.VITE_DEV_SERVER_URL}#/quick-bar`
    : `file://${path.join(process.env.DIST || path.join(__dirname, '../dist'), 'index.html')}#/quick-bar`

  quickBarWin.loadURL(quickUrl)

  // 失焦时自动优雅收起
  quickBarWin.on('blur', () => {
    quickBarWin?.hide()
  })

  // 隐藏后自动重置回极简单行高 (118px)
  quickBarWin.on('hide', () => {
    if (quickBarWin && !quickBarWin.isDestroyed()) {
      const current = quickBarWin.getBounds()
      quickBarWin.setBounds({
        x: current.x,
        y: current.y,
        width: 680,
        height: 118,
      })
    }
  })
}

function toggleQuickBar() {
  if (!quickBarWin) {
    createQuickBarWindow()
  }

  if (quickBarWin?.isVisible()) {
    quickBarWin.hide()
  } else {
    // 每次唤出自动定位至鼠标当前所在屏幕黄金视角
    const bounds = getQuickBarBounds(118)
    quickBarWin?.setBounds(bounds)
    quickBarWin?.show()
    quickBarWin?.focus()
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

// 应用彻底退出前确保子进程销毁与快捷键注销
app.on('before-quit', () => {
  globalShortcut.unregisterAll()
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
      { name: '文档与代码', extensions: ['txt', 'md', 'pdf', 'docx', 'xlsx', 'py', 'json', 'csv'] }
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

// QuickBar 控制 IPC
ipcMain.handle('hide-quick-bar', () => {
  quickBarWin?.hide()
})

ipcMain.handle('resize-quick-bar', (_, { height }: { height: number }) => {
  if (quickBarWin && !quickBarWin.isDestroyed()) {
    const current = quickBarWin.getBounds()
    const targetHeight = Math.max(height, 80)
    quickBarWin.setBounds({
      x: current.x,
      y: current.y,
      width: 680,
      height: targetHeight,
    })
  }
})

ipcMain.handle('open-in-main-window', (_, query: string) => {
  quickBarWin?.hide()
  if (!win) {
    createWindow()
  } else {
    win.show()
    win.focus()
  }
  if (query) {
    win?.webContents.send('focus-chat-query', query)
  }
})

// 读取系统剪贴板（用于 QuickBar 一键速查与分析）
ipcMain.handle('read-clipboard-text', () => {
  return clipboard.readText() || ''
})

// 检查更新 IPC
ipcMain.handle('check-for-updates', async () => {
  if (!app.isPackaged) {
    return { status: 'dev', message: '当前处于开发环境，无须执行更新。' }
  }
  try {
    const res = await autoUpdater.checkForUpdates()
    return { status: 'ok', updateInfo: res?.updateInfo }
  } catch (e: any) {
    return { status: 'error', message: e.message }
  }
})

// 一键重启并安装更新
ipcMain.handle('quit-and-install-update', () => {
  autoUpdater.quitAndInstall(false, true)
})

/**
 * 初始化跨平台全自动静默更新器 (electron-updater)
 */
function initAutoUpdater() {
  if (!app.isPackaged) {
    console.log('[AutoUpdater] 当前处于开发环境，自动跳过更新检测')
    return
  }

  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true

  autoUpdater.on('checking-for-update', () => {
    console.log('[AutoUpdater] 正在向 GitHub Releases 检查最新版本...')
  })

  autoUpdater.on('update-available', (info) => {
    console.log('[AutoUpdater] 发现新版本:', info.version)
    win?.webContents.send('updater-message', {
      status: 'available',
      version: info.version,
      releaseNotes: info.releaseNotes,
    })
  })

  autoUpdater.on('update-not-available', () => {
    console.log('[AutoUpdater] 已是最新版本')
  })

  autoUpdater.on('download-progress', (progressObj) => {
    win?.webContents.send('updater-message', {
      status: 'downloading',
      percent: Math.floor(progressObj.percent),
      bytesPerSecond: progressObj.bytesPerSecond,
    })
  })

  autoUpdater.on('update-downloaded', (info) => {
    console.log('[AutoUpdater] 新版本下载完毕，准备就绪:', info.version)
    win?.webContents.send('updater-message', {
      status: 'downloaded',
      version: info.version,
    })
  })

  autoUpdater.on('error', (err) => {
    console.warn('[AutoUpdater] 更新服务异常:', err.message)
  })

  // 延迟 4 秒执行初次检测，避免启动抢占带宽
  setTimeout(() => {
    autoUpdater.checkForUpdates().catch((err) => {
      console.warn('[AutoUpdater] 初始检查失败:', err)
    })
  }, 4000)
}

// Electron 初始化就绪后创建主窗口、浮动窗口与全局快捷键
app.whenReady().then(() => {
  createWindow()
  createQuickBarWindow()
  initAutoUpdater()

  // 注册 Raycast / Spotlight 风格全局唤出快捷键: Option+Space (Mac) / Alt+Space (Win/Linux) / Cmd+Shift+Space
  try {
    globalShortcut.register('CommandOrControl+Shift+Space', toggleQuickBar)
    globalShortcut.register('Alt+Space', toggleQuickBar)
    if (process.platform === 'darwin') {
      try {
        globalShortcut.register('Option+Space', toggleQuickBar)
      } catch (_) {}
    }
    console.log('[Electron] 成功注册 QuickBar 全局快捷键: Option+Space / Alt+Space / Cmd+Shift+Space')
  } catch (err) {
    console.warn('[Electron] 注册全局快捷键异常:', err)
  }
})
