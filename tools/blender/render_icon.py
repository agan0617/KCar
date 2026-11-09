"""用 assets\\kart.glb 算一張 App 圖示（512x512 PNG）。
用法：<Blender>\\blender.exe -b --factory-startup -P tools\\blender\\render_icon.py -- . icons\\icon-512.png
"""
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ROOT = os.path.abspath(argv[0] if argv else '.')
OUT = os.path.join(ROOT, argv[1] if len(argv) > 1 else os.path.join('icons', 'icon-512.png'))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, 'assets', 'kart.glb'))
sc = bpy.context.scene

world = bpy.data.worlds.new('W')
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = (0.25, 0.55, 1.0, 1)
bg.inputs['Strength'].default_value = 1.0
sc.world = world

cam_data = bpy.data.cameras.new('Cam')
cam_data.lens = 50
cam = bpy.data.objects.new('Cam', cam_data)
sc.collection.objects.link(cam)
# 車頭朝遊戲 +Z ＝ Blender -Y；從右前方斜上方看
target = Vector((0, 0, 0.62))
cam.location = Vector((2.6, -3.6, 2.2))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
sc.camera = cam

sun = bpy.data.lights.new('Sun', 'SUN')
sun.energy = 3.5
so = bpy.data.objects.new('Sun', sun)
so.rotation_euler = (math.radians(45), math.radians(10), math.radians(30))
sc.collection.objects.link(so)

sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x = sc.render.resolution_y = 512
sc.render.film_transparent = False
sc.view_settings.view_transform = 'Standard'
sc.render.filepath = OUT
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.render.render(write_still=True)
print('[icon] wrote', OUT)
