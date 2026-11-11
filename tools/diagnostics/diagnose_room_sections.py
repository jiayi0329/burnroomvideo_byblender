"""PRD 2.2 / architecture 3.2: diagnostic figures before room clipping.

Reuses raw OBJ coordinates already verified by remote Blender import. No bpy,
PostgreSQL, render, mesh mutation or semantic auto-approval.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import median
import uuid

from render_engine.geometry.room_source_io import confined, inverse_xy, materials, read_obj, sha256
from render_engine.geometry.room_source_inputs import REQUIRED_CHECKS, load_inputs
from tools.diagnostics.room_section_geometry import (continuity, quantile, section_geometry, select_sections,
                                       surface_role, triangles, wall_evidence)

def diagnose(inspection: dict, alignment: dict, mesh: dict, scene: Path, wall_search: float=.6) -> dict:
    if not .05 <= wall_search <= 1.0:
        raise ValueError('Wall search must be 0.05..1.0m; it is not a clipping buffer')
    profile=inspection['height_profile']; samples=profile['samples']; spacing=profile['spacing_m']
    if not samples or len(samples) != profile['sample_count']:
        raise ValueError('Height sample count mismatch')
    for point in samples:
        if not all(math.isfinite(v) for v in point['xy']):raise ValueError('Invalid sample XY')
        for field in ('top','bottom'):
            if point[field] is not None and not math.isfinite(point[field]):raise ValueError('Invalid height')
    polygon=inspection['room_polygon_raw_xy']; tris=triangles(mesh)
    for tri in tris:tri['role']=surface_role(tri,samples,spacing)
    points=json.loads((scene/'points.json').read_text(encoding='utf-8'))
    timeline=json.loads((scene/'timeline.json').read_text(encoding='utf-8'))
    ignition_id=int(timeline['start_point'])
    camera_points=[{'device':int(p['device']),'xy':[p['pose']['translation'][k] for k in ('x','y')],
                    'z':p['pose']['translation']['z'],'ignition':int(p['device'])==ignition_id} for p in points]
    ignition=next((p['xy'] for p in camera_points if p['ignition']),None)
    if ignition is None:raise ValueError('Ignition camera not found')
    selections=select_sections(polygon,samples,ignition,wall_search)
    sections=[section_geometry(tris,s) for s in selections]
    lower=[p['bottom'] for p in samples if p['bottom'] is not None]
    upper=[p['top'] for p in samples if p['top'] is not None]
    if not lower or not upper:raise ValueError('Upper/lower sample evidence insufficient')
    lo,hi=median(lower),median(upper)
    # Probe geometric interior fractions plus camera height; no presumed floor.
    heights=sorted(set([round(lo+(hi-lo)*q,4) for q in (.2,.5,.8)] +
                       [round(median(p['z'] for p in camera_points),4)]))
    other=[{'room_id':r['room_id'],'polygon_raw':inverse_xy(r['polygon'],inspection['coordinates']['raw_to_floor_xy'])}
           for r in alignment['rooms'] if r['valid_candidate'] and r['room_id'] != inspection['room_id']]
    walls=wall_evidence(tris,polygon,heights,other,wall_search)
    gaps=[p['top']-p['bottom'] for p in samples if p['top'] is not None and p['bottom'] is not None]
    continuity_data={field:continuity(samples,field,spacing) for field in ('bottom','top')}
    regions=[]
    camera_low=quantile([p['z'] for p in camera_points],.25)
    camera_high=quantile([p['z'] for p in camera_points],.75)
    for field in ('bottom','top'):
        for i,component in enumerate(continuity_data[field]['components'][:8],1):
            hypothesis=('below_camera_floor_or_platform_candidate' if field=='bottom' and component['z_bin_m']<camera_low
                        else 'overhead_structure_candidate' if field=='top' and component['z_bin_m']>camera_high
                        else 'ambiguous_or_incomplete_envelope')
            regions.append({'envelope':field,'component_id':f'C{i}','z_bin_m':component['z_bin_m'],
                'xy_bounds':component['xy_bounds'],'sample_fraction':component['sample_count']/len(samples),
                'geometric_hypothesis':hypothesis,'physical_label_confirmed':False,
                'alternatives':['floor/platform','furniture surface','ceiling/roof/beam','reconstruction artifact or missing surface']})
    return {'scene_code':inspection['scene_code'],'room_id':inspection['room_id'],
        'status':'manual_review_required','ready_for_cut':False,'coordinate_basis':'raw OBJ; remote Blender world-coordinate checks passed',
        'z_transform_applied':False,'polygon_raw_xy':polygon,'height_samples':samples,'spacing_m':spacing,
        'raw_z_bounds':[inspection['coordinates']['raw_bounds']['min'][2],inspection['coordinates']['raw_bounds']['max'][2]],
        'camera_points':camera_points,'sections':sections,
        'height_clusters':{'bottom':profile['bottom_clusters'],'top':profile['top_clusters']},
        'continuity':continuity_data,'surface_region_hypotheses':regions,
        'incomplete_envelope_locations':[p for p in samples if p['surface_count']<2],
        'envelope_clearance_m':{'p10':quantile(gaps,.1),'median':quantile(gaps,.5),'p90':quantile(gaps,.9),
                              'note':'Geometric envelope gap, not certified room height'},
        'wall_evidence':walls,'wall_search_halfwidth_m':wall_search,'wall_height_levels_m':heights,
        'classification_rules':{'vertical_wall_like':'|normal.z| <= 0.25; no semantic guarantee',
            'horizontal':'|normal.z| >= 0.95; compare centroid to nearby 0.25m envelope samples within 0.08m',
            'interior_horizontal_candidate':'May be furniture, platform or ceiling underside; manual review',
            'pair_separation':'Parallel near-vertical surface hits, 0.02..0.5m apart; no solid-wall proof',
            'wall_alignment':'Normal alignment within 15 degrees; merge hits within 3mm',
            'buffer_candidate':'Nearest/paired outside-surface-hit p95 + 2cm, rounded up to 5mm; only if >=50% probes hit; never applied'},
        'unconfirmed':{'physical_floor_z':None,'physical_ceiling_z':None,'wall_thickness_m':None,'approved_clipping_buffer_m':None},
        'review_required':['核对主要下表面色块：真实地板、台阶/平台、家具底部还是重建几何；不能直接统一找平',
            '核对分区上表面：天花板、屋顶、梁或家具顶部；尤其检查缺少上下闭合表面的位置',
            '逐边复核大偏差、缺失探测和相邻房间侵入；成对平行面间距不能直接认定墙厚',
            '地板、顶部结构、逐边墙体策略需绑定本次输入人工确认，工具不会自动放行裁切'],
        'database_accessed':False,'mesh_cut':False,'video_rendered':False}


def write_findings(path: Path, report: dict) -> None:
    lines=[f"# {report['room_id']} 断面诊断摘要",'',
           '原始 XYZ；只读三角面求交。颜色为几何候选类别，不能直接当成物理语义。ready_for_cut=false。','',
           f"高度样本 {len(report['height_samples'])}；断面 {len(report['sections'])}；墙面探测 Z={report['wall_height_levels_m']}m。",'',
           '| 包络 | 主要高度与采样占比 |','|---|---|']
    for field in ('bottom','top'):
        summary='；'.join(f"{c['z_m']:.2f}m ({c['fraction_of_room_samples']:.1%})" for c in report['height_clusters'][field][:5])
        lines.append(f'| {field} | {summary} |')
    lines += ['', '## 空间连续性','']
    for field in ('bottom','top'):
        data=report['continuity'][field]
        largest=data['components'][0]
        lines.append(f"- {field}：{len(data['components'])}个同高度连通块；最大块 Z≈{largest['z_bin_m']}m、{largest['sample_count']}点；相邻跳变>15cm {data['jumps_over_15cm']}/{data['neighbor_pairs']}。")
    lines += ['', '## 边界证据（不是已确认墙厚或裁切参数）','',
              '| 边 | 长度m | 命中比例 | 最近表面偏差绝对值P90m | 成对表面间距中位数m | 相邻房间侵入采样 |',
              '|---|---:|---:|---:|---:|---|']
    for row in report['wall_evidence']:
        if not row['samples']:
            lines.append(f"| {row['edge_id']} | {row['length_m']:.3f} | 短边不估计 | — | — | — |")
            continue
        lines.append(f"| {row['edge_id']} | {row['length_m']:.3f} | {row['hit_fraction']:.1%} | {row['abs_offset_p90_m']} | {row['paired_surface_separation_median_m']} | {row['adjacent_room_intrusion_samples']} |")
    lines += ['', '## 尚待人工核验','',*[f'- {s}' for s in report['review_required']],
              '', '图片索引见 index.html，精确位置/面编号/交点/候选缓冲及方法阈值见 report.json。']
    path.write_text('\n'.join(lines),encoding='utf-8')


def run(data_root: Path, inspection_path: Path, blender_path: Path, alignment_dir: Path, wall_search: float=.6) -> tuple[dict,Path]:
    inspection,alignment,mesh,context=load_inputs(data_root,inspection_path,blender_path,alignment_dir)
    report=diagnose(inspection,alignment,mesh,context['scene'],wall_search)
    report['blender_evidence']={'version':context['evidence']['blender_version'],'provenance':context['evidence_provenance'],
                                'sha256':sha256(blender_path),'inspection_sha256':sha256(inspection_path)}
    output=context['scene']/'diagnostics/room_sections'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True,exist_ok=False)
    try:
        from tools.diagnostics.room_section_plots import plot_report,write_index
        names=plot_report(output,report,mesh)
        report['source_and_history_unchanged']=all(sha256(p)==digest for p,digest in context['guarded'].items())
        if not report['source_and_history_unchanged']:raise ValueError('Input changed during diagnosis')
        report['input_fingerprints']={str(p):digest for p,digest in context['guarded'].items()}
        report['images']=names
        write_findings(output/'findings.md',report)
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        write_index(output,report,names)
    except Exception as exc:
        (output/'failure.json').write_text(json.dumps({'status':'failed','ready_for_cut':False,'error_type':type(exc).__name__}),encoding='utf-8')
        raise
    return report,output


def main() -> int:
    parser=argparse.ArgumentParser(description='Read-only room section PNG diagnostics; never cut/render video')
    parser.add_argument('--data-root',type=Path,default=Path('data'))
    parser.add_argument('--inspection',type=Path,required=True)
    parser.add_argument('--blender-report',type=Path,required=True)
    parser.add_argument('--alignment-dir',type=Path,required=True)
    parser.add_argument('--wall-search',type=float,default=.6)
    args=parser.parse_args()
    try:
        report,output=run(args.data_root,args.inspection,args.blender_report,args.alignment_dir,args.wall_search)
        print(json.dumps({'status':report['status'],'ready_for_cut':False,'samples':len(report['height_samples']),
            'sections':len(report['sections']),'images':len(report['images']),'output':str(output),
            'source_and_history_unchanged':report['source_and_history_unchanged']},ensure_ascii=False),flush=True)
        return 0
    except (OSError,ValueError,KeyError,TypeError,ImportError) as exc:
        print(f'[room-sections] failed: {type(exc).__name__}: {exc}',flush=True)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
