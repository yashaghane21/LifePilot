import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { chatApi } from '../../api/chat'
import { ApiError } from '../../api/http'
import type { StoredMessage } from '../../api/types'
import { Icon } from '../../components/ui/Icon'
import { PageState } from '../../components/ui/PageState'
import { useApi } from '../../lib/useApi'
import { useConversations } from './conversationsContext'
import { Markdown } from './Markdown'

const SUGGESTIONS = ['Help me plan my week', 'How do I start a monthly budget?', 'Give me a 20-minute home workout']

/** /assistant (new chat) and /assistant/:conversationId. */
export function AssistantPage() {
  const { conversationId } = useParams()
  // Remount per conversation, so nothing (messages, errors, a draft) leaks between chats.
  return <ConversationLoader key={conversationId ?? 'new'} conversationId={conversationId ?? null} />
}

function ConversationLoader({ conversationId }: { conversationId: string | null }) {
  const location = useLocation()
  const navigate = useNavigate()
  // A chat that was just created hands its first messages over in navigation state, so the
  // page doesn't refetch what it already has. Captured once, then cleared from history so a
  // reload fetches fresh data instead of showing this stale copy.
  const [handoff] = useState(() => (location.state as { messages?: StoredMessage[] } | null)?.messages)
  useEffect(() => {
    if (handoff) navigate(location.pathname, { replace: true, state: null })
  }, [handoff, navigate, location.pathname])

  if (conversationId === null) return <Chat conversationId={null} initialMessages={[]} />
  if (handoff) return <Chat conversationId={conversationId} initialMessages={handoff} />
  return <LoadConversation id={conversationId} />
}

function LoadConversation({ id }: { id: string }) {
  const load = useCallback(() => chatApi.getConversation(id), [id])
  const state = useApi(load)

  if (state.status === 'error' && state.error instanceof ApiError && state.error.status === 404) {
    return (
      <div className="flex flex-col gap-3 p-10">
        <h1 className="m-0 text-2xl font-semibold">Chat not found</h1>
        <p className="m-0 text-muted">It may have been deleted.</p>
        <Link to="/assistant" className="text-accent hover:text-accent-hover">
          Start a new chat
        </Link>
      </div>
    )
  }
  return <PageState state={state}>{(c) => <Chat conversationId={id} initialMessages={c.messages} />}</PageState>
}

interface Failure {
  text: string
  message: string
}

