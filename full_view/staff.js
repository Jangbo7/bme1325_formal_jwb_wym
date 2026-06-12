import { placeInRoom } from "./placement.js";

export const STAFF = [
  nurse("nurse-er-a", "ed_registration", "female", 0.46, 0.58, "standing"),
  nurse("nurse-er-b", "ed_bedside_nurse", "male", 0.30, 0.60, "walking"),
  doctor("doctor-er-a", "ed_doctor_room", "male", 0.28, 0.58, "standing"),
  doctor("doctor-er-b", "ed_red_resus", "female", 0.50, 0.58, "standing"),

  nurse("nurse-op-reg", "registration_2", "female", 0.56, 0.58, "standing"),
  nurse("nurse-op-triage", "triage_2", "male", 0.56, 0.58, "standing"),
  doctor("doctor-op-a", "consultation_a_2", "female", 0.84, 0.58, "seated"),
  doctor("doctor-op-b", "consultation_b_2", "male", 0.84, 0.58, "seated"),
  doctor("doctor-op-internal", "internal_2", "male", 0.56, 0.58, "seated"),
  doctor("doctor-op-surgery", "surgery_2", "female", 0.56, 0.58, "standing"),
  nurse("nurse-op-wait", "outpatient_waiting", "female", 0.45, 0.60, "walking"),

  nurse("nurse-icu-station-a", "icu_station", "female", 0.30, 0.58, "standing"),
  nurse("nurse-icu-station-b", "icu_station", "male", 0.62, 0.58, "standing"),
  doctor("doctor-icu-bed-a", "icu_beds_a", "female", 0.58, 0.58, "monitoring"),
  doctor("doctor-icu-bed-b", "icu_beds_b", "male", 0.58, 0.58, "monitoring"),
  nurse("nurse-icu-isolation", "icu_isolation", "female", 0.58, 0.58, "monitoring"),

  doctor("doctor-mdt-a", "head_doctor", "female", 0.50, 0.58, "seated"),
  doctor("doctor-mdt-b", "mdt_meeting", "male", 0.50, 0.58, "seated"),
  doctor("doctor-mdt-c", "imaging_review", "female", 0.50, 0.58, "standing"),
  nurse("nurse-mdt-coord", "final_plan", "female", 0.50, 0.58, "standing"),

  nurse("nurse-ward-station-a", "nurse_station", "female", 0.30, 0.58, "standing"),
  nurse("nurse-ward-station-b", "nurse_station", "male", 0.62, 0.58, "walking"),
  doctor("doctor-ward-office", "doctor_office", "male", 0.28, 0.58, "standing"),
  doctor("doctor-ward-round", "resp_ward", "female", 0.42, 0.58, "monitoring"),
  nurse("nurse-ward-room-c", "gensurg_ward", "female", 0.28, 0.58, "monitoring"),
];

export function getStaffForFloor(floorId) {
  return STAFF.filter((staff) => staff.floor === floorId);
}

export function reflowStaffPlacements() {
  STAFF.forEach((member) => {
    try {
      const placement = placeInRoom(member.roomId, member.relX, member.relY);
      member.floor = placement.floor;
      member.x = placement.x;
      member.y = placement.y;
    } catch {
      member.floor = -1;
    }
  });
}

function doctor(id, roomId, gender, relX, relY, pose) {
  return staff(id, roomId, "doctor", gender, relX, relY, pose);
}

function nurse(id, roomId, gender, relX, relY, pose) {
  return staff(id, roomId, "nurse", gender, relX, relY, pose);
}

function staff(id, roomId, role, gender, relX, relY, pose) {
  const placement = placeInRoom(roomId, relX, relY);
  return {
    id,
    floor: placement.floor,
    role,
    gender,
    pose,
    roomId,
    relX,
    relY,
    x: placement.x,
    y: placement.y,
    phase: id.length * 0.29,
  };
}
