/**
 * SSE 流式对话请求载荷接口定义
 */
export interface StreamChatPayload {
  message: string
  session_id: string
  mode: string
  model?: string
  base_url?: string
  api_key?: string
  temperature?: number
  approval_mode?: string
  images?: string[]
}

/**
 * SSE 全链路流式事件回调接口定义
 */
export interface StreamCallbacks {
  /** 收到常规文本 Token */
  onToken: (token: string) => void
  /** 收到深度思考思维链 Token (如 DeepSeek-R1) */
  onThought: (thought: string) => void
  /** 工具开始调用 */
  onToolStart: (toolName: string, inputArgs: any) => void
  /** 工具调用结束并输出结果 */
  onToolEnd: (toolName: string, outputResult: string) => void
  /** 工具调用发生异常 */
  onToolError?: (toolName: string, errorMsg: string) => void
  /** LangGraph 节点生命周期状态流转 */
  onNodeChange: (nodeName: string) => void
  /** 智能模型动态路由通知 */
  onModelRouted?: (info: { model: string; tier?: string; reason?: string }) => void
  /** 长程任务规划步骤更新 */
  onPlan?: (plan: any[]) => void
  /** 异常处理 */
  onError: (errorMsg: string, hint?: string) => void
  /** 流式完成 */
  onDone: (sessionId: string) => void
}

/**
 * 基于标准 Web Fetch API 与 ReadableStream 实现的 SSE 实时流式客户端
 */
export class SSEChatClient {
  private abortController: AbortController | null = null

  /** 中止当前正在进行中的流式生成 */
  public abort() {
    if (this.abortController) {
      this.abortController.abort()
      this.abortController = null
    }
  }

  /**
   * 发起 Server-Sent Events 流式对话请求
   *
   * @param payload 请求入参
   * @param callbacks 监听各类型事件的回调对象
   * @param baseURL 后端基础服务地址
   */
  public async streamChat(
    payload: StreamChatPayload,
    callbacks: StreamCallbacks,
    baseURL: string = 'http://127.0.0.1:8000'
  ) {
    this.abort()
    this.abortController = new AbortController()

    try {
      const response = await fetch(`${baseURL}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(payload),
        signal: this.abortController.signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP 通信异常，状态码: ${response.status}`)
      }

      if (!response.body) {
        throw new Error('当前环境不支持 ReadableStream 数据流。')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        // 保留最后一行未闭合的切片
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed || !trimmed.startsWith('data:')) continue

          const jsonStr = trimmed.replace(/^data:\s*/, '')
          if (!jsonStr) continue

          try {
            const parsed = JSON.parse(jsonStr)
            this.handleEvent(parsed, callbacks)
          } catch (err) {
            console.warn('解析 SSE JSON 数据包失败:', jsonStr)
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('用户手动中断了流式输出。')
        return
      }
      const msg = String(err.message || '')
      if (msg.toLowerCase().includes('network error') || msg.toLowerCase().includes('failed to fetch')) {
        callbacks.onError('网络通信中断或服务连接异常', '后端连接断开或未能完成响应')
      } else {
        callbacks.onError(msg || '流式连接发生未知异常')
      }
    } finally {
      this.abortController = null
    }
  }

  /**
   * 业务事件分发器
   */
  private handleEvent(data: any, callbacks: StreamCallbacks) {
    switch (data.type) {
      case 'token':
        callbacks.onToken(data.content)
        break
      case 'thought':
        callbacks.onThought(data.content)
        break
      case 'tool_start':
        callbacks.onToolStart(data.tool, data.input)
        break
      case 'tool_end':
        callbacks.onToolEnd(data.tool, data.output)
        break
      case 'tool_error':
        if (callbacks.onToolError) {
          callbacks.onToolError(data.tool, data.error)
        } else {
          callbacks.onToolEnd(data.tool, `[工具调用异常]: ${data.error}`)
        }
        break
      case 'node_start':
        callbacks.onNodeChange(data.node)
        break
      case 'model_routed':
        callbacks.onModelRouted?.({
          model: data.model,
          tier: data.tier,
          reason: data.reason,
        })
        break
      case 'plan':
        callbacks.onPlan?.(data.plan)
        break
      case 'error':
        callbacks.onError(data.error, data.hint)
        break
      case 'done':
        callbacks.onDone(data.session_id)
        break
    }
  }
}
