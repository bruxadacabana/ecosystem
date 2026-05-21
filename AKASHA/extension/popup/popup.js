// AKASHA Extension — popup
// Funciona em qualquer aba (não exige que tenha sido aberta pelo AKASHA).

const AKASHA_ORIGIN = "http://localhost:7071";

const dot        = document.getElementById("status-dot");
const urlEl      = document.getElementById("page-url");
const titleEl    = document.getElementById("page-title");
const badges     = document.getElementById("state-badges");
const feedback   = document.getElementById("feedback");
const btnArchive = document.getElementById("btn-archive");
const btnWatch   = document.getElementById("btn-watch-later");
const btnTrack   = document.getElementById("btn-track-site");

let _currentUrl   = "";
let _currentTitle = "";

// ---------------------------------------------------------------------------
// Inicialização
// ---------------------------------------------------------------------------

async function init() {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;

  _currentUrl   = tab.url   ?? "";
  _currentTitle = tab.title ?? "";

  urlEl.textContent   = _currentUrl;
  urlEl.title         = _currentUrl;
  titleEl.textContent = _currentTitle || "—";

  await checkHealth();
  await loadStatus();
}

// ---------------------------------------------------------------------------
// Saúde do AKASHA
// ---------------------------------------------------------------------------

async function checkHealth() {
  try {
    const res = await fetch(`${AKASHA_ORIGIN}/health`, {
      signal: AbortSignal.timeout(3_000),
    });
    if (res.ok) {
      dot.className = "online";
      dot.title     = "AKASHA online";
      return true;
    }
  } catch { /* offline */ }
  dot.className = "offline";
  dot.title     = "AKASHA offline";
  return false;
}

// ---------------------------------------------------------------------------
// Estado da página via GET /context/status
// ---------------------------------------------------------------------------

async function loadStatus() {
  if (!_currentUrl || _currentUrl.startsWith("about:") || _currentUrl.startsWith("moz-")) {
    badges.innerHTML = `<span class="badge">aba interna</span>`;
    setActionsDisabled(true);
    return;
  }

  badges.innerHTML = `<span class="spinner"></span>`;

  try {
    const res = await fetch(
      `${AKASHA_ORIGIN}/context/status?url=${encodeURIComponent(_currentUrl)}`,
      { signal: AbortSignal.timeout(4_000) },
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const parts = [];
    if (data.archived)    parts.push(`<span class="badge yes">arquivada ✓</span>`);
    if (data.in_library)  parts.push(`<span class="badge yes">biblioteca ✓</span>`);
    if (data.related_count > 0)
      parts.push(`<span class="badge count">${data.related_count} relacionados</span>`);
    if (!parts.length)
      parts.push(`<span class="badge">não catalogada</span>`);

    badges.innerHTML = parts.join("");
  } catch {
    badges.innerHTML = `<span class="badge">—</span>`;
  }
}

// ---------------------------------------------------------------------------
// Ações
// ---------------------------------------------------------------------------

function setActionsDisabled(v) {
  [btnArchive, btnWatch, btnTrack].forEach(b => (b.disabled = v));
}

function setFeedback(msg, type = "") {
  feedback.textContent = msg;
  feedback.className   = type;
}

function showSpinnerOn(btn) {
  btn.dataset.label = btn.textContent;
  btn.innerHTML     = `<span class="spinner"></span>`;
  btn.disabled      = true;
}

function restoreBtn(btn) {
  btn.textContent = btn.dataset.label ?? btn.textContent;
  btn.disabled    = false;
}

async function doAction(btn, fetchFn) {
  if (!_currentUrl) return;
  showSpinnerOn(btn);
  setFeedback("");
  try {
    const res = await fetchFn();
    if (res.ok) {
      setFeedback("✓ feito", "ok");
      await loadStatus();
    } else if (res.status === 409) {
      setFeedback("já existe", "");
    } else {
      setFeedback(`erro ${res.status}`, "err");
    }
  } catch {
    setFeedback("AKASHA offline", "err");
  } finally {
    restoreBtn(btn);
  }
}

btnArchive.addEventListener("click", () =>
  doAction(btnArchive, () =>
    fetch(`${AKASHA_ORIGIN}/archive`, {
      method: "POST",
      body:   new URLSearchParams({ url: _currentUrl, tags: "", notes: "" }),
    }),
  ),
);

btnWatch.addEventListener("click", () =>
  doAction(btnWatch, () =>
    fetch(`${AKASHA_ORIGIN}/watch-later/add`, {
      method: "POST",
      body:   new URLSearchParams({ url: _currentUrl, title: _currentTitle }),
    }),
  ),
);

btnTrack.addEventListener("click", () =>
  doAction(btnTrack, () =>
    fetch(`${AKASHA_ORIGIN}/library/add-quick`, {
      method: "POST",
      body:   new URLSearchParams({ url: _currentUrl }),
    }),
  ),
);

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

init();
