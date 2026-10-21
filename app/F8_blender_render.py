"""F8 渲染层阶段五：单房间聚焦 + 体积火焰 + 焦炭化动画 (P0 高保真)。

⚠️ 仅供 Blender 内部 Python 以独立子进程方式执行，绝对禁止在常规后端代码中 import bpy。

运行方式 (容器内):
    blender --background --python app/F8_blender_render.py -- --scene KK-EEz16cmU14

本阶段三大核心逻辑 (对应 PRD_V1.1 P0 优先级):
  1. 空间过滤: 解析 timeline 起火点位, 剔除远离燃烧区域的网格对象,
     相机包围盒仅限燃烧房间局部, 大幅缩减渲染范围并聚焦视觉
  2. 材质焦黑化: 燃烧强度达到峰值后, 用关键帧把保留房间材质的
     Base Color 过渡为纯黑、Roughness 过渡为 1.0 (失去光泽的焦炭形态),
     同时衰减火源发光强度
  3. 体积火焰与烟雾: 起火点生成 Volume 对象 (Principled Volume),
     Emission 表现火舌、Scatter 表现上方聚集的深灰烟雾,
     密度与发光强度随 timeline 强度曲线动态变化 (0 → 峰值 → 衰减)

沿用特性: 动态运镜 (TRACK_TO 约束)、Bloom 泛光、贴图兜底、产物覆盖机制、
逐帧进度日志、720p 预览档。
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

FPS = 24
FIRE_RADIUS = 0.45             # 火焰核心球体半径 (米)
FIRE_EMISSION_STRENGTH = 40.0  # 火焰材质峰值发光强度
FIRE_EMISSION_DECAY = 5.0      # 衰减后的余烬发光强度
FIRE_ENERGY_INITIAL = 300.0    # 火焰点光源初始能量 (瓦)
FIRE_ENERGY_GROWN = 900.0      # 火焰点光源峰值能量
FIRE_ENERGY_DECAY = 120.0      # 衰减后的余烬光照能量
FLAME_DENSITY_PEAK = 1.5       # 火舌体积峰值密度
FLAME_DENSITY_DECAY = 0.3      # 火舌体积衰减后密度
FLAME_EMISSION_PEAK = 80.0     # 火舌体积峰值发光强度
FLAME_EMISSION_DECAY = 8.0     # 火舌体积衰减后发光强度
SMOKE_DENSITY_PEAK = 0.5       # 烟雾体积峰值密度
SMOKE_DENSITY_FINAL = 1.2      # 烟雾聚顶最终密度 (持续累积)
BURN_REGION_MARGIN = 2.5       # 燃烧区域外扩边距 (米)
CAMERA_DISTANCE_FACTOR = 3.0   # 广角距离 = 燃烧区域最大尺寸 * 该系数
CLOSEUP_DISTANCE_FACTOR = 0.6  # 近景距离 = 燃烧区域最大尺寸 * 该系数
DEFAULT_SCENE = "KK-EEz16cmU14"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    """解析 '--' 之后的脚本参数 (Blender 会吞掉自身参数)。"""
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    parser = argparse.ArgumentParser(description="F8 火灾蔓延渲染")
    parser.add_argument("--scene", default=DEFAULT_SCENE, help="场景 code")
    parser.add_argument(
        "--quality", choices=["preview", "final"], default="preview",
        help="渲染档位: preview=720p 快速验证 / final=1080p 正式出片",
    )
    return parser.parse_args(argv)


def clear_scene() -> None:
    """清空默认场景 (Cube / Light / Camera)。"""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def import_mesh(mesh_path: Path) -> None:
    """导入 mesh.obj (保持原始 Z-up 坐标系, 与 points.json 一致)。"""
    if not mesh_path.is_file():
        print(f"[警告] 未找到网格: {mesh_path}, 跳过 (仅渲染火焰)", flush=True)
        return
    bpy.ops.wm.obj_import(filepath=str(mesh_path), up_axis="Z", forward_axis="Y")
    print(f"[F8] 网格已导入: {mesh_path}", flush=True)


def ensure_textures(scene_dir: Path) -> None:
    """贴图兜底: 为缺失 Image Texture 的材质强制接上场景目录下的照片纹理。"""
    candidates = sorted(scene_dir.glob("*.jpg")) + sorted(scene_dir.glob("*.png"))
    texture_path = next(
        (p for p in candidates if p.name.lower().startswith("texture")),
        candidates[0] if candidates else None,
    )
    if texture_path is None:
        print("[警告] 场景目录下未找到任何贴图文件 (.jpg/.png)", flush=True)
        return

    image = bpy.data.images.load(str(texture_path))
    fixed = 0
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            mat.use_nodes = True
        tree = mat.node_tree
        if any(node.type == "TEX_IMAGE" for node in tree.nodes):
            continue
        bsdf = next(
            (node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"), None
        )
        if bsdf is None:
            continue
        tex_node = tree.nodes.new("ShaderNodeTexImage")
        tex_node.image = image
        tree.links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
        fixed += 1

    print(f"[F8] 贴图兜底: 已为 {fixed} 个材质强制接上 {texture_path.name}", flush=True)


def build_point_map(points_path: Path) -> dict[int, tuple[float, float, float]]:
    """读取 points.json, 建立 device (图片编号) -> (x, y, z) 位姿映射。"""
    if not points_path.is_file():
        raise FileNotFoundError(f"points.json 不存在: {points_path}")
    raw_points = json.loads(points_path.read_text(encoding="utf-8"))
    point_map: dict[int, tuple[float, float, float]] = {}
    for point in raw_points:
        t = point["pose"]["translation"]
        point_map[int(point["device"])] = (t["x"], t["y"], t["z"])
    return point_map


def load_timeline(timeline_path: Path) -> dict:
    """读取 timeline.json (F7 输出)。"""
    if not timeline_path.is_file():
        raise FileNotFoundError(f"timeline.json 不存在: {timeline_path}")
    return json.loads(timeline_path.read_text(encoding="utf-8"))


def normalize_model(point_map: dict[int, tuple[float, float, float]]) -> tuple[Vector, float]:
    """模型归一化: 重置缩放并把几何中心平移到世界原点 (0,0,0)。

    返回 (offset, max_dim): offset 供火点坐标同步平移, max_dim 供参考。
    """
    corners: list[Vector] = []
    mesh_objs = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    for obj in mesh_objs:
        corners.extend(obj.matrix_world @ Vector(c) for c in obj.bound_box)
    if not corners:
        print("[警告] 无网格对象, 以点位坐标兜底", flush=True)
        corners = [Vector(pos) for pos in point_map.values()]

    mins = Vector(
        (min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners))
    )
    maxs = Vector(
        (max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners))
    )
    center = (mins + maxs) / 2
    dims = maxs - mins
    offset = -center

    for obj in mesh_objs:
        obj.scale = (1.0, 1.0, 1.0)
        obj.matrix_world.translation += offset

    print(
        f"[F8] 模型尺寸: X={dims.x:.2f} Y={dims.y:.2f} Z={dims.z:.2f} (米) "
        f"| 中心已对齐世界原点 (偏移 {offset.x:.2f}, {offset.y:.2f}, {offset.z:.2f})",
        flush=True,
    )
    return offset, max(dims.x, dims.y, dims.z)


def _near_burn_points(obj: bpy.types.Object, burn_points: list[Vector], margin: float) -> bool:
    """判断网格对象包围盒是否靠近任一燃烧点位 (距离 <= margin)。"""
    world_corners = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
    mins = Vector(
        (min(c.x for c in world_corners), min(c.y for c in world_corners), min(c.z for c in world_corners))
    )
    maxs = Vector(
        (max(c.x for c in world_corners), max(c.y for c in world_corners), max(c.z for c in world_corners))
    )
    for point in burn_points:
        closest = Vector(
            (max(mins.x, min(point.x, maxs.x)),
             max(mins.y, min(point.y, maxs.y)),
             max(mins.z, min(point.z, maxs.z)))
        )
        if (point - closest).length <= margin:
            return True
    return False


def filter_to_burn_region(
    point_map: dict[int, tuple[float, float, float]],
    events: list[dict],
    offset: Vector,
) -> tuple[list[bpy.types.Object], list[Vector]]:
    """空间过滤: 删除远离燃烧区域的网格对象, 仅保留起火房间局部。

    返回 (保留的网格对象列表, 燃烧点位列表[居中坐标系])。
    """
    burn_points = [
        Vector(point_map[int(e["point"])]) + offset
        for e in events
        if int(e["point"]) in point_map
    ]
    if not burn_points:
        burn_points = [Vector(pos) + offset for pos in point_map.values()]

    kept: list[bpy.types.Object] = []
    removed = 0
    for obj in [o for o in bpy.data.objects if o.type == "MESH"]:
        if _near_burn_points(obj, burn_points, BURN_REGION_MARGIN):
            kept.append(obj)
        else:
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1

    print(
        f"[F8] 空间过滤: 保留 {len(kept)} 个网格对象, 剔除 {removed} 个远离燃烧区域的网格 "
        f"(边距 {BURN_REGION_MARGIN}m, 燃烧点位 {len(burn_points)} 个)",
        flush=True,
    )
    return kept, burn_points


def burn_region_bounds(burn_points: list[Vector]) -> tuple[Vector, Vector]:
    """燃烧区域包围盒 (外扩边距), 供相机取景聚焦。"""
    mins = Vector(
        (min(p.x for p in burn_points), min(p.y for p in burn_points), min(p.z for p in burn_points))
    )
    maxs = Vector(
        (max(p.x for p in burn_points), max(p.y for p in burn_points), max(p.z for p in burn_points))
    )
    pad = Vector((BURN_REGION_MARGIN, BURN_REGION_MARGIN, BURN_REGION_MARGIN))
    return mins - pad, maxs + pad


def setup_world() -> None:
    """压抑环境光: 世界背景调暗, 突出火源的光影对比。"""
    world = bpy.context.scene.world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is None:
        background = world.node_tree.nodes.new("ShaderNodeBackground")
    background.inputs["Color"].default_value = (0.25, 0.27, 0.30, 1.0)
    background.inputs["Strength"].default_value = 1.0


def setup_lighting() -> None:
    """太阳光从斜上方打光 (开阴影, 提供基础可见度)。"""
    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 10.0))
    sun = bpy.context.active_object
    sun.name = "SunLight"
    sun.rotation_euler = (0.9, 0.0, 0.5)
    sun.data.energy = 4.0
    sun.data.use_shadow = True


def setup_camera_animation(
    ignition_pos: Vector, max_dim: float, frame_end: int
) -> None:
    """动态运镜: 第 1 帧起火点近景特写, 末帧拉远至燃烧区域广角。

    相机与注视目标均打 Location 关键帧, TRACK_TO 约束全程盯住目标。
    """
    look_target = bpy.data.objects.new("LookTarget", None)
    bpy.context.scene.collection.objects.link(look_target)

    cam_data = bpy.data.cameras.new("SmartCam")
    cam_data.type = "PERSP"
    cam_data.lens = 50.0
    cam_obj = bpy.data.objects.new("SmartCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

    direction = Vector((1.0, 1.0, 1.0)).normalized()
    close_pos = ignition_pos + direction * (max_dim * CLOSEUP_DISTANCE_FACTOR)
    far_pos = direction * (max_dim * CAMERA_DISTANCE_FACTOR)

    cam_obj.location = close_pos
    cam_obj.keyframe_insert(data_path="location", frame=1)
    look_target.location = ignition_pos
    look_target.keyframe_insert(data_path="location", frame=1)

    cam_obj.location = far_pos
    cam_obj.keyframe_insert(data_path="location", frame=frame_end)
    look_target.location = (0.0, 0.0, 0.0)
    look_target.keyframe_insert(data_path="location", frame=frame_end)

    track = cam_obj.constraints.new(type="TRACK_TO")
    track.target = look_target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    bpy.context.scene.camera = cam_obj
    active = bpy.context.scene.camera
    print(
        f"[F8] 动态运镜: 近景={tuple(round(v, 2) for v in close_pos)} "
        f"→ 广角={tuple(round(v, 2) for v in far_pos)} ({frame_end} 帧) "
        f"| 活动相机: {active.name if active else '无'}",
        flush=True,
    )


def make_fire_material() -> bpy.types.Material:
    """创建橙红色高亮自发光材质 (Emission 强度初始为 0, 由关键帧驱动)。"""
    mat = bpy.data.materials.new(name="FireGlow")
    mat.use_nodes = True
    tree = mat.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    emit = tree.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (1.0, 0.35, 0.05, 1.0)
    emit.inputs["Strength"].default_value = 0.0
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emit.outputs["Emission"], output.inputs["Surface"])
    return mat


def char_room_materials(
    kept_objects: list[bpy.types.Object], char_start: int, frame_end: int
) -> None:
    """材质焦黑化动画 (完全燃烧态): 燃烧峰值过后房间材质过渡为焦炭。

    - Base Color 逐渐过渡为纯黑 (0,0,0,1): 带贴图的材质插入 MixRGB 混合节点,
      无贴图的直接关键帧 default_value
    - Roughness 过渡为 1.0 (失去光泽)
    关键帧: 第 1 帧与 char_start 帧保持原值, frame_end 帧为焦炭终态。
    """
    materials = {
        slot
        for obj in kept_objects
        for slot in obj.data.materials
        if slot is not None
    }
    if not materials:
        print("[警告] 保留网格没有任何材质, 跳过焦黑化", flush=True)
        return

    charred = 0
    for mat in materials:
        if not mat.use_nodes:
            mat.use_nodes = True
        tree = mat.node_tree
        bsdf = next(
            (node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"), None
        )
        if bsdf is None:
            continue
        base_in = bsdf.inputs["Base Color"]
        rough_in = bsdf.inputs["Roughness"]

        # --- Base Color → 纯黑 ---
        if base_in.is_linked:
            # 带贴图的材质: 插入 MixRGB, 用 Fac 关键帧混合到黑色
            src_socket = base_in.links[0].from_socket
            mix = tree.nodes.new("ShaderNodeMixRGB")
            mix.blend_type = "MIX"
            mix.inputs["Color2"].default_value = (0.0, 0.0, 0.0, 1.0)
            mix.inputs["Fac"].default_value = 0.0
            for link in list(base_in.links):
                tree.links.remove(link)
            tree.links.new(src_socket, mix.inputs["Color1"])
            tree.links.new(mix.outputs["Color"], base_in)
            mix.inputs["Fac"].keyframe_insert(data_path="default_value", frame=1)
            mix.inputs["Fac"].keyframe_insert(data_path="default_value", frame=char_start)
            mix.inputs["Fac"].default_value = 1.0
            mix.inputs["Fac"].keyframe_insert(data_path="default_value", frame=frame_end)
        else:
            base_in.keyframe_insert(data_path="default_value", frame=1)
            base_in.keyframe_insert(data_path="default_value", frame=char_start)
            base_in.default_value = (0.0, 0.0, 0.0, 1.0)
            base_in.keyframe_insert(data_path="default_value", frame=frame_end)

        # --- Roughness → 1.0 (失去光泽) ---
        rough_in.keyframe_insert(data_path="default_value", frame=1)
        rough_in.keyframe_insert(data_path="default_value", frame=char_start)
        rough_in.default_value = 1.0
        rough_in.keyframe_insert(data_path="default_value", frame=frame_end)

        charred += 1

    print(
        f"[F8] 焦黑化动画: {charred} 个材质将于帧 {char_start}-{frame_end} "
        f"过渡为纯黑焦炭 (Roughness 1.0)",
        flush=True,
    )


def spawn_fire_effects(
    point_map: dict[int, tuple[float, float, float]],
    events: list[dict],
    offset: Vector,
    frame_end: int,
) -> None:
    """生成火焰核心: 球体 + 点光源, 关键帧驱动渐入、峰值与余烬衰减。

    每个事件独立材质:
      - 球体 Scale: 0 -> 1 (出现动画)
      - Emission 强度: 0 -> 峰值 -> 余烬 (40 -> 5)
      - 点光源能量: 0 -> 300 -> 900 -> 120 (火势变大后衰减)
    """
    for event in events:
        point_id = int(event["point"])
        if point_id not in point_map:
            print(f"[警告] 点位 {point_id} 在 points.json 中无坐标, 跳过", flush=True)
            continue
        position = Vector(point_map[point_id]) + offset
        start_frame = int(event["time"]) * FPS + 1
        ramp_frames = FPS
        before_frame = max(1, start_frame - 1)
        peak_frame = start_frame + ramp_frames

        # --- 火焰核心球体 ---
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=FIRE_RADIUS, location=tuple(position)
        )
        sphere = bpy.context.active_object
        sphere.name = f"Fire_{point_id}"
        material = make_fire_material()
        sphere.data.materials.append(material)

        sphere.scale = (0.0, 0.0, 0.0)
        sphere.keyframe_insert(data_path="scale", frame=before_frame)
        sphere.scale = (1.0, 1.0, 1.0)
        sphere.keyframe_insert(data_path="scale", frame=peak_frame)

        emit_node = material.node_tree.nodes["Emission"]
        emit_node.inputs["Strength"].default_value = 0.0
        emit_node.inputs["Strength"].keyframe_insert(
            data_path="default_value", frame=before_frame
        )
        emit_node.inputs["Strength"].default_value = FIRE_EMISSION_STRENGTH
        emit_node.inputs["Strength"].keyframe_insert(
            data_path="default_value", frame=peak_frame
        )
        emit_node.inputs["Strength"].default_value = FIRE_EMISSION_DECAY
        emit_node.inputs["Strength"].keyframe_insert(
            data_path="default_value", frame=frame_end
        )

        # --- 火焰点光源: 渐入 -> 峰值 -> 余烬 ---
        bpy.ops.object.light_add(
            type="POINT", location=tuple(position + Vector((0.0, 0.0, 0.3)))
        )
        light = bpy.context.active_object
        light.name = f"FireLight_{point_id}"
        light.data.color = (1.0, 0.4, 0.08)
        light.data.cutoff_distance = 15.0
        light.data.energy = 0.0
        light.data.keyframe_insert(data_path="energy", frame=before_frame)
        light.data.energy = FIRE_ENERGY_INITIAL
        light.data.keyframe_insert(data_path="energy", frame=peak_frame)
        light.data.energy = FIRE_ENERGY_GROWN
        light.data.keyframe_insert(data_path="energy", frame=peak_frame + FPS * 2)
        light.data.energy = FIRE_ENERGY_DECAY
        light.data.keyframe_insert(data_path="energy", frame=frame_end)

    print(f"[F8] 已生成 {len(events)} 组火焰核心 (球体 + 动态点光源)", flush=True)


def make_volume_material(
    name: str,
    color: tuple[float, float, float],
    density: float,
    emission_strength: float,
) -> tuple[bpy.types.Material, bpy.types.Node]:
    """创建体积材质 (Principled Volume), 返回 (材质, 体积节点)。"""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    tree = mat.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    volume = tree.nodes.new("ShaderNodeVolumePrincipled")
    volume.inputs["Color"].default_value = (*color, 1.0)
    volume.inputs["Density"].default_value = density
    volume.inputs["Emission Strength"].default_value = emission_strength
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(volume.outputs["Volume"], output.inputs["Volume"])
    return mat, volume


def spawn_fire_volumes(
    point_map: dict[int, tuple[float, float, float]],
    events: list[dict],
    offset: Vector,
    frame_end: int,
) -> None:
    """体积火焰与烟雾: 每个起火点生成火舌体积 + 烟雾聚顶体积。

    密度与发光强度按 timeline 强度曲线关键帧驱动:
      火舌: 0 -> 峰值 (1.5 / 80) -> 衰减 (0.3 / 8)
      烟雾: 0 -> 0.5 -> 1.2 (持续累积, 表现烟雾聚顶)
    """
    count = 0
    for event in events:
        point_id = int(event["point"])
        if point_id not in point_map:
            continue
        position = Vector(point_map[point_id]) + offset
        start_frame = int(event["time"]) * FPS + 1
        before_frame = max(1, start_frame - 1)
        peak_frame = start_frame + FPS

        # --- 火舌体积 (竖直拉伸, 橙色 Emission) ---
        flame_mat, flame_node = make_volume_material(
            f"FlameVol_{point_id}", (1.0, 0.35, 0.05), 0.0, 0.0
        )
        bpy.ops.mesh.primitive_cube_add(
            size=1.0, location=tuple(position + Vector((0.0, 0.0, 1.2)))
        )
        flame_obj = bpy.context.active_object
        flame_obj.name = f"Flame_{point_id}"
        flame_obj.scale = (1.0, 1.0, 2.4)  # 竖直拉伸成火舌
        flame_obj.data.materials.append(flame_mat)

        den = flame_node.inputs["Density"]
        em = flame_node.inputs["Emission Strength"]
        den.default_value = 0.0
        em.default_value = 0.0
        den.keyframe_insert(data_path="default_value", frame=before_frame)
        em.keyframe_insert(data_path="default_value", frame=before_frame)
        den.default_value = FLAME_DENSITY_PEAK
        em.default_value = FLAME_EMISSION_PEAK
        den.keyframe_insert(data_path="default_value", frame=peak_frame)
        em.keyframe_insert(data_path="default_value", frame=peak_frame)
        den.default_value = FLAME_DENSITY_DECAY
        em.default_value = FLAME_EMISSION_DECAY
        den.keyframe_insert(data_path="default_value", frame=frame_end)
        em.keyframe_insert(data_path="default_value", frame=frame_end)

        # --- 烟雾聚顶体积 (更大, 深灰, 密度持续累积) ---
        smoke_mat, smoke_node = make_volume_material(
            f"SmokeVol_{point_id}", (0.15, 0.15, 0.16), 0.0, 0.0
        )
        bpy.ops.mesh.primitive_cube_add(
            size=1.0, location=tuple(position + Vector((0.0, 0.0, 2.8)))
        )
        smoke_obj = bpy.context.active_object
        smoke_obj.name = f"Smoke_{point_id}"
        smoke_obj.scale = (2.2, 2.2, 2.6)
        smoke_obj.data.materials.append(smoke_mat)

        smoke_den = smoke_node.inputs["Density"]
        smoke_den.default_value = 0.0
        smoke_den.keyframe_insert(data_path="default_value", frame=before_frame)
        smoke_den.default_value = SMOKE_DENSITY_PEAK
        smoke_den.keyframe_insert(data_path="default_value", frame=peak_frame)
        smoke_den.default_value = SMOKE_DENSITY_FINAL
        smoke_den.keyframe_insert(data_path="default_value", frame=frame_end)

        count += 1

    print(f"[F8] 已生成 {count} 组体积火焰与烟雾 (Principled Volume)", flush=True)


def setup_render(output_path: Path, frame_end: int, quality: str = "preview") -> None:
    """Eevee + 体积渲染参数 + Bloom + FFmpeg 感知无损输出。

    quality: preview=1280x720 快速验证 / final=1920x1080 正式出片 (V6.0 参数化)。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"  # Blender 4.2 的 Eevee
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = frame_end
    if quality == "final":
        scene.render.resolution_x = 1920
        scene.render.resolution_y = 1080
    else:
        scene.render.resolution_x = 1280
        scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.eevee.taa_samples = 1
    scene.eevee.use_ssr = False
    scene.eevee.use_gtao = False
    # 泛光特效
    scene.eevee.use_bloom = True
    scene.eevee.bloom_intensity = 1.0
    scene.eevee.bloom_threshold = 0.6
    # 体积渲染参数 (火舌/烟雾)
    scene.eevee.volumetric_tile_size = "8"  # Blender 4.2 为字符串枚举: '2'/'4'/'8'/'16'
    scene.eevee.volumetric_samples = 24
    scene.eevee.volumetric_shadow_samples = 8
    scene.eevee.volumetric_start = 0.1
    scene.eevee.volumetric_end = 60.0
    # FFmpeg 输出
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "PERC_LOSSLESS"
    scene.render.filepath = str(output_path)


