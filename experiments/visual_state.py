"""CPU geometry for one welded fire body, smoke body and ceiling layer.

No fluid simulation: arrival times and shape motion are artistic controls.
Room clipping applies to every triangle, not only its centre.
"""
import math
import hashlib
import json
from pathlib import Path
from experiments.continuous_field import finite
from render_engine.geometry.room_clip_geometry import halfplane, triangulate
from render_engine.jobs.operation_logging import traced


def adaptation_style(config):
    """Read the frozen R3 style, without changing its approved file or values."""
    path=Path(__file__).resolve().parents[1]/'configs/render/room_fire_round3.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=config['r3_adaptation']['style_sha256']:
        raise ValueError('Frozen R3 adaptation source differs')
    return json.loads(path.read_text(encoding='utf-8'))


def adaptation_state(config,seconds,arrival=None):
    """Absolute local age: smoke first, low advancing fire, then sustained tall fire."""
    if arrival is None:arrival=config.get('accelerated_visual',{}).get('smoke_start_s',0)
    a=config['r3_adaptation'];age=seconds-config['visual']['smoke_lead_s']-arrival
    smooth=lambda x:(lambda v:v*v*(3-2*v))(min(1,max(0,x)))
    large=smooth((age-a['ground_duration_s'])/a['large_growth_s'])
    return {'fire':age>0,'local_fire_age_s':age,'large_fraction':large,
            'ground_fraction':smooth(age/.5),
            'smoke_fraction':min(1,max(0,(seconds-arrival)/config['visual']['growth_s']))}


def sightline_hit(origin,target,faces,cut_z=float('inf'),endpoint_clearance=.025):
    """CPU ray/triangle visibility; opaque geometric gate, not a shader test.

    Ignore contacts within 25mm of the target, not obstacles near the camera.
    The display height cut removes the same portion as Blender's below().
    """
    def sub(a,b):return [a[k]-b[k] for k in range(3)]
    def dot(a,b):return sum(a[k]*b[k] for k in range(3))
    def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    direction=sub(target,origin);length=math.sqrt(dot(direction,direction))
    if length<.1:raise ValueError('Camera too close to inspection target')
    nearest=None
    for index,face in enumerate(faces):
        a,b,c=[v[:3] for v in face['corners']]
        # Conservative segment bounding box rejection.
        if any(max(a[k],b[k],c[k])<min(origin[k],target[k])-1e-9 or min(a[k],b[k],c[k])>max(origin[k],target[k])+1e-9 for k in range(3)):continue
        e1,e2=sub(b,a),sub(c,a);p=cross(direction,e2);det=dot(e1,p)
        if abs(det)<1e-12:continue
        s=sub(origin,a);u=dot(s,p)/det
        if not 0<=u<=1:continue
        q=cross(s,e1);v=dot(direction,q)/det
        if v<0 or u+v>1:continue
        t=dot(e2,q)/det;distance=t*length
        if not 0<distance<length-endpoint_clearance:continue
        point=[origin[k]+t*direction[k] for k in range(3)]
        if point[2]>cut_z+1e-9:continue
        if nearest is None or distance<nearest['distance_m']:
            nearest={'face_index':index,'distance_m':distance,'point_raw_xyz':point}
    return nearest


def inspection_targets(config,seed,ring=None):
    base=config['seed']['proposed_base_z_m'];roof=config['visual']['roof_z_m']
    targets={'seed_base':[seed[0],seed[1],base+.08],
            'initial_flame':[seed[0],seed[1],base+.65],
            'flame_east':[seed[0]+.3,seed[1],base+.3],
            'flame_south':[seed[0],seed[1]-.3,base+.3],
            'early_smoke':[seed[0],seed[1],base+1.2],
            'upper_smoke':[seed[0],seed[1],roof-.15],
            'roof_near_seed':[seed[0],seed[1],roof]}
    if ring and config.get('inspect_roof_outline'):
        nearest=[]
        for a,b in zip(ring,ring[1:]+ring[:1]):
            dx,dy=b[0]-a[0],b[1]-a[1];squared=dx*dx+dy*dy
            if squared<1e-15:continue
            t=max(0,min(1,((seed[0]-a[0])*dx+(seed[1]-a[1])*dy)/squared))
            point=[a[0]+t*dx,a[1]+t*dy,roof]
            nearest.append((sum((point[k]-seed[k])**2 for k in range(2)),point))
        targets['roof_outline']=min(nearest,key=lambda p:p[0])[1]
    return targets


