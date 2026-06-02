// AKASHA Extension — background service worker
// Rastreia abas abertas pelo AKASHA, polling de saúde e insights.

const AKASHA_ORIGIN       = "http://localhost:7071";
const HEALTH_INTERVAL_MS  = 30_000;   // 30s
const INSIGHT_INTERVAL_MS = 60_000;   // 60s

// Abas abertas a partir de resultados do AKASHA (estado em memória)
const _akaShaTabs = new Set();
let   _online     = false;

// ---------------------------------------------------------------------------
// Rastreamento de abas abertas pelo AKASHA
// ---------------------------------------------------------------------------

browser.tabs.onCreated.addListener(async (tab) => {
  if (!tab.openerTabId) return;
  try {
    const opener = await browser.tabs.get(tab.openerTabId);
    if (opener.url?.startsWith(AKASHA_ORIGIN)) {
      _akaShaTabs.add(tab.id);
    }
  } catch {
    // aba opener já fechada
  }
});

browser.tabs.onRemoved.addListener((tabId) => {
  _akaShaTabs.delete(tabId);
});

// O push de contexto (/context/push) é feito pelo content.js, que tem
// acesso ao body_text da página. O background apenas mantém o registro
// de quais tabs foram abertas a partir do AKASHA (_akaShaTabs).

// ---------------------------------------------------------------------------
// Saúde — atualiza ícone active/inactive a cada 30s
// ---------------------------------------------------------------------------

async function checkHealth() {
  try {
    const res = await fetch(`${AKASHA_ORIGIN}/health`, {
      signal: AbortSignal.timeout(4_000),
    });
    _online = res.ok;
  } catch {
    _online = false;
  }

  const suffix = _online ? "" : "_inactive";
  browser.action.setIcon({
    path: {
      "16":  `icons/icon${suffix}16.png`,
      "48":  `icons/icon${suffix}48.png`,
      "128": `icons/icon${suffix}128.png`,
    },
  }).catch(() => {});
}

setInterval(checkHealth, HEALTH_INTERVAL_MS);
checkHealth();   // executa imediatamente no startup

// ---------------------------------------------------------------------------
// Polling de insights — a cada 60s
// ---------------------------------------------------------------------------

async function pollInsight() {
  if (!_online) return;

  // Verifica a aba ativa ANTES de chamar /insight/current.
  // O servidor marca "ext" como consumidor ao receber a requisição — se a aba
  // for o próprio AKASHA (que tem seu overlay nativo), não devemos consumir
  // o slot da extensão, senão a UI recebe text=null e o insight some sem ser visto.
  let activeTab;
  try {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
    activeTab = tab;
  } catch {
    return;
  }
  if (!activeTab)                                 return;
  if (activeTab.url?.startsWith(AKASHA_ORIGIN))   return;

  let data;
  try {
    const res = await fetch(`${AKASHA_ORIGIN}/insight/current`, {
      signal: AbortSignal.timeout(5_000),
    });
    if (!res.ok) return;
    data = await res.json();
  } catch {
    return;
  }

  // Sem insight ou arousal alto (adiado para o próximo ciclo)
  if (!data?.text)               return;
  if (data.reason === "deferred") return;

  try {
    await browser.tabs.sendMessage(activeTab.id, {
      type:       "insight",
      text:       data.text,
      memory_id:  data.memory_id,
      importance: data.importance ?? null,
    });
  } catch {
    // content.js não injetado nessa aba (ex: about:, moz-extension:) — ignora
  }
}

setInterval(pollInsight, INSIGHT_INTERVAL_MS);

// ---------------------------------------------------------------------------
// Mensagens do content script
// ---------------------------------------------------------------------------

browser.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "is_akasha_tab") {
    sendResponse({ result: _akaShaTabs.has(sender.tab?.id) });
  }
});

// ---------------------------------------------------------------------------
// Atalho de teclado → abrir popup
// ---------------------------------------------------------------------------

browser.commands.onCommand.addListener((command) => {
  if (command === "open_popup") {
    browser.action.openPopup().catch(() => {});
  }
});
