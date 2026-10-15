// Appels au serveur local : jeton de session (protection CSRF) + délai max (le cerveau ne gèle jamais)
import { DELAI_JEV_MS } from "./config.js";

const JETON = document.querySelector('meta[name="jeton-session"]')?.content ?? "";

export async function postJSON(url, corps, delaiMs = DELAI_JEV_MS) {
  const ctrl = new AbortController(), minuteur = setTimeout(() => ctrl.abort(), delaiMs);
  try {
    const r = await fetch(url, { method: "POST", signal: ctrl.signal, body: JSON.stringify(corps),
      headers: { "Content-Type": "application/json", "X-Jeton-Session": JETON } });
    const rep = await r.json();
    if (rep.error) throw new Error(rep.detail ? `${rep.error} (${rep.detail})` : rep.error);
    return rep;
  } catch (e) { throw e.name === "AbortError" ? new Error(`délai > ${delaiMs / 1000} s`) : e; }
  finally { clearTimeout(minuteur); }
}