@traced('room.continuous.camera','view_gate')
def camera_view_audit(config,seed,ring,faces):
    """Reject occluded or clipped experimental views before GPU launch."""
    from experiments.continuous_field import inside
    spec=config['cameras'][config['camera']];base=config['seed']['proposed_base_z_m']
    if not 1<=finite(spec['lens'])<=200:raise ValueError('Invalid inspection lens')
    origin=[seed[0]+spec['offset'][0],seed[1]+spec['offset'][1],base+spec['offset'][2]]
    target=[seed[0],seed[1],base+spec['target_height']]
    if not inside(origin[:2],ring):raise ValueError('Inspection camera is outside Room8 boundary')
    forward=[target[k]-origin[k] for k in range(3)];length=math.sqrt(sum(v*v for v in forward));forward=[v/length for v in forward]
    horizontal=math.hypot(forward[0],forward[1])
    if horizontal<1e-6:raise ValueError('Low camera must have a horizontal viewing direction')
    right=[forward[1]/horizontal,-forward[0]/horizontal,0]
    up=[right[1]*forward[2],-right[0]*forward[2],right[0]*forward[1]-right[1]*forward[0]]
    aspect=config['resolution'][0]/config['resolution'][1]
    # Adapter explicitly sets a 36mm horizontal-fit sensor.
    tangent_x=36/(2*spec['lens']);tangent_y=tangent_x/aspect
    records={}
    for name,point in inspection_targets(config,seed,ring).items():
        delta=[point[k]-origin[k] for k in range(3)];depth=sum(delta[k]*forward[k] for k in range(3))
        if depth<=.03:raise ValueError('Inspection target behind camera: '+name)
        ndc=[sum(delta[k]*axis[k] for k in range(3))/(depth*tangent) for axis,tangent in ((right,tangent_x),(up,tangent_y))]
        if max(abs(v) for v in ndc)>.92:raise ValueError('Inspection target outside safe image margin: '+name)
        hit=sightline_hit(origin,point,faces,config['display_cut_z_m'])
        if hit:raise ValueError('Scan blocks inspection target: '+name+' at '+str(round(hit['distance_m'],3))+'m')
        records[name]={'ndc':ndc,'clear':True}
    return {'camera_raw_xyz':origin,'target_raw_xyz':target,'targets':records,'candidate_geometry_only':True}


def temporal_clip(vertices, threshold):
    result=[]
    previous=vertices[-1]
    for current in vertices:
        a,b=previous[2]-threshold,current[2]-threshold
        if (a<0)!=(b<0):
            weight=a/(a-b)
            result.append([previous[k]+weight*(current[k]-previous[k]) for k in range(5)])
        if b<0:result.append(current)
        previous=current
    return result


def validate(config):
    e=config['visual']; base=finite(config['seed']['proposed_base_z_m']);roof=finite(e['roof_z_m'])
    controls=('smoke_lead_s','rise_m_s','layer_spread_m_s','layer_thickness_m','growth_s')
    if 'r3_adaptation' not in config:controls+=('flame_height_m','smoke_density','layer_density','noise_scale')
    for key in controls:
        if not 0<finite(e[key])<=100:raise ValueError('Invalid visual control')
    if roof-base<.3 or e['layer_thickness_m']>=roof-base:raise ValueError('Invalid roof clearance')
    if e['roof_mode'] not in ('full','cutaway','outline'):raise ValueError('Invalid roof mode')
    if e['mode'] not in ('none','smoke','combined','flame'):raise ValueError('Invalid comparison mode')
    if 'r3_adaptation' not in config:
        if any(not 0<=finite(v)<=1 for v in e['smoke_color']) or len(e['smoke_color'])!=4:raise ValueError('Invalid smoke color')
        for key in ('flame_density','emission','light_energy','morph_hz'):
            if not 0<=finite(e[key])<=1000:raise ValueError('Invalid material or light control')
    if type(e['seed']) is not int or not 0<=e['seed']<2**32:raise ValueError('Invalid noise seed')
    if not -2<=finite(config['exposure'])<=2 or not base<finite(config['display_cut_z_m'])<=roof:raise ValueError('Invalid display controls')
    times=config['key_times_s']
    if not 1<=len(times)<=6 or any(not 0<=finite(t)<=12 for t in times) or list(times)!=sorted(set(times)):raise ValueError('At most six unique ordered keyframes in 0..12s')
    if len(config['resolution'])!=2 or any(type(v) is not int or not 2<=v<=limit for v,limit in zip(config['resolution'],(960,540))):raise ValueError('Keyframe resolution budget exceeded')
    if type(config['fps']) is not int or not 2<=config['fps']<=24:raise ValueError('Invalid FPS')
    if 'preview_background' in config:
        b=config['preview_background']
        if len(b['color'])!=4 or any(not 0<=finite(v)<=1 for v in b['color']) or not 0<=finite(b['strength'])<=2:raise ValueError('Invalid preview background')
    if 'r3_adaptation' in config:
        a=config['r3_adaptation'];style=adaptation_style(config)
        for name in ('ground_height_m','ground_duration_s','large_growth_s','smoke_density_gain','layer_density_gain'):
            if not 0<finite(a[name])<=10:raise ValueError('Invalid R3 adaptation control')
        if a['ground_height_m']>=style['art']['flame']['primary_height']:raise ValueError('Low fire must precede tall fire')
    return base,roof


