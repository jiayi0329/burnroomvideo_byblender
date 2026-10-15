"""F8 渲染层阶段一：红球占位验证 (MVP)。

⚠️ 仅供 Blender 内部 Python 以独立子进程方式执行，绝对禁止在常规后端代码中 import bpy。

运行方式 (容器内):
    blender --background --python app/F8_blender_render.py -- --scene KK-EEz16cmU14

坐标系说明: 经实测 points.json 与 mesh.obj 均为 Z-up (z 为高度方向)，
因此 OBJ 导入不做轴转换，球体直接使用点位 translation 坐标。
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

FPS = 24
SPHERE_RADIUS = 0.3
DEFAULT_SCENE = "KK-EEz16cmU14"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    """解析 '--' 之后的脚本参数 (Blender 会吞掉自身参数)。"""
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    parser = argparse.ArgumentParser(description="F8 红球占位渲染")
    parser.add_argument("--scene", default=DEFAULT_SCENE, help="场景 code")
    return parser.parse_args(argv)


def clear_scene() -> None:
    """清空默认场景 (Cube / Light / Camera)。"""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def import_mesh(mesh_path: Path) -> None:
    """导入 mesh.obj (保持原始 Z-up 坐标系, 与 points.json 一致)。"""
    if not mesh_path.is_file():
        print(f"[警告] 未找到网格: {mesh_path}, 跳过 (仅渲染红球)", flush=True)
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


def make_fire_material() -> bpy.types.Material:
    """创建红色自发光材质 (Emission Shader) 作为火焰占位符。"""
    mat = bpy.data.materials.new(name="FireGlow")
    mat.use_nodes = True
    tree = mat.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    emit = tree.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (1.0, 0.05, 0.0, 1.0)
    emit.inputs["Strength"].default_value = 12.0
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emit.outputs["Emission"], output.inputs["Surface"])
    return mat


def spawn_fire_balls(
    point_map: dict[int, tuple[float, float, float]],
    events: list[dict],
    material: bpy.types.Material,
) -> None:
    """按 timeline 事件在对应 3D 坐标生成红球, 用 Scale 关键帧控制出现时刻。

    事件时间 time 秒 → 帧号 frame = time * FPS + 1;
    frame 之前 scale=0 (不可见), frame 起 scale=1。
    """
    for event in events:
        point_id = int(event["point"])
        if point_id not in point_map:
            print(f"[警告] 点位 {point_id} 在 points.json 中无坐标, 跳过", flush=True)
            continue
        x, y, z = point_map[point_id]
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=SPHERE_RADIUS, location=(x, y, z)
        )
        sphere = bpy.context.active_object
        sphere.name = f"Fire_{point_id}"
        sphere.data.materials.append(material)

        frame = int(event["time"]) * FPS + 1
        sphere.scale = (0.0, 0.0, 0.0)
        if frame > 1:
            sphere.keyframe_insert(data_path="scale", frame=1)
            sphere.keyframe_insert(data_path="scale", frame=frame - 1)
        sphere.scale = (1.0, 1.0, 1.0)
        sphere.keyframe_insert(data_path="scale", frame=frame)


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


def setup_camera(bounds_min: Vector, bounds_max: Vector) -> None:
    """在场景中心正上方放置全局俯视正交相机。"""
    center = (bounds_min + bounds_max) / 2
    span_x = bounds_max.x - bounds_min.x
    span_y = bounds_max.y - bounds_min.y

    cam_data = bpy.data.cameras.new("TopCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(span_x, span_y) * 1.3
    cam_obj = bpy.data.objects.new("TopCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.location = (center.x, center.y, bounds_max.z + 3.0)
    cam_obj.rotation_euler = (0.0, 0.0, 0.0)  # 默认朝 -Z, 即正俯视
    bpy.context.scene.camera = cam_obj


def setup_light() -> None:
    """补充一盏太阳光, 让网格模型可见。"""
    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 10.0))
    sun = bpy.context.active_object
    sun.rotation_euler = (0.6, 0.0, 0.5)
    sun.data.energy = 3.0
    sun.data.use_shadow = False  # 关阴影进一步加速软渲染


def setup_render(output_path: Path, frame_end: int) -> None:
    """Eevee + FFmpeg MP4 输出设置。"""
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

    clear_scene()
    import_mesh(scene_dir / "mesh.obj")
    bounds_min, bounds_max = compute_scene_bounds(point_map)
    fire_material = make_fire_material()
    spawn_fire_balls(point_map, events, fire_material)
    setup_light()
    setup_camera(bounds_min, bounds_max)

    # 最后一个事件后多渲染 1 秒, 便于观察最终蔓延状态
    frame_end = max(int(e["time"]) for e in events) * FPS + FPS
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
