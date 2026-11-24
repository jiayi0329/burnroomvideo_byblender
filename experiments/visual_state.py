"""CPU geometry for one welded fire body, smoke body and ceiling layer.

No fluid simulation: arrival times and shape motion are artistic controls.
Room clipping applies to every triangle, not only its centre.
"""
import math
from experiments.continuous_field import finite
from render_engine.geometry.room_clip_geometry import halfplane, triangulate
from render_engine.jobs.operation_logging import traced


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
    for key in ('smoke_lead_s','rise_m_s','layer_spread_m_s','layer_thickness_m','flame_height_m','growth_s','smoke_density','layer_density','noise_scale'):
        if not 0<finite(e[key])<=100:raise ValueError('Invalid visual control')
    if roof-base<.3 or e['layer_thickness_m']>=roof-base:raise ValueError('Invalid roof clearance')
    if e['roof_mode'] not in ('full','cutaway','outline'):raise ValueError('Invalid roof mode')
    if e['mode'] not in ('none','smoke','combined'):raise ValueError('Invalid comparison mode')
    if any(not 0<=finite(v)<=1 for v in e['smoke_color'] ) or len(e['smoke_color'])!=4:raise ValueError('Invalid smoke color')
    for key in ('flame_density','emission','light_energy','morph_hz'):
        if not 0<=finite(e[key])<=1000:raise ValueError('Invalid material or light control')
    if type(e['seed']) is not int or not 0<=e['seed']<2**32:raise ValueError('Invalid noise seed')
    if not -2<=finite(config['exposure'])<=2 or not base<finite(config['display_cut_z_m'])<=roof:raise ValueError('Invalid display controls')
    times=config['key_times_s']
    if not 1<=len(times)<=6 or any(not 0<=finite(t)<=12 for t in times) or list(times)!=sorted(set(times)):raise ValueError('At most six unique ordered keyframes in 0..12s')
    if len(config['resolution'])!=2 or any(type(v) is not int or not 2<=v<=limit for v,limit in zip(config['resolution'],(960,540))):raise ValueError('Keyframe resolution budget exceeded')
    if type(config['fps']) is not int or not 2<=config['fps']<=24:raise ValueError('Invalid FPS')
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
    if e['mode']=='combined':
        result['flame']=envelope(field,ring,t-delay,lambda p:base,flame_top)
    result['smoke']=envelope(field,ring,t,lambda p:base+.002,
                            lambda p:min(roof-.005,base+.005+e['rise_m_s']*max(0.,t-p[2])))
    ceiling_delay=(roof-base)/e['rise_m_s']
    scale=config['field']['visual_speed_m_s']/e['layer_spread_m_s']
    # Re-express the common geodesic arrival field at the ceiling spread speed.
    layer_field=type(field)(field.origin,field.spacing_m,field.allowed,
                           {c:ceiling_delay+a*scale for c,a in field.arrival_s.items()},field.parent)
    result['layer']=envelope(layer_field,ring,t,
                            lambda p:roof-.005-.003-e['layer_thickness_m']*growth(t-p[2]),lambda p:roof-.005)
    for payload in result.values():
        if mesh_components(payload)>1:raise ValueError('Disconnected visual shell; refine domain/grid before rendering')
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
