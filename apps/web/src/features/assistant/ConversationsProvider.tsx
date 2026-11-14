import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { chatApi } from '../../api/chat'
import type { ConversationSummary } from '../../api/types'
import { ConversationsContext, type ConversationsValue } from './conversationsContext'

export function ConversationsProvider({ children }: { children: ReactNode }) {
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    let cancelled = false
    chatApi.listConversations().then(
      (list) => {
        if (!cancelled) setConversations(list)
      },
      () => {
        if (!cancelled) setLoadError(true)
      },
    )
    return () => {
      cancelled = true
    }
  }, [])

  const upsert = useCallback((conversation: ConversationSummary) => {
    setConversations((current) => [conversation, ...(current ?? []).filter((c) => c.id !== conversation.id)])
  }, [])

  const remove = useCallback(async (id: string) => {
    await chatApi.deleteConversation(id)
    setConversations((current) => (current ?? []).filter((c) => c.id !== id))
  }, [])

  const value = useMemo<ConversationsValue>(
    () => ({ conversations, loadError, upsert, remove }),
    [conversations, loadError, upsert, remove],
  )
  return <ConversationsContext value={value}>{children}</ConversationsContext>
}
