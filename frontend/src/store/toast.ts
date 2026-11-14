import { create } from 'zustand'

export type Tone = 'success' | 'warning' | 'critical' | 'ai' | 'info'

export type ToastItem = { id: number; tone: Tone; title: string; description?: string }

type ToastState = {
  toasts: ToastItem[]
  push: (t: Omit<ToastItem, 'id'>) => void
  dismiss: (id: number) => void
}

let next = 1

export const useToasts = create<ToastState>()((set) => ({
  toasts: [],
  push: (t) => set((s) => ({ toasts: [...s.toasts, { ...t, id: next++ }] })),
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

export const toast = (t: Omit<ToastItem, 'id'>) => useToasts.getState().push(t)
