import { Suspense, useEffect, useMemo, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { Bounds, OrbitControls, useBounds, useGLTF } from '@react-three/drei'
import { Box3, Vector3, CanvasTexture } from 'three'
import type { PreviewPoint } from './RoomPreview'

function PointLabel({ id }: { id: string }) {
  const texture = useMemo(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 128
    canvas.height = 64
    const context = canvas.getContext('2d')!
    context.fillStyle = '#17212ddd'
    context.fillRect(0, 0, 128, 64)
    context.fillStyle = '#ffffff'
    context.font = '40px sans-serif'
    context.textAlign = 'center'
    context.fillText(id, 64, 46)
    return new CanvasTexture(canvas)
  }, [id])
  useEffect(() => () => texture.dispose(), [texture])
  return (
    <sprite position={[0, 0.2, 0]} scale={[0.42, 0.21, 1]} renderOrder={2}>
      <spriteMaterial map={texture} depthTest={false} transparent />
    </sprite>
  )
}
function Model({
  url,
  points,
  reset,
  onReady,
  onPointSelect,
}: {
  url: string
  points: PreviewPoint[]
  reset: number
  onReady: (text: string) => void
  onPointSelect?: (id: string) => void
}) {
  const { scene } = useGLTF(url, false, false)
  const clone = useMemo(() => scene.clone(true), [scene])
  const bounds = useBounds()
  const [selected, setSelected] = useState<string>()
  useEffect(() => {
    bounds.refresh(clone).clip()
    const { center, distance } = bounds.getSize()
    const position = center.clone().addScaledVector(new Vector3(1, 1, 1).normalize(), distance)
    bounds.moveTo(position).lookAt({ target: center })
    const box = new Box3().setFromObject(clone).expandByScalar(0.05)
    onReady(
      `${points.filter((p) => box.containsPoint(new Vector3(...p.position))).length}/${points.length} 个点位在模型包围盒内（非墙面边界核验）`,
    )
  }, [clone, bounds, reset, points, onReady])
  return (
    <>
      <primitive object={clone} />
      {points.map((p) => (
        <mesh
          key={p.id}
          position={p.position}
          onClick={(e) => {
            e.stopPropagation()
            setSelected(p.id)
            onPointSelect?.(p.id)
          }}
        >
          <sphereGeometry args={[selected === p.id ? 0.08 : 0.065, 12, 8]} />
          <meshBasicMaterial
            color={selected === p.id ? '#ffe29c' : p.selectable ? '#ff803d' : '#8ec6ed'}
          />
          <PointLabel id={p.id} />
        </mesh>
      ))}
    </>
  )
}
export default function ModelCanvas(props: {
  url: string
  points: PreviewPoint[]
  reset: number
  onReady: (text: string) => void
  onPointSelect?: (id: string) => void
}) {
  return (
    <Canvas
      camera={{ position: [12, 10, 12], fov: 45 }}
      dpr={[1, 1.5]}
      fallback={<p>浏览器不支持 WebGL，请更换支持三维的浏览器。</p>}
    >
      <color attach="background" args={['#141c25']} />
      <ambientLight intensity={1.7} />
      <directionalLight position={[6, 12, 8]} intensity={2} />
      <Suspense fallback={null}>
        <Bounds fit clip observe margin={1.25}>
          <Model {...props} />
        </Bounds>
      </Suspense>
      <OrbitControls makeDefault enableDamping />
    </Canvas>
  )
}
