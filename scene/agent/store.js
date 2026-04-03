export function createAgentStore() {
  return {
    lastPatient: null,
    lastQueues: [],
    syncPatient(patient) {
      this.lastPatient = patient;
      return patient;
    },
    syncQueues(queues) {
      this.lastQueues = Array.isArray(queues) ? queues : [];
      return this.lastQueues;
    },
  };
}

function buildRecommendationBody(meta, patient) {
  const level = meta?.triage_level ?? patient?.triage?.level ?? "-";
  const priority = meta?.priority ?? patient?.priority ?? "-";
  const department = meta?.department ?? patient?.location ?? "Pending";
  return `\u5efa\u8bae\u79d1\u5ba4: ${department}\nTriage Level ${level} | Priority ${priority}`;
}

function isNearDuplicate(previousMessage, nextMessage) {
  if (!previousMessage || !nextMessage) return false;
  return (
    previousMessage.role === nextMessage.role &&
    previousMessage.type === nextMessage.type &&
    previousMessage.body.trim() === nextMessage.body.trim()
  );
}

export function buildDialogueMessages(patient, fallbackUserSummary = "") {
  const turns = patient?.dialogue?.turns || patient?.memory?.short_term_memory?.turns || [];
  if (Array.isArray(turns) && turns.length > 0) {
    const messages = [];
    let lastRecommendationKey = "";
    for (const turn of turns) {
      if (turn.role === "assistant") {
        const meta = turn.metadata || {};
        const recommendationKey = `${meta.department || patient?.location || ""}|${meta.priority || patient?.priority || ""}|${meta.triage_level || patient?.triage?.level || ""}`;
        if (meta.recommendation_changed && meta.message_type !== "final" && recommendationKey && recommendationKey !== lastRecommendationKey) {
          const recommendationMessage = {
            role: "assistant",
            label: "\u5206\u8bca\u5efa\u8bae",
            body: buildRecommendationBody(meta, patient),
            type: "recommendation",
          };
          if (!isNearDuplicate(messages[messages.length - 1], recommendationMessage)) {
            messages.push(recommendationMessage);
            lastRecommendationKey = recommendationKey;
          }
        }
        const assistantMessage = {
          role: "assistant",
          label: meta.message_type === "final" ? "\u6700\u7ec8\u5efa\u8bae" : "\u5206\u8bca\u62a4\u58eb / Triage Agent",
          body: turn.content || "",
          type: meta.message_type === "final" ? "final" : "followup",
        };
        if (!isNearDuplicate(messages[messages.length - 1], assistantMessage)) {
          messages.push(assistantMessage);
        }
        continue;
      }

      const userMessage = {
        role: "user",
        label: "\u60a3\u8005 / Patient",
        body: turn.content || "",
        type: "user",
      };
      if (!isNearDuplicate(messages[messages.length - 1], userMessage)) {
        messages.push(userMessage);
      }
    }
    return messages;
  }

  const assistantMessage = patient?.dialogue?.assistant_message || patient?.triage?.note || "Waiting for triage response.";
  return [
    {
      role: "user",
      label: "\u60a3\u8005 / Patient",
      body: fallbackUserSummary || `${patient?.name || "Patient"} submitted triage information.`,
      type: "user",
    },
    {
      role: "assistant",
      label: "\u5206\u8bca\u62a4\u58eb / Triage Agent",
      body: assistantMessage,
      type: patient?.dialogue?.message_type || "followup",
    },
  ];
}
