const PROXY_URL = "http://localhost:8000/api/chat";

export async function callChatAPI(message, model = "deepseek", imageData = null) {
  const payload = { message, model };
  if (imageData) payload.image = imageData;

  const response = await fetch(PROXY_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `API Error: ${response.status}`);
  }

  const data = await response.json();
  return data.response || "抱歉，我没有收到回复。";
}

export function createUserMessage(content) {
  return { role: "user", content };
}

export function createAssistantMessage(content) {
  return { role: "assistant", content };
}
