import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SettingsState {
  aiEnabled: boolean
  setAiEnabled: (v: boolean) => void
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      aiEnabled: true,
      setAiEnabled: (v) => set({ aiEnabled: v }),
    }),
    { name: 'coai-settings' }
  )
)
