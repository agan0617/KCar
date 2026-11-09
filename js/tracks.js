// 賽道清單（照難度排）。模型與中心線由 tools/blender/<id>_layout.json 經 Blender 產生。
export const TRACKS = [
  { id: 'beach', name: '椰林海灘', difficulty: 1, laps: 3 },
  { id: 'hills', name: '陽光山丘', difficulty: 2, laps: 3 },
  { id: 'desert', name: '仙人掌峽谷', difficulty: 3, laps: 3 },
  { id: 'snow', name: '雪國山道', difficulty: 4, laps: 3 },
  { id: 'city', name: '霓虹夜城', difficulty: 4, laps: 3 },
  { id: 'volcano', name: '熔岩火山', difficulty: 5, laps: 3 },
];

export const trackById = (id) => TRACKS.find((t) => t.id === id) || TRACKS[0];
