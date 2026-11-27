'use strict'

const $ = id => document.getElementById(id)
const player = $('player')
const overlay = $('overlay')
const stage = $('stage')
const online = document.body.dataset.online === 'true'
const draftKey = 'visionbuddy-desk/1'
const states = { adopted: '已采用', pending: '待选择', skipped: '已跳过', none: '纯口播', blocked: '检查标注', plain: '未推荐' }
let mode = 'script'
let plan = null
let decisions = {}
let selected = null
let videoUrl = ''
let videoReady = null
let recording = null
let videoSize = 2 * 1024 ** 3
let previewRequest = 0
let frameReady = false
let animation = 0
let playUntil = null
let exporting = false
let preparing = false

function message(id, text = '', error = false) {
  const element = $(id)
  element.textContent = text
  element.dataset.error = String(error)
}

function element(tag, text, className) {
  const el = document.createElement(tag)
  if (text) el.textContent = text
  if (className) el.className = className
  return el
}

async function request(path, data, content = 'application/json') {
  const body = content === 'application/json' ? JSON.stringify(data) : data
  const res = await fetch('/api/desk/' + path, { method: 'POST', headers: { 'Content-Type': content }, body })
  if (!res.ok) {
    const failure = await res.json().catch(() => ({}))
    throw Error(failure.error || '请求失败，请重试。')
  }
  return res
}

function switchMode(next) {
  mode = next
  for (const button of document.querySelectorAll('[data-mode]')) button.setAttribute('aria-pressed', String(button.dataset.mode === mode))
  for (const panel of document.querySelectorAll('[data-inputs]')) panel.hidden = panel.dataset.inputs !== mode
  $('speech-options').hidden = online || Boolean($('video-srt').files[0])
}

function saveDraft() {
  if (!plan) return
  try {
    localStorage.setItem(draftKey, JSON.stringify({ source: plan.source, decisions, selected, mode, recording }))
  } catch {
    message('intake-status', '浏览器无法保存这份草稿，当前审核仍可继续。', true)
  }
}

function readDraft() {
  try { return JSON.parse(localStorage.getItem(draftKey) || 'null') } catch { return null }
}

function stamp(seconds) {
  const ms = Math.round(seconds * 1000)
  const two = value => String(value).padStart(2, '0')
  const minutes = two(Math.floor(ms / 60000) % 60)
  const clock = minutes + ':' + two(Math.floor(ms / 1000) % 60) + '.' + String(ms % 1000).padStart(3, '0')
  return ms >= 3600000 ? two(Math.floor(ms / 3600000)) + ':' + clock : clock
}

function timelineText(row) {
  return row.time ? stamp(row.time.start) + ' – ' + stamp(row.time.end) : '原句 ' + Number(row.id.slice(1))
}

function decision(row) {
  return decisions[row.id] || { state: row.mode === 'fixed' ? 'adopted' : 'pending', choice: 0 }
}

function rowState(row) {
  return row.candidates.length ? decision(row).state : row.mode
}

function current() {
  const row = plan?.rows.find(item => item.id === selected)
  return row ? [row, row.candidates[decision(row).choice || 0]] : []
}

function placeFor(row, candidate) {
  const { side, scale, start, end } = decision(row)
  return {
    ...candidate.placement,
    ...(side === undefined ? {} : { side }),
    ...(scale === undefined ? {} : { scale }),
    ...(start === undefined ? {} : { start }),
    ...(end === undefined ? {} : { end }),
  }
}

function updateDecision(row, change) {
  decisions[row.id] = { ...decision(row), ...change }
  saveDraft()
}

function videoIdentity() {
  const file = $('video-file').files[0]
  return file ? JSON.stringify([file.name, file.size, file.lastModified]) : null
}