def _register_frame_progress(total_frames: int) -> None:
    """注册逐帧渲染进度回调: 每帧渲染完成打印进度到 stdout (被外部日志系统捕获)。"""
    def _on_frame_done(*args: object) -> None:
        frame = bpy.context.scene.frame_current
        print(
            f"[F8] 帧 {frame}/{total_frames} ({frame / total_frames * 100:.1f}%)",
            flush=True,
        )

    bpy.app.handlers.render_post.append(_on_frame_done)


def main() -> None:
    args = parse_args()
    scene_dir = PROJECT_ROOT / "data" / args.scene
    points_path = scene_dir / "points.json"
    timeline_path = scene_dir / "timeline.json"
    output_path = scene_dir / "output.mp4"

    point_map = build_point_map(points_path)
    timeline = load_timeline(timeline_path)
    events: list[dict] = timeline["spread_events"]
    start_point_id = int(timeline.get("start_point", events[0]["point"]))

    # 覆盖机制: 强制清除旧产物
    if output_path.exists():
        output_path.unlink()
        print(f"[F8] 已删除旧产物: {output_path}", flush=True)

    clear_scene()
    import_mesh(scene_dir / "mesh.obj")
    ensure_textures(scene_dir)
    offset, _ = normalize_model(point_map)

    # ---- 空间过滤: 仅保留燃烧区域局部 ----
    kept_objects, burn_points = filter_to_burn_region(point_map, events, offset)
    bounds_min, bounds_max = burn_region_bounds(burn_points)
    max_dim = max(
        bounds_max.x - bounds_min.x,
        bounds_max.y - bounds_min.y,
        bounds_max.z - bounds_min.z,
    )

    ignition_pos = (
        Vector(point_map[start_point_id]) + offset
        if start_point_id in point_map
        else Vector((0.0, 0.0, 0.0))
    )

    # 时间轴: 最后事件渐入 1 秒, 之后 2 秒为焦黑化/余烬衰减窗口
    last_start = max(int(e["time"]) for e in events) * FPS + 1
    frame_end = last_start + FPS * 3
    char_start = last_start + FPS  # 峰值过后开始焦黑化

    setup_world()
    setup_lighting()
    setup_camera_animation(ignition_pos, max_dim, frame_end)
    char_room_materials(kept_objects, char_start, frame_end)
    spawn_fire_effects(point_map, events, offset, frame_end)
    spawn_fire_volumes(point_map, events, offset, frame_end)
    setup_render(output_path, frame_end, args.quality)
    _register_frame_progress(frame_end)

    scene = bpy.context.scene
    print(
        f"[F8] 渲染配置: engine=Eevee(EEVEE_NEXT) 分辨率={scene.render.resolution_x}x{scene.render.resolution_y} "
        f"档位={args.quality} fps={FPS} 帧范围=1-{frame_end} 事件数={len(events)} 起火点={start_point_id} "
        f"焦黑化起点=帧{char_start} 输出={output_path}",
        flush=True,
    )
    bpy.ops.render.render(animation=True)
    output_size = output_path.stat().st_size / (1024 * 1024)
    print(f"[F8] 渲染完成: {output_path} ({output_size:.2f} MB)", flush=True)


if __name__ == "__main__":
    main()
