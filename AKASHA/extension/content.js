// AKASHA Extension — content script
// Injeta barra de ação em abas abertas pelo AKASHA e exibe overlays de insight.

const AKASHA_ORIGIN = "http://localhost:7071";

const STYLES = `
  :host {
    all: initial;
    font-family: "JetBrains Mono", "Fira Mono", ui-monospace, monospace;
    font-size: 12px;
    color: #C8BFA8;
  }
  * { box-sizing: border-box; }

  /* ── Barra de ação ── */
  #bar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    z-index: 2147483647;
    background: #12161E;
    border-top: 1px solid #2A2F3C;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 16px;
    box-shadow: 0 -2px 8px rgba(0,0,0,.4);
  }
  .ak-logo { color: #D4A820; font-size: 14px; }
  .ak-btn {
    background: transparent;
    border: 1px solid #2A2F3C;
    color: #C8BFA8;
    padding: 3px 10px;
    border-radius: 3px;
    cursor: pointer;
    font: inherit;
    font-size: 11px;
  }
  .ak-btn:hover:not(:disabled) { border-color: #D4A820; color: #D4A820; }
  .ak-btn:disabled { opacity: .4; cursor: default; }
  .ak-status { font-size: 11px; opacity: .7; }
  .ak-close {
    margin-left: auto;
    background: none; border: none;
    color: #4A5060; cursor: pointer;
    font-size: 16px; line-height: 1; padding: 0 4px;
  }
  .ak-close:hover { color: #C8BFA8; }

  /* ── Overlay de insight ── */
  #overlay {
    position: fixed;
    bottom: 24px; right: 24px;
    z-index: 2147483646;
    width: 320px;
    background: #12161E;
    border: 1px solid #2A2F3C;
    border-radius: 6px;
    padding: 14px 16px 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,.5);
    line-height: 1.5;
  }
  .ov-header { font-size: 10px; color: #D4A820; letter-spacing: .08em; margin-bottom: 8px; }
  .ov-text   { color: #E8DFC8; font-size: 13px; font-family: ui-sans-serif, system-ui, sans-serif; margin-bottom: 12px; }
  .ov-actions { display: flex; gap: 8px; justify-content: flex-end; }
  .ov-btn {
    background: transparent;
    border: 1px solid #2A2F3C;
    color: #C8BFA8;
    padding: 4px 12px; border-radius: 3px;
    cursor: pointer; font: inherit; font-size: 12px;
  }
  .ov-btn:hover { border-color: #D4A820; color: #D4A820; }

  /* ── Painel de motivo ── */
  .reason-original {
    background: #1C2030; border: 1px solid #2A2F3C;
    border-radius: 3px; padding: 8px; margin-bottom: 10px;
    font-size: 11px; color: #9A9080;
    max-height: 80px; overflow-y: auto;
  }
  .reason-label { font-size: 11px; color: #9A9080; margin-bottom: 8px; }
  .reason-opts  { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
  .reason-opt {
    background: transparent; border: 1px solid #2A2F3C;
    color: #9A9080; padding: 3px 8px; border-radius: 3px;
    cursor: pointer; font: inherit; font-size: 11px;
  }
  .reason-opt.sel, .reason-opt:hover { border-color: #D4A820; color: #D4A820; }
  .reason-input {
    width: 100%; background: #1C2030;
    border: 1px solid #2A2F3C; color: #C8BFA8;
    padding: 4px 8px; border-radius: 3px;
    font: inherit; font-size: 11px; margin-bottom: 8px; outline: none;
  }
`;

// ---------------------------------------------------------------------------
// Utilitários
// ---------------------------------------------------------------------------

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

async function akFetch(path, opts) {
  return fetch(`${AKASHA_ORIGIN}${path}`, opts);
}

// ---------------------------------------------------------------------------
// Barra de ação (somente em abas rastreadas)
// ---------------------------------------------------------------------------

function mountActionBar() {
  if (document.getElementById("_akasha_bar_host")) return;

  const host   = document.createElement("div");
  host.id      = "_akasha_bar_host";
  const shadow = host.attachShadow({ mode: "open" });

  shadow.innerHTML = `
    <style>${STYLES}</style>
    <div id="bar">
      <span class="ak-logo">⬡</span>
      <button class="ak-btn" data-action="archive">⬡ Arquivar</button>
      <button class="ak-btn" data-action="watch-later">🕐 Ver depois</button>
      <button class="ak-btn" data-action="track-site">🔍 Rastrear site</button>
      <span class="ak-status" id="bar-status"></span>
      <button class="ak-close" id="bar-close" title="Fechar">×</button>
    </div>
  `;

  document.body.appendChild(host);

  shadow.getElementById("bar-close").addEventListener("click", () => host.remove());

  shadow.getElementById("bar").addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;

    const status = shadow.getElementById("bar-status");
    btn.disabled = true;
    status.textContent = "…";

    try {
      const url   = location.href;
      const title = document.title;

      if (btn.dataset.action === "archive") {
        const res = await akFetch("/archive", {
          method: "POST",
          body:   new URLSearchParams({ url, tags: "", notes: "", source: "extension" }),
        });
        status.textContent = res.ok ? "arquivado ✓"
          : res.status === 409 ? "já arquivado"
          : `erro ${res.status}`;
      } else if (btn.dataset.action === "watch-later") {
        const res = await akFetch("/watch-later/add", {
          method: "POST",
          body:   new URLSearchParams({ url, title }),
        });
        status.textContent = res.ok ? "salvo ✓" : `erro ${res.status}`;
      } else if (btn.dataset.action === "track-site") {
        const res = await akFetch("/library/add-quick", {
          method: "POST",
          body:   new URLSearchParams({ url }),
        });
        status.textContent = res.ok ? "site rastreado ✓" : `erro ${res.status}`;
      }
    } catch {
      status.textContent = "AKASHA offline";
    } finally {
      btn.disabled = false;
    }
  });
}