function matchesRecording() {
  if (!recording) return true
  try {
    const pinned = JSON.parse(recording)
    const currentFile = JSON.parse(videoIdentity())
    return Boolean(currentFile && pinned[0] === currentFile[0] && pinned[1] === currentFile[1])
  } catch { return false }
}

function relinkAvailable() {
  const duration = plan?.source.duration
  return Boolean(plan && plan.source.kind !== 'script' && videoUrl && Number.isFinite(player.duration)
    && (duration == null || Math.abs(duration - player.duration) <= .15))
}

function useVideo(row) {
  return Boolean(videoUrl && mode === 'video' && row?.time && Number.isFinite(player.duration) &&
    matchesRecording())
}

function sampleFrames(candidate, place) {
  if (candidate.personal) return candidate.totalFrames
  const seconds = place.start === undefined || candidate.fixedSeconds ? candidate.seconds : place.end - place.start
  return Math.max(1, Math.min(300, Math.round((seconds || candidate.seconds) * 25)))
}

function paint(frame, total) {
  if (frameReady) overlay.contentWindow.postMessage({ type: 'visionbuddy-frame', frame, total }, '*')
}

function stop() {
  cancelAnimationFrame(animation)
  animation = 0
  playUntil = null
  if (!player.paused) player.pause()
}

function paintVideo() {
  const [row, candidate] = current()
  if (!candidate || !useVideo(row) || !frameReady) return
  const place = placeFor(row, candidate)
  const within = player.currentTime >= place.start - .04 && player.currentTime <= place.end + .02
  overlay.hidden = !within
  if (within) {
    const total = sampleFrames(candidate, place)
    paint(Math.min(total - 1, Math.max(0, Math.floor((player.currentTime - place.start) * 25))), total)
  }
}

function playVideoClock() {
  cancelAnimationFrame(animation)
  const tick = () => {
    if (playUntil !== null && player.currentTime >= playUntil) {
      player.pause()
      playUntil = null
      return
    }
    paintVideo()
    if (!player.paused) animation = requestAnimationFrame(tick)
  }
  tick()
}

function playSample() {
  const [row, candidate] = current()
  if (!candidate || !frameReady) return
  stop()
  const place = placeFor(row, candidate)
  if (row.time && (!Number.isFinite(place.start) || !Number.isFinite(place.end) || place.end <= place.start ||
                   place.start < 0 || place.end - place.start > 12.001)) {
    message('review-status', '请填写有效的起止时间，单条画面最多 12 秒。', true)
    return
  }
  if (row.time && candidate.personal && candidate.animated && place.end - place.start > candidate.originalSeconds + .002) {
    message('review-status', '摆放时间不能长于这条个人素材。', true)
    return
  }
  if (useVideo(row)) {
    if (place.end > player.duration + .01) {
      message('review-status', '所选画面超出当前视频，请调整结束秒数。', true)
      return
    }
    playUntil = place.end
    player.currentTime = place.start
    player.play().catch(() => message('review-status', '视频暂时无法播放，请重试或选择兼容视频。', true))
    return
  }
  const total = sampleFrames(candidate, place)
  const last = candidate.personal ? Math.min(total - 1, Math.max(0, Math.round(candidate.seconds * 25) - 1)) : total - 1
  const began = performance.now()
  const tick = now => {
    const frame = Math.min(last, Math.floor((now - began) / 40))
    paint(frame, total)
    if (frame < last) animation = requestAnimationFrame(tick)
  }
  overlay.hidden = false
  animation = requestAnimationFrame(tick)
}

function applyPlacement(row, candidate, populate = true) {
  const place = placeFor(row, candidate)
  if (populate) {
    $('clip-start').value = place.start ?? ''
    $('clip-end').value = place.end ?? ''
    $('side').value = place.side
    $('scale').value = Math.round(place.scale * 100)
  }
  overlay.dataset.side = place.side
  stage.style.setProperty('--overlay-width', (place.scale * 100) + '%')
  paintVideo()
}

