'use strict'

const node = (selector) => document.querySelector(selector)
async function loadDemos() {
  const responses = await Promise.all(['visual/treatments.json', 'visual/catalog.json'].map(file => fetch(file)))
  if (responses.some(response => !response.ok)) throw Error('演示暂未加载，请刷新页面。')
  const [demos, visual] = await Promise.all(responses.map(response => response.json()))
  const objects = new Map(visual.objects.map(object => [object.id, object]))
  let selected = null

  function choose(demo) {
    selected = demo
    node('#demo-title').textContent = demo.label + ' · ' + demo.assetId
    node('#demo-preview').src = '/api/visionbuddy/demo?asset=' + encodeURIComponent(demo.assetId)
    node('#demo-copy').disabled = false
    node('#demo-notice').textContent = ''
    node('#demo-text').hidden = true
    render()
  }

  function render() {
    const q = node('#demo-search').value.trim().toLowerCase()
    const list = node('#demo-cards')
    list.replaceChildren()
    for (const demo of demos) {
      const object = objects.get(demo.object)
      if (![demo.label, demo.description, demo.assetId, object.name].some(text => text.toLowerCase().includes(q))) continue
      const button = document.createElement('button')
      button.className = 'outline demo-choice'
      button.dataset.assetId = demo.assetId
      button.setAttribute('aria-pressed', String(demo === selected))
      const title = document.createElement('strong')
      title.textContent = demo.label
      const detail = document.createElement('span')
      detail.textContent = demo.assetId + ' · ' + object.name
      button.append(title, detail)
      button.onclick = () => choose(demo)
      list.append(button)
    }
  }

  node('#demo-search').oninput = render
  node('#demo-copy').onclick = async () => {
    const object = objects.get(selected.object)
    const mark = '（画面：用' + object.name + ' ' + object.assetId + '，做「' + selected.label + '」' + selected.assetId + '。）'
    try {
      await navigator.clipboard.writeText(mark)
      node('#demo-notice').textContent = '已复制，粘贴到对应原句后。'
    } catch {
      const field = node('#demo-text')
      field.hidden = false
      field.value = mark
      field.select()
      node('#demo-notice').textContent = '标注已选中，可按复制快捷键。'
    }
  }
  const code = (new URLSearchParams(location.search).get('asset') || '').toUpperCase()
  choose(demos.find(demo => demo.assetId === code) || demos[0])
}
loadDemos().catch(error => { node('#demo-notice').textContent = error.message })
