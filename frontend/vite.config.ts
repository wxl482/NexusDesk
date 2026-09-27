import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import electron from 'vite-plugin-electron'
import renderer from 'vite-plugin-electron-renderer'

/**
 * Vite 构建配置文件
 * 深度集成 Vue 3 单文件组件支持与 Electron 双进程编译构建
 */
export default defineConfig(({ mode }) => {
  return {
    plugins: [
      // Vue 3 单文件组件编译器
      vue(),
      // Electron 主进程与预加载脚本构建插件
      electron([
        {
          entry: 'electron/main.ts',
          vite: {
            build: {
              outDir: 'dist-electron',
              rollupOptions: {
                external: ['electron'],
              },
            },
          },
        },
        {
          entry: 'electron/preload.ts',
          onstart(options) {
            // 预加载脚本变动时自动重载渲染窗口
            options.reload()
          },
          vite: {
            build: {
              outDir: 'dist-electron',
              rollupOptions: {
                external: ['electron'],
              },
            },
          },
        },
      ]),
      // 开启 Electron 渲染进程通信桥梁
      renderer(),
    ],
    resolve: {
      // 路径别名配置：将 @ 指向 src 目录
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 5173,
      // 开发服务器代理：转发 REST 与 SSE 接口到 Python FastAPI 后端
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
        '/health': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        }
      }
    }
  }
})