function statusControls(row, candidate) {
  const status = rowState(row)
  $('adopt').textContent = status === 'adopted' ? '已采用' : '采用'
  $('adopt').disabled = status === 'adopted'
  $('skip').textContent = status === 'skipped' ? '恢复待选' : '跳过'
  $('alternate').hidden = row.candidates.length < 2
  $('play').disabled = !frameReady
  $('review-actions').hidden = !candidate
}

function lineList() {
  if (!plan) return
  const list = $('lines')
  const visible = plan.rows.filter(row => row.mode !== 'plain' || $('show-plain').checked || selected === row.id)
  const elements = []
  for (const row of visible) {
    const button = element('button', '', 'line')
    button.type = 'button'
    button.dataset.row = row.id
    button.setAttribute('aria-pressed', String(row.id === selected))
    const meta = element('span', '', 'line-meta')
    const state = rowState(row)
    const label = element('span', states[state], 'state')
    label.dataset.state = state
    meta.append(element('time', timelineText(row), 'stamp'), label)
    if (row.mode === 'fixed') meta.append(element('span', '稿内指定', 'state'))
    button.append(meta, element('span', row.quote, 'line-quote'))
    button.onclick = () => { selectRow(row.id, true) }
    elements.push(button)
  }
  list.replaceChildren(...elements)
  if (!elements.length) list.append(element('p', '这份口播暂时没有合适的推荐。可显示全部原句或修改画面标注。'))
  const stats = plan.rows.reduce((out, row) => {
    const key = rowState(row)
    out[key] = (out[key] || 0) + 1
    return out
  }, {})
  $('counts').textContent = plan.rows.length + ' 条原句 · ' + (stats.pending || 0) + ' 待选 · ' +
    (stats.adopted || 0) + ' 已采用 · ' + (stats.none || 0) + ' 纯口播'
  $('export-count').textContent = '已采用 ' + (stats.adopted || 0) + ' 条'
  $('export').disabled = exporting || !stats.adopted
}

function pickVersion(row, index) {
  if ((decision(row).choice || 0) === index) return
  updateDecision(row, { choice: index, state: 'pending' })
  selectRow(row.id)
}

async function selectRow(id, listFocus = false) {
  selected = id
  saveDraft()
  lineList()
  if (listFocus) $('lines').querySelector('[aria-pressed="true"]')?.focus({ preventScroll: true })
  const [row, candidate] = current()
  const epoch = ++previewRequest
  frameReady = false
  stop()
  overlay.onload = null
  overlay.hidden = true
  message('review-status')
  $('proof-time').textContent = row ? timelineText(row) : ''
  $('proof-quote').textContent = row?.quote || '选择一句查看'
  $('proof-reason').textContent = candidate?.versionReason || row?.reason || (row ? '此句保留口播。' : '')
  $('choices').replaceChildren()
  $('placement').hidden = !candidate || !row.time
  $('relink-video').hidden = !relinkAvailable() || matchesRecording()
  player.hidden = !useVideo(row)
  stage.classList.toggle('video', !player.hidden)
  stage.style.setProperty('--video-ratio', String(player.videoWidth / player.videoHeight || 16 / 9))
  stage.hidden = !candidate && player.hidden
  $('review-actions').hidden = !candidate
  if (!candidate) {
    overlay.removeAttribute('srcdoc')
    if (row?.notes.length && row.mode !== 'none') message('review-status', row.notes.join('　'))
    if (useVideo(row)) player.currentTime = row.time.start
    return
  }

  for (const [index, version] of row.candidates.entries()) {
    const button = element('button', (version.personal ? '我的素材 · ' : '') + version.title + '  ' + version.codes.join(' · '))
    button.type = 'button'
    button.setAttribute('aria-pressed', String(index === (decision(row).choice || 0)))
    button.onclick = () => pickVersion(row, index)
    $('choices').append(button)
  }
  stage.style.setProperty('--overlay-aspect', candidate.aspect.join(' / '))
  applyPlacement(row, candidate)
  statusControls(row, candidate)
  message('review-status', '正在准备透明小样…')
  try {
    const res = await request('preview', { source: plan.source, row: row.id, choice: decision(row).choice || 0 })
    const html = await res.text()
    if (epoch !== previewRequest) return
    overlay.onload = () => {
      if (epoch !== previewRequest) return
      frameReady = true
      overlay.hidden = false
      statusControls(row, candidate)
      const place = placeFor(row, candidate)
      const frames = sampleFrames(candidate, place)
      if (useVideo(row)) {
        player.currentTime = Math.min(Math.max(0, place.start || 0), player.duration)
        paintVideo()
      } else {
        paint(candidate.personal ? candidate.poster :
          candidate.effects.length ? Math.round((frames - 1) * .55) : frames - 1, frames)
      }
      const hint = row.time && !useVideo(row) ? '沿用原时间码 · 可调摆放起止。' :
        useVideo(row) ? '可在原片上试看，调整左右位置和宽度。' : '对应原句 · 时间待与原片对齐。'
      message('review-status', hint)
    }
    overlay.srcdoc = html
  } catch (error) {
    if (epoch === previewRequest) message('review-status', error.message, true)
  }
}

