"""Blender-only adapter. Import bpy lazily; offline tests never import Blender."""
from experiments.visual_state import geometry, roof_mesh, inspection_targets
from render_engine.jobs.operation_logging import traced


@traced('room.continuous.camera','blender_view_gate')
def verify_blender_view(scene,snapshot):
    """Check evaluated renderable scan meshes, not merely candidate geometry."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from bpy_extras.object_utils import world_to_camera_view
    bpy.context.view_layer.update();origin=scene.camera.matrix_world.translation.copy()
    trees=[];depsgraph=bpy.context.evaluated_depsgraph_get()
    for obj in scene.objects:
        if obj.type!='MESH' or obj.hide_render:continue
        evaluated=obj.evaluated_get(depsgraph);mesh=evaluated.to_mesh()
        try:
            if not mesh.vertices or not mesh.polygons:continue
            mesh.calc_loop_triangles()
            trees.append((obj.name,BVHTree.FromPolygons([evaluated.matrix_world@v.co for v in mesh.vertices],[tuple(t.vertices) for t in mesh.loop_triangles],all_triangles=True)))
        finally:evaluated.to_mesh_clear()
    targets={}
    for name,point in inspection_targets(snapshot['config'],snapshot['seed_xy'],snapshot['polygon']).items():
        point=Vector(point);ndc=world_to_camera_view(scene,scene.camera,point)
        if ndc.z<=0 or not (.04<=ndc.x<=.96 and .04<=ndc.y<=.96):raise ValueError('Blender camera clips inspection target: '+name)
        delta=point-origin;length=delta.length
        for object_name,tree in trees:
            location,normal,index,distance=tree.ray_cast(origin,delta.normalized(),max(0,length-.025))
            if location is not None:raise ValueError('Blender scan blocks '+name+' via '+object_name+' at '+str(round(distance,3))+'m')
        targets[name]={'image_xy':[ndc.x,ndc.y],'clear':True}
    return {'actual_blender_view_checked':True,'camera':list(origin),'targets':targets,'scan_meshes_checked':[n for n,_ in trees]}


def volume_material(bpy,name,config,fire=False):
    material=bpy.data.materials.new(name);material.use_nodes=True
    nodes=material.node_tree.nodes;nodes.clear();links=material.node_tree.links
    output=nodes.new('ShaderNodeOutputMaterial');volume=nodes.new('ShaderNodeVolumePrincipled')
    links.new(volume.outputs['Volume'],output.inputs['Volume'])
    for key in ('Density Attribute','Color Attribute','Temperature Attribute'):
        if key in volume.inputs:volume.inputs[key].default_value=''
    position=nodes.new('ShaderNodeNewGeometry');noise=nodes.new('ShaderNodeTexNoise');noise.noise_dimensions='4D'
    noise.name='SharedWorldNoise';noise.inputs['Scale'].default_value=config['visual']['noise_scale']
    links.new(position.outputs['Position'],noise.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.05,.05,.05,1);ramp.color_ramp.elements[1].color=(1,1,1,1)
    links.new(noise.outputs['Fac'],ramp.inputs['Fac'])
    multiply=nodes.new('ShaderNodeMath');multiply.operation='MULTIPLY'
    multiply.name='EffectDensity'
    multiply.inputs[1].default_value=config['visual']['flame_density'] if fire else config['visual']['smoke_density']
    links.new(ramp.outputs['Color'],multiply.inputs[0]);links.new(multiply.outputs[0],volume.inputs['Density'])
    volume.inputs['Color'].default_value=(1,.15,.01,1) if fire else config['visual']['smoke_color']
    volume.inputs['Anisotropy'].default_value=.1
    volume.inputs['Blackbody Intensity'].default_value=0
    volume.inputs['Emission Strength'].default_value=config['visual']['emission'] if fire else 0
    volume.inputs['Emission Color'].default_value=(1,.12,.005,1) if fire else (0,0,0,1)
    if fire:
        emission=nodes.new('ShaderNodeMath');emission.operation='MULTIPLY';emission.inputs[1].default_value=config['visual']['emission']
        links.new(noise.outputs['Fac'],emission.inputs[0]);links.new(emission.outputs[0],volume.inputs['Emission Strength'])
    return material


def construct(snapshot):
    import bpy
    from render_engine.blender.F8_room_helpers import mesh_faces,below,make_mesh
    from render_engine.blender.F8_room_fire_style import configure_render,lighting
    from render_engine.blender.F8_room_animation import independent_camera
    bpy.ops.wm.open_mainfile(filepath=snapshot['asset_blend'])
    scene=bpy.context.scene;config=snapshot['config'];ring=snapshot['polygon']
    from experiments.continuous_field import field_from_config
    field=field_from_config(config,ring,snapshot['seed_xy'])
    collection=bpy.data.collections.new('A2_Continuous_Experiment');scene.collection.children.link(collection)
    # Display derivative only; original mesh/material datablocks are not edited.
    source=bpy.data.objects['RoomSource'];source.hide_render=True
    display=make_mesh('A2_ScanDisplay',below(mesh_faces(source),config['display_cut_z_m']),{m.name:m for m in bpy.data.materials})
    for owner in list(display.users_collection):owner.objects.unlink(display)
    collection.objects.link(display)
    style=snapshot['r3_style'];configure_render(scene,style)
    scene.view_settings.exposure=config['exposure']
    center=[(min(p[k] for p in ring)+max(p[k] for p in ring))/2 for k in (0,1)]+[config['seed']['proposed_base_z_m']+.4]
    lighting(scene,center,max(max(p[k] for p in ring)-min(p[k] for p in ring) for k in (0,1)),style)
    def object_mesh(name,payload,material=None):
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(payload['vertices'],payload.get('edges',[]),payload['faces']);mesh.update()
        obj=bpy.data.objects.new(name,mesh);collection.objects.link(obj)
        if material:mesh.materials.append(material)
        return obj
    roof=object_mesh('A2_HypotheticalRoof',roof_mesh(ring,config['visual']['roof_z_m'],config['visual']['roof_mode']))
    roof['physical_height_measured']=False
    if config['visual']['roof_mode']=='outline':
        roof.hide_render=True
        curve=bpy.data.curves.new('A2_RoofOutline','CURVE');curve.dimensions='3D';curve.bevel_depth=.012
        spline=curve.splines.new('POLY');spline.points.add(len(ring)-1);spline.use_cyclic_u=True
        for point,(x,y) in zip(spline.points,ring):point.co=(x,y,config['visual']['roof_z_m'],1)
        line=bpy.data.objects.new(curve.name,curve);collection.objects.link(line)
        if config.get('require_clear_view'):
            # An explicitly artificial engineering outline, not a scanned roof.
            outline=bpy.data.materials.new('A2_EngineeringRoofOutline');outline.use_nodes=True
            nodes=outline.node_tree.nodes;nodes.clear()
            output=nodes.new('ShaderNodeOutputMaterial');emission=nodes.new('ShaderNodeEmission')
            emission.inputs['Color'].default_value=(.18,.42,.65,1);emission.inputs['Strength'].default_value=.8
            outline.node_tree.links.new(emission.outputs[0],output.inputs['Surface']);curve.materials.append(outline)
    materials={name:volume_material(bpy,'A2_'+name,config,name=='flame') for name in ('flame','smoke','layer')}
    # Ceiling density is independent and bounded, not a solid black cap.
    materials['layer'].node_tree.nodes['EffectDensity'].inputs[1].default_value=config['visual']['layer_density']
    objects={name:object_mesh('A2_'+name,{'vertices':[],'faces':[]},materials[name]) for name in materials}
    camera_name=config['camera']
    if camera_name in ('v1','v1_final'):
        ref=snapshot['camera_reference'];scene.camera=None
        name='A2_FormalV1Overview' if camera_name=='v1_final' else 'A2_R3SampleReference'
        camera=independent_camera(scene,name,ref['position'],ref['target'],ref['type']=='ORTHO',ref['ortho_scale'])
        for key in ('lens','ortho_scale','clip_start','clip_end','sensor_width','sensor_fit'):setattr(camera.data,key,ref[key])
    else:
        seed=snapshot['seed_xy'];base=config['seed']['proposed_base_z_m']
        spec=config['cameras'][camera_name]
        camera=independent_camera(scene,'A2_'+camera_name,[seed[0]+spec['offset'][0],seed[1]+spec['offset'][1],base+spec['offset'][2]],[seed[0],seed[1],base+spec['target_height']],False,10)
        camera.data.lens=spec['lens']
        if config.get('require_clear_view'):
            camera.data.sensor_width=36;camera.data.sensor_fit='HORIZONTAL'
    scene.camera=camera
    for marker in scene.timeline_markers:marker.camera=None
    if config.get('require_clear_view'):
        import json
        scene['a2_camera_audit_json']=json.dumps(verify_blender_view(scene,snapshot))
    light_data=bpy.data.lights.new('A2_FireBounce','POINT');light_data.color=(1,.18,.02)
    light=bpy.data.objects.new(light_data.name,light_data);collection.objects.link(light)
    light.location=(*snapshot['seed_xy'],config['seed']['proposed_base_z_m']+.4)
    def apply(seconds):
        payloads=geometry(field,ring,config,seconds)
        for name,obj in objects.items():
            mesh=obj.data;mesh.clear_geometry();mesh.from_pydata(payloads[name]['vertices'],[],payloads[name]['faces']);mesh.update()
            obj.hide_render=not bool(payloads[name]['faces'])
            materials[name].node_tree.nodes['SharedWorldNoise'].inputs['W'].default_value=seconds*config['visual']['morph_hz']+config['visual']['seed']
        light_data.energy=(config['visual']['light_energy']*min(1,max(0,seconds-config['visual']['smoke_lead_s'])/2) if config['visual']['mode']=='combined' else 0)
    def frame_change(current,*args):apply((current.frame_current-1)/current.render.fps)
    bpy.app.handlers.frame_change_pre.append(frame_change)
    apply(0)
    return scene,apply
