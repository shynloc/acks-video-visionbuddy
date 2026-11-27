'use strict'

window.VisionBuddyBrowserAssets = (() => {
  const types = {
    png: ['png', 'image/png'],
    svg: ['svg', 'image/svg+xml'],
    html: ['html', 'text/html'],
    htm: ['html', 'text/html'],
    mp4: ['video', 'video/mp4'],
    mov: ['video', 'video/quicktime'],
    webm: ['video', 'video/webm'],
    mkv: ['video', 'video/x-matroska'],
  }
  let ready

  function read(request) {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
  }

  function database() {
    if (!ready) {
      ready = new Promise((resolve, reject) => {
        const request = indexedDB.open('visionbuddy-personal-assets', 1)
        request.onupgradeneeded = () => {
          const db = request.result
          db.createObjectStore('heads', { keyPath: 'assetId' })
          const versions = db.createObjectStore('versions', { keyPath: 'ref' })
          versions.createIndex('assetId', 'assetId')
          db.createObjectStore('files')
        }
        request.onerror = () => reject(request.error)
        request.onblocked = () => reject(Error('请关闭其他「我的素材」页面，再刷新重试。'))
        request.onsuccess = () => {
          const db = request.result
          db.onversionchange = () => {
            db.close()
            ready = null
          }
          resolve(db)
        }
      }).catch(error => {
        ready = null
        throw error
      })
    }
    return ready
  }

  async function query(name, select) {
    const db = await database()
    return read(select(db.transaction(name).objectStore(name)))
  }

  async function list(search) {
    const key = search.trim().normalize('NFKC').toLowerCase()
    const items = await query('heads', store => store.getAll())
    return items.filter(item => [item.name, item.uses, item.ref, ...item.keywords].some(
      text => text.normalize('NFKC').toLowerCase().includes(key),
    )).sort((a, b) => b.updated - a.updated || b.ref.localeCompare(a.ref))
  }

  async function revisions(code) {
    const history = await query('versions', store => store.index('assetId').getAll(code.split('@')[0]))
    return history.sort((a, b) => b.version - a.version)
  }

  function decode(file) {
    return file.arrayBuffer().then(bytes => {
      try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes) }
      catch { throw Error('请选择 UTF-8 编码的文件。') }
    })
  }

  async function prepare(file) {
    const extension = file.name.split('.').at(-1).toLowerCase()
    if (!Object.hasOwn(types, extension)) throw Error('请选择 PNG、SVG、视频或单文件 HTML。')
    const [kind, mime] = types[extension]
    const limit = (kind === 'svg' || kind === 'html') ? 12 : 128
    if (!file.size || file.size > limit * 1024**2) throw Error('文件为空或超过 ' + limit + ' MB。')
    if (kind === 'png') {
      const signature = new Uint8Array(await file.slice(0, 8).arrayBuffer())
      if (signature.join(',') !== '137,80,78,71,13,10,26,10') throw Error('无法识别这份 PNG 原件。')
    }
    if (kind === 'svg') {
      const markup = await decode(file)
      if (/<!DOCTYPE/i.test(markup)) throw Error('请选择可独立打开的 SVG 文件。')
      const xml = new DOMParser().parseFromString(markup, 'image/svg+xml')
      if (xml.documentElement.localName !== 'svg' || xml.querySelector('parsererror'))
        throw Error('无法读取这份 SVG 原件。')
    }
    if (kind === 'html') await decode(file)
    return {
      fileId: crypto.randomUUID(),
      originalName: file.name,
      media: { import: { kind }, mime },
      original: file.slice(0, file.size, mime),
    }
  }

  async function save(meta, file, parent) {
    const prepared = file ? await prepare(file) : null
    const uses = meta.uses.trim()
    const name = meta.name.trim() || prepared?.originalName.replace(/\.[^.]+$/, '').slice(0, 96)
    if (!name || !uses) throw Error('请填写素材名称和用途。')
    const db = await database()
    const tx = db.transaction(['heads', 'versions', 'files'], 'readwrite')
    const done = new Promise((resolve, reject) => {
      tx.oncomplete = resolve
      tx.onabort = tx.onerror = () => reject(tx.error || Error('浏览器未能保存这次更改。'))
    })
    try {
      const heads = tx.objectStore('heads')
      const current = parent ? await read(heads.get(parent.assetId)) : null
      if (parent && current?.ref !== parent.ref) throw Error('这款素材已更新。重新选择当前版后再编辑。')
      if (!current && !prepared) throw Error('请先选择原件。')
      const assetId = current?.assetId || 'MY-' + crypto.randomUUID().replaceAll('-', '').slice(0, 10).toUpperCase()
      const version = (current?.version || 0) + 1
      const { fileId, originalName, media } = prepared || current
      const item = {
        assetId, version, ref: assetId + '@V' + String(version).padStart(4, '0'),
        name, uses, fileId, originalName, media, updated: Date.now(),
        keywords: [...new Set(meta.keywords.split(/[、，,；;\n]/).map(word => word.trim()).filter(Boolean))],
        rights: Object.fromEntries(['author', 'origin', 'license'].map(key => [key, meta[key].trim()])),
      }
      if (prepared) tx.objectStore('files').add(prepared.original, fileId)
      tx.objectStore('versions').add(item)
      if (current) heads.put(item)
      else heads.add(item)
      await done
      return item
    } catch (error) {
      try { tx.abort() } catch {}
      await done.catch(() => {})
      if (error.name === 'QuotaExceededError') throw Error('浏览器存储空间不足。可以先下载并备份已有原件。')
      throw error
    }
  }

  async function original(item) {
    const file = await query('files', store => store.get(item.fileId))
    if (!file) throw Error('浏览器找不到这份素材的原件。')
    return file
  }

  async function htmlPreview(file) {
    const template = document.createElement('template')
    template.innerHTML = await decode(file)
    for (const element of template.content.querySelectorAll('script, iframe, frame, object, embed, link, base, meta, form'))
      element.remove()
    for (const element of template.content.querySelectorAll('a, area, svg a')) {
      for (const name of ['href', 'xlink:href', 'target', 'ping', 'download']) element.removeAttribute(name)
    }
    const policy = "default-src 'none'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; form-action 'none'; base-uri 'none'"
    return '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' +
      policy + '">' + template.innerHTML
  }

  return { database, list, revisions, save, original, htmlPreview }
})()