function loadPlan(value, prior = {}, active = null, videoID = null) {
  plan = value
  recording = videoID
  decisions = prior
  const choices = plan.rows.filter(row => row.mode !== 'plain')
  const row = choices.find(item => item.candidates.length) || choices[0]
  $('review').hidden = false
  $('intake').open = false
  $('source-summary').textContent = (plan.source.kind === 'script' ? '口播稿' :
    plan.source.kind === 'srt' ? 'SRT 时间码' : '本机转写时间码') + ' · ' + plan.rows.length + ' 条原句'
  $('warnings').hidden = !plan.warnings.length
  $('warnings').textContent = plan.warnings.join(' ')
  selectRow(active && plan.rows.some(item => item.id === active) ? active : row?.id || null)
}

async function attachVideo(file) {
  stop()
  if (videoUrl) URL.revokeObjectURL(videoUrl)
  videoUrl = ''
  if (!file) {
    player.removeAttribute('src')
    player.load()
    return null
  }
  videoUrl = URL.createObjectURL(file)
  return new Promise((resolve, reject) => {
    player.onloadedmetadata = () => {
      if (Number.isFinite(player.duration) && player.duration > 0) resolve(player.duration)
      else reject(Error('无法读取视频时长。'))
    }
    player.onerror = () => reject(Error('浏览器无法播放这段视频。可使用其 MP4 版本或先导入 SRT。'))
    player.src = videoUrl
  })
}

async function captionText(file) {
  const bytes = new Uint8Array(await file.arrayBuffer())
  if (bytes[0] === 0xff && bytes[1] === 0xfe) return new TextDecoder('utf-16le').decode(bytes)
  if (bytes[0] === 0xfe && bytes[1] === 0xff) return new TextDecoder('utf-16be').decode(bytes)
  try { return new TextDecoder('utf-8', {fatal:true}).decode(bytes) }
  catch { return new TextDecoder('gb18030', {fatal:true}).decode(bytes) }
}

