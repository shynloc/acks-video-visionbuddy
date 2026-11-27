'use strict'

const $ = id => document.getElementById(id)
const api = '/api/personal/'
const form = $('asset-form')
const frame = $('personal-proof')
const browserMode = document.body.dataset.browserAssets === 'true'
const browserLibrary = browserMode ? window.VisionBuddyBrowserAssets : null
const names = {png:'PNG',svg:'SVG',html:'HTML',video:'透明视频'}
if (browserMode) names.video = '视频'
let items = []
let active = null
let versions = []
let proof = ''
let previewMedia = null
let previewUrl = ''
let editMode = 'new'
let parent = null
let busy = false
let listTicket = 0
let viewTicket = 0
let timer = 0
const marked = new Set()

function status(id, text = '', error = false) {
  $(id).textContent = text
  $(id).dataset.error = String(error)
}

function node(tag, text = '', style = '') {
  const element = document.createElement(tag)
  element.textContent = text
  if (style) element.className = style
  return element
}

function address(action, fields = {}) {
  return api + action + '?' + new URLSearchParams(fields)
}

async function request(url, options) {
  if (browserMode) throw Error('这里使用浏览器素材库。')
  const res = await fetch(url, options)
  if (!res.ok) {
    const error = await res.json().catch(() => ({}))
    throw Error(error.error || '读取本机素材失败。')
  }
  return res
}

function paintList() {
  const list = $('assets')
  list.replaceChildren()
  if (!items.length) {
    list.append(node('p', $('asset-search').value ? '没有找到匹配的素材。' : '还没有个人素材。可从上方导入第一款。'))
    return
  }
  for (const item of items) {
    const button = node('button', '', 'line')
    button.type = 'button'
    button.dataset.asset = item.assetId
    button.setAttribute('aria-pressed', String(active?.assetId === item.assetId))
    const kind = names[item.media.import.kind]
    const image = browserMode ? node('span', kind, 'asset-thumb asset-format') : node('img', '', 'asset-thumb')
    if (!browserMode) {
      image.alt = ''
      image.loading = 'lazy'
      image.src = address('thumb', {ref:item.ref})
    }
    const caption = node('span', '', 'asset-caption')
    caption.append(node('span', item.name, 'line-quote'),
                   node('span', names[item.media.import.kind] + ' · ' + item.ref, 'stamp'))
    button.append(image, caption)
    button.onclick = () => { select(item.assetId) }
    if (browserMode) {
      list.append(button)
      continue
    }
    const wrap = node('div', '', 'asset-list-row')
    const check = node('input', '', 'team-check')
    check.type = 'checkbox'
    check.checked = marked.has(item.ref)
    check.setAttribute('aria-label', '选择分享 ' + item.name)
    check.onchange = () => {
      if (check.checked) marked.add(item.ref)
      else marked.delete(item.ref)
      refreshSharing()
    }
    wrap.append(check, button)
    list.append(wrap)
  }
}

async function reload(chosen) {
  const ticket = ++listTicket
  const query = $('asset-search').value
  const result = browserMode ? await browserLibrary.list(query) :
    (await (await request(address('library', {q:query}))).json()).items
  if (ticket !== listTicket) return
  items = result
  paintList()
  if (chosen) await select(chosen)
  else if (!active && items[0]) await select(items[0].assetId)
}

async function select(code) {
  const ticket = ++viewTicket
  status('detail-status', '正在读素材…')
  try {
    const history = browserMode ? await browserLibrary.revisions(code) :
      (await (await request(address('versions', {ref:code}))).json()).versions
    if (ticket !== viewTicket) return
    versions = history
    const item = versions.find(value => value.ref === code) || versions[0]
    if (!item) throw Error('找不到这条个人素材。')
    await show(item, ticket)
  } catch (error) {
    if (ticket === viewTicket) status('detail-status', error.message, true)
  }
}

async function showOriginal(item, ticket) {
  const original = await browserLibrary.original(item)
  const kind = item.media.import.kind
  const html = kind === 'html' ? await browserLibrary.htmlPreview(original) : ''
  if (ticket !== viewTicket) return
  previewUrl = URL.createObjectURL(original)
  const download = $('download-original')
  download.href = previewUrl
  download.download = item.originalName
  if (html) {
    proof = html
    frame.srcdoc = html
    frame.hidden = false
    return
  }
  previewMedia = node(kind === 'video' ? 'video' : 'img', '', 'browser-original')
  if (kind === 'video') {
    previewMedia.controls = true
    previewMedia.playsInline = true
    previewMedia.preload = 'metadata'
    previewMedia.setAttribute('aria-label', item.name)
  } else {
    previewMedia.alt = item.name
  }
  previewMedia.addEventListener('error', () => {
    if (ticket === viewTicket) status('detail-status', kind === 'video' ?
      '当前浏览器无法播放这个编码。可下载原件，或换成浏览器支持的视频。' : '无法预览这份图片。', true)
  })
  previewMedia.src = previewUrl
  $('own-stage').append(previewMedia)
}

