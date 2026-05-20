import mermaid from 'mermaid'
import { ref, onMounted, watch, nextTick } from 'vue'

mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    primaryColor: '#7c3aed',
    primaryTextColor: '#e2e8f0',
    primaryBorderColor: '#6d28d9',
    lineColor: '#94a3b8',
    secondaryColor: '#1e1b4b',
    tertiaryColor: '#0f172a',
    background: '#0f172a',
    mainBkg: '#1e1b4b',
    nodeBorder: '#7c3aed',
    clusterBkg: '#1e1b4b',
    titleColor: '#c4b5fd',
    edgeLabelBackground: '#1e293b',
    nodeTextColor: '#e2e8f0',
    fontSize: '12px',
  },
  flowchart: { curve: 'basis', padding: 15 },
  sequence: { mirrorActors: false },
  fontFamily: '"JetBrains Mono", "Fira Code", monospace',
})

let renderCount = 0

export async function renderMermaid(code) {
  const id = `mermaid-${++renderCount}-${Date.now().toString(36)}`
  try {
    const { svg } = await mermaid.render(id, code)
    return svg
  } catch (err) {
    console.warn('[Mermaid] render error:', err)
    return `<pre class="mermaid-error">Mermaid syntax error: ${err.message || err}</pre>`
  }
}

export function extractMermaidBlocks(text) {
  if (!text) return []
  const blocks = []
  const regex = /```mermaid\s*\n([\s\S]*?)```/g
  let match
  while ((match = regex.exec(text)) !== null) {
    blocks.push({
      code: match[1].trim(),
      fullMatch: match[0],
      index: match.index,
    })
  }
  return blocks
}

export function splitByMermaid(text) {
  if (!text) return [{ type: 'text', content: '' }]
  const blocks = extractMermaidBlocks(text)
  if (!blocks.length) return [{ type: 'text', content: text }]

  const parts = []
  let lastIndex = 0

  for (const block of blocks) {
    if (block.index > lastIndex) {
      const before = text.slice(lastIndex, block.index).trim()
      if (before) parts.push({ type: 'text', content: before })
    }
    parts.push({ type: 'mermaid', code: block.code })
    lastIndex = block.index + block.fullMatch.length
  }

  if (lastIndex < text.length) {
    const after = text.slice(lastIndex).trim()
    if (after) parts.push({ type: 'text', content: after })
  }

  return parts
}