function Chat({ conversationId, initialMessages }: { conversationId: string | null; initialMessages: StoredMessage[] }) {
  const [messages, setMessages] = useState(initialMessages)
  const [pending, setPending] = useState<string | null>(null)
  const [failure, setFailure] = useState<Failure | null>(null)
  const [showDetails, setShowDetails] = useState(() => window.matchMedia('(min-width: 1200px)').matches)
  const { upsert } = useConversations()
  const navigate = useNavigate()
  const endRef = useRef<HTMLDivElement>(null)

  // False once the user has moved to another chat: a late reply must not navigate them back.
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  // Keep the newest message in view, as chat apps do.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, pending, failure])

  async function send(text: string) {
    setPending(text)
    setFailure(null)
    try {
      const response = await chatApi.send({
        message: text,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      })
      upsert(response.conversation)
      if (!alive.current) return
      const next = [...messages, response.user_message, response.assistant_message]
      if (conversationId === null) {
        navigate(`/assistant/${response.conversation.id}`, { state: { messages: next } })
      } else {
        setMessages(next)
      }
    } catch (error) {
      if (!alive.current) return
      setFailure({
        text,
        message: error instanceof ApiError ? error.message : 'Could not reach LifePilot. Check your connection.',
      })
    } finally {
      if (alive.current) setPending(null)
    }
  }

  const lastReply = messages.findLast((m) => m.role === 'assistant') ?? null
  const isEmpty = messages.length === 0 && pending === null && failure === null

  return (
    <div className="flex h-full">
      <section aria-label="Conversation" className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 flex-none items-center justify-between gap-3 px-5">
          <h1 className="m-0 text-lg font-semibold">Assistant</h1>
          <button
            type="button"
            onClick={() => setShowDetails((v) => !v)}
            aria-pressed={showDetails}
            className="flex h-9 cursor-pointer items-center gap-2 rounded-lg border-none bg-transparent px-3 text-sm font-medium text-ink-soft hover:bg-bubble"
          >
            <Icon name="trace" size={16} />
            How it was answered
          </button>
        </header>

        {isEmpty ? (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-6 px-5 pb-16">
            <h2 className="m-0 text-center text-2xl font-semibold sm:text-3xl">What can I help with?</h2>
            <div className="w-full max-w-3xl">
              <Composer onSend={send} disabled={false} autoFocus />
            </div>
            <ul aria-label="Suggestions" className="m-0 flex list-none flex-wrap justify-center gap-2 p-0">
              {SUGGESTIONS.map((suggestion) => (
                <li key={suggestion}>
                  <button
                    type="button"
                    onClick={() => void send(suggestion)}
                    className="h-9 cursor-pointer rounded-full border border-line bg-transparent px-4 text-sm text-ink-soft hover:bg-bubble"
                  >
                    {suggestion}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <ol aria-label="Messages" className="mx-auto my-0 flex max-w-3xl list-none flex-col gap-8 px-5 py-6">
                {messages.map((message) => (
                  <li key={message.id} className="flex flex-col">
                    {message.role === 'user' ? <UserBubble text={message.content} /> : <AssistantReply message={message} />}
                  </li>
                ))}
                {pending !== null && (
                  <>
                    <li className="flex flex-col">
                      <UserBubble text={pending} />
                    </li>
                    <li className="flex flex-col">
                      <Thinking />
                    </li>
                  </>
                )}
                {failure && (
                  <>
                    <li className="flex flex-col">
                      <UserBubble text={failure.text} faded />
                    </li>
                    <li className="flex flex-col">
                      <div
                        role="alert"
                        className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-warning-line bg-warning-soft px-4 py-3 text-sm text-warning"
                      >
                        <span>Not sent. {failure.message}</span>
                        <button
                          type="button"
                          onClick={() => void send(failure.text)}
                          className="flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-warning-line bg-transparent px-3 text-sm font-semibold text-warning hover:bg-canvas"
                        >
                          <Icon name="retry" size={14} />
                          Retry
                        </button>
                      </div>
                    </li>
                  </>
                )}
              </ol>
              <div ref={endRef} />
            </div>

            <div className="mx-auto w-full max-w-3xl flex-none px-5 pb-4">
              <Composer onSend={send} disabled={pending !== null} />
            </div>
          </>
        )}
        <p className="m-0 flex-none px-5 pb-3 text-center text-xs text-muted">
          LifePilot can make mistakes. It can't read or change your saved records yet.
        </p>
      </section>

      {showDetails && <DetailsPanel reply={lastReply} onClose={() => setShowDetails(false)} />}
    </div>
  )
}

function UserBubble({ text, faded = false }: { text: string; faded?: boolean }) {
  return (
    <div
      className={`max-w-[75%] self-end rounded-3xl bg-bubble px-5 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap ${
        faded ? 'opacity-60' : ''
      }`}
    >
      {text}
    </div>
  )
}

function AssistantReply({ message }: { message: StoredMessage }) {
  return (
    <div className="flex flex-col gap-2.5">
      <Markdown text={message.content} />
      {message.finish_reason === 'length' && (
        <p className="m-0 text-xs font-medium text-warning">This reply was cut off because it reached the length limit.</p>
      )}
      <div className="-ml-1.5 flex">
        <CopyButton text={message.content} />
      </div>
    </div>
  )
}

function Thinking() {
  return (
    <div role="status" className="flex items-center gap-2 text-sm text-muted">
      <span className="flex gap-1" aria-hidden="true">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="size-2 animate-bounce rounded-full bg-muted"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </span>
      LifePilot is thinking…
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard blocked (permissions or insecure context): nothing to copy to.
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? 'Copied' : 'Copy message'}
      title={copied ? 'Copied' : 'Copy'}
      className="flex size-8 cursor-pointer items-center justify-center rounded-lg border-none bg-transparent text-muted hover:bg-bubble hover:text-ink"
    >
      <Icon name={copied ? 'check' : 'copy'} size={16} />
    </button>
  )
}

function Composer({
  onSend,
  disabled,
  autoFocus = false,
}: {
  onSend: (text: string) => void
  disabled: boolean
  autoFocus?: boolean
}) {
  const [text, setText] = useState('')
  const canSend = text.trim().length > 0 && !disabled

  function submit() {
    if (!canSend) return
    onSend(text.trim())
    setText('')
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submit()
  }

  // Enter sends; Shift+Enter inserts a new line.
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-2 rounded-[28px] border border-line bg-surface p-2 shadow-sm focus-within:border-muted"
    >
      <button
        type="button"
        disabled
        aria-label="Attach a file (coming with statement import)"
        title="Attach a file: coming with statement import"
        className="flex size-10 flex-none items-center justify-center rounded-full border-none bg-transparent text-muted disabled:cursor-not-allowed"
      >
        <Icon name="plus" size={20} />
      </button>
      <label htmlFor="message" className="sr-only">
        Message LifePilot
      </label>
      <textarea
        id="message"
        rows={1}
        value={text}
        maxLength={8000}
        autoFocus={autoFocus}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask LifePilot anything…"
        className="max-h-40 min-h-10 flex-1 resize-none border-none bg-transparent px-1 py-2.5 text-[15px] leading-5 text-ink outline-none [field-sizing:content]"
      />
      <button
        type="submit"
        disabled={!canSend}
        aria-label="Send message"
        className="flex size-10 flex-none cursor-pointer items-center justify-center rounded-full border-none bg-accent text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Icon name="send" strokeWidth={2.2} />
      </button>
    </form>
  )
}

/** "0.00010800" → "$0.000108". Display only: string formatting, no float arithmetic on money. */
function formatUsd(cost: string | null): string {
  if (cost === null) return 'not reported'
  const trimmed = cost.includes('.') ? cost.replace(/0+$/, '').replace(/\.$/, '') : cost
  return trimmed === '0' ? '$0 (free model)' : `$${trimmed}`
}

function DetailsPanel({ reply, onClose }: { reply: StoredMessage | null; onClose: () => void }) {
  const rows: [string, string][] = reply
    ? [
        ['Model', reply.model ?? 'unknown'],
        ['Tokens in', String(reply.input_tokens ?? '—')],
        ['Tokens out', String(reply.output_tokens ?? '—')],
        ['Cost', formatUsd(reply.cost_usd)],
        ['Time', reply.latency_ms === null ? '—' : `${(reply.latency_ms / 1000).toFixed(1)} s`],
        ['Finished', reply.finish_reason === 'stop' ? 'complete' : (reply.finish_reason ?? '—')],
      ]
    : []

  return (
    <aside
      aria-labelledby="details-heading"
      className="flex w-80 flex-none flex-col gap-5 overflow-y-auto border-l border-line bg-surface px-5 py-4"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <h2 id="details-heading" className="m-0 text-base font-semibold">
            How this answer was made
          </h2>
          <span className="text-xs text-muted">Latest reply in this chat</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close panel"
          className="flex size-8 flex-none cursor-pointer items-center justify-center rounded-lg border-none bg-transparent text-muted hover:bg-bubble hover:text-ink"
        >
          <Icon name="panel" size={16} />
        </button>
      </div>

      {reply ? (
        <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 text-sm">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted">{label}</dt>
              <dd className="m-0 font-medium break-all">{value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="m-0 text-sm text-muted">Send a message to see how the reply was produced.</p>
      )}

      <div className="flex flex-col gap-1.5 rounded-xl bg-bubble p-3.5">
        <span className="text-[13px] font-semibold">Sent to the language model</span>
        <span className="text-[13px] leading-normal text-muted">
          LifePilot's instructions, up to the last 20 messages of this chat, and your new message. Your name, email
          and saved records are not sent.
        </span>
      </div>
      <p className="m-0 text-xs leading-normal text-muted">
        Coming next: replies that stream in word by word, then tools that read and save your records, each result
        checked against the database before LifePilot confirms it.
      </p>
    </aside>
  )
}
