const RULE_STORAGE_PREFIX = "sim-hospital-event-rules:";

export async function fetchRuleIndex() {
  return fetchStaticJson("./event-rules/index.json", "event rules index");
}

export async function fetchRuleCategory(file) {
  const stored = window.localStorage.getItem(`${RULE_STORAGE_PREFIX}${file}`);
  if (stored) return JSON.parse(stored);

  return fetchStaticJson(`./event-rules/${encodeURIComponent(file)}`, file);
}

export async function saveRuleCategory(file, category) {
  const body = JSON.stringify(category, null, 2);
  let response = null;
  try {
    response = await fetch(`./api/event-rules/${encodeURIComponent(file)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch {
    response = null;
  }

  if (response?.ok) {
    window.localStorage.removeItem(`${RULE_STORAGE_PREFIX}${file}`);
    return { mode: "file" };
  }

  window.localStorage.setItem(`${RULE_STORAGE_PREFIX}${file}`, body);
  return { mode: "browser" };
}

async function fetchStaticJson(staticUrl, label) {
  const staticResponse = await fetch(staticUrl, { cache: "no-store" });
  if (!staticResponse.ok) throw new Error(`Unable to load ${label}: ${staticResponse.status}`);
  return staticResponse.json();
}
