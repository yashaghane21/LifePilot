/**
 * Reads a Server-Sent Events body: blocks separated by a blank line, each with `event:` and
 * `data:` lines. We parse it ourselves because the browser's EventSource only supports GET
 * and cannot send an Authorization header.
 */
export interface SseMessage {
  event: string
  data: string
}

export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseMessage> {
  const reader = body.getReader()
  // stream: true keeps a multi-byte character (₹, emoji) that is split across chunks intact.
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      // Network chunks don't line up with events: keep any incomplete tail for the next read.
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let end: number
      while ((end = buffer.indexOf('\n\n')) !== -1) {
        const block = buffer.slice(0, end)
        buffer = buffer.slice(end + 2)
        const message = parseBlock(block)
        if (message) yield message
      }
    }
  } finally {
    // Also runs when the consumer stops early (Stop button): releases the connection.
    await reader.cancel().catch(() => undefined)
  }
}

function parseBlock(block: string): SseMessage | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    // Lines starting with ':' are comments (keep-alives) and are ignored.
  }
  return data.length > 0 ? { event, data: data.join('\n') } : null
}
