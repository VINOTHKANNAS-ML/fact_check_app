const API_BASE = import.meta.env.VITE_API_BASE || "https://fake-news-verifier-agent.onrender.com";

function authHeaders() {
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function register(username, password) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Register failed");
  return res.json();
}

export async function login(username, password) {
  const form = new URLSearchParams();
  form.append("username", username);
  form.append("password", password);
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Login failed");
  const data = await res.json();
  localStorage.setItem("access_token", data.access_token);
  return data;
}

export function logout() {
  localStorage.removeItem("access_token");
}

export function isLoggedIn() {
  return !!localStorage.getItem("access_token");
}

export async function verifyText(query) {
  const res = await fetch(`${API_BASE}/verify/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Verify failed");
  return res.json();
}

export async function verifyAudio(blob) {
  const form = new FormData();
  form.append("file", blob, "recording.webm");
  const res = await fetch(`${API_BASE}/verify/audio`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: form,
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Verify failed");
  return res.json();
}

export async function getHistory() {
  const res = await fetch(`${API_BASE}/verify/history`, {
    headers: { ...authHeaders() },
  });
  if (!res.ok) return [];
  return res.json();
}
