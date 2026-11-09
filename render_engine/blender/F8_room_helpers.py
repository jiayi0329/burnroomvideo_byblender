"""Blender-only shared room mesh, display-cut, camera and ray helpers.

No standalone entry point. Ordinary backend/launcher code must not import bpy
or this module. Legacy B/D/E names re-export these exact implementations.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def make_mesh(name: str, faces: list[dict], materials: dict) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    corners = [v for face in faces for v in face['corners']]
    mesh.from_pydata([v[:3] for v in corners], [], [(i,i+1,i+2) for i in range(0,len(corners),3)])
    uv = mesh.uv_layers.new(name='UVMap')
    for loop in mesh.loops:
        uv.data[loop.index].uv = corners[loop.vertex_index][3:5]
    names = sorted({face['material'] for face in faces})
    for mat in names:
        mesh.materials.append(materials[mat])
    for p, face in zip(mesh.polygons, faces):
        p.material_index = names.index(face['material'])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def below(faces: list[dict], z: float) -> list[dict]:
    """Display derivative only: clip faces below an explicitly artificial view plane."""
    output = []
    for face in faces:
        result = []
        previous = face['corners'][-1]
        for current in face['corners']:
            if (previous[2] <= z) != (current[2] <= z):
                t = (z-previous[2])/(current[2]-previous[2])
                result.append([previous[k]+t*(current[k]-previous[k]) for k in range(5)])
            if current[2] <= z:
                result.append(current)
            previous = current
        for i in range(1,len(result)-1):
            output.append({'material': face['material'], 'corners': [result[0],result[i],result[i+1]]})
    if not output:
        raise ValueError('Display cut plane removed all source geometry')
    return output


def contains(x: float, y: float, polygon: list) -> bool:
    inside = False
    for i,a in enumerate(polygon):
        b = polygon[(i+1)%len(polygon)]
        if (a[1]>y) != (b[1]>y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def interior_camera(polygon: list) -> tuple[float,float]:
    lo = [min(v[k] for v in polygon) for k in (0,1)]
    hi = [max(v[k] for v in polygon) for k in (0,1)]
    candidates = []
    for ix in range(1,30):
        for iy in range(1,30):
            p = [lo[0]+(hi[0]-lo[0])*ix/30,lo[1]+(hi[1]-lo[1])*iy/30]
            if not contains(*p, polygon):
                continue
            distances = []
            for i,a in enumerate(polygon):
                b = polygon[(i+1)%len(polygon)]
                length2 = sum((b[k]-a[k])**2 for k in (0,1))
                t = max(0,min(1,sum((p[k]-a[k])*(b[k]-a[k]) for k in (0,1))/length2))
                distances.append(math.dist(p,[a[k]+t*(b[k]-a[k]) for k in (0,1)]))
            candidates.append((min(distances), p))
    if not candidates:
        raise ValueError('No interior camera candidate')
    return tuple(max(candidates)[1])


def mesh_faces(obj: bpy.types.Object) -> list[dict]:
    mesh = obj.data
    if not mesh.uv_layers.active or any(len(p.vertices)!=3 for p in mesh.polygons):
        raise ValueError('Triangular room mesh and UVs required')
    return [{'material':mesh.materials[p.material_index].name,'corners':
        [list(obj.matrix_world @ mesh.vertices[mesh.loops[i].vertex_index].co)+list(mesh.uv_layers.active.data[i].uv)
         for i in p.loop_indices]} for p in mesh.polygons]


def camera(scene: bpy.types.Scene, position: list, aim: list, ortho: bool=False, span: float=10) -> bpy.types.Object:
    obj = scene.camera
    if obj is None:
        obj = bpy.data.objects.new('DemoCamera',bpy.data.cameras.new('DemoCamera'))
        scene.collection.objects.link(obj)
        scene.camera = obj
        target = bpy.data.objects.new('DemoTarget',None)
        scene.collection.objects.link(target)
        c = obj.constraints.new('TRACK_TO')
        c.track_axis,c.up_axis,c.target = 'TRACK_NEGATIVE_Z','UP_Y',target
    obj.location = position
    obj.constraints[0].target.location = aim
    obj.data.type = 'ORTHO' if ortho else 'PERSP'
    obj.data.lens,obj.data.clip_start,obj.data.ortho_scale = 18,.03,span*1.3
    bpy.context.view_layer.update()
    return obj


def closest_hit(origin: Vector, direction: Vector, objects: list) -> tuple | None:
    hits = []
    for obj in objects:
        inverse = obj.matrix_world.inverted()
        hit,local,normal,index = obj.ray_cast(inverse @ origin,(inverse.to_3x3() @ direction).normalized())
        if hit:
            world = obj.matrix_world @ local
            world_normal = (inverse.transposed().to_3x3() @ normal).normalized()
            hits.append(((world-origin).length,world,world_normal,index,obj))
    return min(hits,key=lambda value:value[0]) if hits else None
