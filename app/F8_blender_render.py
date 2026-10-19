"""F8 渲染层阶段二：真实场景渲染框架 (GPU 服务器版)。

⚠️ 仅供 Blender 内部 Python 以独立子进程方式执行，绝对禁止在常规后端代码中 import bpy。

运行方式 (容器内):
    blender --background --python app/F8_blender_render.py -- --scene KK-EEz16cmU14

本阶段实现:
  1. 明亮光照: 太阳光 (开阴影) + 亮色世界环境, 确保模型清晰可见
  2. 智能机位: 依据网格包围盒自动计算 45° 俯角透视机位并 LookAt 场景中心
  3. 蔓延动画: 每个火焰事件独立材质 + 点光源, Emission/能量/缩放三路关键帧 1 秒渐入,
     火焰燃起的同时照亮房间, 实现基于 timeline.json 的真实动态蔓延

坐标系说明: points.json 与 mesh.obj 均为 Z-up (z 为高度方向),
因此 OBJ 导入不做轴转换, 球体直接使用点位 translation 坐标。
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

FPS = 24
FIRE_RADIUS = 0.45          # 火焰球体半径 (米)
FIRE_EMISSION_STRENGTH = 12.0   # 火焰材质发光强度
FIRE_GLOW_ENERGY = 400.0    # 火焰点光源能量 (瓦)
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


def setup_world() -> None:
    """设置亮色世界背景, 提供环境补光, 避免场景死黑。"""
    world = bpy.context.scene.world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is None:
        background = world.node_tree.nodes.new("ShaderNodeBackground")
    background.inputs["Color"].default_value = (0.55, 0.6, 0.65, 1.0)
    background.inputs["Strength"].default_value = 1.0


def setup_lighting() -> None:
    """太阳光从斜上方打光 (开阴影, 增强立体感)。"""
    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 10.0))
    sun = bpy.context.active_object
    sun.name = "SunLight"
    sun.rotation_euler = (0.9, 0.0, 0.5)  # 斜向下照射
    sun.data.energy = 6.0
    sun.data.use_shadow = True


def setup_camera(bounds_min: Vector, bounds_max: Vector) -> None:
    """智能机位: 依据包围盒自动计算 45° 俯角透视相机并对准场景中心。"""
    center = (bounds_min + bounds_max) / 2
    radius = (bounds_max - center).length  # 包围球半径

    cam_data = bpy.data.cameras.new("SmartCam")
    cam_data.type = "PERSP"
    cam_data.lens = 50.0
    cam_obj = bpy.data.objects.new("SmartCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

    # 45° 俯角 + 45° 方位角的单位方向向量
    direction = Vector((0.5, 0.5, 0.7071))
    # 依据垂直视场角计算距离, 保证包围球完整入画 (留 25% 边距)
    fov_v = cam_data.angle
    distance = (radius / math.sin(fov_v / 2)) * 1.25
    cam_obj.location = center + direction * distance
    # LookAt 场景中心
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    bpy.context.scene.camera = cam_obj
    print(
        f"[F8] 相机已放置: 中心=({center.x:.2f}, {center.y:.2f}, {center.z:.2f}) "
        f"距离={distance:.2f}m",
        flush=True,
    )


def make_fire_material() -> bpy.types.Material:
    """创建红色自发光材质 (Emission 强度初始为 0, 由关键帧驱动渐入)。"""
    mat = bpy.data.materials.new(name="FireGlow")
    mat.use_nodes = True
    tree = mat.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    emit = tree.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (1.0, 0.2, 0.02, 1.0)
    emit.inputs["Strength"].default_value = 0.0
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emit.outputs["Emission"], output.inputs["Surface"])
    return mat


def spawn_fire_effects(
    point_map: dict[int, tuple[float, float, float]], events: list[dict]
) -> None:
    """按 timeline 事件生成火焰效果: 球体 + 点光源, 三路关键帧做 1 秒渐入。

    每个事件独立材质 (避免共享材质导致关键帧互相覆盖):
      - 球体 Scale:  0 -> 1 (出现动画)
      - Emission 强度: 0 -> 全亮 (材质从原色渐变为发光红)
      - 点光源能量: 0 -> 全亮 (火焰照亮房间, 强化蔓延视觉)
    事件时间 time 秒 -> 帧号 = time * FPS + 1; 之后 1 秒内渐入完成。
    """
    for event in events:
        point_id = int(event["point"])
        if point_id not in point_map:
            print(f"[警告] 点位 {point_id} 在 points.json 中无坐标, 跳过", flush=True)
            continue
        x, y, z = point_map[point_id]
        start_frame = int(event["time"]) * FPS + 1
        ramp_frames = FPS  # 渐入时长 1 秒
        before_frame = max(1, start_frame - 1)

        # --- 火焰球体 ---
        bpy.ops.mesh.primitive_uv_sphere_add(radius=FIRE_RADIUS, location=(x, y, z))
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

        # --- 火焰点光源 ---
        bpy.ops.object.light_add(type="POINT", location=(x, y, z + 0.3))
        light = bpy.context.active_object
        light.name = f"FireLight_{point_id}"
        light.data.color = (1.0, 0.4, 0.08)
        light.data.energy = 0.0
        light.data.keyframe_insert(data_path="energy", frame=before_frame)
        light.data.energy = FIRE_GLOW_ENERGY
        light.data.keyframe_insert(
            data_path="energy", frame=start_frame + ramp_frames
        )

    print(f"[F8] 已生成 {len(events)} 组火焰效果 (球体 + 点光源)", flush=True)


def compute_scene_bounds(
    point_map: dict[int, tuple[float, float, float]]
) -> tuple[Vector, Vector]:
    """计算场景包围盒: 优先取网格对象, 无网格时退回点位坐标。"""
    corners: list[Vector] = []
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            for corner in obj.bound_box:
                corners.append(obj.matrix_world @ Vector(corner))
    if not corners:
        corners = [Vector(pos) for pos in point_map.values()]
    mins = Vector(
        (min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners))
    )
    maxs = Vector(
        (max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners))
    )
    return mins, maxs


def setup_render(output_path: Path, frame_end: int) -> None:
    """Eevee + FFmpeg MP4 输出设置 (占位阶段用低分辨率加速)。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"  # Blender 4.2 的 Eevee
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = frame_end
    scene.render.resolution_x = 640   # 占位验证用低分辨率, 加速软渲染
    scene.render.resolution_y = 360
    scene.eevee.taa_samples = 1      # 关闭多重采样 (软渲染下 16x 采样是最大瓶颈)
    scene.eevee.use_ssr = False      # 关闭屏幕空间反射
    scene.eevee.use_gtao = False     # 关闭环境光遮蔽
    scene.eevee.use_bloom = False    # 关闭泛光
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
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

    # 覆盖机制: 强制清除旧产物, 保证每次生成的都是最新渲染的视频
    if output_path.exists():
        output_path.unlink()
        print(f"[F8] 已删除旧产物: {output_path}", flush=True)

    clear_scene()
    import_mesh(scene_dir / "mesh.obj")
    bounds_min, bounds_max = compute_scene_bounds(point_map)
    setup_world()
    setup_lighting()
    setup_camera(bounds_min, bounds_max)
    spawn_fire_effects(point_map, events)

    # 最后事件渐入 1 秒 + 观察尾帧 1 秒
    last_start = max(int(e["time"]) for e in events) * FPS + 1
    frame_end = last_start + FPS * 2
    setup_render(output_path, frame_end)
    _register_frame_progress(frame_end)

    scene = bpy.context.scene
    print(
        f"[F8] 渲染配置: engine=Eevee(EEVEE_NEXT) 分辨率={scene.render.resolution_x}x{scene.render.resolution_y} "
        f"fps={FPS} 帧范围=1-{frame_end} 事件数={len(events)} 输出={output_path}",
        flush=True,
    )
    bpy.ops.render.render(animation=True)
    output_size = output_path.stat().st_size / (1024 * 1024)
    print(f"[F8] 渲染完成: {output_path} ({output_size:.2f} MB)", flush=True)


if __name__ == "__main__":
    main()
