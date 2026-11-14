// Real backend calls for the assistant (Phase 3.2, streaming 3.3).
import { apiFetch, apiStream } from './http'
import { readSse } from './sse'
import type { ChatRequest, ChatResponse, ConversationDetail, ConversationSummary } from './types'

/** Events of POST /chat/stream, in order: start, delta…, then done or error. */
export type ChatStreamEvent =
  | { type: 'start'; conversation_id: string; title: string }
  | { type: 'delta'; text: string }
  | ({ type: 'done' } & ChatResponse)
  | { type: 'error'; code: string; message: string; request_id: string | null }

export const chatApi = {
  listConversations: (): Promise<ConversationSummary[]> => apiFetch('/conversations'),

  getConversation: (id: string): Promise<ConversationDetail> =>
    apiFetch(`/conversations/${encodeURIComponent(id)}`),

  deleteConversation: (id: string): Promise<void> =>
    apiFetch(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  send: (request: ChatRequest): Promise<ChatResponse> =>
    apiFetch('/chat', { method: 'POST', body: JSON.stringify(request) }),

  /**
   * Stream a reply. Errors before the stream starts (validation, 404, 401) throw ApiError;
   * errors after it starts arrive as an `error` event. Abort `signal` to stop the reply.
   */
  async *stream(request: ChatRequest, signal: AbortSignal): AsyncGenerator<ChatStreamEvent> {
    const response = await apiStream('/chat/stream', { method: 'POST', body: JSON.stringify(request), signal })
    if (!response.body) throw new Error('Streaming is not supported by this browser')
    for await (const message of readSse(response.body)) {
      yield { type: message.event, ...JSON.parse(message.data) } as ChatStreamEvent
    }
  },
}
