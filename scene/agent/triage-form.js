export function buildTriagePayloadFromFormValues({ fields, zoneLabel, floor }) {
  const symptoms = fields.symptoms?.value?.trim() || "unspecified symptoms";
  const temp = Number.parseFloat(fields.temp?.value ?? "37.8");
  const heartRate = Number.parseInt(fields.heartRate?.value ?? "105", 10);
  const systolic = Number.parseInt(fields.systolic?.value ?? "132", 10);
  const diastolic = Number.parseInt(fields.diastolic?.value ?? "86", 10);
  const pain = Number.parseInt(fields.pain?.value ?? "5", 10);

  return {
    patient_id: "P-self",
    name: "You (Player)",
    symptoms,
    vitals: {
      temp_c: Number.isFinite(temp) ? temp : 37.8,
      heart_rate: Number.isFinite(heartRate) ? heartRate : 105,
      systolic_bp: Number.isFinite(systolic) ? systolic : 132,
      diastolic_bp: Number.isFinite(diastolic) ? diastolic : 86,
      pain_score: Number.isFinite(pain) ? Math.max(0, Math.min(10, pain)) : 5,
    },
    location: zoneLabel,
    floor,
  };
}
