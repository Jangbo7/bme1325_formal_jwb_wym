import { placeInRoom } from "./placement.js";

export const PATIENTS = [
  // Walking patients use room-relative anchors so layout edits keep them inside valid areas.
  walkingPatient("walk-er-1", "ed_pager", 0.55, 0.52, "#5f8ec9"),
  walkingPatient("walk-op-1", "outpatient_waiting", 0.78, 0.55, "#5f8ec9"),
  walkingPatient("walk-mdt-1", "mdt_lounge", 0.62, 0.55, "#8f7ed0"),

  // Waiting patients in waiting areas.
  waitingPatient("wait-er-1", "ed_waiting", 0.36, 0.62, "#7899c6"),
  waitingPatient("wait-er-2", "ed_waiting", 0.64, 0.62, "#c69072"),
  waitingPatient("wait-op-1", "outpatient_waiting", 0.32, 0.62, "#7899c6"),
  waitingPatient("wait-op-2", "outpatient_waiting", 0.58, 0.62, "#c69072"),
  waitingPatient("wait-ward-1", "ward_admission", 0.72, 0.58, "#7fa98f"),

  // Outpatient consultation scenes.
  consultationPatient("consult-a", "consultation_a_2", 0.72, 0.56, "#5f8ec9", "female", "doctor-op-a"),
  consultationPatient("consult-b", "consultation_b_2", 0.72, 0.56, "#8a79c9", "male", "doctor-op-b"),
  consultationPatient("consult-int", "internal_2", 0.42, 0.58, "#5f8ec9", "male", "doctor-op-internal"),

  // Bed patients in ICU and ward.
  bedPatient("icu-bed-a", "icu_beds_a", 0.20, 0.40, "#f2c799", "#d46d8e"),
  bedPatient("icu-bed-b", "icu_beds_b", 0.20, 0.40, "#f2c799", "#d46d8e"),
  bedPatient("icu-isolation", "icu_isolation", 0.20, 0.40, "#f2c799", "#cf6f8c"),
  bedPatient("ward-bed-a", "resp_ward", 0.20, 0.40, "#f2c799", "#76c59d"),
  bedPatient("ward-bed-b", "card_ward", 0.20, 0.40, "#f2c799", "#76c59d"),
  bedPatient("ward-bed-c", "peds_ward", 0.20, 0.40, "#f2c799", "#76c59d"),
];

export function getPatientsForFloor(floorId) {
  return PATIENTS.filter((patient) => patient.floor === floorId);
}

function bedPatient(id, roomId, relX, relY, skin, blanket) {
  return basePatient(id, roomId, "bed", relX, relY, { skin, blanket });
}

function consultationPatient(id, roomId, relX, relY, color, doctorGender, doctorProfileId) {
  return basePatient(id, roomId, "consultation", relX, relY, { color, doctorGender, doctorProfileId });
}

function waitingPatient(id, roomId, relX, relY, color) {
  return basePatient(id, roomId, "waiting", relX, relY, { color });
}

function walkingPatient(id, roomId, relX, relY, color) {
  return basePatient(id, roomId, "walking", relX, relY, { color, phase: id.length * 0.37 });
}

function basePatient(id, roomId, form, relX, relY, style) {
  const placement = placeInRoom(roomId, relX, relY);
  return {
    id,
    floor: placement.floor,
    form,
    roomId,
    relX,
    relY,
    x: placement.x,
    y: placement.y,
    ...style,
  };
}
