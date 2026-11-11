// Node 端（server、模擬工具）讀賽道資料：中心線＋碰撞（v2 賽道才有 _col.json）
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

export function readTrackData(root, id) {
  const data = JSON.parse(readFileSync(join(root, 'assets', id + '_path.json'), 'utf8'));
  const cp = join(root, 'assets', id + '_col.json');
  if (existsSync(cp)) data.col = JSON.parse(readFileSync(cp, 'utf8'));
  return data;
}