async function show(item, ticket = ++viewTicket) {
  active = item
  proof = ''
  frame.removeAttribute('srcdoc')
  if (browserMode) {
    frame.hidden = true
    previewMedia?.remove()
    previewMedia = null
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    previewUrl = ''
    $('download-original').removeAttribute('href')
  }
  $('asset-ref').textContent = item.ref
  $('detail-name').textContent = item.name
  $('detail-uses').textContent = item.uses
  $('detail-keywords').textContent = item.keywords.join('、') || '未登记'
  for (const key of ['author','origin','license']) $('detail-' + key).textContent = item.rights[key] || '未登记'
  $('asset-versions').replaceChildren(...versions.map(v => new Option(v.ref + (v === versions[0] ? ' · 当前版' : ''), v.ref)))
  $('asset-versions').value = item.ref
  $('version-note').textContent = browserMode ?
    (item === versions[0] ? '正在查看当前版。' : '正在查看保留的旧版。') :
    (item === versions[0] ? '当前版用于新推荐。' : '旧版保留，可供已有工程使用。')
  $('replace-asset').disabled = item !== versions[0]
  $('edit-asset').disabled = item !== versions[0]
  if (!browserMode) $('download-original').href = address('original', {ref:item.ref})
  $('replay-asset').hidden = browserMode ? !['video','html'].includes(item.media.import.kind) : item.media.frames === 1
  $('asset-detail').hidden = false
  $('own-stage').hidden = false
  if (!browserMode) {
    $('own-stage').style.setProperty('--overlay-aspect', item.media.width + ' / ' + item.media.height)
    $('own-stage').style.setProperty('--asset-ratio', item.media.width / item.media.height)
  }
  paintList()
  try {
    if (browserMode) {
      await showOriginal(item, ticket)
      if (ticket === viewTicket) status('detail-status')
      return
    }
    const html = await (await request(address('preview', {ref:item.ref}))).text()
    if (ticket !== viewTicket) return
    proof = html
    frame.srcdoc = proof
    status('detail-status')
  } catch (error) {
    if (ticket === viewTicket) status('detail-status', error.message, true)
  }
}

function importOptions() {
  if (browserMode) return
  const name = $('asset-file').files[0]?.name.toLowerCase() || ''
  const video = /\.(mov|mp4|webm|mkv)$/.test(name)
  const html = /\.html?$/.test(name)
  $('media-options').hidden = !(video || html)
  $('start-field').hidden = !video
  $('canvas-field').hidden = !html
  $('asset-seconds').placeholder = video ? '默认最多 12 秒' : '默认 3 秒'
  $('file-tip').textContent = video ? '原件随素材保存。请选取最长 12 秒的可导出片段。' :
    html ? '单文件 HTML 可保留原件，有逐帧函数或 CSS 动画时会生成透明动画。' :
    '支持 PNG、SVG、带 Alpha 的视频和可离线打开的单文件 HTML。'
}

function openEditor(mode = 'new', item = null) {
  editMode = mode
  parent = item
  form.reset()
  $('file-label').hidden = mode === 'edit'
  $('form-label').textContent = mode === 'replace' ? '换版 · ' + item.ref :
    mode === 'edit' ? '修改登记 · ' + item.ref : browserMode ? '导入素材' : '导入本机素材'
  $('save-asset').textContent = mode === 'replace' ? '保存新版' : mode === 'edit' ? '保存登记新版' : '导入素材'
  $('cancel-asset').hidden = mode === 'new'
  if (item) {
    $('asset-name').value = item.name
    $('asset-uses').value = item.uses
    $('asset-keywords').value = item.keywords.join('、')
    for (const key of ['author','license','origin']) $('asset-' + key).value = item.rights[key]
  }
  importOptions()
  status('asset-status')
  if (item) {
    $('asset-form-card').open = true
    $('asset-form-card').scrollIntoView({block:'nearest'})
  }
}