async function buildFromInput() {
  if (mode === 'script') return (await request('plan', { fresh:true, source: { kind: 'script', text: $('script').value } })).json()
  const attach = mode === 'srt' ? $('srt').files[0] : $('video-srt').files[0]
  if (mode === 'srt' && !attach) throw Error('请选择 SRT 字幕文件。')
  const duration = mode === 'video' && videoReady ? await videoReady : null
  if (mode === 'video' && !duration) throw Error('先选择已有视频。')
  if (attach) {
    if (attach.size > 500000) throw Error('SRT 文件过大，请使用对应的口播段落。')
    return (await request('plan', { fresh:true, source: { kind: 'srt', text: await captionText(attach), duration } })).json()
  }
  if (online) throw Error('请为视频选择配套 SRT。原片将在浏览器中播放。')
  if (!$('model').value) throw Error('本机没有可用的 Whisper 模型。可以先导入配套 SRT。')
  if ($('video-file').files[0].size > videoSize) throw Error('本机转写最多支持 2 GB。较大的视频可直接配套 SRT 试看。')
  const params = new URLSearchParams({ model: $('model').value, language: $('language').value })
  message('intake-status', '正在本机转写视频声音。完成后将按时间码推荐。')
  return (await request('transcribe?' + params.toString(), $('video-file').files[0], 'application/octet-stream')).json()
}

async function submitPlan(event) {
  event.preventDefault()
  if (preparing) return
  preparing = true
  $('plan-button').disabled = true
  for (const input of document.querySelectorAll('#intake-form input, #intake-form select, .mode button')) input.disabled = true
  message('intake-status', '正在读口播内容…')
  try {
    const result = await buildFromInput()
    message('intake-status')
    loadPlan(result, {}, null, mode === 'video' ? videoIdentity() : null)
  } catch (error) {
    message('intake-status', error.message, true)
  } finally {
    for (const input of document.querySelectorAll('#intake-form input, #intake-form select, .mode button')) input.disabled = false
    $('plan-button').disabled = false
    preparing = false
  }
}

