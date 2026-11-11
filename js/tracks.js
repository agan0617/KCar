// 賽道清單（照難度排）。模型、中心線、碰撞由 tools/blender/<id>_layout.json 經 build_track2.py 產生（格式見 tools/blender/TRACK_V2.md）。
// difficulty：顯示的星等；ai：電腦車手強度用的難度（省略＝difficulty，可以有小數）。
export const TRACKS = [
  { id: 'beach', name: '椰林海灘', difficulty: 1, laps: 3 },
  { id: 'sakura', name: '櫻花古都', difficulty: 2, laps: 3 },
  { id: 'snow', name: '雪國山道', difficulty: 3, laps: 3 },
  { id: 'city', name: '霓虹夜城', difficulty: 4, laps: 3 },
  { id: 'volcano', name: '熔岩火山', difficulty: 5, laps: 3 },
];

export const trackById = (id) => TRACKS.find((t) => t.id === id) || TRACKS[0];
export const aiLevel = (meta) => meta.ai ?? meta.difficulty;
