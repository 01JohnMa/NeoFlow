import * as React from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

type ModalProps = {
  open: boolean
  title?: string
  message?: string
  confirmText?: string
  onClose: () => void
  children?: React.ReactNode
}

export function Modal({
  open,
  title = '提示',
  message,
  confirmText = '知道了',
  onClose,
  children,
}: ModalProps) {
  React.useEffect(() => {
    if (!open) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          'relative w-full max-w-md rounded-xl border border-border-default bg-bg-card shadow-xl',
          'p-6 text-text-primary'
        )}
      >
        <h3 className="text-lg font-semibold">{title}</h3>
        {message && <p className="mt-3 text-sm text-text-secondary">{message}</p>}
        {children}
        <div className="mt-6 flex justify-end">
          <Button onClick={onClose}>{confirmText}</Button>
        </div>
      </div>
    </div>
  )
}
