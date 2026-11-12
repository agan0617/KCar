# Blender 背景模式：把 HDR 讀成 float32 numpy（上下翻成第 0 列＝最上面），存 .npy
import bpy, numpy as np, sys, os
argv = sys.argv[sys.argv.index('--') + 1:]
out_dir = argv[0]
for p in argv[1:]:
    img = bpy.data.images.load(p)
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)[::-1, :, :3].copy()
    name = os.path.basename(p).replace('_2k.hdr', '').replace('_1k.hdr', '')
    np.save(os.path.join(out_dir, name + '.npy'), a)
    print('OK', name, w, h, float(a.max()))
