"""Blender adapter for shared-space fire and extinction-dominant black smoke."""
from experiments.visual_state import adaptation_style,adaptation_state
from experiments.conflagration import validate_controls,smooth


def build_material(bpy,name,config,kind):
    p=validate_controls(config);style=adaptation_style(config)
    material=bpy.data.materials.new(name);material.use_nodes=True
    material.volume_intersection_method='ACCURATE'
    nodes=material.node_tree.nodes;nodes.clear();links=material.node_tree.links
    def node(code,label=None):
        n=nodes.new(code)
        if label:n.name=label
        return n
    def math_node(operation,a,b):
        n=node('ShaderNodeMath');n.operation=operation
        for i,value in enumerate((a,b)):
            if isinstance(value,(int,float)):n.inputs[i].default_value=value
            else:links.new(value,n.inputs[i])
        return n.outputs[0]
    out=node('ShaderNodeOutputMaterial')
    pos=node('ShaderNodeNewGeometry');flow=node('ShaderNodeVectorMath','CF_Flow');flow.operation='ADD'
    links.new(pos.outputs['Position'],flow.inputs[0])
    noise=node('ShaderNodeTexNoise','CF_Noise');noise.noise_dimensions='4D'
    noise.inputs['Scale'].default_value=p['noise_scale'];noise.inputs['Detail'].default_value=3
    noise.inputs['Roughness'].default_value=.65;noise.inputs['Distortion'].default_value=.35
    links.new(flow.outputs[0],noise.inputs['Vector'])
    fine=node('ShaderNodeTexNoise','CF_FineNoise');fine.noise_dimensions='4D'
    fine.inputs['Scale'].default_value=p['noise_scale']*2.31;fine.inputs['Detail'].default_value=2
    links.new(flow.outputs[0],fine.inputs['Vector'])
    mask=math_node('MULTIPLY',noise.outputs['Fac'],1-p['density_floor'])
    # A positive interior density floor supplies a connected body; emission is
    # separately broken by finer moving noise, rather than a solid orange block.
    mask=math_node('ADD',mask,p['density_floor'])
    density=node('ShaderNodeValue','DensityEnvelope').outputs[0]
    controls={'density':density}
    if kind in ('smoke','layer'):
        scatter=node('ShaderNodeVolumeScatter','CF_DarkScatter')
        scatter.inputs['Color'].default_value=p['smoke_color'];scatter.inputs['Anisotropy'].default_value=.1
        links.new(math_node('MULTIPLY',mask,density),scatter.inputs['Density'])
        absorption=node('ShaderNodeVolumeAbsorption','CF_Extinction')
        absorption.inputs['Color'].default_value=(.5,.5,.5,1)
        strength=node('ShaderNodeValue','AbsorptionEnvelope').outputs[0];controls['absorption']=strength
        links.new(math_node('MULTIPLY',mask,strength),absorption.inputs['Density'])
        combined=node('ShaderNodeAddShader');links.new(scatter.outputs[0],combined.inputs[0]);links.new(absorption.outputs[0],combined.inputs[1])
        links.new(combined.outputs[0],out.inputs['Volume'])
    else:
        volume=node('ShaderNodeVolumePrincipled','CF_FireVolume')
        for key in ('Density Attribute','Color Attribute','Temperature Attribute'):
            if key in volume.inputs:volume.inputs[key].default_value=''
        volume.inputs['Blackbody Intensity'].default_value=0
        volume.inputs['Color'].default_value=style['art']['flame']['scatter_color']
        links.new(math_node('MULTIPLY',mask,density),volume.inputs['Density'])
        generated=node('ShaderNodeTexCoord');height=node('ShaderNodeSeparateXYZ')
        links.new(generated.outputs['Generated'],height.inputs[0])
        fade=math_node('SUBTRACT',1,height.outputs['Z'])
        selector=math_node('MULTIPLY',fade,noise.outputs['Fac'])
        colors=node('ShaderNodeValToRGB','CF_R3Colors')
        entries=colors.color_ramp.elements;entries[0].position=0;entries[1].position=.9
        entries[0].color=style['art']['flame']['colors'][0];entries[1].color=style['art']['flame']['colors'][3]
        for position,color in zip((.32,.7),style['art']['flame']['colors'][1:3]):entries.new(position).color=color
        links.new(selector,colors.inputs['Fac']);links.new(colors.outputs['Color'],volume.inputs['Emission Color'])
        emission=node('ShaderNodeValue','EmissionEnvelope').outputs[0];controls['emission']=emission
        ribbons=math_node('MULTIPLY',noise.outputs['Fac'],fine.outputs['Fac'])
        links.new(math_node('MULTIPLY',math_node('MULTIPLY',ribbons,fade),emission),volume.inputs['Emission Strength'])
        links.new(volume.outputs['Volume'],out.inputs['Volume'])
    material['kind']=kind;material['representation']='continuous_shared_space_extinction_or_fire'
    return material,controls


def update_material(material,controls,config,kind,seconds):
    p=validate_controls(config);state=adaptation_state(config,seconds)
    material.node_tree.nodes['CF_Flow'].inputs[1].default_value=(.13*seconds,-.07*seconds,-seconds*p['noise_speed'])
    for name,tempo in (('CF_Noise',1),('CF_FineNoise',1.37)):
        material.node_tree.nodes[name].inputs['W'].default_value=config['visual']['seed']+seconds*p['noise_speed']*tempo
    if kind in ('smoke','layer'):
        active=state['smoke_fraction']
        controls['density'].default_value=p['smoke_scatter_density']*active
        controls['absorption'].default_value=p['layer_absorption_density' if kind=='layer' else 'smoke_absorption_density']*active
    else:
        active=state['ground_fraction'];large=smooth((seconds-p['start_s'])/p['transition_s'])
        controls['density'].default_value=p['body_density']*active
        controls['emission'].default_value=(p['minimum_visible_emission']+(p['body_emission']-p['minimum_visible_emission'])*large)*active


def material_settings(material):
    nodes=material.node_tree.nodes
    result={'name':material.name,'kind':material.get('kind'),'density':nodes['DensityEnvelope'].outputs[0].default_value,
            'volume_output_connected':any(n.inputs['Volume'].is_linked for n in nodes if n.bl_idname=='ShaderNodeOutputMaterial'),
            'noise_scale':nodes['CF_Noise'].inputs['Scale'].default_value,
            'node_types':[n.bl_idname for n in nodes]}
    for label in ('AbsorptionEnvelope','EmissionEnvelope'):
        if nodes.get(label):result[label]=nodes[label].outputs[0].default_value
    if nodes.get('CF_DarkScatter'):result['scatter_color']=list(nodes['CF_DarkScatter'].inputs['Color'].default_value)
    return result
