export function createMedicalRecordPresenter(medicalRecord) {
  return {
    syncPatientData({ patient, visit }) {
      if (!patient) {
        medicalRecord.patientInfo = null;
        medicalRecord.triageInfo = null;
        medicalRecord.consultationInfo = null;
        medicalRecord.testInfo = null;
        return;
      }

      // 患者基本信息
      medicalRecord.patientInfo = {
        id: patient.id || "-",
        name: patient.name || "未知患者",
        age: patient.age || "-",
        gender: patient.gender || "-"
      };

      // 分诊信息
      if (patient.triage_data) {
        medicalRecord.triageInfo = {
          level: patient.triage_data.level || "-",
          department: patient.triage_data.department || "-",
          symptoms: patient.triage_data.symptoms || "-",
          vitalSigns: {
            temperature: patient.triage_data.temperature || "-",
            heartRate: patient.triage_data.heart_rate || "-",
            bloodPressure: patient.triage_data.blood_pressure || "-"
          },
          timestamp: patient.triage_data.timestamp || new Date().toISOString()
        };
      }

      // 问诊信息
      if (visit?.data?.internal_medicine_data) {
        const imData = visit.data.internal_medicine_data;
        medicalRecord.consultationInfo = {
          doctor: imData.doctor_name || "医生",
          diagnosis: imData.diagnosis || "-",
          prescription: imData.prescription || [],
          notes: imData.notes || "-",
          timestamp: imData.timestamp || new Date().toISOString()
        };
      }

      // 检查报告信息
      if (visit?.data?.simulated_report) {
        const report = visit.data.simulated_report;
        medicalRecord.testInfo = {
          category: report.category_label || "-",
          items: report.test_items || [],
          report: report.report_text || "-",
          timestamp: report.generated_at || new Date().toISOString()
        };
      }
    },
    clear() {
      medicalRecord.patientInfo = null;
      medicalRecord.triageInfo = null;
      medicalRecord.consultationInfo = null;
      medicalRecord.testInfo = null;
    }
  };
}

export function renderMedicalRecord(ctx, medicalRecord, canvas, camera) {
  if (!medicalRecord.patientInfo) {
    return;
  }

  const panelWidth = 380;
  const panelHeight = 420;
  const panelX = 16;
  const panelY = canvas.height - panelHeight - 16;

  // 绘制面板背景
  ctx.fillStyle = "rgba(16, 11, 24, 0.86)";
  ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
  ctx.strokeStyle = "rgba(174, 129, 255, 0.72)";
  ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);

  // 标题
  ctx.textAlign = "left";
  ctx.font = "14px 'Segoe UI'";
  ctx.fillStyle = "#d8b8ff";
  ctx.fillText("病历卡", panelX + 12, panelY + 22);

  let yOffset = 40;
  const lineHeight = 16;
  const sectionSpacing = 24;

  // 患者信息
  drawSection(ctx, "患者信息", panelX, panelY + yOffset, panelWidth);
  yOffset += 20;
  drawInfoLine(ctx, "ID:", medicalRecord.patientInfo.id, panelX, panelY + yOffset, panelWidth);
  yOffset += lineHeight;
  drawInfoLine(ctx, "姓名:", medicalRecord.patientInfo.name, panelX, panelY + yOffset, panelWidth);
  yOffset += lineHeight;
  drawInfoLine(ctx, "年龄:", medicalRecord.patientInfo.age, panelX, panelY + yOffset, panelWidth);
  yOffset += lineHeight;
  drawInfoLine(ctx, "性别:", medicalRecord.patientInfo.gender, panelX, panelY + yOffset, panelWidth);
  yOffset += sectionSpacing;

  // 分诊信息
  if (medicalRecord.triageInfo) {
    drawSection(ctx, "分诊信息", panelX, panelY + yOffset, panelWidth);
    yOffset += 20;
    drawInfoLine(ctx, "级别:", medicalRecord.triageInfo.level, panelX, panelY + yOffset, panelWidth);
    yOffset += lineHeight;
    drawInfoLine(ctx, "科室:", medicalRecord.triageInfo.department, panelX, panelY + yOffset, panelWidth);
    yOffset += lineHeight;
    drawInfoLine(ctx, "症状:", medicalRecord.triageInfo.symptoms, panelX, panelY + yOffset, panelWidth);
    yOffset += lineHeight;
    drawInfoLine(ctx, "体温:", medicalRecord.triageInfo.vitalSigns.temperature, panelX, panelY + yOffset, panelWidth);
    yOffset += lineHeight;
    drawInfoLine(ctx, "心率:", medicalRecord.triageInfo.vitalSigns.heartRate, panelX, panelY + yOffset, panelWidth);
    yOffset += lineHeight;
    drawInfoLine(ctx, "血压:", medicalRecord.triageInfo.vitalSigns.bloodPressure, panelX, panelY + yOffset, panelWidth);
    yOffset += sectionSpacing;
  }

  // 问诊信息
  if (medicalRecord.consultationInfo) {
    drawSection(ctx, "问诊记录", panelX, panelY + yOffset, panelWidth);
    yOffset += 20;
    drawInfoLine(ctx, "医生:", medicalRecord.consultationInfo.doctor, panelX, panelY + yOffset, panelWidth);
    yOffset += lineHeight;
    drawInfoLine(ctx, "诊断:", medicalRecord.consultationInfo.diagnosis, panelX, panelY + yOffset, panelWidth);
    yOffset += lineHeight;
    drawInfoLine(ctx, "处方:", medicalRecord.consultationInfo.prescription.join(", "), panelX, panelY + yOffset, panelWidth);
    yOffset += lineHeight;
    drawInfoLine(ctx, "备注:", medicalRecord.consultationInfo.notes, panelX, panelY + yOffset, panelWidth);
    yOffset += sectionSpacing;
  }

  // 检查报告
  if (medicalRecord.testInfo) {
    drawSection(ctx, "检查报告", panelX, panelY + yOffset, panelWidth);
    yOffset += 20;
    drawInfoLine(ctx, "类别:", medicalRecord.testInfo.category, panelX, panelY + yOffset, panelWidth);
    yOffset += lineHeight;
    drawInfoLine(ctx, "项目:", medicalRecord.testInfo.items.join(", "), panelX, panelY + yOffset, panelWidth);
    yOffset += lineHeight;
    drawInfoLine(ctx, "报告:", "查看详情", panelX, panelY + yOffset, panelWidth);
  }
}

function drawSection(ctx, title, x, y, width) {
  ctx.font = "12px 'Segoe UI'";
  ctx.fillStyle = "#a8f8ff";
  ctx.fillText(title, x + 12, y);
  ctx.strokeStyle = "rgba(174, 129, 255, 0.3)";
  ctx.beginPath();
  ctx.moveTo(x + 12, y + 4);
  ctx.lineTo(x + width - 12, y + 4);
  ctx.stroke();
}

function drawInfoLine(ctx, label, value, x, y, width) {
  ctx.font = "11px 'Segoe UI'";
  ctx.fillStyle = "#f2ebff";
  ctx.fillText(label, x + 12, y);
  ctx.fillStyle = "#8ef0be";
  ctx.textAlign = "right";
  ctx.fillText(value, x + width - 12, y);
  ctx.textAlign = "left";
}

export function createMedicalRecord() {
  return {
    patientInfo: null,
    triageInfo: null,
    consultationInfo: null,
    testInfo: null
  };
}