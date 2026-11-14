import { createContext, useContext } from 'react'
import type { ConversationSummary } from '../../api/types'

export interface ConversationsValue {
  /** null while the first load is in flight. */
  conversations: ConversationSummary[] | null
  loadError: boolean
  /** Insert or update a conversation and move it to the top (it was just active). */
  upsert: (conversation: ConversationSummary) => void
  remove: (id: string) => Promise<void>
}

export const ConversationsContext = createContext<ConversationsValue | null>(null)

/** The signed-in user's conversations, shared by the sidebar and the assistant page. */
export function useConversations(): ConversationsValue {
  const value = useContext(ConversationsContext)
  if (!value) throw new Error('useConversations must be used inside <ConversationsProvider>')
  return value
}
