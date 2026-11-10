"""离线校验户型/OBJ/相机坐标，生成房间归属草案和交互叠加图。

只读取显式指定的成功探测目录；不调用 API、Blender 或渲染服务。
通过完整安装包运行，保留app模块兼容路径；不再单独复制CLI到stdin执行。
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import uuid

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from render_engine.geometry.floorplan_alignment import (
    Point, MIN_AREA, MIN_WIDTH, BOUNDARY_TOLERANCE,
    finite, area, edges, segment_distance, cross, segments_intersect,
    self_intersects, contains, parse_rooms, classify, room_overlap_candidates,
    apply_transform, axis_candidates, read_mesh, rank_candidates,
    resolve_source, sha256, analyze,
)


def write_overlay(path: Path, rooms: list[dict], mesh: list[Point], cameras: list[dict], candidates: list[dict], selected: str, ignition: int) -> None:
    """无需外部资源的本地 HTML/SVG 校验图，支持切换轴向假设。"""
    payload = json.dumps({
        "rooms": rooms, "mesh": mesh[::max(1, math.ceil(len(mesh) / 4000))],
        "cameras": cameras, "candidates": candidates, "selected": selected, "ignition": ignition,
    }, ensure_ascii=True).replace("<", "\\u003c")
    template = '''<!doctype html><meta charset="utf-8"><title>户型坐标校验</title>
<style>body{font:16px system-ui;margin:24px;background:#f8fafc;color:#172033}svg{background:white;border:1px solid #ccd4df;width:100%;max-width:1200px}label{margin-right:20px}p{max-width:1100px;line-height:1.6}select{padding:7px}</style>
<h2>户型 / OBJ 俯视 / 相机点位校验</h2>
<p>这是坐标假设的比较图，尚未确认配准，也未裁切。黑色为相机点编号，红色为选中的起火拍摄点，灰色为抽样 OBJ 顶点；虚线为待复核房间。下拉选项不代表配准已通过。坐标使用原始模型 XY，不使用 F8 居中偏移。</p>
<label>原始模型 XY → 户型 XY <select id="candidate"></select></label>
<label><input id="mesh" type="checkbox" checked>显示模型投影</label>
<label><input id="labels" type="checkbox" checked>显示点位编号</label>
<p id="stats"></p><svg id="plot" viewBox="0 0 1200 850" role="img" aria-label="户型与模型叠加图"></svg>
<p>核对墙面是否重合、相机点是否位于实际拍摄房间、门口点是否存在歧义。相机所在房间不等同于照片中烧痕所在房间。图中不自动推断层高。</p>
<script>const data=__DATA__;
const select=document.getElementById('candidate'),svg=document.getElementById('plot');
for(const c of data.candidates){const o=document.createElement('option');o.value=c.id;o.textContent=c.id+' (墙点到抽样模型均距 '+c.wall_to_sampled_mesh_mean_m.toFixed(3)+'m)';select.append(o)}select.value=data.selected;
function node(tag,attrs,text){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;svg.append(n);return n}
function draw(){svg.replaceChildren();const c=data.candidates.find(x=>x.id===select.value),[a,b,d,e,tx,ty]=c.matrix;
const trans=p=>[a*p[0]+b*p[1]+tx,d*p[0]+e*p[1]+ty];
const cloud=data.mesh.map(trans),cams=data.cameras.map(p=>({...p,p:trans(p.xy)}));
const all=[...cloud,...data.rooms.flatMap(r=>r.polygon),...cams.map(p=>p.p)];
let minX=Math.min(...all.map(p=>p[0])),maxX=Math.max(...all.map(p=>p[0])),minY=Math.min(...all.map(p=>p[1])),maxY=Math.max(...all.map(p=>p[1]));
const scale=Math.min(1080/Math.max(maxX-minX,1),730/Math.max(maxY-minY,1));
const xy=p=>[60+(p[0]-minX)*scale,790-(p[1]-minY)*scale];
if(document.getElementById('mesh').checked)for(const p of cloud){const [x,y]=xy(p);node('circle',{cx:x,cy:y,r:1.2,fill:'#94a3b8',opacity:.4})}
const colors=['#2563eb','#059669','#9333ea','#d97706','#0891b2','#be185d'];
data.rooms.forEach((r,i)=>{if(!r.polygon.length)return;const color=r.valid_candidate?colors[i%colors.length]:'#dc2626';node('polygon',{points:r.polygon.map(p=>xy(p).join(',')).join(' '),fill:color,'fill-opacity':.08,stroke:color,'stroke-width':2,'stroke-dasharray':r.valid_candidate?'none':'6 4'});const avg=r.polygon.reduce((s,p)=>[s[0]+p[0]/r.polygon.length,s[1]+p[1]/r.polygon.length],[0,0]);const [x,y]=xy(avg);node('text',{x,y,fill:color,'font-size':14},r.room_id+' '+r.label+' '+r.area_m2.toFixed(2)+'m²')});
for(const c of cams){const [x,y]=xy(c.p),hot=c.device===data.ignition;const circle=node('circle',{cx:x,cy:y,r:hot?7:4,fill:hot?'#dc2626':'#111827',stroke:'white','stroke-width':1.5});const title=document.createElementNS(svg.namespaceURI,'title');title.textContent='device='+c.device+' floor XY='+c.p.map(v=>v.toFixed(3)).join(',');circle.append(title);if(document.getElementById('labels').checked)node('text',{x:x+8,y:y-6,fill:hot?'#dc2626':'#111827','font-size':13,'font-weight':hot?'bold':'normal'},String(c.device))}
node('text',{x:60,y:830,fill:'#334155','font-size':13},'X →，Y ↑；单位 m；红点 '+data.ignition+' 是起火拍摄点候选');
document.getElementById('stats').textContent='当前假设 '+c.id+'；模型抽样误差仅供比较，不是标定残差。相机判断：'+JSON.stringify(c.camera_status_counts)}
select.onchange=draw;document.getElementById('mesh').onchange=draw;document.getElementById('labels').onchange=draw;draw();</script>'''
    path.write_text(template.replace("__DATA__", payload), encoding="utf-8")


def write_outputs(output_dir: Path, report: dict, chart: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "alignment_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "point_rooms.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        columns = ["device", "status", "room_id", "floor_x", "floor_y", "nearest_boundary_m", "ignition", "in_timeline", "inside_rooms", "near_boundary_rooms"]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in report["memberships_provisional"]:
            writer.writerow({
                **{key: row[key] for key in columns if key in row},
                "floor_x": row["floor_xy"][0], "floor_y": row["floor_xy"][1],
                "inside_rooms": ";".join(row["inside_rooms"]), "near_boundary_rooms": ";".join(row["near_boundary_rooms"]),
            })
    write_overlay(output_dir / "overlay.html", **chart)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze server floorplan and point membership without rendering")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("/app/data"))
    parser.add_argument("--probe-dir", type=Path, required=True, help="Successful server probe directory, not the local offline report")
    parser.add_argument("--floor-index", type=int, default=0)
    parser.add_argument("--transform", choices=[c["id"] for c in axis_candidates()], help="Explicit hypothesis for review; does not confirm alignment")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.scene):
        parser.error("Invalid scene code")
    try:
        scene_dir = args.data_root / args.scene
        report, chart = analyze(scene_dir, args.probe_dir, args.floor_index, args.transform)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        output_dir = scene_dir / "diagnostics" / "alignment" / run_id
        write_outputs(output_dir, report, chart)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"[floorplan-align] failed: {type(exc).__name__}: {exc}", flush=True)
        return 1
    valid = [room["room_id"] for room in report["rooms"] if room["valid_candidate"]]
    invalid = [{"room_id": room["room_id"], "problems": room["problems"]} for room in report["rooms"] if not room["valid_candidate"]]
    print(json.dumps({
        "status": report["status"], "floorplan_ready_for_crop": False,
        "transform_hypothesis": report["selected_transform"]["id"],
        "valid_room_candidates": valid, "flagged_rooms": invalid,
        "room_overlap_candidates": report["room_overlap_candidates"],
        "ignition_candidate": report["ignition_candidate"],
        "target_room_event_devices_provisional": report["target_room_event_devices_provisional"],
        "output_dir": str(output_dir),
    }, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
