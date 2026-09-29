import { contextBridge, ipcRenderer } from 'electron'

/**
 * 预加载脚本 (Preload Script)
 * 通过 contextBridge 将受限、安全的原生能力暴露给渲染进程 (window.electronAPI)，
 * 避免在前端直接开启 nodeIntegration，符合 Electron 安全开发最佳实践规范。
 */
contextBridge.exposeInMainWorld('electronAPI', {
  // 获取当前后端服务探活状态
  getBackendStatus: () => ipcRenderer.invoke('get-backend-status'),
  
  // 唤起原生文件选择窗口
  openFileDialog: () => ipcRenderer.invoke('open-file-dialog'),
  
  // 订阅后端状态变更通知
  onBackendStatus: (callback: (status: { running: boolean; port: number }) => void) => {
    ipcRenderer.on('backend-status', (_, data) => callback(data))
  },
  
  // 唤起外部默认浏览器打开链接
  openExternal: (url: string) => ipcRenderer.invoke('open-external', url),

  // Raycast / Spotlight 悬浮小窗控制器
  hideQuickBar: () => ipcRenderer.invoke('hide-quick-bar'),
  openInMainWindow: (query?: string) => ipcRenderer.invoke('open-in-main-window', query),
  onFocusChatQuery: (callback: (query: string) => void) => {
    ipcRenderer.on('focus-chat-query', (_, query) => callback(query))
  },

  // 剪贴板快速读取
  readClipboardText: () => ipcRenderer.invoke('read-clipboard-text'),

  // 全自动更新控制与事件监听 (electron-updater)
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  quitAndInstallUpdate: () => ipcRenderer.invoke('quit-and-install-update'),
  onUpdaterMessage: (callback: (data: any) => void) => {
    ipcRenderer.on('updater-message', (_, data) => callback(data))
  },

  // 桌面环境标识与操作系统平台
  isElectron: true,
  platform: process.platform,
})
