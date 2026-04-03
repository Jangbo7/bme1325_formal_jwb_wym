$content = Get-Content -Path "e:\shanghaitech\ai_hospital\bme1325_formal_jwb_wym-main\scene\bundle.js" -Raw -Encoding UTF8

$old = '}

function getDoctorSystemPrompt() {
  return `你是一位专业的医生，名字叫"Dr.林"。你需要：
1. 详细询问患者的症状和病史
2. 提供专业的医疗建议
3. 如需进一步检查，建议患者做相应检查
4. 开具处方或建议住院治疗
5. 保持专业、温和的态度
6. 回答要专业但通俗易懂`;
}'

$new = '}

function getDoctorSystemPrompt(npc) {
  const isInternalDoctor = npc && npc.department === "internal";
  const ragContext = isInternalDoctor ? INTERNAL_MEDICINE_RAG : "";

  if (isInternalDoctor) {
    return `你是一位内科医生，名字叫"Dr.林"，你在内科诊室工作。你是专业的内科医生，拥有丰富的内科医学知识。

\${ragContext}

你需要：
1. 礼貌地问候患者，询问症状
2. 详细询问患者的症状和病史（包括症状起始时间、持续多久、严重程度、伴随症状等）
3. 根据症状进行初步诊断和鉴别诊断
4. 提供专业的医疗建议和治疗方案
5. 如需进一步检查，建议患者做相应检查（如血常规、尿常规、心电图、X光等）
6. 如需开药，说明药物名称、用法用量
7. 保持专业、温和、耐心的态度
8. 回答要专业但通俗易懂，让患者能够理解
9. 如果患者情况紧急或严重，及时提醒患者去急诊

注意：你只负责内科疾病，其他科室疾病请建议患者去相应科室。`;
  }

  return `你是一位专业的医生，名字叫"Dr.林"。你需要：
1. 详细询问患者的症状和病史
2. 提供专业的医疗建议
3. 如需进一步检查，建议患者做相应检查
4. 开具处方或建议住院治疗
5. 保持专业、温和的态度
6. 回答要专业但通俗易懂`;
}'

if ($content.Contains($old)) {
    $content = $content.Replace($old, $new)
    Set-Content -Path "e:\shanghaitech\ai_hospital\bme1325_formal_jwb_wym-main\scene\bundle.js" -Value $content -Encoding UTF8 -NoNewline
    Write-Host "Replacement successful"
} else {
    Write-Host "Old string not found"
    $idx = $content.IndexOf('function getDoctorSystemPrompt')
    if ($idx -ne -1) {
        Write-Host "Found at position $idx"
        Write-Host $content.Substring($idx, 300)
    }
}