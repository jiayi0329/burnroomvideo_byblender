/** Existing backend contracts. Catalog integer IDs must not be confused with business IDs. */
export interface RoomContext {
  scene_code: string
  room_id: string
  asset_version: string
  layout_version_id: number
}
export interface CreateRoomJob extends RoomContext {
  style_preset: 'r3'
  preset: 'test' | 'final'
  camera_mode: 'overview' | 'closeup'
  confirm_render: true
  approval_job_id?: string
}
export interface CatalogAsset {
  id: number
  kind: string
  size_bytes: number
  sha256: string
  uploaded: boolean
}
export type ConnectionState = 'unconnected' | 'connecting' | 'connected' | 'disconnected'
export type ResourceState = 'unconnected' | 'loading' | 'empty' | 'error' | 'success'
