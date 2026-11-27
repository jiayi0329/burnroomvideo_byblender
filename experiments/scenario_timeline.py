"""Absolute visual scenario script and CPU footprint measurements; no CFD or GPU."""
import math
from experiments.continuous_field import finite
from experiments.visual_state import geometry,adaptation_state
from render_engine.jobs.operation_logging import traced


def validate_timeline(config):
    script=config['scenario_timeline']
    duration=finite(script['duration_s']);cut=finite(script['camera_cut_s'])
    if not 0<cut<duration<=12 or script['transition']!='cut':raise ValueError('Invalid scenario camera cut')
    if 'late_camera_s' in script and not cut<finite(script['late_camera_s'])<duration:raise ValueError('Invalid third-camera time')
    if config['camera']!='scenario' or 'r3_adaptation' not in config:raise ValueError('Scenario requires the adapted effect')
    samples=script['report_times_s']
    if not 1<=len(samples)<=32 or samples!=sorted(set(samples)) or any(not 0<=finite(t)<=duration for t in samples):raise ValueError('Invalid scenario report times')
    if any(t>duration for t in config['key_times_s']):raise ValueError('Keyframe exceeds scenario duration')
    return script


def camera_at(config,seconds):
    script=validate_timeline(config);t=finite(seconds)
    if not 0<=t<=script['duration_s']:raise ValueError('Time outside scenario')
    if 'late_camera_s' in script and t>=script['late_camera_s']:return 'late'
    return 'low' if t<script['camera_cut_s'] else 'v1_final'


def footprint(payload,seed,base):
    vertices=payload['vertices'];area=0
    for face in payload['faces']:
        # Upper+lower XY projections occur twice; vertical sides have zero area.
        xy=[vertices[i] for i in face]
        area+=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(xy,xy[1:]+xy[:1])))/4
    return {'area_m2':area,'xy_bounds_m':[[min(p[k] for p in vertices),max(p[k] for p in vertices)] for k in (0,1)] if vertices else None,
            'max_distance_from_seed_m':max((math.dist(p[:2],seed) for p in vertices),default=0),
            'max_height_above_base_m':max((p[2]-base for p in vertices),default=0)}


@traced('room.continuous.scenario','evaluate_script')
def scenario_report(config,field,polygon,seed):
    script=validate_timeline(config);base=config['seed']['proposed_base_z_m'];roof=config['visual']['roof_z_m']
    delay=config['visual']['smoke_lead_s']
    cf=config.get('conflagration')
    ground=(cf['start_s']-min(field.arrival_s.values())-delay) if cf else config['r3_adaptation']['ground_duration_s']
    large=cf['transition_s'] if cf else config['r3_adaptation']['large_growth_s']
    samples=[]
    from experiments.visual_state import envelope
    complete=envelope(field,polygon,max(field.arrival_s.values())+1,lambda p:base,lambda p:base+.1)
    denominator=footprint(complete,seed,base)['area_m2']
    if denominator<=0:raise ValueError('Empty allowed visual support')
    layout=None
    if 'accelerated_visual' in config:
        from experiments.visual_composition import patch_layout,composition
        layout=patch_layout(field,config)
    for t in script['report_times_s']:
        meshes=geometry(field,polygon,config,t)
        sample={'seconds':t,'camera':camera_at(config,t),'seed_state':adaptation_state(config,t),
                'regions':{name:footprint(mesh,seed,base) for name,mesh in meshes.items()}}
        for region in sample['regions'].values():region['support_coverage_ratio']=region['area_m2']/denominator
        if layout is not None:
            patches=composition(field,polygon,config,t,layout)
            sample['r3_composition']={'tongue_clusters':sum(p['kind']=='tongue' for p in patches),'smoke_plumes':sum(p['kind']=='plume' for p in patches),
                'max_tongue_height_m':max((v[2]-base for p in patches if p['kind']=='tongue' for v in p['mesh']['vertices']),default=0),
                'not_visible_pixel_coverage':True}
        samples.append(sample)
    events=[{'cell':list(cell),'raw_xy_m':field.xy(cell),'smoke_after_s':arrival,'flame_after_s':arrival+delay,
             'tall_growth_after_s':max(arrival+delay,cf['start_s']) if cf else arrival+delay+ground,
             'tall_growth_complete_s':max(arrival+delay+.6,cf['start_s']+large) if cf else arrival+delay+ground+large}
            for cell,arrival in sorted(field.arrival_s.items(),key=lambda v:(v[1],v[0]))]
    return {'rendered':False,'units':'raw scan XYZ metres, absolute seconds','not_physical_prediction':True,
            'domain':'Room8 boundary-constrained visual support, not verified fuel',
            'allowed_visual_support_area_m2':denominator,'unreachable_cells':len(field.unreachable),
            'timeline':{'duration_s':script['duration_s'],'camera_cut_s':script['camera_cut_s'],'transition':'cut',
                        'roof_raw_z_m':roof,'seed_smoke_after_s':min(field.arrival_s.values()),'seed_fire_after_s':min(field.arrival_s.values())+delay,'seed_tall_growth_after_s':min(field.arrival_s.values())+delay+ground,
                        'seed_tall_growth_complete_s':min(field.arrival_s.values())+delay+ground+large,
                        'ceiling_layer_after_s':min(field.arrival_s.values())+(roof-base)/(config['visual']['rise_m_s']*.85)},
            'samples':samples,'cell_events':events}


def script_text(report):
    t=report['timeline']
    lines=['Room8 假设火灾情景脚本（CPU几何计划，尚未渲染）',
           '所有时间为绝对秒；面积是生成包络的水平投影，不是可见烟浓度边界或真实燃烧面积。',
           '空间范围仅为边界约束的视觉支持域，不代表已核实可燃物。',
           f"0秒无火烟；{t['seed_smoke_after_s']}秒后22号区域出烟；{t['seed_fire_after_s']}秒后出现低位火焰。",
           f"{t['seed_tall_growth_after_s']}秒起种子附近开始长高，{t['seed_tall_growth_complete_s']}秒完成预设大火增长。较晚到达的区域按各自局部年龄增长。",
           f"镜头：0至{t['camera_cut_s']}秒前观察22号起火区域；{t['camera_cut_s']}秒直接切换外部总览；若配置第三机位，则按samples中late阶段切换。不做穿墙运镜。",
           f"假设天花板原始Z={t['roof_raw_z_m']}m，非实测层高。烟层在{t['ceiling_layer_after_s']:.3f}秒之后开始形成。",
           '秒 | 火焰投影m² | 烟柱投影m² | 烟柱最远水平距离m | 顶部烟层投影m² | 镜头']
    for sample in report['samples']:
        r=sample['regions']
        lines.append(f"{sample['seconds']:g} | {r['flame']['area_m2']:.3f} | {r['smoke']['area_m2']:.3f} | {r['smoke']['max_distance_from_seed_m']:.3f} | {r['layer']['area_m2']:.3f} | {sample['camera']}")
    lines.append('逐单元坐标、出烟/起火/抬高时间以及各阶段XY包围盒见同目录scenario-script.json。')
    return '\n'.join(lines)+'\n'
