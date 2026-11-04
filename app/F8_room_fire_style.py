"""Blender-only F8-D versioned still-image styles; no entry point or video render.

Caller owns isolated outputs. Source room geometry/materials are not modified here.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from room_fire_config import curve_value, tongue_specs, flame_mesh, plume_mesh, smoke_state


def checked(owner: object, name: str, value: object) -> object:
    """Do not silently accept unsupported/clamped Blender settings."""
    if not hasattr(owner,name):raise RuntimeError(f'Blender {bpy.app.version_string}: missing required setting {name}')
    try:setattr(owner,name,value)
    except (TypeError,ValueError) as exc:raise RuntimeError(f'Cannot apply Blender setting {name}={value!r}') from exc
    actual=getattr(owner,name)
    if isinstance(value,float):
        if abs(actual-value)>1e-5:raise RuntimeError(f'Blender clamped {name}: requested={value}, actual={actual}')
    elif actual!=value:raise RuntimeError(f'Blender did not apply {name}: requested={value}, actual={actual}')
    return actual


def configure_render(scene: bpy.types.Scene, config: dict) -> dict:
    q=config['quality']; art=config['art']
    render={'engine':'BLENDER_EEVEE_NEXT','resolution_x':q['resolution'][0],'resolution_y':q['resolution'][1],
        'resolution_percentage':100,'fps':q['fps'],'film_transparent':False,'use_file_extension':True,
        'use_compositing':False,'use_sequencer':False,'use_motion_blur':False}
    actual={'blender_version':bpy.app.version_string,'render':{k:checked(scene.render,k,v) for k,v in render.items()}}
    checked(scene,'use_nodes',False)  # No inherited compositor/Bloom processing.
    actual['color_management']={k:checked(scene.view_settings,k,v) for k,v in
        {'view_transform':q['view_transform'],'look':q['look'],'exposure':art['exposure'],
         'gamma':q['gamma'],'use_curve_mapping':False}.items()}
    actual['display_device']=checked(scene.display_settings,'display_device',q['display_device'])
    image={'file_format':'PNG','color_mode':'RGB','color_depth':'8','compression':15}
    actual['image']={k:checked(scene.render.image_settings,k,v) for k,v in image.items()}
    if hasattr(scene.render.image_settings,'color_management'):
        actual['image']['color_management']=checked(scene.render.image_settings,'color_management','FOLLOW_SCENE')
    eevee={'taa_render_samples':q['render_samples'],'taa_samples':16,'use_raytracing':False,
        'use_shadows':True,'use_volumetric_shadows':q['volume_shadows'],
        'volumetric_tile_size':q['volume_tile_size'],'volumetric_samples':q['volume_steps'],
        'volumetric_shadow_samples':q['volume_shadow_steps'],'use_volume_custom_range':True,
        'volumetric_ray_depth':q['volume_ray_depth'],
        'volumetric_start':q['volume_start'],'volumetric_end':q['volume_end'],
        'volumetric_sample_distribution':.8,'volumetric_light_clamp':0.0,
        'shadow_ray_count':q['shadow_rays'],'shadow_step_count':q['shadow_steps']}
    actual['eevee']={k:checked(scene.eevee,k,v) for k,v in eevee.items()}
    actual['compositor_nodes_enabled']=scene.use_nodes
    actual['bloom']=False
    actual['animation_enabled']=False
    return actual


def lighting(scene: bpy.types.Scene, center: list, span: float, config: dict) -> dict:
    art=config['art']
    # Remove inherited lights only in memory, so the requested three lights are the actual set.
    for obj in list(scene.objects):
        if obj.type=='LIGHT':bpy.data.objects.remove(obj,do_unlink=True)
    prefix='Round'+str(art.get('revision',1))
    scene.world=bpy.data.worlds.new(prefix+'World'); scene.world.use_nodes=True
    background=scene.world.node_tree.nodes['Background']
    background.inputs['Color'].default_value=art['world_color']
    background.inputs['Strength'].default_value=art['world_strength']
    values=[]
    for spec in art['area_lights']:
        data=bpy.data.lights.new(prefix+spec['name'],'AREA')
        data.energy=spec['energy']; data.size=spec['size']; data.color=spec['color']; data.shape='SQUARE'; data.use_shadow=True
        checked(data,'volume_factor',spec.get('volume_factor',art.get('area_volume_factor',1.0)))
        obj=bpy.data.objects.new(data.name,data); scene.collection.objects.link(obj)
        obj.location=Vector(center)+Vector(spec['offset'])
        target=Vector(center)+Vector(spec.get('target_offset',[0,0,0]))
        obj.rotation_euler=(target-obj.location).to_track_quat('-Z','Y').to_euler()
        values.append({'name':data.name,'energy':data.energy,'size':data.size,'shape':data.shape,
                       'position':list(obj.location),'target':list(target),'rotation_euler':list(obj.rotation_euler),
                       'color':list(data.color),'use_shadow':data.use_shadow,
                       'volume_factor':data.volume_factor})
    return {'world_color':list(background.inputs['Color'].default_value),
            'world_strength':background.inputs['Strength'].default_value,'area_lights':values}


def volume_material(name: str, smoke: bool, config: dict, phase: float, end_frame: int) -> tuple:
    style=config['art']['smoke' if smoke else 'flame']; fps=config['quality']['fps']
    round2=config['art'].get('revision',1)>=2
    mat=bpy.data.materials.new(name); mat.use_nodes=True
    # Curled plume is non-convex; FAST's convex shortcut is only kept for old spheres.
    mat.volume_intersection_method='FAST' if smoke and not round2 else config['quality']['flame_intersection']
    nodes=mat.node_tree.nodes; nodes.clear(); links=mat.node_tree.links
    out=nodes.new('ShaderNodeOutputMaterial'); volume=nodes.new('ShaderNodeVolumePrincipled'); volume.name='PrincipledEffect'
    links.new(volume.outputs['Volume'],out.inputs['Volume'])
    volume.inputs['Blackbody Intensity'].default_value=0
    volume.inputs['Absorption Color'].default_value=(1,1,1,1)
    volume.inputs['Anisotropy'].default_value=style['anisotropy']
    volume.inputs['Emission Strength'].default_value=0
    volume.inputs['Emission Color'].default_value=(0,0,0,1)
    for field in ('Density Attribute','Color Attribute','Temperature Attribute'):
        if field in volume.inputs:volume.inputs[field].default_value=''
    coord=nodes.new('ShaderNodeTexCoord')
    stretch=nodes.new('ShaderNodeVectorMath'); stretch.operation='MULTIPLY'
    stretch.inputs[1].default_value=(1,1,style['stretch_z'])
    links.new(coord.outputs['Generated'],stretch.inputs[0])
    flow=nodes.new('ShaderNodeVectorMath'); flow.name='EffectFlow'; flow.operation='ADD'; links.new(stretch.outputs['Vector'],flow.inputs[0])
    noise=nodes.new('ShaderNodeTexNoise'); noise.name='EffectNoise'; noise.noise_dimensions='4D'
    noise.inputs['Scale'].default_value=style['noise_scale']; noise.inputs['Detail'].default_value=style['noise_detail']
    noise.inputs['Roughness'].default_value=style['noise_roughness']; noise.inputs['Distortion'].default_value=style['noise_distortion']
    links.new(flow.outputs['Vector'],noise.inputs['Vector'])
    for frame in (1,end_frame):
        seconds=(frame-1)/fps
        flow.inputs[1].default_value=(phase*.17,phase*.11,-seconds*style['flow_speed'])
        flow.inputs[1].keyframe_insert('default_value',frame=frame)
        noise.inputs['W'].default_value=phase+seconds*style['morph_speed']
        noise.inputs['W'].keyframe_insert('default_value',frame=frame)
    for curve in mat.node_tree.animation_data.action.fcurves:
        for key in curve.keyframe_points:key.interpolation='LINEAR'
    ramp=nodes.new('ShaderNodeValToRGB')
    ramp.name='DensityThresholds'; ramp.color_ramp.interpolation='LINEAR'
    ramp.color_ramp.elements[0].position=style['noise_low']; ramp.color_ramp.elements[1].position=style['noise_high']
    links.new(noise.outputs['Fac'],ramp.inputs['Fac'])
    separate=nodes.new('ShaderNodeSeparateXYZ'); links.new(coord.outputs['Generated'],separate.inputs[0])
    fade=nodes.new('ShaderNodeMath'); fade.operation='SUBTRACT'; fade.inputs[0].default_value=1
    links.new(separate.outputs['Z'],fade.inputs[1])
    # Noise is not converted into a large, uniformly luminous mist field.
    mask=nodes.new('ShaderNodeMath'); mask.operation='MULTIPLY'
    links.new(ramp.outputs['Color'],mask.inputs[0]); links.new(fade.outputs[0],mask.inputs[1])
    if smoke and round2:
        # Keep a dark, continuous plume body; noise still breaks its edges.
        filled=nodes.new('ShaderNodeMath'); filled.operation='MULTIPLY_ADD'; filled.name='SmokeBodyNoise'
        filled.inputs[1].default_value=1-style['density_noise_floor']; filled.inputs[2].default_value=style['density_noise_floor']
        links.new(ramp.outputs['Color'],filled.inputs[0])
        links.new(filled.outputs[0],mask.inputs[0])
    if smoke:
        # Fade sphere edges instead of showing a solid, uniformly bounded smoke ball.
        squares=[]
        for axis in ('X','Y'):
            offset=nodes.new('ShaderNodeMath'); offset.operation='SUBTRACT'; offset.inputs[1].default_value=.5
            links.new(separate.outputs[axis],offset.inputs[0])
            square=nodes.new('ShaderNodeMath'); square.operation='MULTIPLY'
            links.new(offset.outputs[0],square.inputs[0]); links.new(offset.outputs[0],square.inputs[1]); squares.append(square)
        radius=nodes.new('ShaderNodeMath'); radius.operation='ADD'
        for i,node in enumerate(squares):links.new(node.outputs[0],radius.inputs[i])
        width=nodes.new('ShaderNodeMath'); width.operation='MULTIPLY'; width.inputs[1].default_value=4
        links.new(radius.outputs[0],width.inputs[0])
        falloff=nodes.new('ShaderNodeMath'); falloff.operation='SUBTRACT'; falloff.inputs[0].default_value=1; falloff.use_clamp=True
        links.new(width.outputs[0],falloff.inputs[1])
        soft=nodes.new('ShaderNodeMath'); soft.operation='MULTIPLY'
        links.new(mask.outputs[0],soft.inputs[0]); links.new(falloff.outputs[0],soft.inputs[1]); mask=soft
    density_level=nodes.new('ShaderNodeValue'); density_level.name='DensityEnvelope'
    density=nodes.new('ShaderNodeMath'); density.operation='MULTIPLY'; density.name='DensityOnly'
    if smoke or not round2:links.new(mask.outputs[0],density.inputs[0])
    links.new(density_level.outputs[0],density.inputs[1])
    links.new(density.outputs[0],volume.inputs['Density'])
    colors=nodes.new('ShaderNodeValToRGB')
    colors.name='EffectColors'; colors.color_ramp.interpolation='LINEAR'
    if smoke:
        # Thicker regions are darker; thin wisps retain a dark-gray scattering edge.
        colors.color_ramp.elements[0].color=style['edge_color']
        colors.color_ramp.elements[1].color=style['dark_color']
        links.new(mask.outputs[0],colors.inputs['Fac']); links.new(colors.outputs['Color'],volume.inputs['Color'])
        if round2:
            # Extinction is explicit, non-emissive and independent of incident white light.
            absorption=nodes.new('ShaderNodeVolumeAbsorption'); absorption.name='SmokeExtraAbsorption'
            absorption.inputs['Color'].default_value=(.5,.5,.5,1)
            absorb_density=nodes.new('ShaderNodeMath'); absorb_density.operation='MULTIPLY'; absorb_density.name='SmokeAbsorptionRatio'
            absorb_density.inputs[1].default_value=style['absorption_ratio']
            links.new(density.outputs[0],absorb_density.inputs[0])
            links.new(absorb_density.outputs[0],absorption.inputs['Density'])
            combined=nodes.new('ShaderNodeAddShader'); combined.name='SmokeScatterAndAbsorption'
            links.new(volume.outputs['Volume'],combined.inputs[0]); links.new(absorption.outputs[0],combined.inputs[1])
            links.new(combined.outputs[0],out.inputs['Volume'])
        return mat,{'density':density_level.outputs[0]}
    volume.inputs['Color'].default_value=style['scatter_color']
    colors.color_ramp.elements[0].position=0; colors.color_ramp.elements[0].color=style['colors'][0]
    colors.color_ramp.elements[1].position=.9; colors.color_ramp.elements[1].color=style['colors'][3]
    for position,color in zip((.32,.7),style['colors'][1:3]):colors.color_ramp.elements.new(position).color=color
    # Radial selector concentrates yellow in a small core; shell geometry supplies separate tongues.
    squares=[]
    for axis in ('X','Y'):
        offset=nodes.new('ShaderNodeMath'); offset.operation='SUBTRACT'; offset.inputs[1].default_value=.5
        links.new(separate.outputs[axis],offset.inputs[0])
        square=nodes.new('ShaderNodeMath'); square.operation='MULTIPLY'
        links.new(offset.outputs[0],square.inputs[0]); links.new(offset.outputs[0],square.inputs[1]); squares.append(square)
    radius=nodes.new('ShaderNodeMath'); radius.operation='ADD'
    for i,node in enumerate(squares):links.new(node.outputs[0],radius.inputs[i])
    radial=nodes.new('ShaderNodeMath'); radial.operation='MULTIPLY'; radial.inputs[1].default_value=4
    links.new(radius.outputs[0],radial.inputs[0])
    core=nodes.new('ShaderNodeMath'); core.operation='SUBTRACT'; core.inputs[0].default_value=1; core.use_clamp=True
    links.new(radial.outputs[0],core.inputs[1])
    if round2:
        # Four radial density layers, separate from the accepted emission/color path.
        layers=nodes.new('ShaderNodeValToRGB'); layers.name='FlameDensityLayers'; layers.color_ramp.interpolation='LINEAR'
        entries=layers.color_ramp.elements
        for i,(position,weight) in enumerate(style['density_layers']):
            entry=entries[i] if i<2 else entries.new(position)
            entry.position=position; entry.color=(weight,weight,weight,1)
        links.new(core.outputs[0],layers.inputs['Fac'])
        filled=nodes.new('ShaderNodeMath'); filled.operation='MULTIPLY_ADD'; filled.name='FlameBodyNoise'
        filled.inputs[1].default_value=1-style['density_noise_floor']; filled.inputs[2].default_value=style['density_noise_floor']
        links.new(ramp.outputs['Color'],filled.inputs[0])
        body=nodes.new('ShaderNodeMath'); body.operation='MULTIPLY'; body.name='FlameBodyThickness'
        links.new(layers.outputs['Color'],body.inputs[0]); links.new(filled.outputs[0],body.inputs[1])
        tall=nodes.new('ShaderNodeMath'); tall.operation='MULTIPLY'; tall.name='FlameDensityHeightFade'
        links.new(body.outputs[0],tall.inputs[0]); links.new(fade.outputs[0],tall.inputs[1])
        links.new(tall.outputs[0],density.inputs[0])
    selector=nodes.new('ShaderNodeMath'); selector.operation='MULTIPLY'
    links.new(core.outputs[0],selector.inputs[0]); links.new(ramp.outputs['Color'],selector.inputs[1])
    links.new(selector.outputs[0],colors.inputs['Fac']); links.new(colors.outputs['Color'],volume.inputs['Emission Color'])
    sharp=nodes.new('ShaderNodeMath'); sharp.operation='POWER'; sharp.inputs[1].default_value=style['emission_mask_power']
    links.new(mask.outputs[0],sharp.inputs[0])
    emission_level=nodes.new('ShaderNodeValue'); emission_level.name='EmissionEnvelope'
    emission=nodes.new('ShaderNodeMath'); emission.operation='MULTIPLY'; emission.name='EmissionIndependentOfDensity'
    links.new(sharp.outputs[0],emission.inputs[0]); links.new(emission_level.outputs[0],emission.inputs[1])
    links.new(emission.outputs[0],volume.inputs['Emission Strength'])
    return mat,{'density':density_level.outputs[0],'emission':emission_level.outputs[0]}


def material_settings(mat: bpy.types.Material) -> dict:
    nodes=mat.node_tree.nodes; volume=nodes['PrincipledEffect']; noise=nodes['EffectNoise']
    return {'name':mat.name,'noise':{key:noise.inputs[key].default_value for key in
            ('Scale','Detail','Roughness','Distortion')},'noise_dimensions':noise.noise_dimensions,
        'color_ramp':[{'position':e.position,'color':list(e.color)} for e in nodes['EffectColors'].color_ramp.elements],
        'density_thresholds':[e.position for e in nodes['DensityThresholds'].color_ramp.elements],
        'scatter_color_default':list(volume.inputs['Color'].default_value),'scatter_color_linked':volume.inputs['Color'].is_linked,
        'anisotropy':volume.inputs['Anisotropy'].default_value,
        'absorption_color':list(volume.inputs['Absorption Color'].default_value),
        'emission_strength_linked':volume.inputs['Emission Strength'].is_linked,
        'blackbody_intensity':volume.inputs['Blackbody Intensity'].default_value,
        'emission_and_density_independent':bool(nodes.get('EmissionIndependentOfDensity')),
        'volume_intersection_method':mat.volume_intersection_method,
        'density_layers':[{'position':e.position,'weight':e.color[0]} for e in nodes['FlameDensityLayers'].color_ramp.elements]
            if nodes.get('FlameDensityLayers') else None,
        'body_noise_floor':nodes['FlameBodyNoise'].inputs[2].default_value if nodes.get('FlameBodyNoise') else
            nodes['SmokeBodyNoise'].inputs[2].default_value if nodes.get('SmokeBodyNoise') else 0,
        'extra_absorption_ratio':nodes['SmokeAbsorptionRatio'].inputs[1].default_value if nodes.get('SmokeAbsorptionRatio') else 0,
        'extra_absorption_color':list(nodes['SmokeExtraAbsorption'].inputs['Color'].default_value) if nodes.get('SmokeExtraAbsorption') else None}


def add_fire(scene: bpy.types.Scene, timeline: dict, points: list[dict], floor: float,
             surfaces: list, config: dict, closest_hit: object) -> dict:
    q=config['quality']; art=config['art']; f=art['flame']; s=art['smoke']; fps=q['fps']
    positions={int(p['device']):p['pose']['translation'] for p in points}
    end_frame=math.ceil((max(e['time'] for e in timeline['spread_events'])+s['density_curve'][-1][0])*fps)+1
    anchors=[]; all_specs=[]
    for event in timeline['spread_events']:
        device=event['point']; p=positions[device]; start=event['time']
        hit=closest_hit(Vector((p['x'],p['y'],floor+1.15)),Vector((0,0,-1)),surfaces)
        base=max(floor,hit[1].z+.015) if hit else floor
        primary=device==timeline['start_point']; specs=tongue_specs(config,device,primary); phase=specs[0]['phase']
        vertices,faces=flame_mesh(specs,q['tongue_rings'],q['tongue_sides'])
        mesh=bpy.data.meshes.new('TongueCluster_'+str(device)); mesh.from_pydata(vertices,[],faces); mesh.update()
        flame=bpy.data.objects.new(mesh.name,mesh); scene.collection.objects.link(flame); flame.location=(p['x'],p['y'],base)
        mat,fc=volume_material('FlameStyle_'+str(device),False,config,phase,end_frame); mesh.materials.append(mat)
        if art.get('revision',1)>=2:
            sv,sf=plume_mesh(config,phase+2)
            smoke_mesh=bpy.data.meshes.new('SmokePlume_'+str(device)); smoke_mesh.from_pydata(sv,[],sf); smoke_mesh.update()
            smoke=bpy.data.objects.new(smoke_mesh.name,smoke_mesh); scene.collection.objects.link(smoke)
            smoke.location=(p['x'],p['y'],base)
        else:
            bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=1,location=(p['x'],p['y'],base+1))
            smoke=bpy.context.object; smoke.name='Smoke_'+str(device)
        sm,sc=volume_material(smoke.name,True,config,phase+2,end_frame); smoke.data.materials.append(sm)
        light=bpy.data.lights.new('FireLight_'+str(device),'POINT'); light.color=f['light_color']
        light.shadow_soft_size=f['light_radius']; light.use_shadow=True
        checked(light,'use_custom_distance',True); light.cutoff_distance=f['light_distance']
        checked(light,'volume_factor',f.get('light_volume_factor',1.0))
        lamp=bpy.data.objects.new(light.name,light); scene.collection.objects.link(lamp); lamp.location=(p['x'],p['y'],base+.65)
        for frame in range(1,end_frame+1):
            age=(frame-1)/fps-start
            a=curve_value(config['events']['fire_curve'],age)
            flicker=1+f['flicker_amplitude']*(.65*math.sin(2*math.pi*f['flicker_hz']*max(0,age)+phase)+
                        .35*math.sin(2*math.pi*f['flicker_hz']*.61*max(0,age)+phase*1.7))
            for socket,value in ((fc['density'],f['density']*a),(fc['emission'],f['emission']*a*flicker),
                                 (sc['density'],s['density']*curve_value(s['density_curve'],age))):
                socket.default_value=value; socket.keyframe_insert('default_value',frame=frame)
            flame.scale=(.35+.65*a,.35+.65*a,(.04+.96*a)*(1+(flicker-1)*.5))
            flame.rotation_euler=(f['sway_radians']*math.sin(age*5+phase),f['sway_radians']*math.cos(age*4+phase),0)
            flame.keyframe_insert('scale',frame=frame); flame.keyframe_insert('rotation_euler',frame=frame)
            if art.get('revision',1)>=2:
                state=smoke_state(config,age,primary)
                smoke.scale=(state['radius'],state['radius'],state['height'])
                smoke.location.z=base+state['emitter_offset']
            else:
                growth=curve_value(s['growth_curve'],max(0,age))
                smoke.scale=(s['radius']*growth,s['radius']*growth,s['height']*.5*growth)
                smoke.location.z=base+.8+s['height']*.25*growth+max(0,age)*s['rise_speed']
            smoke.keyframe_insert('scale',frame=frame); smoke.keyframe_insert('location',frame=frame)
            light.energy=f['light_energy']*a*flicker; light.keyframe_insert('energy',frame=frame)
        anchors.append({'device':device,'reference_floor_z':floor,'display_fire_base_z':base})
        all_specs.append({'device':device,'primary':primary,'tongues':specs,'phase':phase,
            'flame_object':flame.name,'smoke_object':smoke.name,'light_energy_coefficient':f['light_energy'],
            'flame_material':material_settings(mat),'smoke_material':material_settings(sm),
            'smoke_shape':s.get('shape','uv_sphere'),
            'smoke_samples':[{'seconds':seconds,'age':seconds-start,**smoke_state(config,seconds-start,primary)}
                for seconds in q['sample_times']] if art.get('revision',1)>=2 else [],
            'light_effective':{'radius':light.shadow_soft_size,'use_shadow':light.use_shadow,
                'custom_distance':light.use_custom_distance,'cutoff_distance':light.cutoff_distance,'volume_factor':light.volume_factor}})
    return {'anchors':anchors,'clusters':all_specs,'animation_keyframe_end':end_frame,
            'volume_object_count':len(all_specs)*2,'note':'Procedural visual effect; no CFD, no Hybrid or boundary-front implementation'}


def snapshot_settings(scene: bpy.types.Scene) -> dict:
    return {'color_management':{k:getattr(scene.view_settings,k) for k in ('view_transform','look','exposure','gamma','use_curve_mapping')},
        'camera':{'type':scene.camera.data.type,'position':list(scene.camera.matrix_world.translation),
                  'target':list(scene.camera.constraints[0].target.location),'lens':scene.camera.data.lens,
                  'ortho_scale':scene.camera.data.ortho_scale,'dof':scene.camera.data.dof.use_dof,
                  'sensor_width':scene.camera.data.sensor_width,'sensor_fit':scene.camera.data.sensor_fit,
                  'clip_start':scene.camera.data.clip_start,'clip_end':scene.camera.data.clip_end},
        'lights':[{'name':obj.name,'type':obj.data.type,'energy':obj.data.energy,'color':list(obj.data.color),
                   'volume_factor':obj.data.volume_factor}
                  for obj in scene.objects if obj.type=='LIGHT'],
        'volume_controls':[{'material':mat.name,'density_level':mat.node_tree.nodes['DensityEnvelope'].outputs[0].default_value,
            'emission_level':mat.node_tree.nodes['EmissionEnvelope'].outputs[0].default_value
                if mat.node_tree.nodes.get('EmissionEnvelope') else 0}
            for mat in bpy.data.materials if mat.use_nodes and mat.node_tree.nodes.get('DensityEnvelope')],
        'smoke_objects':[{'name':obj.name,'position':list(obj.location),'scale':list(obj.scale),
                          'world_bounds_z':[min((obj.matrix_world @ Vector(c)).z for c in obj.bound_box),
                                            max((obj.matrix_world @ Vector(c)).z for c in obj.bound_box)]}
                         for obj in scene.objects if obj.type=='MESH' and obj.name.startswith(('Smoke_','SmokePlume_'))],
        'resolution':[scene.render.resolution_x,scene.render.resolution_y],'frame':scene.frame_current}
