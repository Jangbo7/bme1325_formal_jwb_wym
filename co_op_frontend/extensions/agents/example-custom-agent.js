export const exampleCustomAgent = {
  id: "example-custom-agent",
  label: "Example Custom Agent",
  roleLabel: "Demo Doctor",
  roomHint: "Replace this file with your own doctor-agent integration.",
  request: {
    createSession: {
      method: "POST",
      endpoint: "/api/v1/internal-medicine-sessions",
      buildBody: ({ player, room }) => ({
        patient_id: player.patientId,
        name: player.name,
        visit_id: player.visitId,
        round: 1,
        room_id: room.id,
      }),
      parseCreatedSession: (response) => ({
        sessionId: response.session_id || null,
        openingMessage: response.patient?.dialogue?.assistant_message || "Session created.",
      }),
    },
    sendMessage: {
      method: "POST",
      endpoint: ({ sessionId }) => `/api/v1/internal-medicine-sessions/${sessionId}/messages`,
      buildBody: ({ player, message }) => ({
        patient_id: player.patientId,
        name: player.name,
        visit_id: player.visitId,
        message,
      }),
      parseReply: (response) => ({
        text: response.patient?.dialogue?.assistant_message || "No reply message was returned.",
      }),
    },
  },
};
