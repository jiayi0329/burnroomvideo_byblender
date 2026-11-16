import { createContext, useContext } from 'react'
import type { Source, Asset, Point, Job } from './contracts'
export interface Resources {
  status: 'unconfigured' | 'loading' | 'connected' | 'error'
  error?: string
  traceId?: string
  sources: Source[]
  source?: Source
  assets: Asset[]
  points: Point[]
  jobs: Job[]
  refresh: () => void
  select: (index: number) => void
}
export const empty: Resources = {
  status: 'unconfigured',
  sources: [],
  assets: [],
  points: [],
  jobs: [],
  refresh: () => {},
  select: () => {},
}
export const Context = createContext<Resources>(empty)
export function useResources() {
  return useContext(Context)
}
