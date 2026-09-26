// Visual check helper (headless Chrome): node scripts/shot.mjs <url> <out.png> [steps-json]
// steps: [{"slow":["/api/search",1500]}|{"hover":"sel"}|{"type":["sel","text"]}|{"click":"sel"}|{"wait":ms}|{"shot":"file.png"}|{"width":n,"height":n}]
import puppeteer from 'puppeteer-core'

const [url, out, stepsJson] = process.argv.slice(2)
const steps = stepsJson ? JSON.parse(stepsJson) : []
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: 'new',
  args: ['--no-sandbox'],
})
const page = await browser.newPage()
const logs = []
page.on('console', (m) => logs.push(`[${m.type()}] ${m.text()}`))
page.on('pageerror', (e) => logs.push(`[pageerror] ${e.message}`))
await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 1 })
await page.goto(url, { waitUntil: 'networkidle0' })
for (const s of steps) {
  if (s.fail) {
    // make the first N matching requests fail at the network level, e.g. {"fail": ["/api/search", 2]} (server asleep)
    const [needle, times] = s.fail
    let left = times
    await page.setRequestInterception(true)
    page.on('request', (req) => {
      if (req.url().includes(needle) && req.method() !== 'OPTIONS' && left > 0) { left--; req.abort('connectionrefused') }
      else req.continue()
    })
  }
  if (s.slow) {
    // delay matching requests in the browser, e.g. {"slow": ["/api/search", 1500]} to see loading states
    const [needle, ms] = s.slow
    await page.setRequestInterception(true)
    page.on('request', (req) => {
      if (req.url().includes(needle)) setTimeout(() => req.continue(), ms)
      else req.continue()
    })
  }
  if (s.width) await page.setViewport({ width: s.width, height: s.height || 800 })
  if (s.hover) await page.hover(s.hover)
  if (s.type) { await page.click(s.type[0]); await page.keyboard.type(s.type[1], { delay: 20 }) }
  if (s.press) await page.keyboard.press(s.press)
  if (s.click) await page.click(s.click)
  if (s.wait) await new Promise((r) => setTimeout(r, s.wait))
  if (s.eval) console.log('eval:', JSON.stringify(await page.evaluate(s.eval)))
  if (s.shot) await page.screenshot({ path: s.shot, fullPage: !!s.full })
}
await page.screenshot({ path: out })
if (logs.length) console.log(logs.join('\n'))
await browser.close()
