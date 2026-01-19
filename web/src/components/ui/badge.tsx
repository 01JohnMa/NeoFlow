import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'bg-primary-500/10 text-primary-400 border border-primary-500/20',
        secondary: 'bg-bg-hover text-text-secondary border border-border-default',
        success: 'bg-success-500/10 text-success-500 border border-success-500/20',
        warning: 'bg-warning-500/10 text-warning-500 border border-warning-500/20',
        error: 'bg-error-500/10 text-error-500 border border-error-500/20',
        outline: 'border border-border-default text-text-secondary',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }



