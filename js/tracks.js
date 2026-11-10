// 賽道清單（照難度排）。模型與中心線由 tools/blender/<id>_layout.json 經 Blender 產生。
// difficulty：顯示的星等；ai：電腦車手強度用的難度（省略＝difficulty，可以有小數）。
// 甩尾彎多的賽道，電腦不甩就撞牆，同樣強度會顯得特別弱，所以用 ai 把牠們調回跟同星等賽道相近。
export const TRACKS = [
  { id: 'beach', name: '椰林海灘', difficulty: 1, laps: 3 },
  { id: 'hills', name: '陽光山丘', difficulty: 2, laps: 3 },
  { id: 'sakura', name: '櫻花古都', difficulty: 2, ai: 2.9, laps: 3 },
  { id: 'desert', name: '仙人掌峽谷', difficulty: 3, laps: 3 },
  { id: 'autumn', name: '秋楓山谷', difficulty: 3, ai: 3.9, laps: 3 },
  { id: 'snow', name: '雪國山道', difficulty: 4, laps: 3 },
  { id: 'city', name: '霓虹夜城', difficulty: 4, laps: 3 },
  { id: 'candy', name: '糖果樂園', difficulty: 4, laps: 3 },
  { id: 'volcano', name: '熔岩火山', difficulty: 5, laps: 3 },
  { id: 'harbor', name: '星空港灣', difficulty: 5, laps: 3 },
];

export const trackById = (id) => TRACKS.find((t) => t.id === id) || TRACKS[0];
export const aiLevel = (meta) => meta.ai ?? meta.difficulty;
