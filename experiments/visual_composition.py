"""R3 tongue/plume meshes on irregular coarse patches, over a continuous base.

No scan-point igniters; no GPU/API imports. Patch footprints must lie inside the
same active support as the continuous front. All values are visual hypotheses.
"""
import math
import random
from experiments.continuous_field import inside,finite,segment_inside
from experiments.visual_state import adaptation_style,adaptation_state
from render_engine.effects.room_fire_config import tongue_specs,flame_mesh,plume_mesh
from render_engine.jobs.operation_logging import traced


def local_arrival(field,point):
    x=(point[0]-field.origin[0])/field.spacing_m;y=(point[1]-field.origin[1])/field.spacing_m
    i,j=math.floor(x),math.floor(y);u,v=x-i,y-j
    # Same diagonal as visual_state.envelope; missing quads are conservatively excluded.
    cells=((i,j),(i+1,j),(i+1,j+1),(i,j+1))
    if not all(c in field.arrival_s for c in cells):return None
    a,b,c,d=[field.arrival_s[k] for k in cells]
    return a*(1-u)+b*(u-v)+c*v if u>=v else a*(1-v)+c*u+d*(v-u)


@traced('room.continuous.visual','coarse_patch_layout')
def patch_layout(field,config):
    spacing=finite(config['accelerated_visual']['patch_spacing_m'])
    a=config['accelerated_visual']
    if type(a['max_patches']) is not int or not 1<=a['max_patches']<=100:raise ValueError('Invalid patch count budget')
    if 'conflagration' not in config:
        if not .3<=finite(a['early_tongue_height_m'])<=1.2 or not .5<=finite(a['tongue_width_gain'])<=1.5 or not .05<=finite(a['plume_density_gain'])<=1:raise ValueError('Invalid R3 patch controls')
    if not .45<=spacing<=1.5:raise ValueError('Patch spacing outside visual budget')
    rng=random.Random(config['visual']['seed']);candidates=[]
    for i,j in sorted(field.arrival_s):
        cells=((i,j),(i+1,j),(i+1,j+1),(i,j+1))
        if not all(c in field.arrival_s for c in cells):continue
        xy=[field.origin[0]+(i+.5)*field.spacing_m,field.origin[1]+(j+.5)*field.spacing_m]
        candidates.append((max(field.arrival_s[c] for c in cells),rng.random(),xy))
    chosen=[]
    for arrival,rank,xy in sorted(candidates,key=lambda v:(round(v[0],1),v[1])):
        if all(math.dist(xy,p['xy'])>=spacing for p in chosen):
            chosen.append({'id':len(chosen),'xy':xy,'smoke_after_s':arrival,'fire_after_s':arrival+config['visual']['smoke_lead_s']})
    if len(chosen)>config['accelerated_visual']['max_patches']:raise ValueError('Patch object budget exceeded')
    if 'conflagration' in config:
        from experiments.conflagration import detail_subset
        chosen=detail_subset(chosen,config)
    return chosen


def fit_mesh(vertices,faces,xy,base,height,field,ring,seconds,delay):
    """Shrink XY only until the entire R3 footprint is inside active support.

    Height stays independently controlled. Linear XY bounds make accepted faces
    stay within their active triangle patch; edge midpoints additionally checked.
    """
    for scale in (1,.8,.6,.4,.25,.12,.06,.03):
        result=[(xy[0]+p[0]*scale,xy[1]+p[1]*scale,base+p[2]*height) for p in vertices]
        points=[p[:2] for p in result]
        points.extend(((result[f[k]][0]+result[f[(k+1)%len(f)]][0])/2,(result[f[k]][1]+result[f[(k+1)%len(f)]][1])/2) for f in faces for k in range(len(f)))
        if all(inside(p,ring) and (a:=local_arrival(field,p)) is not None and a+delay<seconds for p in points):
            if all(segment_inside(result[f[k]][:2],result[f[(k+1)%len(f)]][:2],ring) for f in faces for k in range(len(f))):
                return {'vertices':result,'faces':faces,'xy_fit_scale':scale}
    return None


@traced('room.continuous.visual','r3_patch_geometry')
def composition(field,ring,config,seconds,layout):
    style=adaptation_style(config);f=style['art']['flame'];a=config['accelerated_visual']
    base=config['seed']['proposed_base_z_m'];roof=config['visual']['roof_z_m'];lead=config['visual']['smoke_lead_s']
    result=[]
    for p in layout:
        age=seconds-p['fire_after_s'];smoke_age=seconds-p['smoke_after_s']
        if smoke_age<=0:continue
        phase=p['id']*.713
        flame_base=base
        variation=None
        if 'conflagration' in config:
            from experiments.conflagration import body_height,detail_variation,smooth
            cf=config['conflagration'];variation=detail_variation(config,p['id'])
            phase=variation['phase']
        if age>0 and config['visual']['mode'] in ('combined','flame'):
            state=adaptation_state(config,seconds,p['smoke_after_s'])
            if not variation:h=a['early_tongue_height_m']*state['ground_fraction']+(roof-base-.12-a['early_tongue_height_m'])*state['large_fraction']
            if variation:
                large=smooth((seconds-cf['start_s'])/cf['transition_s'])
                surface=body_height(config,p['xy'],seconds,p['smoke_after_s'])
                flame_base=base+surface*.55*large
                top=min(roof-.12,base+surface+(.25+.4*large)*variation['scale']*state['ground_fraction'])
                h=max(.02,top-flame_base)
            specs=tongue_specs(style,22000+p['id'],True)
            # Actual R3 curved closed tongues, with absolute-time sway, not a top-height envelope.
            for v in specs:
                v['lean']=[q+.06*math.sin(seconds*3*(variation['tempo'] if variation else 1)+phase+k) for k,q in enumerate(v['lean'])]
                v['radius']*=a['tongue_width_gain'] if not variation else variation['scale']*cf['initial_scale_m']/f['primary_radius']
            vertices,faces=flame_mesh(specs,style['quality']['tongue_rings'],style['quality']['tongue_sides'])
            maximum=max(v[2] for v in vertices)
            mesh=fit_mesh(vertices,faces,p['xy'],flame_base,max(.02,h)/maximum,field,ring,seconds,lead)
            if mesh:result.append({'name':'tongue-'+str(p['id']),'kind':'tongue','local_age_s':age,'mesh':mesh,'patch':p['id']})
        if config['visual']['mode'] in ('combined','smoke') and p['id']%2==0:
            vertices,faces=plume_mesh(style,phase+seconds*style['art']['smoke']['morph_speed'])
            radius=min(.7,.16+.12*smoke_age);height=min(roof-base-.03,config['visual']['rise_m_s']*smoke_age)
            if variation:radius*=cf['smoke_radius_gain']
            vertices=[[v[0]*radius,v[1]*radius,v[2]] for v in vertices]
            mesh=fit_mesh(vertices,faces,p['xy'],base+.015,max(.02,height),field,ring,seconds,0)
            if mesh:result.append({'name':'plume-'+str(p['id']),'kind':'plume','local_age_s':smoke_age,'mesh':mesh,'patch':p['id']})
    return result