def mesh_components(payload):
    """Edge-connected closed-shell count; reject cracks/nonmanifold output."""
    edges={}
    for index,face in enumerate(payload['faces']):
        if len(set(face))!=len(face):raise ValueError('Degenerate face')
        for a,b in zip(face,face[1:]+face[:1]):edges.setdefault(tuple(sorted((a,b))),[]).append(index)
    if any(len(v)!=2 for v in edges.values()):raise ValueError('Envelope is not closed')
    neighbors={i:set() for i in range(len(payload['faces']))}
    for a,b in edges.values():neighbors[a].add(b);neighbors[b].add(a)
    remaining=set(neighbors);count=0
    while remaining:
        pending=[remaining.pop()];count+=1
        while pending:
            for other in neighbors[pending.pop()]&remaining:remaining.remove(other);pending.append(other)
    return count


def envelope(field, ring, threshold, bottom, top):
    """Triangulated continuous arrival interpolation, welded closed volume.

    Quads need four reachable, unblocked vertices. Narrow one-node corridors
    may be conservatively omitted; visual validation remains necessary.
    """
    vertices=[];faces=[];lookup={};edges={};room=triangulate(ring)
    def vertex(p,z):
        key=(round(p[0],9),round(p[1],9),round(z,9))
        if key not in lookup:lookup[key]=len(vertices);vertices.append(tuple(key))
        return lookup[key]
    for i,j in sorted(field.arrival_s):
        cells=((i,j),(i+1,j),(i+1,j+1),(i,j+1))
        if not all(c in field.arrival_s for c in cells):continue
        for ids in ((0,1,2),(0,2,3)):
            raw=[[*field.xy(cells[k]),field.arrival_s[cells[k]],0.,0.] for k in ids]
            for triangle in room:
                clipped=raw
                for k in range(3):clipped=halfplane(clipped,triangle[k],triangle[(k+1)%3])
                if len(clipped)<3:continue
                clipped=temporal_clip(clipped,threshold)
                clean=[]
                for p in clipped:
                    if not clean or math.dist(p[:2],clean[-1][:2])>1e-10:clean.append(p)
                if len(clean)>1 and math.dist(clean[0][:2],clean[-1][:2])<=1e-10:clean.pop()
                clipped=clean
                if len(clipped)<3:continue
                area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(clipped,clipped[1:]+clipped[:1]))
                if abs(area)<1e-12:continue
                upper=[vertex(p,top(p)) for p in clipped];lower=[vertex(p,bottom(p)) for p in clipped]
                for k in range(1,len(upper)-1):
                    faces.extend([(upper[0],upper[k],upper[k+1]),(lower[0],lower[k+1],lower[k])])
                for k,a in enumerate(upper):
                    b=upper[(k+1)%len(upper)];key=tuple(sorted((a,b)))
                    if a!=b:edges.setdefault(key,[]).append((a,b,lower[k],lower[(k+1)%len(lower)]))
    for edge in edges.values():
        if len(edge)==1:
            a,b,lo_a,lo_b=edge[0];faces.append((a,lo_a,lo_b,b))
        elif len(edge)>2:raise ValueError('Nonmanifold upper surface')
    return {'vertices':vertices,'faces':faces}


