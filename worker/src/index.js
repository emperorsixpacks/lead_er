// lead_er tracking worker.
// Routes:
//   /o/<token>.gif  -> transparent pixel, records "open"
//   /c/<token>?u=... -> 302 redirect, records "click"
//   /u/<token>       -> unsubscribe confirmation page, records "unsub"
//
// Env: API_URL, API_SECRET, NTFY_TOPIC (optional NTFY_URL, default https://ntfy.sh)

const GIF = Uint8Array.from(
  atob("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"),
  (c) => c.charCodeAt(0),
);

export default {
  // Cron trigger: draft the outreach PDF and email it to you for manual sending.
  async scheduled(event, env, ctx) {
    await fetch(env.API_URL + "/pipeline/draft?limit=20", { method: "POST" }).catch(() => {});
  },

  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const parts = url.pathname.split("/").filter(Boolean); // ["o", "<token>.gif"]
    const kind = parts[0];
    const raw = parts[1] || "";
    const token = raw.replace(".gif", "");
    const ua = req.headers.get("user-agent") || "";
    const ip = req.headers.get("cf-connecting-ip") || "";

    if (kind === "u") {
      // Unsubscribe: record it, show a confirmation page.
      const event = { token, type: "unsub", ua, ip };
      ctx.waitUntil(report(event, env));
      return html(
        "You have been unsubscribed. You will not receive further emails from us.",
        200,
      );
    }

    if (kind === "c") {
      const dest = url.searchParams.get("u");
      const event = { token, type: "click", url: dest, ua, ip };
      ctx.waitUntil(report(event, env));
      const safe = dest && /^https?:\/\//.test(dest) ? dest : "https://yourdomain.com";
      return Response.redirect(safe, 302);
    }

    // Default: open pixel.
    const event = { token, type: "open", ua, ip };
    ctx.waitUntil(report(event, env));
    return new Response(GIF, {
      headers: { "content-type": "image/gif", "cache-control": "no-store, max-age=0" },
    });
  },
};

async function report(event, env) {
  const body = JSON.stringify(event);
  const sig = await hmac(env.API_SECRET, body);
  let info = {};
  try {
    const r = await fetch(env.API_URL + "/events", {
      method: "POST",
      body,
      headers: { "content-type": "application/json", "x-sig": sig },
    });
    if (r.ok) info = await r.json().catch(() => ({}));
  } catch (e) {
    // swallow; tracking must never block the pixel/redirect
  }

  if (info.notify !== false) {
    const ntfy = (env.NTFY_URL || "https://ntfy.sh").replace(/\/$/, "");
    const topic = env.NTFY_TOPIC;
    if (topic) {
      await fetch(`${ntfy}/${topic}`, {
        method: "POST",
        headers: {
          Title: `${event.type.toUpperCase()}: ${info.business || event.token}`,
        },
        body: info.business ? `${info.business} (${info.category || ""})` : "event received",
      }).catch(() => {});
    }
  }
}

async function hmac(secret, msg) {
  const k = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const s = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(msg));
  return [...new Uint8Array(s)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function html(message, status) {
  return new Response(
    `<!doctype html><html><body style="font-family:sans-serif;padding:40px">${message}</body></html>`,
    { status, headers: { "content-type": "text/html; charset=utf-8" } },
  );
}
