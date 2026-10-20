import { Tabs as T } from 'radix-ui'
import * as React from 'react'
import { cn } from '@/lib/cn'

export const Tabs = T.Root

export const TabsList = React.forwardRef<
  React.ComponentRef<typeof T.List>,
  React.ComponentPropsWithoutRef<typeof T.List>
>(({ className, ...props }, ref) => (
  <T.List ref={ref} className={cn('inline-flex rounded-xl bg-surface-2 p-1', className)} {...props} />
))
TabsList.displayName = 'TabsList'

export const TabsTrigger = React.forwardRef<
  React.ComponentRef<typeof T.Trigger>,
  React.ComponentPropsWithoutRef<typeof T.Trigger>
>(({ className, ...props }, ref) => (
  <T.Trigger
    ref={ref}
    className={cn(
      'min-h-9 rounded-lg px-3 text-sm font-medium text-muted transition-colors focus-visible:outline-2 focus-visible:outline-focus data-[state=active]:bg-surface data-[state=active]:text-text data-[state=active]:shadow-sm',
      className,
    )}
    {...props}
  />
))
TabsTrigger.displayName = 'TabsTrigger'

export const TabsContent = T.Content