function utf8Header(value) {
  const bytes = new TextEncoder().encode(JSON.stringify(value))
  return btoa(Array.from(bytes, v => String.fromCharCode(v)).join(''))
}

form.onsubmit = async event => {
  event.preventDefault()
  if (busy) return
  const file = $('asset-file').files[0]
  if (editMode !== 'edit' && !file) return status('asset-status', '请先选择本机文件。', true)
  const meta = Object.fromEntries(['name','uses','keywords','author','license','origin','seconds','start','canvas']
    .map(key => [key,$('asset-' + key).value]))
  if (parent) meta.ref = parent.ref
  busy = true
  for (const input of form.querySelectorAll('input, textarea, select, button')) input.disabled = true
  status('asset-status', browserMode ? '正在保存到浏览器…' : '正在本机保存并生成小样…')
  try {
    let item
    if (browserMode) {
      item = await browserLibrary.save(meta, file, parent)
    } else {
      const options = file ? {method:'POST', body:file, headers:{
        'Content-Type':'application/octet-stream', 'X-VisionBuddy-Metadata':utf8Header({...meta, filename:file.name})
      }} : {method:'POST', body:JSON.stringify(meta), headers:{'Content-Type':'application/json'}}
      item = (await (await request(api + (file ? 'import' : 'edit'), options)).json()).item
    }
    $('asset-search').value = ''
    openEditor()
    $('asset-form-card').open = false
    await reload(item.ref)
    status('detail-status', '已保存 ' + item.ref)
  } catch (error) {
    status('asset-status', error.message, true)
  } finally {
    busy = false
    for (const input of form.querySelectorAll('input, textarea, select, button')) input.disabled = false
  }
}

function refreshSharing() {
  $('team-save').disabled = !marked.size
  $('team-save').textContent = marked.size ? '保存已选素材 · ' + marked.size : '保存已选素材'
}

$('team-save').onclick = async () => {
  if (!marked.size) return
  $('team-save').disabled = true
  status('team-status', '正在保存选中的素材版本及授权…')
  try {
    const response = await request(api+'share', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({refs:[...marked]})})
    const url = URL.createObjectURL(await response.blob())
    const link = node('a')
    link.href = url
    link.download = 'VisionBuddy-个人素材分享包.zip'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 30000)
    status('team-status', '个人素材分享包已保存。')
  } catch (error) { status('team-status',error.message,true) }
  finally { refreshSharing() }
}
$('team-open').onclick = () => $('team-file').click()
$('team-file').onchange = async () => {
  const file = $('team-file').files[0]
  if (!file) return
  $('team-open').disabled = true
  status('team-status','正在恢复分享包…')
  try {
    const result = await (await request(api+'receive', {method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file})).json()
    const mapping = Object.entries(result.versions)
    const conflicts = mapping.filter(([from,to]) => from !== to).length
    $('asset-search').value = ''
    await reload(mapping[0]?.[1])
    status('team-status', '已恢复 '+mapping.length+' 个素材版本。'+(conflicts ? ' 有 '+conflicts+' 个冲突版本保留在独立编号下。' : ''))
  } catch (error) { status('team-status',error.message,true) }
  finally { $('team-open').disabled=false; $('team-file').value='' }
}

$('asset-search').oninput = () => {
  clearTimeout(timer)
  timer = setTimeout(() => reload().catch(error => status('detail-status', error.message, true)), 100)
}
$('asset-versions').onchange = () => {
  const item = versions.find(version => version.ref === $('asset-versions').value)
  if (item) show(item)
}
$('asset-file').onchange = importOptions
$('replace-asset').onclick = () => { if (!busy) openEditor('replace',active) }
$('edit-asset').onclick = () => { if (!busy) openEditor('edit',active) }
$('replay-asset').onclick = () => {
  if (proof) frame.srcdoc = proof
  else if (previewMedia?.tagName === 'VIDEO' && previewMedia.readyState) {
    previewMedia.currentTime = 0
    previewMedia.play().catch(() => status('detail-status', '可在播放器中点播放。', true))
  }
}
$('cancel-asset').onclick = () => { openEditor(); $('asset-form-card').open = false }
const selectedRef = new URL(location.href).searchParams.get('ref')
if (browserMode && !browserLibrary) {
  status('detail-status', '浏览器素材库未载入，请刷新页面。', true)
} else {
  const ready = browserMode ? browserLibrary.database() : Promise.resolve()
  ready.then(() => {
    $('save-asset').disabled = false
    return reload(selectedRef)
  }).catch(error => status('detail-status', error.message || '无法读取浏览器素材库。', true))
}
