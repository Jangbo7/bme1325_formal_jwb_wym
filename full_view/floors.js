import { ELEVATOR_SPAWN } from "./layout.js";

export const FLOORS = [
  {
    id: 1,
    label: "1F Emergency",
    shortLabel: "1F",
    subtitle: "Aligned emergency floor with intake, rescue, consult rooms, entrance, and bottom-right elevator.",
    spawn: ELEVATOR_SPAWN,
    departmentKinds: ["emergency"],
  },
  {
    id: 2,
    label: "2F Outpatient",
    shortLabel: "2F",
    subtitle: "Outpatient office grid aligned with registration, triage, consultation, lab, and pharmacy nodes.",
    spawn: ELEVATOR_SPAWN,
    departmentKinds: ["outpatient", "pharmacy", "lab"],
  },
  {
    id: 3,
    label: "3F ICU",
    shortLabel: "3F",
    subtitle: "Aligned ICU floor with station, monitored beds, support, and bottom-right elevator.",
    spawn: ELEVATOR_SPAWN,
    departmentKinds: ["icu"],
  },
  {
    id: 4,
    label: "4F MDT",
    shortLabel: "4F",
    subtitle: "Aligned MDT floor with meeting, imaging review, specialist planning, and elevator.",
    spawn: ELEVATOR_SPAWN,
    departmentKinds: ["mdt"],
  },
  {
    id: 5,
    label: "5F Ward",
    shortLabel: "5F",
    subtitle: "Aligned inpatient floor with nurse station, wards, doctor office, and elevator.",
    spawn: ELEVATOR_SPAWN,
    departmentKinds: ["ward"],
  },
];
