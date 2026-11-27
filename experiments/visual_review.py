"""Controlled comparison presets and pure CPU orthographic framing."""
from copy import deepcopy
import math


def comparison_config(config,mode):
    if mode not in ('A','B','C','D','E'):raise ValueError('Unknown visual comparison')
    c=deepcopy(config);c['visual']['mode']={'A':'none','B':'flame','C':'smoke','D':'combined','E':'combined'}[mode]
    if mode=='E':c['visual']['roof_mode']='cutaway'
    c['comparison_mode']=mode;c['render_authorized']=False
    return c


def fit_overview(reference,polygon,base,roof,aspect,margin=.07):
    """Keep the reference orientation; translate in the image plane and fit bounds."""
    c=deepcopy(reference);forward=[b-a for a,b in zip(c['position'],c['target'])]
    norm=math.sqrt(sum(v*v for v in forward));forward=[v/norm for v in forward]
    planar=math.hypot(forward[0],forward[1]);right=[forward[1]/planar,-forward[0]/planar,0]
    up=[right[1]*forward[2],-right[0]*forward[2],right[0]*forward[1]-right[1]*forward[0]]
    points=[[x,y,z] for x,y in polygon for z in (base,roof)]
    bounds=[]
    for axis in (right,up):
        values=[sum((p[k]-c['target'][k])*axis[k] for k in range(3)) for p in points]
        bounds.append((min(values),max(values)))
    shift=[sum((b[0]+b[1])/2*axis[k] for b,axis in zip(bounds,(right,up))) for k in range(3)]
    c['target']=[c['target'][k]+shift[k] for k in range(3)];c['position']=[c['position'][k]+shift[k] for k in range(3)]
    c['ortho_scale']=max(bounds[0][1]-bounds[0][0],(bounds[1][1]-bounds[1][0])*aspect)/(1-2*margin)
    c['rotation_world_euler']=[math.atan2(planar,-forward[2]),0,math.atan2(-forward[0],forward[1])]
    c['experimental_reframe']=True;c['coverage_scope']='11-vertex boundary floor/roof envelope, not visibility or pixel coverage'
    return c
