// 游戏对象定义

// 玩家对象
export const player = {
  x: 8 * 32, // 8 * TILE
  y: 10 * 32, // 10 * TILE
  width: 18,
  height: 18,
  speed: 180,
};

// 房间定义
export const rooms = [
  { x: 3, y: 4, w: 11, h: 8, kind: "ward" },
  { x: 15, y: 3, w: 10, h: 7, kind: "pharmacy" },
  { x: 27, y: 4, w: 11, h: 9, kind: "office" },
  { x: 3, y: 14, w: 13, h: 10, kind: "emergency" },
  { x: 18, y: 13, w: 12, h: 11, kind: "hall" },
  { x: 32, y: 15, w: 12, h: 10, kind: "rest" },
  { x: 11, y: 26, w: 12, h: 7, kind: "lab" },
  { x: 26, y: 27, w: 14, h: 6, kind: "icu" },
];

// 门的定义
export const doorSpecs = [
  { roomIndex: 0, side: "right", offset: 2.5, length: 2, label: "WARD-A" },
  { roomIndex: 0, side: "bottom", offset: 4.5, length: 2, label: "WARD-B" },
  { roomIndex: 1, side: "right", offset: 2, length: 2, label: "PHARM-1" },
  { roomIndex: 1, side: "bottom", offset: 4, length: 2, label: "PHARM-2" },
  { roomIndex: 2, side: "left", offset: 3, length: 2, label: "OFFICE-A" },
  { roomIndex: 2, side: "bottom", offset: 4.5, length: 2, label: "OFFICE-B" },
  { roomIndex: 3, side: "top", offset: 5, length: 2, label: "ER-A" },
  { roomIndex: 3, side: "right", offset: 4.5, length: 2, label: "ER-B" },
  { roomIndex: 4, side: "left", offset: 4.5, length: 2, label: "LOBBY-W" },
  { roomIndex: 4, side: "right", offset: 4.5, length: 2, label: "LOBBY-E" },
  { roomIndex: 4, side: "bottom", offset: 4, length: 2, label: "LOBBY-S" },
  { roomIndex: 5, side: "left", offset: 4, length: 2, label: "REST-A" },
  { roomIndex: 5, side: "bottom", offset: 4.5, length: 2, label: "REST-B" },
  { roomIndex: 6, side: "top", offset: 4.5, length: 2, label: "LAB-A" },
  { roomIndex: 6, side: "right", offset: 2.5, length: 2, label: "LAB-B" },
  { roomIndex: 7, side: "left", offset: 2, length: 2, label: "ICU-A" },
  { roomIndex: 7, side: "top", offset: 5.5, length: 2, label: "ICU-B" },
];

// 道具定义
export const props = [
  { x: 5.2, y: 5.3, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { x: 8.2, y: 5.3, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { x: 5.4, y: 8.2, w: 1.2, h: 1.2, type: "plant", z: 24 },
  { x: 9.2, y: 8.3, w: 1.7, h: 1.1, type: "cabinet", z: 28 },
  { x: 17.3, y: 4.8, w: 3.2, h: 1.2, type: "reception", z: 22 },
  { x: 19.6, y: 7.3, w: 1.2, h: 1.2, type: "screen", z: 26 },
  { x: 29.2, y: 5.2, w: 2.2, h: 1.1, type: "desk", z: 20 },
  { x: 33.1, y: 5.2, w: 1.2, h: 1.2, type: "plant", z: 24 },
  { x: 34.2, y: 8.2, w: 2.1, h: 1.2, type: "sofa", z: 18 },
  { x: 5.2, y: 16.2, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { x: 8.6, y: 16.1, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { x: 6.1, y: 19.3, w: 1.2, h: 1.2, type: "screen", z: 26 },
  { x: 11.0, y: 20.2, w: 2.5, h: 1.2, type: "cabinet", z: 28 },
  { x: 21.2, y: 15.2, w: 4.3, h: 1.4, type: "reception", z: 22 },
  { x: 20.2, y: 19.4, w: 1.5, h: 1.1, type: "desk", z: 20 },
  { x: 24.1, y: 19.2, w: 1.5, h: 1.1, type: "desk", z: 20 },
  { x: 34.2, y: 17.3, w: 2.1, h: 1.2, type: "sofa", z: 18 },
  { x: 38.4, y: 17.2, w: 1.2, h: 1.2, type: "plant", z: 24 },
  { x: 35.2, y: 20.4, w: 3.0, h: 1.1, type: "desk", z: 20 },
  { x: 13.2, y: 27.2, w: 1.4, h: 1.4, type: "screen", z: 26 },
  { x: 16.2, y: 27.3, w: 2.6, h: 1.1, type: "cabinet", z: 28 },
  { x: 28.1, y: 28.2, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { x: 32.0, y: 28.2, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { x: 36.0, y: 28.3, w: 1.2, h: 1.2, type: "screen", z: 26 },
];
