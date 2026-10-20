import { createContext, useContext } from 'react'

/** Where a widget is drawn: inline in the chat, or large in the desktop canvas. */
export type WidgetLayout = 'inline' | 'canvas'

export const WidgetLayoutContext = createContext<WidgetLayout>('inline')

export function useWidgetLayout(): WidgetLayout {
  return useContext(WidgetLayoutContext)
}
