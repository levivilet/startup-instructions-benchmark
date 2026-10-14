const { app, BrowserWindow } = require('electron')
const fs = require('node:fs')
const { setTimeout: delay } = require('node:timers/promises')
app.whenReady().then(() => {
  const window = new BrowserWindow({ width: 1000, height: 700 })
  if (process.argv.includes('--benchmark-verify-render')) {
    window.webContents.once('did-finish-load', async () => {
      try {
        const rendered = await window.webContents.executeJavaScript(
          'document.title === "Basic Electron" && document.querySelector("h1")?.textContent === "Basic Electron"'
        )
        process.stdout.write(`BENCHMARK_RENDER_VERIFIED=${rendered}\n`)
        if (!rendered) {
          app.exit(1)
          return
        }
        const exitSignal = process.env.BASIC_ELECTRON_BENCHMARK_EXIT_SIGNAL
        if (!exitSignal) {
          app.exit(1)
          return
        }
        const deadline = Date.now() + 10000
        while (!fs.existsSync(exitSignal) && Date.now() < deadline) await delay(10)
        if (fs.existsSync(exitSignal)) app.quit()
        else app.exit(1)
      } catch {
        process.stdout.write('BENCHMARK_RENDER_VERIFIED=false\n')
        app.exit(1)
      }
    })
  }
  window.loadURL('data:text/html,<title>Basic Electron</title><h1>Basic Electron</h1>')
})
