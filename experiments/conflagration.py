"""Connected three-dimensional fire body; R3 tongues are sparse surface detail.

Art-directed, absolute time, no CFD. This module never imports bpy or starts GPU.
"""
import math
import random
from experiments.continuous_field import finite
from render_engine.jobs.operation_logging import traced


def smooth(value):
    v=min(1,max(0,value));return v*v*(3-2*v)


def validate_controls(config):
    p=config['conflagration'];required={'start_s','transition_s','initial_height_m','initial_scale_m','surface_height_m',
        'body_height_m','body_thickness_gain','body_density','body_emission','minimum_visible_emission',
        'density_floor','noise_scale','noise_speed','height_irregularity','detail_count','detail_size_variation',
        'smoke_scatter_density','smoke_absorption_density','smoke_color','smoke_radius_gain','layer_absorption_density',
        'light_volume_gain','fire_light_energy'}
    if set(p)!=required:raise ValueError('Missing/unused conflagration parameter')
    for name in required-{'detail_count','smoke_color'}:
        if not 0<finite(p[name])<=100:raise ValueError('Invalid conflagration control: '+name)
    if type(p['detail_count']) is not int or not 1<=p['detail_count']<=16:raise ValueError('Detail budget must be <=16')
    if not 0<p['density_floor']<1 or not 0<p['height_irregularity']<.7 or not 0<p['detail_size_variation']<.7:raise ValueError('Invalid body/detail variation')
    if len(p['smoke_color'])!=4 or any(not 0<=finite(v)<=1 for v in p['smoke_color']):raise ValueError('Invalid dark smoke color')
    clearance=config['visual']['roof_z_m']-config['seed']['proposed_base_z_m']
    if p['body_height_m']>=clearance-.1 or p['surface_height_m']>=p['initial_height_m']:raise ValueError('Invalid connected body clearance')
    if p['light_volume_gain']>1:raise ValueError('Invalid volume illumination gain')
    return p


def body_height(config,point,seconds,arrival):
    p=validate_controls(config);age=seconds-arrival-config['visual']['smoke_lead_s']
    local=smooth(age/.6);large=smooth((seconds-p['start_s'])/p['transition_s'])
    x,y=point[:2];seed=config['visual']['seed']
    # Incommensurate travelling waves: spatially shared, no patch/grid repetition.
    clock=seconds*p['noise_speed']
    wave=(math.sin(x*.83+y*1.17-clock*.91+seed)+
          .55*math.sin(x*1.91-y*.67+clock*1.37)+
          .27*math.sin(x*3.13+y*2.39-clock*2.03))/1.82
    contour=1-p['height_irregularity']*(.5+.5*wave)/(1+p['body_thickness_gain'])
    height=(p['initial_height_m']*(1-large)+p['body_height_m']*large)*local*contour
    clearance=config['visual']['roof_z_m']-config['seed']['proposed_base_z_m']-.15
    return min(clearance,.015+height)


@traced('room.continuous.visual','connected_conflagration_body')
def body_mesh(field,ring,config,seconds):
    from experiments.visual_state import envelope
    p=validate_controls(config);base=config['seed']['proposed_base_z_m'];lead=config['visual']['smoke_lead_s']
    return envelope(field,ring,seconds-lead,lambda v:base+.01,
                    lambda v:base+body_height(config,v,seconds,v[2]))


def detail_subset(layout,config):
    p=validate_controls(config);rng=random.Random(config['visual']['seed']+6021)
    # Keep a seed-near detail for the small-fire phase; jitter rank of the rest.
    if not layout:return []
    ranked=sorted(((rng.random(),v) for v in layout[1:]),key=lambda v:v[0])
    return [layout[0]]+[v for _,v in ranked[:p['detail_count']-1]]


def detail_variation(config,index):
    p=validate_controls(config);rng=random.Random(config['visual']['seed']+index*104729)
    return {'scale':1+rng.uniform(-p['detail_size_variation'],p['detail_size_variation']),
            'tempo':rng.uniform(.65,1.55),'phase':rng.uniform(0,2*math.pi)}
