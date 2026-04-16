/**
 * ecosystem.ts — utilitário TypeScript do ecossistema (OGMA).
 *
 * Lê/escreve ~/.local/share/ecosystem/ecosystem.json (Linux) ou
 * %APPDATA%\ecosystem\ecosystem.json (Windows) usando a API do Electron.
 */

import { app } from "electron";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

export interface AetherConfig {
  vault_path: string;
  exe_path?:  string;
}

export interface KosmosConfig {
  data_path: string;
  archive_path: string;
}

export interface OgmaConfig {
  data_path: string;
  exe_path?: string;
}

export interface MnemosyneConfig {
  watched_dir?:  string;
  vault_dir?:    string;
  index_paths:   string[];
  exe_path?:     string;
}

export interface HubConfig {
  data_path: string;
}

export interface EcosystemConfig {
  aether: AetherConfig;
  kosmos: KosmosConfig;
  ogma: OgmaConfig;
  mnemosyne: MnemosyneConfig;
  hub: HubConfig;
}

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const DEFAULTS: EcosystemConfig = {
  aether:    { vault_path: "" },
  kosmos:    { data_path: "", archive_path: "" },
  ogma:      { data_path: "" },
  mnemosyne: { index_paths: [] },
  hub:       { data_path: "" },
};

// ---------------------------------------------------------------------------
// Caminho do arquivo
// ---------------------------------------------------------------------------

export function ecosystemPath(): string {
  // app.getPath("appData") retorna %APPDATA% no Windows e ~/.config no Linux.
  // Para Linux seguimos XDG_DATA_HOME (~/.local/share) em vez de ~/.config.
  if (process.platform === "linux") {
    const xdg = process.env["XDG_DATA_HOME"] || path.join(os.homedir(), ".local", "share");
    return path.join(xdg, "ecosystem", "ecosystem.json");
  }
  return path.join(app.getPath("appData"), "ecosystem", "ecosystem.json");
}

// ---------------------------------------------------------------------------
// Leitura
// ---------------------------------------------------------------------------

export function readEcosystem(): EcosystemConfig {
  const filePath = ecosystemPath();
  if (!fs.existsSync(filePath)) {
    return structuredClone(DEFAULTS);
  }
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const data = JSON.parse(raw) as Partial<Record<keyof EcosystemConfig, unknown>>;
    return {
      aether:    { ...DEFAULTS.aether,    ...(data.aether    as Partial<AetherConfig>    ?? {}) },
      kosmos:    { ...DEFAULTS.kosmos,    ...(data.kosmos    as Partial<KosmosConfig>    ?? {}) },
      ogma:      { ...DEFAULTS.ogma,      ...(data.ogma      as Partial<OgmaConfig>      ?? {}) },
      mnemosyne: { ...DEFAULTS.mnemosyne, ...(data.mnemosyne as Partial<MnemosyneConfig> ?? {}) },
      hub:       { ...DEFAULTS.hub,       ...(data.hub       as Partial<HubConfig>       ?? {}) },
    };
  } catch {
    return structuredClone(DEFAULTS);
  }
}

// ---------------------------------------------------------------------------
// Escrita atômica
// ---------------------------------------------------------------------------

export function writeSection<K extends keyof EcosystemConfig>(
  appKey: K,
  section: Partial<EcosystemConfig[K]>,
): void {
  const filePath = ecosystemPath();
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });

  const data = readEcosystem();
  data[appKey] = { ...data[appKey], ...section } as EcosystemConfig[K];

  const tmp = filePath + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), "utf-8");
  fs.renameSync(tmp, filePath);
}
