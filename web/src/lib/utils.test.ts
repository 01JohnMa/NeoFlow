import { describe, expect, it } from 'vitest'
import { getStatusColor, getStatusText } from '@/lib/utils'

describe('document status helpers', () => {
  it('renders queued status text and color', () => {
    expect(getStatusText('queued')).toBe('排队中')
    expect(getStatusColor('queued')).toContain('text-accent-400')
  })
})