function download(body, name) {
  const url = URL.createObjectURL(body)
  const link = element('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 30000)
}

function projectState() {
  return {libraryRelease:plan.libraryRelease, source:plan.source, decisions, selected, mode, recording}
}

async function saveProject() {
  if (!plan || preparing || exporting) return
  exporting = true
  lineList()
  $('save-project').disabled = true
  message('export-status', '正在保存原句、审核记录和引用的素材版本…')
  try {
    const result = await request('save-project', projectState())
    download(await result.blob(), 'VisionBuddy-审核工程.zip')
    message('export-status', '审核工程 ZIP 已保存。')
  } catch (error) {
    message('export-status', error.message, true)
  } finally {
    exporting = false
    $('save-project').disabled = false
    lineList()
  }
}

async function openProject(file) {
  if (!file) return
  try {
    let project, result, restored
    message('intake-status', '正在恢复审核工程…')
    if (/\.zip$/i.test(file.name)) {
      restored = await (await request('open-project', file, 'application/octet-stream')).json()
      project = restored.project
      result = restored.plan
    } else {
      if (file.size > 3 * 1024 ** 2) throw Error('审核工程文件过大。')
      project = JSON.parse(await file.text())
      if (!['visionbuddy-project/1','visionbuddy-plan/1'].includes(project.format))
        throw Error('请选择 VisionBuddy 审核工程 ZIP 或 JSON。')
      result = await (await request('plan', {source:project.source})).json()
      if (result.libraryRelease !== project.libraryRelease) throw Error('请用工程记录的公共素材库版本打开。')
    }
    if (project.source.kind === 'script') $('script').value = project.source.text
    const modes = {script:'script',srt:'srt',transcript:'video'}
    switchMode(Object.hasOwn(modes, project.mode) ? project.mode : modes[project.source.kind])
    loadPlan(result, project.decisions || {}, project.selected || null, project.recording || null)
    message('intake-status')
    message('export-status', restored && !online ? '已恢复审核工程及引用的个人素材版本。' : '已恢复审核选择。')
  } catch (error) {
    message('intake-status', error.message, true)
  } finally {
    $('project-file').value = ''
  }
}

async function exportPack() {
  if (!plan || exporting) return
  exporting = true
  lineList()
  message('export-status', online ? '正在打包，审核选择已保存…' : '正在本机渲染与打包，审核选择已保存…')
  try {
    const result = await request('export', { ...projectState(), media: $('export-media').value })
    download(await result.blob(), 'VisionBuddy-口播素材包.zip')
    message('export-status', '素材包已导出。')
  } catch (error) {
    message('export-status', error.message, true)
  } finally {
    exporting = false
    lineList()
  }
}

for (const button of document.querySelectorAll('[data-mode]')) button.onclick = () => {
  switchMode(button.dataset.mode)
  if (selected) selectRow(selected)
}
$('video-srt').onchange = () => { $('speech-options').hidden = online || Boolean($('video-srt').files[0]) }
$('video-file').onchange = () => {
  const file = $('video-file').files[0]
  videoReady = attachVideo(file)
  videoReady.then(duration => {
    if (duration) {
      const mismatch = !matchesRecording()
      $('relink-video').hidden = !mismatch || !relinkAvailable()
      message('intake-status', '视频已就绪 · ' + stamp(duration) + (mismatch ? '。确认是工程原片后可重新关联。' : ''))
      if (selected) selectRow(selected)
    }
  }, error => message('intake-status', error.message, true))
}
$('relink-video').onclick = () => {
  if (!relinkAvailable()) return
  recording = videoIdentity()
  saveDraft()
  $('relink-video').hidden = true
  message('intake-status','已关联选中的原片。')
  if (selected) selectRow(selected)
}
$('intake-form').onsubmit = submitPlan
$('plan-button').disabled = false
$('show-plain').onchange = lineList
$('play').onclick = playSample
$('adopt').onclick = () => {
  const [row, candidate] = current()
  updateDecision(row, { state: 'adopted' })
  statusControls(row, candidate)
  lineList()
}
$('skip').onclick = () => {
  const [row, candidate] = current()
  updateDecision(row, { state: rowState(row) === 'skipped' ? 'pending' : 'skipped' })
  statusControls(row, candidate)
  lineList()
}
$('alternate').onclick = () => {
  const [row] = current()
  pickVersion(row, ((decision(row).choice || 0) + 1) % row.candidates.length)
}
$('export').onclick = exportPack
$('save-project').onclick = saveProject
$('open-project').onclick = () => $('project-file').click()
$('project-file').onchange = () => openProject($('project-file').files[0])
for (const [id, field, read, event] of [
  ['clip-start', 'start', el => el.value === '' ? null : Number(el.value), 'change'],
  ['clip-end', 'end', el => el.value === '' ? null : Number(el.value), 'change'],
  ['side', 'side', el => el.value, 'change'],
  ['scale', 'scale', el => Number(el.value) / 100, 'input'],
]) {
  $(id).addEventListener(event, () => {
    const [row, candidate] = current()
    if (!candidate) return
    updateDecision(row, { [field]: read($(id)) })
    applyPlacement(row, candidate, false)
  })
}
player.addEventListener('play', playVideoClock)
player.addEventListener('seeked', paintVideo)
player.addEventListener('pause', paintVideo)
player.addEventListener('timeupdate', paintVideo)

if (online) {
  $('speech-options').hidden = true
} else fetch('/api/desk/capabilities').then(res => res.json()).then(data => {
  const model = $('model')
  model.replaceChildren(...(data.models.length ? data.models.map(name => new Option(name, name)) :
    [new Option('本机暂无模型，请选配套 SRT', '')]))
  videoSize = data.videoLimit
}).catch(() => { $('model').replaceChildren(new Option('暂时无法读取本机模型', '')) })

const restored = readDraft()
if (restored) {
  if (restored.source.kind === 'script') $('script').value = restored.source.text
  switchMode(restored.mode || 'script')
  request('plan', { source: restored.source }).then(res => res.json()).then(value => {
    loadPlan(value, restored.decisions || {}, restored.selected, restored.recording)
    if (mode === 'video') message('intake-status', '审核选择已恢复。要在原片上试摆，请重新选择本机视频。')
  }).catch(error => message('intake-status', error.message, true))
}
