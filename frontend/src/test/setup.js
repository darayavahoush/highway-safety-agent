// jsdom has no WebGL, canvas, layout engine or ResizeObserver. Provide the
// minimum so components can mount; anything real-browser is out of scope here.
import { vi } from 'vitest'

globalThis.ResizeObserver = globalThis.ResizeObserver || class { observe() {} unobserve() {} disconnect() {} }
globalThis.IntersectionObserver = globalThis.IntersectionObserver || class { observe() {} unobserve() {} disconnect() {} takeRecords() { return [] } }
window.matchMedia = window.matchMedia || ((q) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }))
window.scrollTo = () => {}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
// Canvas: return a permissive no-op 2D context instead of jsdom's "not implemented" error.
HTMLCanvasElement.prototype.getContext = () =>
  new Proxy({}, { get: (_t, k) => (k === 'canvas' ? document.createElement('canvas') : () => ({ width: 0 })), set: () => true })

// The 3D map needs WebGL, which jsdom cannot provide.
vi.mock('../components/CorridorMap3D.jsx', () => ({ default: () => null }))
