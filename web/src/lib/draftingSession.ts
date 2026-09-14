export const DRAFTING_SESSION_PARAM = 'session'

/** 从 URL search 中读取草拟会话 id（会话 id 即解析 Job id）。 */
export function readDraftingSessionId(search: string): string | null {
  const value = new URLSearchParams(search).get(DRAFTING_SESSION_PARAM)?.trim()
  return value ? value : null
}

/** 写回草拟会话 id：传 null 时移除参数，其余参数保持不变。 */
export function writeDraftingSessionId(search: string, sessionId: string | null): string {
  const params = new URLSearchParams(search)
  if (sessionId) {
    params.set(DRAFTING_SESSION_PARAM, sessionId)
  } else {
    params.delete(DRAFTING_SESSION_PARAM)
  }
  return params.toString()
}
