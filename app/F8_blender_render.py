"""F8 渲染层阶段四：电影级动态运镜 + 光影特效 (720p 预览档)。

⚠️ 仅供 Blender 内部 Python 以独立子进程方式执行，绝对禁止在常规后端代码中 import bpy。

运行方式 (容器内):
    blender --background --python app/F8_blender_render.py -- --scene KK-EEz16cmU14

本阶段特性:
  1. 动态运镜: 第 1 帧在起火点近景特写, 末帧拉远至全局广角, Location 打关键帧,
     TRACK_TO 约束全程紧盯 (注视目标本身也随关键帧从起火点移到模型中心)
  2. Bloom 泛光: 显式开启, 火源产生真实光晕
  3. 高亮火源: Emission 强度 40 + 橙红色, 结合 Bloom 亮得刺眼
  4. 压抑环境: 世界环境光调暗; 火源点光源能量随关键帧持续增大, 模拟火势变大
  5. 1080p 高清 + FFmpeg 感知无损质量
  6. 贴图兜底: 修复 MTL map_Ka 不被导入器支持的问题,
     为缺失 Image Texture 的材质强制接上场景目录下的照片纹理

坐标系: points.json 与 mesh.obj 均为 Z-up; 模型居中偏移同步应用于火点坐标。
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

FPS = 24
FIRE_RADIUS = 0.45             # 火焰球体半径 (米)
FIRE_EMISSION_STRENGTH = 40.0  # 火焰材质发光强度 (高亮, 配合 Bloom)
FIRE_ENERGY_INITIAL = 300.0    # 火焰点光源初始能量 (瓦)
FIRE_ENERGY_GROWN = 900.0      # 火焰点光源成长后能量 (模拟火势变大)
FIRE_GROW_SPAN_FRAMES = FPS * 2  # 光源能量成长时长 (2 秒)
CAMERA_DISTANCE_FACTOR = 3.0   # 广角距离 = 模型最大尺寸 * 该系数
CLOSEUP_DISTANCE_FACTOR = 0.6  # 近景距离 = 模型最大尺寸 * 该系数 (贴近起火点)
DEFAULT_SCENE = "KK-EEz16cmU14"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    """解析 '--' 之后的脚本参数 (Blender 会吞掉自身参数)。"""
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    parser = argparse.ArgumentParser(description="F8 火灾蔓延渲染")
    parser.add_argument("--scene", default=DEFAULT_SCENE, help="场景 code")
    return parser.parse_args(argv)


def clear_scene() -> None:
    """清空默认场景 (Cube / Light / Camera)。"""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def import_mesh(mesh_path: Path) -> None:
    """导入 mesh.obj (保持原始 Z-up 坐标系, 与 points.json 一致)。"""
    if not mesh_path.is_file():
        print(f"[警告] 未找到网格: {mesh_path}, 跳过 (仅渲染火焰球)", flush=True)
        return
    bpy.ops.wm.obj_import(filepath=str(mesh_path), up_axis="Z", forward_axis="Y")
    print(f"[F8] 网格已导入: {mesh_path}", flush=True)


def ensure_textures(scene_dir: Path) -> None:
    """贴图兜底: 为缺失 Image Texture 的材质强制接上场景目录下的照片纹理。

    背景: MTL 中贴图常声明在 map_Ka 通道, Blender OBJ 导入器不支持该通道,
    导致模型只有几何轮廓没有纹理。此函数为没有贴图节点的材质补接 Base Color。
    """
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
            continue  # 已有贴图节点, 不重复处理
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

    返回 (offset, max_dim): offset 供火点坐标同步平移, max_dim 供相机定距。
    无网格时以点位坐标兜底。
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
        obj.scale = (1.0, 1.0, 1.0)            # 重置缩放
        obj.matrix_world.translation += offset  # 整体平移居中

    print(
        f"[F8] 模型尺寸: X={dims.x:.2f} Y={dims.y:.2f} Z={dims.z:.2f} (米) "
        f"| 中心已对齐世界原点 (偏移 {offset.x:.2f}, {offset.y:.2f}, {offset.z:.2f})",
        flush=True,
    )
    return offset, max(dims.x, dims.y, dims.z)


def setup_world() -> None:
    """压抑环境光: 世界背景调暗, 突出火源的光影对比。"""
    world = bpy.context.scene.world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is None:
        background = world.node_tree.nodes.new("ShaderNodeBackground")
    background.inputs["Color"].default_value = (0.25, 0.27, 0.30, 1.0)  # 暗蓝灰
    background.inputs["Strength"].default_value = 1.0


def setup_lighting() -> None:
    """太阳光从斜上方打光 (开阴影, 提供基础可见度)。"""
    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 10.0))
    sun = bpy.context.active_object
    sun.name = "SunLight"
    sun.rotation_euler = (0.9, 0.0, 0.5)  # 斜向下照射
    sun.data.energy = 4.0
    sun.data.use_shadow = True


def setup_camera_animation(
    ignition_pos: Vector, max_dim: float, frame_end: int
) -> None:
    """动态运镜: 第 1 帧起火点近景特写, 末帧拉远至全局广角。

    相机与注视目标 (LookTarget) 均打 Location 关键帧:
      - 相机: 起火点斜上方近景 → 模型斜上方 3 倍尺寸广角
      - 注视目标: 起火点 → 模型中心 (原点)
    TRACK_TO 约束全程生效, 镜头方向零手算, 保证 100% 盯住目标。
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

    # 第 1 帧: 近景特写起火点
    cam_obj.location = close_pos
    cam_obj.keyframe_insert(data_path="location", frame=1)
    look_target.location = ignition_pos
    look_target.keyframe_insert(data_path="location", frame=1)
    # 末帧: 拉远至全局广角
    cam_obj.location = far_pos
    cam_obj.keyframe_insert(data_path="location", frame=frame_end)
    look_target.location = (0.0, 0.0, 0.0)
    look_target.keyframe_insert(data_path="location", frame=frame_end)

    track = cam_obj.constraints.new(type="TRACK_TO")
    track.target = look_target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    # 强制激活相机
    bpy.context.scene.camera = cam_obj
    active = bpy.context.scene.camera
    print(
        f"[F8] 动态运镜: 近景={tuple(round(v, 2) for v in close_pos)} "
        f"→ 广角={tuple(round(v, 2) for v in far_pos)} ({frame_end} 帧) "
        f"| 活动相机: {active.name if active else '无'}",
        flush=True,
    )


