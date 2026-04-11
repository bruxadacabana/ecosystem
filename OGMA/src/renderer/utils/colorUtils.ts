/**
 * Utilitários de cor para o módulo académico do OGMA.
 * Gera cores HSL consistentes e calibradas para a paleta sépia.
 */

/**
 * Devolve uma cor HSL consistente para um nome de disciplina.
 * O mesmo nome produz sempre a mesma cor (hash determinística).
 */
export function disciplineColor(name: string, dark: boolean): string {
  const hue = stringToHue(name)
  // Saturação e luminosidade calibradas para o sistema sépia
  const sat = dark ? 50 : 55
  const lig = dark ? 44 : 34
  return `hsl(${hue}, ${sat}%, ${lig}%)`
}

/**
 * Versão com alpha — útil para fundos/tintas subtis.
 */
export function disciplineColorAlpha(name: string, dark: boolean, alpha: number): string {
  const hue = stringToHue(name)
  const sat = dark ? 50 : 55
  const lig = dark ? 44 : 34
  return `hsla(${hue}, ${sat}%, ${lig}%, ${alpha})`
}

/**
 * Gera um código no formato PREFIX### para uma disciplina.
 * O prefixo é derivado do nome (primeiras 3 letras significativas).
 * O número é o próximo disponível com base nos códigos existentes.
 *
 * @param title         Nome da disciplina
 * @param existingCodes Lista de códigos já existentes no projeto
 */
export function generateCode(title: string, existingCodes: string[]): string {
  const prefix = extractPrefix(title)
  const pattern = new RegExp(`^${prefix}(\\d+)$`)
  const nums = existingCodes
    .map(c => c?.match(pattern)?.[1])
    .filter((n): n is string => !!n)
    .map(Number)
  const next = nums.length > 0 ? Math.max(...nums) + 1 : 1
  return `${prefix}${String(next).padStart(3, '0')}`
}

// ── Internos ──────────────────────────────────────────────────────────────────

function stringToHue(str: string): number {
  // djb2 hash
  let hash = 5381
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash) ^ str.charCodeAt(i)
    hash = hash & hash // força 32 bits
  }
  return Math.abs(hash) % 360
}

function extractPrefix(title: string): string {
  // Remove acentos → maiúsculas → só letras → primeiros 3 chars
  const clean = title
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toUpperCase()
    .replace(/[^A-Z]/g, '')
  return clean.slice(0, 3).padEnd(3, 'X')
}
