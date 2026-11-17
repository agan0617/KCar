"""賽道 layout 產生工具：用「走直線、轉彎、指定高度」描述一圈，輸出 tools/blender/<id>_layout.json（格式見 tools/blender/TRACK_V2.md）。

用法（每條賽道一支設計腳本，放 tools/tracks/<id>.py）：

    from layout_lib import Course
    c = Course('coast', name='斷崖海岸', theme='beach', look='coast', difficulty=3, laps=2,
               defaults=dict(w=7.5, bank=0, curb=1.0, wallL='wall', wallR='wall', run=3.0, edge='grass'),
               start=(0, 0), heading=0)            # heading：度，0＝往 +x，90＝往 +z（面朝 +x 時 +z 在右手邊）
    c.go(150, tag='start_straight', w=9.5)         # 直線 150 m；之後的點都套用 w=9.5（屬性會一路延續，直到下次改）
    c.turn(60, -90, y=4)                            # 半徑 60、右轉 90°（負＝右轉、正＝左轉），彎道終點高度 4 m
    c.go(None, free=True)                           # 長度待定：最後 c.close() 會解這兩段的長度，讓迴圈接回起點
    ...
    c.close()                                       # 檢查總轉角＝±360°，解 free 直線長度，補高度
    c.boost('hp1', frac=0.5, d=-3, len=10, w=2.5)  # 加速帶：在 tag 那一段的 frac 位置（0＝段首、1＝段尾）
    c.shortcut('a', 'b', via=[(x, z, y), ...], w=3.5, surf='dirt')
    c.hazard('water', [(x, z), ...], y=-1)
    c.prop('lighthouse', 'tagname', frac=0.5, d=30)
    c.write()

高度：每一段可以給 y（段尾的絕對高度）；沒給的沿距離線性內插。轉彎段給 flat=True 時整個彎維持段首高度（髮夾彎用）。
跳台：c.go(22, y=..., gap=True) 這一段沒有路面（段首點標 gap，段內不加點）。
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, 'blender')

ONE_SHOT = {'gap', 'gapFill'}  # 只套用在這一點、不往後延續的屬性


class Course:
    def __init__(self, id, name, theme, difficulty, laps, defaults, look=None, note='', start=(0.0, 0.0), heading=0.0, y0=0.0):
        self.id, self.name, self.theme, self.look = id, name, theme, look
        self.difficulty, self.laps, self.note = difficulty, laps, note
        self.DEF = dict(defaults)
        self.start = (float(start[0]), float(start[1]))
        self.h0 = float(heading)
        self.y0 = float(y0)
        self.segs = []
        self.extra = dict(boost=[], shortcuts=[], hazards=[], props=[])
        self.closed = False

    # ------------------------------------------------------------ 描述路線
    def go(self, L, y=None, tag=None, free=False, gap=False, step=40.0, **attrs):
        """直線 L 公尺（free=True 時 L 由 close() 解）。"""
        self.segs.append(dict(kind='S', L=L, y=y, tag=tag, free=free, gap=gap, step=step, a=attrs))
        return self

    def turn(self, R, deg, y=None, tag=None, flat=False, step=15.0, **attrs):
        """圓弧：半徑 R，轉 deg 度（正＝左轉、負＝右轉）。
        座標慣例（跟遊戲一致）：面朝 +x 時 +z 在右手邊；內部的 heading 從 +x 往 +z 量（往右轉為正），所以這裡存 -deg。"""
        self.segs.append(dict(kind='A', R=float(R), deg=-float(deg), y=y, tag=tag, flat=flat, step=step, a=attrs))
        return self

    def hairpin(self, R, side, y=None, tag=None, **attrs):
        """180° 髮夾：side='L' 或 'R'。"""
        return self.turn(R, 180 if side == 'L' else -180, y=y, tag=tag, **attrs)

    # ------------------------------------------------------------ 幾何
    def _walk(self, lens):
        """依段長展開成取樣點。回傳 [(x, z, heading_deg, seg_index, t_in_seg)] 與每段起點的座標。"""
        x, z = self.start
        h = self.h0
        pts = []
        seg_start = []
        for i, s in enumerate(self.segs):
            seg_start.append((x, z, h))
            if s['kind'] == 'S':
                L = lens[i]
                n = 1 if s['gap'] else max(1, int(math.ceil(L / s['step'])))
                dx, dz = math.cos(math.radians(h)), math.sin(math.radians(h))
                for k in range(n):
                    t = k / n
                    pts.append((x + dx * L * t, z + dz * L * t, h, i, t))
                x += dx * L
                z += dz * L
            else:
                R, deg = s['R'], s['deg']
                sg = 1 if deg > 0 else -1
                # 圓心在前進方向的左（左轉）或右（右轉）
                cx = x + R * math.cos(math.radians(h + 90 * sg))
                cz = z + R * math.sin(math.radians(h + 90 * sg))
                a0 = math.degrees(math.atan2(z - cz, x - cx))
                n = max(2, int(math.ceil(abs(deg) / s['step'])))
                for k in range(n):
                    t = k / n
                    a = math.radians(a0 + deg * t)
                    pts.append((cx + R * math.cos(a), cz + R * math.sin(a), h + deg * t, i, t))
                a = math.radians(a0 + deg)
                x, z = cx + R * math.cos(a), cz + R * math.sin(a)
                h += deg
        return pts, seg_start, (x, z, h)

    def _seg_len(self, s, L=None):
        if s['kind'] == 'S':
            return L if L is not None else s['L']
        return abs(math.radians(s['deg'])) * s['R']

    def close(self):
        tot = sum(s['deg'] for s in self.segs if s['kind'] == 'A')
        if abs(tot - 360 * round(tot / 360)) > 0.01 or abs(round(tot / 360)) > 1:
            raise ValueError(f'{self.id}: 總轉角 {tot:.2f}°，要是 ±360°（一般迴圈）或 0°（8 字形）')
        free = [i for i, s in enumerate(self.segs) if s['kind'] == 'S' and s['free']]
        if len(free) != 2:
            raise ValueError(f'{self.id}: 要剛好兩段 free 直線，現在 {len(free)} 段')
        lens = [s.get('L') or 0.0 for s in self.segs]
        for i in free:
            lens[i] = 0.0
        _, ss, (ex, ez, _) = self._walk(lens)
        # 兩段 free 直線的方向（與長度無關）
        d = [(math.cos(math.radians(ss[i][2])), math.sin(math.radians(ss[i][2]))) for i in free]
        rx, rz = self.start[0] - ex, self.start[1] - ez
        det = d[0][0] * d[1][1] - d[0][1] * d[1][0]
        if abs(det) < 1e-6:
            raise ValueError(f'{self.id}: 兩段 free 直線平行，解不出來')
        L1 = (rx * d[1][1] - rz * d[1][0]) / det
        L2 = (d[0][0] * rz - d[0][1] * rx) / det
        if L1 < 5 or L2 < 5:
            raise ValueError(f'{self.id}: free 直線解出負的或太短（{L1:.1f}, {L2:.1f}），調整其他段')
        lens[free[0]], lens[free[1]] = L1, L2
        self.lens = lens
        self.free_lens = (round(L1, 1), round(L2, 1))
        self._build()
        self.closed = True
        return self

    def _build(self):
        pts, ss, _ = self._walk(self.lens)
        # 每段的起點沿線距離
        cum = []
        s = 0.0
        for i, sg in enumerate(self.segs):
            cum.append(s)
            s += self._seg_len(sg, self.lens[i])
        self.total = s
        self.seg_s = cum
        # 高度：段尾給 y 的當錨點
        anchors = [(0.0, self.y0)]
        for i, sg in enumerate(self.segs):
            end = cum[i] + self._seg_len(sg, self.lens[i])
            if sg['y'] is not None:
                anchors.append((end, float(sg['y'])))
            elif sg['kind'] == 'A' and sg.get('flat'):
                # 平的彎：前一段要有給 y（段首高度確定），整個彎維持那個高度
                if abs(anchors[-1][0] - cum[i]) > 1e-6:
                    raise ValueError(f'{self.id}: flat 彎（第 {i} 段 {sg.get("tag")}）前一段要給 y')
                anchors.append((end, anchors[-1][1]))
        if abs(anchors[-1][0] - self.total) > 1e-6:
            anchors.append((self.total, self.y0))
        elif abs(anchors[-1][1] - self.y0) > 0.05:
            raise ValueError(f'{self.id}: 最後一段 y={anchors[-1][1]}，要回到起點高度 {self.y0}')

        def y_at(sv):
            for (s0, y0), (s1, y1) in zip(anchors, anchors[1:]):
                if s0 <= sv <= s1 + 1e-9:
                    return y0 if s1 - s0 < 1e-9 else y0 + (y1 - y0) * (sv - s0) / (s1 - s0)
            return anchors[-1][1]
        # flat 彎：整段維持段首高度（錨點內插時跳過它）
        self.points, self.tagidx = [], {}
        cur = dict(self.DEF)
        last_seg = -1
        for (x, z, h, i, t) in pts:
            sg = self.segs[i]
            sv = cum[i] + self._seg_len(sg, self.lens[i]) * t
            if sg['kind'] == 'A' and sg.get('flat'):
                y = y_at(cum[i])
            else:
                y = y_at(sv)
            q = {'p': [round(x, 2), round(z, 2), round(y, 2)]}
            if i != last_seg:
                persist = {k: v for k, v in sg['a'].items() if k not in ONE_SHOT}
                cur.update(persist)
                if sg['tag']:
                    self.tagidx[sg['tag']] = len(self.points)
                last_seg = i
            for k, v in cur.items():
                if self.DEF.get(k) != v:
                    q[k] = v
            if t == 0:
                for k in ONE_SHOT:
                    if k in sg['a']:
                        q[k] = sg['a'][k]
                if sg['kind'] == 'S' and sg['gap']:
                    q['gap'] = True
            self.points.append(q)
        # tag 段的終點索引（下一段的第一點）
        self.tagend = {}
        firsts = {}
        for idx, (_, _, _, i, t) in enumerate(pts):
            firsts.setdefault(i, idx)
        for i, sg in enumerate(self.segs):
            if sg['tag']:
                self.tagend[sg['tag']] = firsts.get(i + 1, len(pts))

    # ------------------------------------------------------------ 位置查詢（給捷徑、物件用）
    def at(self, tag, frac=0.0):
        """tag 那一段 frac 處的 layout 'at'（控制點索引＋小數）。"""
        a, b = self.tagidx[tag], self.tagend[tag]
        v = a + (b - a) * frac
        return round(v, 3)

    def pos(self, tag, frac=0.0, d=0.0):
        """tag 那一段 frac 處的中心線座標 (x, z, y)，d＝往右偏移。近似：在控制點之間線性內插。"""
        v = self.at(tag, frac)
        i = int(math.floor(v))
        f = v - i
        n = len(self.points)
        p0, p1 = self.points[i % n]['p'], self.points[(i + 1) % n]['p']
        x, z, y = (p0[k] + (p1[k] - p0[k]) * f for k in range(3))
        if d:
            tx, tz = p1[0] - p0[0], p1[1] - p0[1]
            ll = math.hypot(tx, tz) or 1
            # 右方：面朝 +x 時右手邊是 +z → 右向量 (-tz, tx)
            x += -tz / ll * d
            z += tx / ll * d
        return (round(x, 2), round(z, 2), round(y, 2))

    def boost(self, tag, frac=0.5, d=0.0, len=10, w=2.5):
        self.extra['boost'].append(dict(at=self.at(tag, frac), d=d, len=len, w=w))

    def shortcut(self, tag_from, tag_to, via, w=3.5, surf='dirt', ffrac=0.0, tfrac=0.0, **kw):
        self.extra['shortcuts'].append(dict(**{'from': self.at(tag_from, ffrac), 'to': self.at(tag_to, tfrac)},
                                            via=[list(map(lambda v: round(v, 2), p)) for p in via], w=w, surf=surf, **kw))

    def hazard(self, type, poly, y):
        self.extra['hazards'].append(dict(type=type, y=y, poly=[[round(a, 1), round(b, 1)] for a, b in poly]))

    def prop(self, kind, tag, frac=0.5, d=0.0, rot=0):
        self.extra['props'].append(dict(kind=kind, at=self.at(tag, frac), d=d, rot=rot))

    # ------------------------------------------------------------ 輸出
    def write(self):
        if not self.closed:
            self.close()
        lay = dict(id=self.id, name=self.name, theme=self.theme)
        if self.look:
            lay['look'] = self.look
        lay.update(difficulty=self.difficulty, laps=self.laps, note=self.note, defaults=self.DEF, points=self.points,
                   boost=self.extra['boost'], shortcuts=self.extra['shortcuts'], hazards=self.extra['hazards'], props=self.extra['props'])
        # 每段 tag 的沿線距離（設計值，跟實際中心線差幾公尺；給 tools/sim_walls.mjs 標位置用，產生器不讀）
        lay['tags'] = {sg['tag']: [round(self.seg_s[i]), round(self.seg_s[i] + self._seg_len(sg, self.lens[i]))]
                       for i, sg in enumerate(self.segs) if sg['tag']}
        out = os.path.join(OUT_DIR, f'{self.id}_layout.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(lay, f, ensure_ascii=False, indent=1)
        ys = [p['p'][2] for p in self.points]
        print(f'{self.id}: {len(self.points)} 點、約 {self.total:.0f} m、高度 {min(ys):.1f}～{max(ys):.1f}、free 直線 {self.free_lens} → {out}')
        return out

    def sketch(self, png=None, free_guess=100.0):
        """俯視草圖（PIL）：路線依高度上色（藍低→紅高）、標出每段 tag、起點；還沒 close 時 free 直線用 free_guess 長度畫，並畫出到起點的缺口。"""
        from PIL import Image, ImageDraw, ImageFont
        lens = getattr(self, 'lens', None) or [(s.get('L') if s.get('L') is not None else free_guess) if s['kind'] == 'S' else 0 for s in self.segs]
        pts, ss, end = self._walk(lens)
        ys = None
        if getattr(self, 'points', None) and len(self.points) == len(pts):
            ys = [p['p'][2] for p in self.points]
        xs = [p[0] for p in pts] + [self.start[0], end[0]]
        zs = [p[1] for p in pts] + [self.start[1], end[1]]
        x0, x1, z0, z1 = min(xs) - 40, max(xs) + 40, min(zs) - 40, max(zs) + 40
        S = 1400 / max(x1 - x0, z1 - z0)
        W, H = int((x1 - x0) * S) + 1, int((z1 - z0) * S) + 1
        im = Image.new('RGB', (W, H), (245, 245, 240))
        d = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype('msjh.ttc', 16)
        except Exception:
            font = ImageFont.load_default()
        P = lambda x, z: ((x - x0) * S, (z - z0) * S)  # noqa: E731  （+z 往下畫：面朝 +x 時右手邊在畫面下方，跟遊戲小地圖一樣右轉＝順時針）
        for g in range(int(x0 // 100) * 100, int(x1) + 1, 100):
            d.line([P(g, z0), P(g, z1)], fill=(225, 225, 220))
        for g in range(int(z0 // 100) * 100, int(z1) + 1, 100):
            d.line([P(x0, g), P(x1, g)], fill=(225, 225, 220))
        ymin = min(ys) if ys else 0
        ymax = max(ys) if ys else 1
        for k in range(len(pts)):
            a = pts[k]
            b = pts[k + 1] if k + 1 < len(pts) else (end[0], end[1])
            t = ((ys[k] - ymin) / max(1e-6, ymax - ymin)) if ys else 0.5
            col = (int(40 + 200 * t), 60, int(220 - 180 * t))
            gap = self.segs[a[3]]['kind'] == 'S' and self.segs[a[3]].get('gap')
            d.line([P(a[0], a[1]), P(b[0], b[1])], fill=(255, 0, 255) if gap else col, width=5)
        for i, sg in enumerate(self.segs):
            if sg['tag']:
                x, z, _ = ss[i]
                d.ellipse([P(x, z)[0] - 3, P(x, z)[1] - 3, P(x, z)[0] + 3, P(x, z)[1] + 3], fill=(0, 0, 0))
                lab = sg['tag'] + (f' {ys[[q[3] for q in pts].index(i)]:.0f}m' if ys else '')
                d.text((P(x, z)[0] + 5, P(x, z)[1] - 8), lab, fill=(0, 0, 0), font=font)
        sx, sz = P(*self.start)
        d.rectangle([sx - 6, sz - 6, sx + 6, sz + 6], outline=(0, 160, 0), width=3)
        if not getattr(self, 'closed', False):
            d.line([P(end[0], end[1]), (sx, sz)], fill=(255, 0, 0), width=2)
        png = png or os.path.join(HERE, '..', 'tmp_layout', f'{self.id}_sketch.png')
        os.makedirs(os.path.dirname(png), exist_ok=True)
        im.save(png)
        return os.path.normpath(png)

    def report_tags(self):
        for k in self.tagidx:
            print(f'  {k:16s} at {self.tagidx[k]}～{self.tagend[k]}  pos {self.pos(k, 0)}')
