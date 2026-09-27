/**
 * 敏感操作审批数据结构与解析工具
 * 支持解析结构化 approval 代码块以及自然语言 Markdown 确认表格
 */

export interface ApprovalData {
  action: string // 'delete_file' | 'execute_command' | 'write_file' | string
  title: string
  type: string
  target: string
  impact: string
  confirmPrompt: string
  rejectPrompt: string
}

/**
 * 从大模型回复内容中提取待审批的敏感操作数据
 */
export function parseApprovalData(content: string): ApprovalData | null {
  if (!content) return null

  // 1. 优先解析结构化 ```approval ... ``` 代码块
  const jsonMatch = content.match(/```(?:approval|json:approval)\s*([\s\S]*?)```/i)
  if (jsonMatch) {
    try {
      const data = JSON.parse(jsonMatch[1].trim())
      const action = data.action || 'delete_file'
      const target = data.target || ''

      // 智能推断工具类别名称（对标截图中的“终端”、“文件系统”等）
      let opType = data.type || ''
      if (!opType || opType === '操作类型' || opType === '系统操作') {
        if (action === 'execute_terminal_command' || action === 'execute_command' || /mkdir|rm|git|npm|python|bash|sh|ls|curl|chmod|pnpm|yarn/i.test(target)) {
          opType = '终端'
        } else if (action === 'delete_file' || action === 'write_file' || target.startsWith('/') || target.includes('.')) {
          opType = '文件系统'
        } else {
          opType = '终端'
        }
      }

      // 智能生成自然亲切的疑问句（对标截图：“允许我在桌面创建名为“22”的文件夹吗？”）
      let title = (data.title || '').trim()
      const fileName = target.split('/').filter(Boolean).pop() || target
      if (!title || title.includes('待执行') || title.includes('敏感操作确认')) {
        if (action === 'delete_file') {
          title = fileName ? `允许我永久删除“${fileName}”吗？` : '允许我删除该文件吗？'
        } else if (action === 'write_file') {
          title = fileName ? `允许我写入文件“${fileName}”吗？` : '允许我写入该文件吗？'
        } else if (target.includes('mkdir')) {
          title = '允许我在桌面创建该文件夹吗？'
        } else if (action === 'execute_terminal_command' || action === 'execute_command') {
          title = '允许我执行此终端命令吗？'
        } else {
          title = '允许执行此操作吗？'
        }
      } else if (!/[吗\?？]$/.test(title)) {
        title = `${title}吗？`
      }

      return {
        action,
        title,
        type: opType,
        target,
        impact: data.impact || '该操作将对系统或文件产生影响，请审阅后确认是否允许。',
        confirmPrompt: data.confirm_prompt || `允许执行：${target || title}`,
        rejectPrompt: data.reject_prompt || `已拒绝此操作，取消执行。`,
      }
    } catch (e) {
      console.warn('解析 approval json 代码块失败', e)
    }
  }

  // 2. 启发式解析形如 Markdown 确认表格
  const hasDeleteMarker = content.includes('待执行的删除操作') || content.includes('删除文件')
  const hasConfirmAsk = content.includes('请问是否确认') || content.includes('请您确认') || content.includes('确认删除')
  
  if (hasDeleteMarker && hasConfirmAsk) {
    // 提取目标文件路径
    let target = ''
    const targetMatch = content.match(/目标文件\s*\|\s*`?([^`\n\r|]+)`?/i)
    if (targetMatch) {
      target = targetMatch[1].trim().replace(/\s*\(约.*?\)/, '').trim()
    } else {
      const pathMatch = content.match(/(?:\/|~|[a-zA-Z]:\\)[^\s`'"，,\n\r|]+(?:\.[a-zA-Z0-9]+)?/)
      if (pathMatch) {
        target = pathMatch[0].trim()
      }
    }

    const fileName = target.split('/').filter(Boolean).pop() || target
    return {
      action: 'delete_file',
      title: fileName ? `允许我永久删除“${fileName}”吗？` : '允许我删除该文件吗？',
      type: '文件系统',
      target: target,
      impact: '文件将被直接删除，不经过废纸篓，无法通过系统恢复。',
      confirmPrompt: target ? `允许删除该文件：${target}` : '允许执行删除操作',
      rejectPrompt: '已拒绝此操作，请取消删除，保留原有文件。',
    }
  }

  // 3. 通用高危命令解析 (如包含 execute_command 待确认)
  if (content.includes('待执行的命令') || (content.includes('终端命令') && hasConfirmAsk)) {
    let targetCmd = ''
    const cmdMatch = content.match(/`([^`]+)`/)
    if (cmdMatch) targetCmd = cmdMatch[1].trim()

    return {
      action: 'execute_command',
      title: '允许我执行此终端命令吗？',
      type: '终端',
      target: targetCmd,
      impact: '该命令可能修改本地系统配置或进程状态，请审阅后确认。',
      confirmPrompt: targetCmd ? `允许执行终端命令：${targetCmd}` : '允许执行命令',
      rejectPrompt: '已取消执行该终端命令。',
    }
  }

  return null
}

/**
 * 净化回复正文：移除隐藏的 ```approval 代码块以及 DeepSeek DSML 原生工具标记，避免向用户展示裸露的 JSON 或底层 XML 协议代码
 */
export function cleanApprovalContent(content: string): string {
  if (!content) return ''
  let cleaned = content.replace(/```(?:approval|json:approval)\s*[\s\S]*?```/gi, '')
  // 彻底剔除 DeepSeek DSML 原生标记（如 <|DSML||calls> 等底层未解析协议片段）
  cleaned = cleaned.replace(/<[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*calls\s*>[\s\S]*?<\/[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*calls\s*>/gi, '')
  cleaned = cleaned.replace(/<[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*invoke[\s\S]*?<\/[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*invoke\s*>/gi, '')
  cleaned = cleaned.replace(/<\/?(?:[\|｜]\s*)?DSML\s*(?:[\|｜]{1,2})?[^>]*>/gi, '')
  return cleaned.trim()
}
