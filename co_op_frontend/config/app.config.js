export const APP_CONFIG = {
  title: "Hospital Co-op Frontend Kit",
  api: {
    baseUrl: "http://127.0.0.1:8787",
    apiKey: "mock-key-001",
    timeoutMs: 20000,
  },
  controls: {
    interactKey: "KeyE",
    exitKey: "KeyQ",
  },
  scene: {
    tileSize: 32,
    canvasWidth: 1440,
    canvasHeight: 900,
    campusTiles: { width: 84, height: 54 },
    playerSpawn: { x: 42 * 32, y: 47 * 32 },
    mainGate: { x: 42 * 32, y: 47 * 32 },
    objectiveRoomId: "consultation-a",
    highlightColor: "#ffbf5d",
  },
  assets: {
    grassTile: "./assets/textures/grass-tile.svg",
    wallTile: "./assets/textures/wall-tile.svg",
    deskTile: "./assets/textures/desk.svg",
    clinicFloorTile: "./assets/textures/clinic-floor-checker.svg",
    doctorSprite: "./assets/sprites/doctor-redcross.svg",
    patientSprites: [
      "./assets/sprites/patient-blue.svg",
      "./assets/sprites/patient-green.svg",
      "./assets/sprites/patient-orange.svg",
      "./assets/sprites/patient-purple.svg",
      "./assets/sprites/patient-red.svg",
    ],
  },
};
