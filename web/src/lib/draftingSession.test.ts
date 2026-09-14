import { describe, expect, it } from 'vitest'

import {
  DRAFTING_SESSION_PARAM,
  readDraftingSessionId,
  writeDraftingSessionId,
} from './draftingSession'

describe('readDraftingSessionId', () => {
  it('返回 URL 中的会话 id', () => {
    expect(readDraftingSessionId('?session=job-1')).toBe('job-1')
  })

  it('忽略空白值', () => {
    expect(readDraftingSessionId('?session=%20')).toBeNull()
  })

  it('没有参数时返回 null', () => {
    expect(readDraftingSessionId('')).toBeNull()
    expect(readDraftingSessionId('?foo=bar')).toBeNull()
  })
})

describe('writeDraftingSessionId', () => {
  it('写入会话 id 时保留其他参数', () => {
    const search = writeDraftingSessionId('?tab=configs', 'job-1')
    const params = new URLSearchParams(search)
    expect(params.get(DRAFTING_SESSION_PARAM)).toBe('job-1')
    expect(params.get('tab')).toBe('configs')
  })

  it('传 null 时移除会话参数', () => {
    const search = writeDraftingSessionId('?tab=configs&session=job-1', null)
    const params = new URLSearchParams(search)
    expect(params.get(DRAFTING_SESSION_PARAM)).toBeNull()
    expect(params.get('tab')).toBe('configs')
  })
})
