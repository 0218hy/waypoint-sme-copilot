import { Switch as S } from 'radix-ui'
import * as React from 'react'
import { cn } from '@/lib/cn'

export const Switch = React.forwardRef<
  React.ComponentRef<typeof S.Root>,
  React.ComponentPropsWithoutRef<typeof S.Root>
>(({ className, ...props }, ref) => (
  <S.Root
    ref={ref}
    className={cn(
      'peer inline-flex h-7 w-12 shrink-0 items-center rounded-full border-2 border-transparent bg-surface-3 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-accent',
      className,
    )}
    {...props}
  >
    <S.Thumb className="pointer-events-none block size-6 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0" />
  </S.Root>
))
Switch.displayName = 'Switch'
