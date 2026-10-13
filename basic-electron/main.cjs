const { app, BrowserWindow } = require('electron')
app.whenReady().then(() => {
  const window = new BrowserWindow({ width: 1000, height: 700 })
  window.loadURL('data:text/html,<title>Basic Electron</title><h1>Basic Electron</h1>')
})
