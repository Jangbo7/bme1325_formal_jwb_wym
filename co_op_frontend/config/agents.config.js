import { exampleCustomAgent } from "../extensions/agents/example-custom-agent.js";

const createDefaultSessionAgent = ({ id, label, roleLabel, createEndpoint, messageEndpoint, round = 1, roomHint }) => ({
  id,
  label,
  roleLabel,
  roomHint,
  request: {
    createSession: {
      method: "POST",
      endpoint: createEndpoint,
      buildBody: ({ player, room }) => ({
        patient_id: player.patientId,
        name: player.name,
        visit_id: player.visitId,
        round,
        room_id: room.id,
      }),
      parseCreatedSession: (response) => ({
        sessionId: response.session_id || null,
        openingMessage: response.patient?.dialogue?.assistant_message || `${label} connected.`,
      }),
    },
    sendMessage: {
      method: "POST",
      endpoint: ({ sessionId }) => messageEndpoint(sessionId),
      buildBody: ({ player, room, message, sessionId }) => ({
        patient_id: player.patientId,
        name: player.name,
        visit_id: player.visitId,
        room_id: room.id,
        session_id: sessionId,
        message,
      }),
      parseReply: (response) => ({
        text: response.patient?.dialogue?.assistant_message
          || response.reply
          || response.message
          || "Agent responded without a standard dialogue payload.",
      }),
    },
  },
});

export const AGENT_DEFINITIONS = [
  createDefaultSessionAgent({
    id: "internal-medicine-agent",
    label: "Internal Medicine Agent",
    roleLabel: "Doctor",
    createEndpoint: "/api/v1/internal-medicine-sessions",
    messageEndpoint: (sessionId) => `/api/v1/internal-medicine-sessions/${sessionId}/messages`,
    roomHint: "Default example for consultation room A.",
  }),
  createDefaultSessionAgent({
    id: "surgery-agent",
    label: "Surgery Agent",
    roleLabel: "Doctor",
    createEndpoint: "/api/v1/surgery-sessions",
    messageEndpoint: (sessionId) => `/api/v1/surgery-sessions/${sessionId}/messages`,
    roomHint: "Default example for consultation room B.",
  }),
  createDefaultSessionAgent({
    id: "specialty-a-agent",
    label: "Specialty Agent A",
    roleLabel: "Specialist",
    createEndpoint: "/api/v1/internal-medicine-sessions",
    messageEndpoint: (sessionId) => `/api/v1/internal-medicine-sessions/${sessionId}/messages`,
    roomHint: "Replace this with your own specialty agent.",
  }),
  createDefaultSessionAgent({
    id: "specialty-b-agent",
    label: "Specialty Agent B",
    roleLabel: "Specialist",
    createEndpoint: "/api/v1/internal-medicine-sessions",
    messageEndpoint: (sessionId) => `/api/v1/internal-medicine-sessions/${sessionId}/messages`,
    roomHint: "Replace this with another specialty agent.",
  }),
  createDefaultSessionAgent({
    id: "icu-agent",
    label: "ICU Agent",
    roleLabel: "ICU Doctor",
    createEndpoint: "/api/v1/icu-sessions",
    messageEndpoint: (sessionId) => `/api/v1/icu-sessions/${sessionId}/messages`,
    roomHint: "Default example for ICU consultation.",
  }),
  exampleCustomAgent,
];
