'use strict'
async function startGallery() {
  const resource = await fetch('catalog.json')
  if (!resource.ok) throw Error('动效词库加载失败，请刷新页面。')
  window.DATA = await resource.json()
  for (const file of ['renderer.js', 'illustrations.js', 'gallery.js']) {
    await new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = file
      script.onload = resolve
      script.onerror = reject
      document.body.append(script)
    })
  }
}
startGallery().catch(() => {
  document.getElementById('notice').textContent = '素材库加载失败，请刷新页面。'
})
