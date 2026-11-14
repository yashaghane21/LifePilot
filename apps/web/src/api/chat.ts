// Real backend calls for the assistant (Phase 3.2).
import { apiFetch } from './http'
import type { ChatRequest, ChatResponse, ConversationDetail, ConversationSummary } from './types'

export const chatApi = {
  listConversations: (): Promise<ConversationSummary[]> => apiFetch('/conversations'),

  getConversation: (id: string): Promise<ConversationDetail> =>
    apiFetch(`/conversations/${encodeURIComponent(id)}`),

  deleteConversation: (id: string): Promise<void> =>
    apiFetch(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  send: (request: ChatRequest): Promise<ChatResponse> =>
    apiFetch('/chat', { method: 'POST', body: JSON.stringify(request) }),
}
