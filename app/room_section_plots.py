"""Standalone diagnostic figures via Matplotlib Agg; no scene renderer."""
from __future__ import annotations

from collections import defaultdict
from html import escape
import os
from pathlib import Path

COLORS = {'lower_envelope_candidate':'#1765ab','upper_envelope_candidate':'#d97706',
          'vertical_wall_like':'#475569','interior_horizontal_candidate':'#9333ea',
          'sloped_or_uncertain':'#9b8a19','horizontal_uncertain':'#adadad'}


def plot_report(output: Path, report: dict, mesh: dict) -> list[str]:
    os.environ['MPLCONFIGDIR']=str((output/'.matplotlib-cache').resolve())
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Patch

    plt.rcParams.update({'font.size':9,'axes.grid':True,'grid.alpha':.16,'savefig.dpi':160})
    polygon = report['polygon_raw_xy']; closed = polygon + polygon[:1]
    samples = report['height_samples']; names = []
    def save(fig: object, name: str) -> None:
        fig.savefig(output/name, bbox_inches='tight')
        plt.close(fig); names.append(name)
    def plan(ax: object) -> None:
        ax.plot([p[0] for p in closed],[p[1] for p in closed],color='#162538',lw=1.5)
        ax.set_aspect('equal'); ax.set_xlabel('Raw X (m)'); ax.set_ylabel('Raw Y (m)')
    def mark_points(ax: object) -> None:
        for point in report['camera_points']:
            x,y = point['xy']; hot = point['ignition']
            ax.scatter(x,y,s=36 if hot else 8,c='#dc2626' if hot else '#111827',zorder=5)
            ax.annotate(str(point['device']),(x,y),xytext=(3,3),textcoords='offset points',fontsize=7)

    fig,ax = plt.subplots(figsize=(12,6))
    cloud = mesh['vertices'][::max(1,len(mesh['vertices'])//3500)]
    ax.scatter([p[0] for p in cloud],[p[1] for p in cloud],s=.5,c='#b1bac7',alpha=.45)
    plan(ax); mark_points(ax)
    for section in report['sections']:
        origin,u = section['origin'],section['direction']
        if section['kind']=='boundary':
            ax.scatter(*origin,s=18,c='#0f766e')
            ax.annotate(section['id'],origin,xytext=(4,-10),textcoords='offset points',fontsize=7,color='#0f766e')
        else:
            for a,b in section['room_intervals']:
                ax.plot([origin[0]+a*u[0],origin[0]+b*u[0]],[origin[1]+a*u[1],origin[1]+b*u[1]],
                        '--',lw=.8,alpha=.7,color='#dc2626' if section['kind']=='ignition' else '#2563eb')
            if section['room_intervals']:
                t=section['room_intervals'][0][0]
                ax.text(origin[0]+t*u[0],origin[1]+t*u[1],section['id'],fontsize=7)
    ax.set_title(f"{report['room_id']} section locations | {report['spacing_m']}m height samples | original XYZ retained")
    ax.set_xlim(min(p[0] for p in polygon)-.8,max(p[0] for p in polygon)+1.2)
    ax.set_ylim(min(p[1] for p in polygon)-.6,max(p[1] for p in polygon)+.6)
    save(fig,'01_sampling_plan.png')

    fig,axes = plt.subplots(2,1,figsize=(12,10))
    for ax,field in zip(axes,('bottom','top')):
        valid = [p for p in samples if p[field] is not None]
        scatter = ax.scatter([p['xy'][0] for p in valid],[p['xy'][1] for p in valid],
                             c=[p[field] for p in valid],cmap='viridis',s=20,marker='s')
        missing = [p for p in samples if p[field] is None]
        if missing:
            ax.scatter([p['xy'][0] for p in missing],[p['xy'][1] for p in missing],c='red',marker='x',s=30)
        plan(ax); mark_points(ax)
        ax.set_title(f'{field.upper()} geometric envelope (not certified floor/ceiling); red X = missing')
        fig.colorbar(scatter,ax=ax,label='Raw Z (m)',shrink=.8)
    fig.tight_layout(); save(fig,'02_height_envelopes.png')

    fig,axes = plt.subplots(2,1,figsize=(12,10))
    for ax,field in zip(axes,('bottom','top')):
        components = report['continuity'][field]['components']
        for i,component in enumerate(components):
            xy=component['sample_xy']; color = plt.get_cmap('tab20')(i%20) if i<12 else '#d1d5db'
            ax.scatter([p[0] for p in xy],[p[1] for p in xy],s=20,c=[color],marker='s')
            if i<8:
                center=[sum(p[k] for p in xy)/len(xy) for k in (0,1)]
                ax.annotate(f"C{i+1}: {component['z_bin_m']:.2f}m / {component['sample_count']} pts",center,
                            fontsize=7,bbox={'facecolor':'white','alpha':.8,'edgecolor':'none'})
        plan(ax); ax.set_title(f'{field.upper()} connected patches | same 5cm bin, four-neighbor grid')
    fig.tight_layout(); save(fig,'03_surface_continuity.png')

    legend=[Patch(color=color,label=label.replace('_',' ')) for label,color in COLORS.items()]
    z0,z1=report['raw_z_bounds']
    def draw_section(ax: object, section: dict, small: bool=False) -> None:
        groups=defaultdict(list)
        for segment in section['segments']:
            groups[segment['role']].append(segment['tz'])
        for role,segments in groups.items():
            ax.add_collection(LineCollection(segments,colors=COLORS[role],linewidths=.7 if small else 1.1))
        for a,b in section['room_intervals']:
            ax.axvspan(a,b,color='#d1fae5',alpha=.25,zorder=-1)
        if section['kind']=='boundary':
            ax.axvline(0,color='#dc2626',ls='--',lw=1)
        for cluster in report['height_clusters']['bottom'][:3]:
            ax.axhline(cluster['z_m'],color=COLORS['lower_envelope_candidate'],ls=':',lw=.5,alpha=.5)
        for cluster in report['height_clusters']['top'][:3]:
            ax.axhline(cluster['z_m'],color=COLORS['upper_envelope_candidate'],ls=':',lw=.5,alpha=.5)
        ax.set_xlim(section['window']); ax.set_ylim(z0-.15,z1+.15)
        ax.set_aspect('equal',adjustable='box')
        ax.set_xlabel('Signed distance along section (m)'); ax.set_ylabel('Original Z (m)')
        o=section['origin']; u=section['direction']
        ax.set_title(f"{section['id']} | origin=({o[0]:.3f},{o[1]:.3f}) u=({u[0]:.3f},{u[1]:.3f})",fontsize=8 if small else 10)
    for section in report['sections']:
        fig,ax=plt.subplots(figsize=(11,6))
        draw_section(ax,section)
        fig.legend(handles=legend,loc='lower center',ncol=3,fontsize=7)
        fig.subplots_adjust(bottom=.2)
        save(fig,f"section_{section['id']}.png")
    for page,start in enumerate(range(0,len(report['sections']),6),1):
        fig,axes=plt.subplots(3,2,figsize=(14,13))
        for ax,section in zip(axes.flat,report['sections'][start:start+6]):
            draw_section(ax,section,True)
        for ax in list(axes.flat)[len(report['sections'][start:start+6]):]:
            ax.axis('off')
        fig.legend(handles=legend,loc='lower center',ncol=3,fontsize=8)
        fig.suptitle('Geometric sections: evidence categories only; no permanent mesh cutting')
        fig.tight_layout(rect=(0,.06,1,.97)); save(fig,f'04_sections_overview_{page}.png')

    rows=[r for r in report['wall_evidence'] if r['samples']]
    fig,axes=plt.subplots(math_rows(len(rows)),2,figsize=(14,3.0*math_rows(len(rows))),squeeze=False)
    for ax,row in zip(axes.flat,rows):
        valid=[s for s in row['samples'] if s['nearest_offset_m'] is not None]
        if valid:
            sc=ax.scatter([s['along_edge_m'] for s in valid],[s['z_m'] for s in valid],
                c=[s['nearest_offset_m'] for s in valid],cmap='coolwarm',vmin=-.15,vmax=.15,s=30)
            fig.colorbar(sc,ax=ax,label='Signed nearest offset (m)',shrink=.8,extend='both')
        missing=[s for s in row['samples'] if s['nearest_offset_m'] is None]
        if missing:
            ax.scatter([s['along_edge_m'] for s in missing],[s['z_m'] for s in missing],marker='x',c='black',s=15)
        ax.set_title(f"{row['edge_id']} | parallel-surface hit {row['hit_fraction']:.0%} | pair spacing is NOT certified thickness")
        ax.set_xlabel('Distance along edge (m)');ax.set_ylabel('Sample height Z (m)')
    for ax in list(axes.flat)[len(rows):]:ax.axis('off')
    fig.tight_layout();save(fig,'05_boundary_offsets.png')
    return names


def math_rows(count: int) -> int:
    return max(1,(count+1)//2)


def write_index(output: Path, report: dict, names: list[str]) -> None:
    role_text='蓝：下包络候选；橙：上包络候选；灰：近竖直面；紫：内部水平面候选；黄：斜面；浅灰：未分类水平面。颜色不是物理语义确认。'
    primary=[n for n in names if not n.startswith('section_')]
    gallery=''.join(f'<h3>{escape(n)}</h3><a href="{escape(n)}"><img loading="lazy" src="{escape(n)}" style="max-width:100%"></a>' for n in primary)
    singles=''.join(f'<li><a href="{escape(n)}">{escape(n)}</a></li>' for n in names if n.startswith('section_'))
    html=f'''<!doctype html><meta charset="utf-8"><title>房间断面核验</title>
<body style="font:16px system-ui;max-width:1400px;margin:30px auto;padding:0 20px">
<h1>{escape(report['room_id'])} 裁切前几何断面核验</h1>
<p>只读诊断：原始 XYZ；未裁切、未渲染视频、未修改数据库。ready_for_cut=false。</p>
<p>{role_text}</p><p>绿色底色是断面穿过目标房间的范围；边界断面红色竖线为户型边界，正方向朝房间内。墙体偏差图黑叉表示在搜索范围内未命中平行竖直面，不直接等于门洞。</p>
<p>高度图红叉表示缺少上表面；连续区域只表示采样邻接。不能从色块直接认定统一地板或天花板。<a href="report.json">完整结构化报告</a> · <a href="findings.md">核验摘要</a></p>
{gallery}<h2>单独断面原图</h2><ul>{singles}</ul></body>'''
    (output/'index.html').write_text(html,encoding='utf-8')