// ---------------------------------------------------------------------------
// Overlay de insight
// ---------------------------------------------------------------------------

let _overlayHost = null;

function removeOverlay() {
  _overlayHost?.remove();
  _overlayHost = null;
}

function mountInsightOverlay(text, memoryId, importance) {
  removeOverlay();

  const host   = document.createElement("div");
  host.id      = "_akasha_overlay_host";
  const shadow = host.attachShadow({ mode: "open" });

  shadow.innerHTML = `
    <style>${STYLES}</style>
    <div id="overlay">
      <div class="ov-header">⬡ AKASHA</div>
      <div class="ov-text" id="ov-text">${esc(text)}</div>
      <div class="ov-actions">
        <button class="ov-btn" id="ov-confirm">✓</button>
        <button class="ov-btn" id="ov-dismiss">✗</button>
      </div>
    </div>
  `;

  document.body.appendChild(host);
  _overlayHost = host;

  shadow.getElementById("ov-confirm").addEventListener("click", async () => {
    await sendFeedback(memoryId, "confirmed");
    removeOverlay();
  });

  shadow.getElementById("ov-dismiss").addEventListener("click", async () => {
    const data = await sendFeedback(memoryId, "dismissed");
    if (data?.ask_reason) {
      showReasonPanel(shadow, text, memoryId);
    } else {
      removeOverlay();
    }
  });
}

function showReasonPanel(shadow, originalText, memoryId) {
  const REASONS = ["já sabia disso", "irrelevante agora", "incorreto", "outro"];
  let selected  = "";

  const overlay = shadow.getElementById("overlay");
  overlay.innerHTML = `
    <div class="ov-header">⬡ AKASHA — o que estava errado?</div>
    <div class="reason-original">${esc(originalText)}</div>
    <div class="reason-label">selecione um motivo:</div>
    <div class="reason-opts">
      ${REASONS.map(r => `<button class="reason-opt" data-r="${esc(r)}">${esc(r)}</button>`).join("")}
    </div>
    <input class="reason-input" id="reason-detail" type="text" placeholder="detalhe opcional…" />
    <div class="ov-actions">
      <button class="ov-btn" id="reason-ok">confirmar</button>
    </div>
  `;

  overlay.querySelectorAll(".reason-opt").forEach(b => {
    b.addEventListener("click", () => {
      overlay.querySelectorAll(".reason-opt").forEach(x => x.classList.remove("sel"));
      b.classList.add("sel");
      selected = b.dataset.r;
    });
  });

  overlay.querySelector("#reason-ok").addEventListener("click", async () => {
    const detail = overlay.querySelector("#reason-detail").value.trim();
    const reason = [selected, detail].filter(Boolean).join(" — ") || "sem motivo";
    await sendFeedbackReason(memoryId, reason);
    removeOverlay();
  });
}

async function sendFeedback(memoryId, feedback) {
  try {
    const res = await akFetch("/insight/feedback", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ memory_id: memoryId, feedback }),
    });
    if (res.ok) return res.json();
  } catch { /* offline */ }
  return null;
}

async function sendFeedbackReason(memoryId, reason) {
  try {
    await akFetch("/insight/feedback_reason", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ memory_id: memoryId, reason }),
    });
  } catch { /* offline */ }
}

// ---------------------------------------------------------------------------
// Contexto de leitura — push de conteúdo + timer de visibilidade
// ---------------------------------------------------------------------------

let _visibleStart = null;
let _totalVisibleMs = 0;

function _sendReadingTime(timeMs) {
  if (timeMs < 5_000) return;
  fetch(`${AKASHA_ORIGIN}/context/time`, {
    method:    "POST",
    headers:   { "Content-Type": "application/json" },
    body:      JSON.stringify({ url: location.href, time_ms: timeMs }),
    keepalive: true,
  }).catch(() => {});
}

function _startReadingTimer() {
  if (document.visibilityState === "visible") {
    _visibleStart = Date.now();
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      _visibleStart = Date.now();
    } else if (_visibleStart !== null) {
      _totalVisibleMs += Date.now() - _visibleStart;
      _visibleStart = null;
      _sendReadingTime(_totalVisibleMs);
    }
  });

  window.addEventListener("pagehide", () => {
    if (_visibleStart !== null) {
      _totalVisibleMs += Date.now() - _visibleStart;
      _visibleStart = null;
    }
    _sendReadingTime(_totalVisibleMs);
  });
}

async function _pushContext() {
  try {
    await akFetch("/context/push", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url:       location.href,
        title:     document.title,
        body_text: document.body?.innerText?.slice(0, 3000) ?? "",
      }),
    });
  } catch { /* AKASHA offline */ }
}

// ---------------------------------------------------------------------------
// Mensagens do background
// ---------------------------------------------------------------------------

browser.runtime.onMessage.addListener((msg) => {
  if (msg.type === "insight") {
    mountInsightOverlay(msg.text, msg.memory_id, msg.importance ?? null);
  }
});

// ---------------------------------------------------------------------------
// Inicialização — injeta barra apenas em abas rastreadas
// ---------------------------------------------------------------------------

(async () => {
  try {
    const res = await browser.runtime.sendMessage({ type: "is_akasha_tab" });
    if (!res?.result) return;
    mountActionBar();
    _pushContext();
    _startReadingTimer();
  } catch { /* runtime desconectado */ }
})();
