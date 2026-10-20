import { Popover as P } from 'radix-ui'
import * as React from 'react'
import { cn } from '@/lib/cn'

export const Popover = P.Root
export const PopoverTrigger = P.Trigger
export const PopoverClose = P.Close

export const PopoverContent = React.forwardRef<
  React.ComponentRef<typeof P.Content>,
  React.ComponentPropsWithoutRef<typeof P.Content>
>(({ className, align = 'start', sideOffset = 6, ...props }, ref) => (
  <P.Portal>
    <P.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      collisionPadding={12}
      className={cn(
        'z-50 w-[min(20rem,calc(100vw-24px))] rounded-xl border border-border bg-surface p-3 text-sm text-text shadow-lg outline-none',
        className,
      )}
      {...props}
    />
  </P.Portal>
))
PopoverContent.displayName = 'PopoverContent'