def make_fire_material() -> bpy.types.Material:
    """创建橙红色高亮自发光材质 (Emission 强度初始为 0, 由关键帧驱动渐入)。"""
    mat = bpy.data.materials.new(name="FireGlow")
    mat.use_nodes = True
    tree = mat.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    emit = tree.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (1.0, 0.35, 0.05, 1.0)  # 耀眼橙红
    emit.inputs["Strength"].default_value = 0.0
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emit.outputs["Emission"], output.inputs["Surface"])
    return mat


def spawn_fire_effects(
    point_map: dict[int, tuple[float, float, float]],
    events: list[dict],
    offset: Vector,
) -> None:
    """按 timeline 事件生成火焰效果: 球体 + 点光源, 关键帧驱动渐入与成长。

    每个事件独立材质:
      - 球体 Scale: 0 -> 1 (出现动画)
      - Emission 强度: 0 -> 40 (材质从原色渐变为刺眼发光橙红)
      - 点光源能量: 0 -> 300 -> 900 (火势变大, 照亮范围持续扩张)
    火点坐标统一叠加模型居中偏移量, 与模型保持对齐。
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

        # --- 火焰球体 ---
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=FIRE_RADIUS, location=tuple(position)
        )
        sphere = bpy.context.active_object
        sphere.name = f"Fire_{point_id}"
        material = make_fire_material()  # 每个事件独立材质
        sphere.data.materials.append(material)

        sphere.scale = (0.0, 0.0, 0.0)
        sphere.keyframe_insert(data_path="scale", frame=before_frame)
        sphere.scale = (1.0, 1.0, 1.0)
        sphere.keyframe_insert(data_path="scale", frame=start_frame + ramp_frames)

        emit_node = material.node_tree.nodes["Emission"]
        emit_node.inputs["Strength"].default_value = 0.0
        emit_node.inputs["Strength"].keyframe_insert(
            data_path="default_value", frame=before_frame
        )
        emit_node.inputs["Strength"].default_value = FIRE_EMISSION_STRENGTH
        emit_node.inputs["Strength"].keyframe_insert(
            data_path="default_value", frame=start_frame + ramp_frames
        )

        # --- 火焰点光源: 能量随关键帧逐渐变大, 模拟火势扩张 ---
        bpy.ops.object.light_add(
            type="POINT", location=tuple(position + Vector((0.0, 0.0, 0.3)))
        )
        light = bpy.context.active_object
        light.name = f"FireLight_{point_id}"
        light.data.color = (1.0, 0.4, 0.08)
        light.data.cutoff_distance = 15.0  # 照亮范围 15 米
        light.data.energy = 0.0
        light.data.keyframe_insert(data_path="energy", frame=before_frame)
        light.data.energy = FIRE_ENERGY_INITIAL
        light.data.keyframe_insert(
            data_path="energy", frame=start_frame + ramp_frames
        )
        light.data.energy = FIRE_ENERGY_GROWN
        light.data.keyframe_insert(
            data_path="energy", frame=start_frame + ramp_frames + FIRE_GROW_SPAN_FRAMES
        )

    print(f"[F8] 已生成 {len(events)} 组火焰效果 (球体 + 动态点光源)", flush=True)


def setup_render(output_path: Path, frame_end: int) -> None:
    """Eevee + Bloom + 720p 预览档 + FFmpeg 感知无损输出。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"  # Blender 4.2 的 Eevee
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = frame_end
    scene.render.resolution_x = 1280          # 720p 预览档 (快速看效果)
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100  # 100% 渲染百分比
    scene.eevee.taa_samples = 1
    scene.eevee.use_ssr = False
    scene.eevee.use_gtao = False
    # 泛光特效: 火源高亮区域产生真实光晕
    scene.eevee.use_bloom = True
    scene.eevee.bloom_intensity = 1.0
    scene.eevee.bloom_threshold = 0.6
    # FFmpeg 输出: 感知无损最高质量
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

    # 覆盖机制: 强制清除旧产物, 保证每次生成的都是最新渲染的视频
    if output_path.exists():
        output_path.unlink()
        print(f"[F8] 已删除旧产物: {output_path}", flush=True)

    clear_scene()
    import_mesh(scene_dir / "mesh.obj")
    ensure_textures(scene_dir)
    offset, max_dim = normalize_model(point_map)

    # 起火点坐标 (与模型同步平移后); 缺失时退回模型中心
    ignition_pos = (
        Vector(point_map[start_point_id]) + offset
        if start_point_id in point_map
        else Vector((0.0, 0.0, 0.0))
    )

    # 最后事件渐入 1 秒 + 观察尾帧 1 秒
    last_start = max(int(e["time"]) for e in events) * FPS + 1
    frame_end = last_start + FPS * 2

    setup_world()
    setup_lighting()
    setup_camera_animation(ignition_pos, max_dim, frame_end)
    spawn_fire_effects(point_map, events, offset)
    setup_render(output_path, frame_end)
    _register_frame_progress(frame_end)

    scene = bpy.context.scene
    print(
        f"[F8] 渲染配置: engine=Eevee(EEVEE_NEXT) 分辨率={scene.render.resolution_x}x{scene.render.resolution_y} "
        f"fps={FPS} 帧范围=1-{frame_end} 事件数={len(events)} 起火点={start_point_id} 输出={output_path}",
        flush=True,
    )
    bpy.ops.render.render(animation=True)
    output_size = output_path.stat().st_size / (1024 * 1024)
    print(f"[F8] 渲染完成: {output_path} ({output_size:.2f} MB)", flush=True)


if __name__ == "__main__":
    main()
