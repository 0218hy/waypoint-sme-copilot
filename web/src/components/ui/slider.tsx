import { Slider as S } from 'radix-ui'
import * as React from 'react'
import { cn } from '@/lib/cn'

export const Slider = React.forwardRef<
  React.ComponentRef<typeof S.Root>,
  React.ComponentPropsWithoutRef<typeof S.Root> & { thumbLabel?: string; trackOverlay?: React.ReactNode }
>(({ className, thumbLabel, trackOverlay, ...props }, ref) => (
  <S.Root
    ref={ref}
    className={cn('relative flex h-11 w-full touch-none select-none items-center', className)}
    {...props}
  >
    <S.Track className="relative h-2.5 w-full grow overflow-hidden rounded-full bg-surface-3">
      {trackOverlay}
      <S.Range className="absolute h-full bg-accent" />
    </S.Track>
    <S.Thumb
      aria-label={thumbLabel}
      className="block size-7 rounded-full border-2 border-accent bg-surface shadow-md transition-transform focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:scale-110 disabled:opacity-50"
    />
  </S.Root>
))
Slider.displayName = 'Slider'
