"""PRD 2.2 round-one art/events/quality configuration and deterministic geometry.

Pure stdlib, usable by offline tests and Blender Python; no bpy/DB dependency.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import random


def load_config(path: Path) -> dict:
    config=json.loads(path.read_text(encoding='utf-8'))
    validate(config)
    return config


def validate(c: dict) -> None:
    if set(c)!={'schema_version','art','events','quality'} or c['schema_version']!=1:
        raise ValueError('Expected art/events/quality configuration schema 1')
    def finite(value: object) -> None:
        if isinstance(value,dict):
            for item in value.values():finite(item)
        elif isinstance(value,list):
            for item in value:finite(item)
        elif isinstance(value,(int,float)) and not math.isfinite(value):
            raise ValueError('Nonfinite configuration')
    finite(c)
    art,events,q=c['art'],c['events'],c['quality']; f=art['flame']; s=art['smoke']
    if events['layer_seconds']!=1.5 or events['excluded_devices']!=[32,42]:
        raise ValueError('Round one preserves the existing Room8 BFS policy')
    expected=[[0,0],[.9,.25],[1.9,.6],[3,1],[4.5,.6],[6,.2],[8,0]]
    if events['fire_curve']!=expected:raise ValueError('Round one preserves the existing fire activation envelope')
    if not 3<=f['primary_tongues']<=5 or not 1<=f['secondary_tongues']<=3:
        raise ValueError('Tongue count outside approved range')
    for name in ('primary_tongues','secondary_tongues'):
        if type(f[name]) is not int:raise ValueError('Integer tongue counts required')
    if any(f[k]<=0 for k in ('primary_height','secondary_height','primary_radius','secondary_radius','emission')):
        raise ValueError('Positive flame dimensions/emission required')
    if not 0<=f['lean_degrees']<=20 or not 0<=f['sway_radians']<=.15:
        raise ValueError('Lean/sway outside round-one limits')
    if s['radius']<=0 or s['height']<=0 or s['rise_speed']<=0:
        raise ValueError('Positive smoke dimensions/rise speed required')
    if type(q['fps']) is not int or not 8<=q['fps']<=60:raise ValueError('Invalid FPS')
    if not 0<f['flicker_hz']<q['fps']/2 or not 0<=f['flicker_amplitude']<=.3:
        raise ValueError('Flicker must remain below temporal Nyquist and within amplitude budget')
    if any(type(q[k]) is not int for k in ('tongue_rings','tongue_sides')) or not 2<=q['tongue_rings']<=16 or not 6<=q['tongue_sides']<=24:
        raise ValueError('Tongue mesh budget exceeded')
    if len(q['resolution'])!=2 or any(type(v) is not int or not 128<=v<=1920 for v in q['resolution']):
        raise ValueError('Invalid sample resolution')
    if len(q['sample_times'])!=3 or q['sample_times']!=sorted(set(q['sample_times'])) or not 0<=min(q['sample_times'])<max(q['sample_times'])<=12:
        raise ValueError('Exactly three increasing sample times within 12 seconds required')
    if q['bloom'] is not False:raise ValueError('Bloom is disabled in round one')
    if q['flame_intersection']!='ACCURATE' or not 2*f['primary_tongues']<=q['volume_ray_depth']<=16:
        raise ValueError('Merged tongues need accurate volume intersection and sufficient ray depth')
    if q['volume_tile_size'] not in ('2','4','8','16') or not 8<=q['volume_steps']<=128 or not 8<=q['render_samples']<=128:
        raise ValueError('Invalid render/volume quality budget')
    if not 0<q['volume_start']<q['volume_end']<=100:raise ValueError('Invalid volume range')
    for node in (f,s):
        if not 0<=node['noise_low']<node['noise_high']<=1:raise ValueError('Invalid noise thresholds')
        if not 0<node['density']<=20 or not 0<node['flow_speed']<=5:raise ValueError('Invalid density/flow')
    for curve in (events['fire_curve'],s['density_curve'],s['growth_curve']):
        if any(len(pair)!=2 for pair in curve) or len(curve)<2 or curve[0][0]!=0:
            raise ValueError('Invalid curve')
        if any(a[0]>=b[0] for a,b in zip(curve,curve[1:])) or any(t<0 or v<0 for t,v in curve):
            raise ValueError('Curve times must increase; values must be nonnegative')
    colors=[art['world_color'],*f['colors'],s['dark_color'],s['edge_color']]
    if len(f['colors'])!=4 or any(len(rgb)!=4 or any(not 0<=v<=1 for v in rgb) for rgb in colors):
        raise ValueError('Expected four linear RGBA flame colors and valid RGBA values')
    if len(art['area_lights'])!=3 or any(light['energy']<0 or light['size']<=0 or len(light['offset'])!=3 for light in art['area_lights']):
        raise ValueError('Expected three valid area lights')
    if not -5<=art['exposure']<=3 or not 0<=art['world_strength']<=2:
        raise ValueError('Invalid exposure/world strength')
    if not 0<f['light_distance']<=20 or f['light_energy']<0 or f['light_radius']<=0:
        raise ValueError('Invalid fire light settings')
    if not 12<=art['closeup']['lens']<=100 or len(art['closeup']['offset'])!=3:
        raise ValueError('Invalid closeup lens/offset')
    if any(type(q[k]) is not int for k in ('render_samples','volume_steps','volume_shadow_steps','shadow_rays','shadow_steps','volume_ray_depth')):
        raise ValueError('Integer quality budgets required')
    if not 1<=q['volume_shadow_steps']<=32 or not 1<=q['shadow_rays']<=4 or not 1<=q['shadow_steps']<=16:
        raise ValueError('Shadow sample budget exceeded')


def curve_value(curve: list, seconds: float) -> float:
    if seconds<curve[0][0]:return 0.0
    for (t0,v0),(t1,v1) in zip(curve,curve[1:]):
        if seconds<=t1:
            u=(seconds-t0)/(t1-t0); smooth=u*u*(3-2*u)
            return v0+(v1-v0)*smooth
    return float(curve[-1][1])


def tongue_specs(config: dict, device: int, primary: bool) -> list[dict]:
    f=config['art']['flame']; rng=random.Random(config['art']['seed']+device*7919)
    count=f['primary_tongues'] if primary else f['secondary_tongues']
    result=[]
    for i in range(count):
        angle=2*math.pi*i/count+rng.uniform(-.3,.3)
        height=f['primary_height' if primary else 'secondary_height']*rng.uniform(.72,1.15)
        radius=f['primary_radius' if primary else 'secondary_radius']*rng.uniform(.72,1.15)
        spread=0 if i==0 else radius*.9
        tilt=math.tan(math.radians(f['lean_degrees'])*rng.uniform(.35,1))*height
        result.append({'height':height,'radius':radius,'offset':[math.cos(angle)*spread,math.sin(angle)*spread],
                       'lean':[math.cos(angle+.5)*tilt,math.sin(angle+.5)*tilt], 'phase':rng.uniform(0,2*math.pi)})
    return result


def flame_mesh(specs: list[dict], rings: int, sides: int) -> tuple[list,list]:
    """Closed curved lobes merged into ONE mesh/object, with deterministic irregularity."""
    vertices=[]; faces=[]
    for spec in specs:
        first=len(vertices)
        for ring in range(rings):
            t=ring/(rings-1)
            radius=spec['radius']*(.85+.25*math.sin(t*math.pi))*max(.025,(1-t)**.85)
            for side in range(sides):
                angle=2*math.pi*side/sides
                ripple=1+.13*math.sin(angle*3+t*7+spec['phase'])
                center=[spec['offset'][k]+spec['lean'][k]*t**1.45 for k in (0,1)]
                vertices.append([center[0]+radius*ripple*math.cos(angle),center[1]+radius*ripple*math.sin(angle),t*spec['height']])
        faces.append(tuple(first+i for i in reversed(range(sides))))
        for ring in range(rings-1):
            for side in range(sides):
                a=first+ring*sides+side; b=first+ring*sides+(side+1)%sides
                faces.append((a,b,b+sides,a+sides))
        faces.append(tuple(first+(rings-1)*sides+i for i in range(sides)))
    return vertices,faces
