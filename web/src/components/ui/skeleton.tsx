import { cn } from '@/lib/cn'

export function Skeleton({ className, height }: { className?: string; height?: number }) {
  return <div aria-hidden style={height ? { height } : undefined} className={cn('animate-pulse rounded-lg bg-surface-3 motion-reduce:animate-none', className)} />
}