@traced('room.continuous.visual', 'absolute_geometry')
def geometry(field, ring, config, seconds):
    t=finite(seconds)
    if t<0:raise ValueError('Negative time')
    base,roof=validate(config);e=config['visual'];delay=e['smoke_lead_s']
    empty=lambda:{'vertices':[],'faces':[]}
    result={'flame':empty(),'smoke':empty(),'layer':empty()}
    if e['mode']=='none':return result
    def growth(age):return min(1.,max(0.,age)/e['growth_s'])
    def flame_top(p):
        noise=.7+.3*math.sin(p[0]*1.7+p[1]*2.3+t*2.1+e['seed'])**2
        return min(roof-.01,base+.003+e['flame_height_m']*growth(t-delay-p[2])*noise)
    smoke_top=lambda p:min(roof-.005,base+.005+e['rise_m_s']*max(0.,t-p[2]))
    if 'r3_adaptation' in config:
        from render_engine.effects.room_fire_config import tongue_specs
        style=adaptation_style(config);a=config['r3_adaptation'];f=style['art']['flame'];s=style['art']['smoke']
        tongues=tongue_specs(style,22,True)
        # A continuous, room-clipped height field, not one new flame per grid cell.
        seed_cell=min(field.arrival_s,key=field.arrival_s.get);seed=field.xy(seed_cell)
        def flame_top(p):
            state=adaptation_state(config,t,p[2]);x,y=p[0]-seed[0],p[1]-seed[1]
            lobes=max(math.exp(-((x-v['offset'][0])**2+(y-v['offset'][1])**2)/(2*(v['radius']*1.4)**2))*min(1,v['height']/f['primary_height']) for v in tongues)
            waves=sum((.5+.5*math.sin((x*math.cos(v['phase'])+y*math.sin(v['phase']))/(v['radius']*2)+v['phase']+t*f['morph_speed']))**5 for v in tongues)/len(tongues)
            contour=max(lobes,waves)*(.9+.1*math.sin(t*f['flicker_hz']*2*math.pi+x+y))
            height=(a['ground_height_m']*state['ground_fraction']+state['large_fraction']*(f['primary_height']-a['ground_height_m']))*(.12+.88*contour)
            return min(roof-.02,base+.004+height)
        def smoke_top(p):
            age=max(0,t-p[2]);curl=.85+.15*math.sin(p[0]*3+p[1]*2+t*s['morph_speed'])
            return min(roof-.005,base+.005+e['rise_m_s']*age*curl)
    if 'accelerated_visual' in config:
        def flame_top(p):return base+.004+.16*adaptation_state(config,t,p[2])['ground_fraction']
    if e['mode'] in ('combined','flame'):
        result['flame']=envelope(field,ring,t-delay,lambda p:base,flame_top)
    result['smoke']=envelope(field,ring,t,lambda p:base+.002,smoke_top)
    ceiling_delay=(roof-base)/(e['rise_m_s']*(.85 if 'r3_adaptation' in config else 1))+config.get('accelerated_visual',{}).get('smoke_start_s',0)
    scale=config['field']['visual_speed_m_s']/e['layer_spread_m_s']
    start=config.get('accelerated_visual',{}).get('smoke_start_s',0)
    # Re-express the common geodesic arrival field at the ceiling spread speed.
    layer_times=({c:ceiling_delay+d/e['layer_spread_m_s'] for c,d in field.distance_m.items()} if field.distance_m is not None else
                 {c:ceiling_delay+(a-start)*scale for c,a in field.arrival_s.items()})
    layer_field=type(field)(field.origin,field.spacing_m,field.allowed,layer_times,field.parent)
    result['layer']=envelope(layer_field,ring,t,
                            lambda p:roof-.005-.003-e['layer_thickness_m']*growth(t-p[2]),lambda p:roof-.005)
    for payload in result.values():
        if mesh_components(payload)>1:raise ValueError('Disconnected visual shell; refine domain/grid before rendering')
    if e['mode']=='flame':result['smoke']=empty();result['layer']=empty()
    return result


def roof_mesh(ring,z,mode):
    """Display only: changing mode never changes smoke constraints."""
    if mode=='outline':return {'vertices':[(x,y,z) for x,y in ring], 'faces':[], 'edges':[(i,(i+1)%len(ring)) for i in range(len(ring))]}
    if mode not in ('full','cutaway'):raise ValueError('Invalid roof mode')
    faces=[];vertices=[];mid=(min(p[0] for p in ring)+max(p[0] for p in ring))/2
    for triangle in triangulate(ring):
        p=[[x,y,z,0,0] for x,y in triangle]
        if mode=='cutaway':p=halfplane(p,[mid,1],[mid,0]) # retain x >= mid
        if len(p)<3:continue
        start=len(vertices);vertices.extend(tuple(v[:3]) for v in p)
        faces.extend((start,start+k,start+k+1) for k in range(1,len(p)-1))
    return {'vertices':vertices,'faces':faces,'edges':[]}
