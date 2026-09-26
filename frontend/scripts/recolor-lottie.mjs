// Recolor the "Search" Lottie for the emerald/black theme — programmatically, by LAYER NAME.
// (Hand find/replace is unsafe: the same numbers appear in unrelated places.)
//
//   node scripts/recolor-lottie.mjs [in.json] [out.json]
//   defaults: src/assets/lottie/search.source.json → src/assets/lottie/search_emerald_dark.json
//
// Every palette is the Tailwind *emerald* family, the same hue the UI uses (#10b981, #34d399, #6ee7b7…).
import { readFileSync, writeFileSync } from 'node:fs'

const [inPath = 'src/assets/lottie/search.source.json', outPath = 'src/assets/lottie/search_emerald_dark.json'] =
  process.argv.slice(2)

const hex = (h) => [1, 3, 5].map((i) => +(parseInt(h.slice(i, i + 2), 16) / 255).toFixed(4))
const C = {
  black: [0, 0, 0],
  emerald600: hex('#059669'), // deep emerald  (glow centre)
  emerald400: hex('#34d399'), // bright emerald (glow mid)
  emerald100: hex('#d1fae5'), // pale emerald  (glow edge; pages)
  emerald200: hex('#a7f3d0'), // page folds / edges
  emerald500: hex('#10b981'), // pages seen through the lens (= UI --emerald)
  emerald700: hex('#047857'), // folds of lens pages
  emerald800: hex('#065f46'), // text lines on pale pages
  emerald900: hex('#064e3b'), // text lines on vivid lens pages
  glass: hex('#d9d9d9'), //      magnifier: light neutral, visible on black
}
const SRC = {
  slate: [0.267, 0.278, 0.357],
  white: [1, 1, 1],
  offWhite: [0.941, 0.941, 0.941],
  pinkA: [0.902, 0, 0.337],
  pinkB: [0.922, 0, 0.345],
  wineA: [0.486, 0.094, 0.243],
  wineB: [0.459, 0.11, 0.239],
}
const near = (a, b, tol = 0.006) => a.every((v, i) => Math.abs(v - b[i]) <= tol)

// layer-name pattern → list of [sourceColor, targetColor] for solid fills/strokes
const SOLID_RULES = [
  [/^Mag glass$/, [[SRC.slate, C.glass]]],
  [/^Page \d+$/, [[SRC.white, C.emerald100], [SRC.offWhite, C.emerald200], [SRC.slate, C.emerald800]]],
  [/^Coloured Page \d+$/, [
    [SRC.pinkA, C.emerald500], [SRC.pinkB, C.emerald500], [SRC.wineA, C.emerald700], [SRC.wineB, C.emerald700],
    [SRC.offWhite, C.emerald200], [SRC.slate, C.emerald900],
  ]],
]

const counts = {}
const bump = (k) => (counts[k] = (counts[k] || 0) + 1)

function recolorGradient(layerName, gf) {
  const k = gf.g.k.k
  const n = gf.g.p // number of colour stops; alpha stops follow and are left untouched
  for (let s = 0; s < n; s++) {
    const i = s * 4
    const pos = k[i]
    let target
    if (layerName === 'White gradient') target = C.black // white vignette → black vignette
    else if (layerName === 'Colour gradient') target = pos < 0.5 ? C.emerald600 : pos < 0.9 ? C.emerald400 : C.emerald100
    if (target) {
      k.splice(i + 1, 3, ...target)
      bump(`${layerName}: gradient stop @${pos}`)
    }
  }
}

function walk(node, layerName, rules) {
  if (Array.isArray(node)) return node.forEach((n) => walk(n, layerName, rules))
  if (!node || typeof node !== 'object') return
  if ((node.ty === 'fl' || node.ty === 'st') && node.c?.a === 0 && Array.isArray(node.c.k)) {
    const rgb = node.c.k.slice(0, 3)
    const hit = rules.find(([from]) => near(rgb, from))
    if (hit) {
      node.c.k.splice(0, 3, ...hit[1])
      bump(`${layerName}: ${node.ty} ${from2s(hit[0])} → ${from2s(hit[1])}`)
    }
  }
  if (node.ty === 'gf') recolorGradient(layerName, node)
  for (const v of Object.values(node)) walk(v, layerName, rules)
}
const from2s = (c) => '#' + c.map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('')

const data = JSON.parse(readFileSync(inPath, 'utf8'))
const required = ['Mag glass', 'White gradient', 'Colour gradient', 'Page 1', 'Coloured Page 2']
for (const name of required) {
  if (!data.layers.some((l) => l.nm.trim() === name)) throw new Error(`expected layer "${name}" not found — wrong file?`)
}

for (const layer of data.layers) {
  const name = layer.nm.trim()
  const rules = SOLID_RULES.find(([re]) => re.test(name))?.[1] ?? []
  walk(layer.shapes, name, rules)
}

// Gate: nothing gold / cream / white / pink may remain in a VISIBLE layer (track-matte layers are never drawn).
const FORBIDDEN = { gold: [0.898, 0.522, 0], cream: [0.949, 0.761, 0.5], white: SRC.white, offWhite: SRC.offWhite,
  pink: SRC.pinkA, pink2: SRC.pinkB, slate: SRC.slate }
const leftovers = []
for (const layer of data.layers) {
  if (layer.td === 1) continue // matte source
  const scan = (n) => {
    if (Array.isArray(n)) return n.forEach(scan)
    if (!n || typeof n !== 'object') return
    if ((n.ty === 'fl' || n.ty === 'st') && n.c?.a === 0) {
      for (const [label, col] of Object.entries(FORBIDDEN)) if (near(n.c.k.slice(0, 3), col)) leftovers.push(`${layer.nm.trim()}: ${n.ty} ${label}`)
    }
    if (n.ty === 'gf') {
      const k = n.g.k.k
      for (let s = 0; s < n.g.p; s++) {
        const rgb = k.slice(s * 4 + 1, s * 4 + 4)
        for (const [label, col] of Object.entries(FORBIDDEN)) if (near(rgb, col)) leftovers.push(`${layer.nm.trim()}: gradient ${label}`)
      }
    }
    Object.values(n).forEach(scan)
  }
  scan(layer.shapes)
}
// the magnifier's zero-width slate strokes are invisible; any other leftover is an error
const real = leftovers.filter((l) => !/^Mag glass: st slate|White gradient: st slate/.test(l))
if (real.length) {
  console.error('Unmapped colours left in visible layers:\n  ' + [...new Set(real)].join('\n  '))
  process.exit(1)
}

data.nm = 'Search (emerald dark)'
writeFileSync(outPath, JSON.stringify(data))
console.log(`wrote ${outPath}`)
for (const [k, v] of Object.entries(counts).sort()) console.log(`  ${String(v).padStart(3)} × ${k}`)
