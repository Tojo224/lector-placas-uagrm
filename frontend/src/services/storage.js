const AUTH_KEY = "lector_placas_session";

export function saveSession(session) {
  try {
    const data = { user: session?.user ?? null };
    localStorage.setItem(AUTH_KEY, JSON.stringify(data));
  } catch {
    // Fail silently — app still works in memory
  }
}

export function readSession() {
  const raw = localStorage.getItem(AUTH_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(AUTH_KEY);
  } catch {
    // Fail silently — app still works in memory
  }
}
