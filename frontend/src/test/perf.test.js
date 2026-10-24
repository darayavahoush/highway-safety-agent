import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve } from 'node:path'

const root = process.cwd()
const css = readFileSync(resolve(root, 'src/styles/app.css'), 'utf8')

describe('load-time guards', () => {
  it('no image in public/ is over 400 KB (the old PNG scenes were 2.4 MB each)', () => {
    const big = readdirSync(resolve(root, 'public'))
      .filter((f) => /\.(png|jpe?g|webp|gif)$/i.test(f))
      .map((f) => [f, statSync(resolve(root, 'public', f)).size])
      .filter(([, size]) => size > 400 * 1024)
    expect(big).toEqual([])
  })

  it('no PNG/JPEG scene photos are referenced by the stylesheet', () => {
    expect(css.match(/highway-[a-z-]+\.(png|jpe?g)/g) || []).toEqual([])
  })

  it('every scene image the stylesheet points at exists in public/', () => {
    const refs = [...new Set(css.match(/\/highway-[a-z-]+\.webp/g) || [])]
    expect(refs.length).toBeGreaterThan(0)
    const missing = refs.filter((r) => { try { statSync(resolve(root, 'public' + r)); return false } catch { return true } })
    expect(missing).toEqual([])
  })

  it('the app clock ticks once a second, not four times (it re-renders the whole app)', () => {
    const hook = readFileSync(resolve(root, 'src/state/useControlRoom.js'), 'utf8')
    expect(hook).toMatch(/function useNow\(ms = 1000\)/)
  })
})
