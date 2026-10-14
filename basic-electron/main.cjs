const { app, BrowserWindow } = require('electron')
app.whenReady().then(() => {
  const window = new BrowserWindow({ width: 1000, height: 700 })
  if (process.argv.includes('--benchmark-verify-render')) {
    window.webContents.once('did-finish-load', async () => {
      try {
        const rendered = await window.webContents.executeJavaScript(
          'document.title === "Basic Electron" && document.querySelector("h1")?.textContent === "Basic Electron"'
        )
        process.stdout.write(`BENCHMARK_RENDER_VERIFIED=${rendered}\n`)
        if (rendered) app.quit()
        else app.exit(1)
      } catch {
        process.stdout.write('BENCHMARK_RENDER_VERIFIED=false\n')
        app.exit(1)
      }
    })
  }
  window.loadURL('data:text/html,<title>Basic Electron</title><h1>Basic Electron</h1>')
})
