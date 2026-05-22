/**
 * Testes unitários para src/renderer/utils/colorUtils.ts
 *
 * Todas as funções são puras — sem DOM, sem Electron, sem rede.
 * Cobre:
 *   - disciplineColor: cor HSL determinística a partir de nome
 *   - disciplineColorAlpha: versão com canal alpha
 *   - generateCode: código PREFIX### único a partir de título
 */

import { describe, it, expect } from 'vitest'
import {
  disciplineColor,
  disciplineColorAlpha,
  generateCode,
} from '../src/renderer/utils/colorUtils'


// ---------------------------------------------------------------------------
// disciplineColor
// ---------------------------------------------------------------------------

describe('disciplineColor', () => {
  it('retorna string no formato hsl()', () => {
    const color = disciplineColor('Matemática', false)
    expect(color).toMatch(/^hsl\(\d+, \d+%, \d+%\)$/)
  })

  it('é determinística — mesmo nome produz sempre a mesma cor', () => {
    const a = disciplineColor('Física', false)
    const b = disciplineColor('Física', false)
    expect(a).toBe(b)
  })

  it('nomes diferentes produzem cores diferentes (na maioria)', () => {
    const a = disciplineColor('Química', false)
    const b = disciplineColor('Biologia', false)
    expect(a).not.toBe(b)
  })

  it('modo dark altera saturação/luminosidade mas mantém hue', () => {
    const light = disciplineColor('História', false)
    const dark  = disciplineColor('História', true)
    expect(light).not.toBe(dark)
    // Extrai hue de ambas e compara
    const hueOf = (s: string) => parseInt(s.match(/\d+/)![0])
    expect(hueOf(light)).toBe(hueOf(dark))
  })

  it('funciona com string vazia', () => {
    const color = disciplineColor('', false)
    expect(color).toMatch(/^hsl\(/)
  })
})


// ---------------------------------------------------------------------------
// disciplineColorAlpha
// ---------------------------------------------------------------------------

describe('disciplineColorAlpha', () => {
  it('retorna string no formato hsla()', () => {
    const color = disciplineColorAlpha('Arte', false, 0.5)
    expect(color).toMatch(/^hsla\(/)
  })

  it('inclui o alpha especificado', () => {
    const color = disciplineColorAlpha('Música', false, 0.3)
    expect(color).toContain('0.3')
  })

  it('alpha 1.0 produz cor completamente opaca', () => {
    const color = disciplineColorAlpha('Filosofia', false, 1)
    expect(color).toContain('1)')
  })
})


// ---------------------------------------------------------------------------
// generateCode
// ---------------------------------------------------------------------------

describe('generateCode', () => {
  it('formato PREFIX### com 3 letras e 3 dígitos', () => {
    const code = generateCode('Matemática', [])
    expect(code).toMatch(/^[A-Z]{3}\d{3}$/)
  })

  it('primeiro código sem existentes é PREFIX001', () => {
    const code = generateCode('Física', [])
    expect(code).toMatch(/001$/)
  })

  it('incrementa sobre código existente', () => {
    const first  = generateCode('Química', [])
    const second = generateCode('Química', [first])
    const n1 = parseInt(first.slice(3))
    const n2 = parseInt(second.slice(3))
    expect(n2).toBe(n1 + 1)
  })

  it('ignora códigos de outro prefixo', () => {
    const code = generateCode('Biologia', ['FIS001', 'FIS002'])
    expect(code).toMatch(/^BIO/)
    expect(code).toMatch(/001$/)
  })

  it('remove acentos do prefixo', () => {
    const code = generateCode('Álgebra', [])
    expect(code).toMatch(/^ALG/)
  })

  it('título vazio usa padding X', () => {
    const code = generateCode('', [])
    expect(code).toMatch(/^XXX/)
  })

  it('título com apenas números usa padding X', () => {
    const code = generateCode('123', [])
    expect(code).toMatch(/^XXX/)
  })
})
