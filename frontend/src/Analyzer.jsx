import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

const API_BASE = import.meta.env.VITE_API_BASE || ''

const ACCENT = '#f59e0b'   // amber — distinct from strategy (blue) and indicator (purple) chats

// Temperature is fixed low for objective, analytical output
const ANALYSIS_TEMPERATURE = 0.2

const STRATEGY_PROMPT_KEYS = [
  'explain', 'risks', 'conditions', 'overfitting',
  'buyHold', 'improvements', 'missingRules', 'sensitivity',
]

const INDICATOR_PROMPT_KEYS = [
  'explain', 'range', 'signals', 'limitations',
  'lookback', 'useInStrategy', 'tuneParams', 'compare',
]

export default function Analyzer() {
  const { t, i18n } = useTranslation()
  const [tab, setTab] = useState('strategies')        // 'strategies' | 'indicators'
  const [strategies, setStrategies] = useState([])
  const [indicators, setIndicators] = useState([])
  const [loadingList, setLoadingList] = useState(true)
  const [listError, setListError] = useState('')

  const [selected, setSelected] = useState(null)      // {type, id, name}
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [modelName, setModelName] = useState(undefined) // undefined=loading, null=none, string=name

  const bottomRef = useRef(null)

  // ── Fetch lists + model on mount ───────────────────────────────────────────
  useEffect(() => {
    setLoadingList(true)
    Promise.all([
      fetch(`${API_BASE}/api/db/strategies`).then(r => r.json()),
      fetch(`${API_BASE}/api/db/indicators`).then(r => r.json()),
      fetch(`${API_BASE}/api/db/model-keys`).then(r => r.json()),
    ])
      .then(([sd, id, md]) => {
        setStrategies(sd.strategies || [])
        setIndicators(id.indicators || [])
        const active = (md.keys || []).find(k => k.active)
        setModelName(active?.model_name || null)
      })
      .catch(() => {
        setListError(t('analyzer.failedLoad'))
        setModelName(null)
      })
      .finally(() => setLoadingList(false))
  }, [])

  // ── Auto-scroll to bottom on new messages ─────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  // ── Select an item: reset chat with opening message ───────────────────────
  function selectItem(type, id, name) {
    setSelected({ type, id, name })
    setInput('')
    setMessages([
      {
        role: 'assistant',
        content: type === 'strategy'
          ? t('analyzer.loadedStrategy', { name })
          : t('analyzer.loadedIndicator', { name }),
      },
    ])
  }

  // ── Send a message (text or quick prompt) ─────────────────────────────────
  async function handleSend(textOverride) {
    const text = (textOverride ?? input).trim()
    if (!text || !selected || sending) return

    const userMsg = { role: 'user', content: text }
    const nextMessages = [...messages, userMsg]
    setMessages(nextMessages)
    setInput('')
    setSending(true)

    try {
      const resp = await fetch(`${API_BASE}/api/ai/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject_type: selected.type,
          subject_id: selected.id,
          messages: nextMessages,
          temperature: ANALYSIS_TEMPERATURE,
          language: i18n.language,
        }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${resp.status}`)
      }
      const data = await resp.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: t('analyzer.errorPrefix', { message: err.message }), isError: true },
      ])
    } finally {
      setSending(false)
    }
  }

  // ── Keyboard submit ────────────────────────────────────────────────────────
  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // ── Prompts for current subject type ──────────────────────────────────────
  const promptKeys = selected?.type === 'strategy' ? STRATEGY_PROMPT_KEYS : INDICATOR_PROMPT_KEYS
  const promptGroup = selected?.type === 'strategy' ? 'strategyPrompts' : 'indicatorPrompts'
  const quickPrompts = promptKeys.map(k => t(`analyzer.${promptGroup}.${k}`))

  // ── Current list to display ────────────────────────────────────────────────
  const items = tab === 'strategies' ? strategies : indicators

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', gap: '1.25rem', height: 'calc(100vh - 80px)', minHeight: 0 }}>

      {/* ── Left sidebar: item selector ──────────────────────────────────────── */}
      <aside style={{
        width: 280,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
      }}>
        {/* Tab strip */}
        <div className="tab-strip" style={{ marginBottom: 0 }}>
          {['strategies', 'indicators'].map(tabId => (
            <button
              key={tabId}
              className={`tab-btn${tab === tabId ? ' active' : ''}`}
              onClick={() => setTab(tabId)}
              style={tab === tabId ? { borderBottomColor: ACCENT, color: ACCENT } : {}}
            >
              {tabId === 'strategies' ? t('analyzer.strategiesTab') : t('analyzer.indicatorsTab')}
            </button>
          ))}
        </div>

        {/* Item list */}
        <div style={{
          flex: 1,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
        }}>
          {loadingList && (
            <div style={{ color: 'var(--text-mute)', fontSize: '0.85rem', padding: '0.5rem' }}>
              {t('common.loading')}
            </div>
          )}
          {listError && (
            <div className="alert alert-error" style={{ fontSize: '0.8rem' }}>{listError}</div>
          )}
          {!loadingList && items.length === 0 && (
            <div style={{ color: 'var(--text-mute)', fontSize: '0.85rem', padding: '0.5rem' }}>
              {tab === 'strategies' ? t('analyzer.noStrategiesSaved') : t('analyzer.noIndicatorsSaved')}
            </div>
          )}
          {items.map(item => {
            const id = item.id
            const name = item.name
            const isActive = selected?.id === id && selected?.type === (tab === 'strategies' ? 'strategy' : 'indicator')
            return (
              <button
                key={id}
                onClick={() => selectItem(tab === 'strategies' ? 'strategy' : 'indicator', id, name)}
                style={{
                  textAlign: 'left',
                  background: isActive ? 'rgba(245,158,11,0.12)' : 'var(--surface)',
                  border: `1px solid ${isActive ? ACCENT : 'var(--border)'}`,
                  borderRadius: 8,
                  padding: '0.6rem 0.8rem',
                  cursor: 'pointer',
                  color: isActive ? ACCENT : 'var(--text)',
                  fontSize: '0.875rem',
                  fontWeight: isActive ? 600 : 400,
                  transition: 'all 0.15s',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <span style={{ color: 'var(--text-mute)', fontSize: '0.75rem' }}>
                  {item.is_builtin ? '★' : '○'}
                </span>
                {name}
              </button>
            )
          })}
        </div>
      </aside>

      {/* ── Right panel: chat ─────────────────────────────────────────────────── */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        gap: '0.75rem',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          flexWrap: 'wrap',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '1.25rem' }}>🔍</span>
            <div>
              <div style={{ fontWeight: 600, fontSize: '1rem' }}>
                {selected ? selected.name : t('analyzer.title')}
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-mute)' }}>
                {selected
                  ? (selected.type === 'strategy' ? t('analyzer.analysingStrategy') : t('analyzer.analysingIndicator'))
                  : t('analyzer.selectToStart')}
              </div>
            </div>
          </div>
          {/* Model badge */}
          {modelName === undefined ? null : modelName ? (
            <span style={{
              background: 'rgba(245,158,11,0.15)',
              color: ACCENT,
              border: `1px solid ${ACCENT}40`,
              borderRadius: 20,
              padding: '0.2rem 0.7rem',
              fontSize: '0.75rem',
              fontWeight: 500,
            }}>
              {modelName}
            </span>
          ) : (
            <span style={{
              background: 'rgba(239,68,68,0.12)',
              color: '#ef4444',
              border: '1px solid #ef444440',
              borderRadius: 20,
              padding: '0.2rem 0.7rem',
              fontSize: '0.75rem',
            }}>
              {t('analyzer.noAiModel')}
            </span>
          )}
        </div>

        {/* No selection placeholder */}
        {!selected && (
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-mute)',
            gap: '0.75rem',
          }}>
            <div style={{ fontSize: '3rem' }}>🔍</div>
            <div style={{ fontSize: '0.95rem' }}>
              {t('analyzer.pickToBegin')}
            </div>
          </div>
        )}

        {/* Chat area */}
        {selected && (
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 10,
            overflow: 'hidden',
          }}>
            {/* Messages */}
            <div style={{
              flex: 1,
              overflowY: 'auto',
              padding: '1rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}>
              {messages.map((msg, idx) => (
                <div key={idx} style={{
                  display: 'flex',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}>
                  <div style={{
                    maxWidth: '80%',
                    padding: '0.65rem 0.9rem',
                    borderRadius: msg.role === 'user' ? '12px 12px 3px 12px' : '12px 12px 12px 3px',
                    background: msg.isError
                      ? 'rgba(239,68,68,0.15)'
                      : msg.role === 'user'
                        ? ACCENT
                        : 'var(--panel2)',
                    color: msg.isError ? '#ef4444' : msg.role === 'user' ? '#000' : 'var(--text)',
                    fontSize: '0.875rem',
                    lineHeight: 1.55,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    border: msg.isError ? '1px solid #ef444430' : 'none',
                  }}>
                    {msg.content}
                  </div>
                </div>
              ))}

              {/* Typing indicator */}
              {sending && (
                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <div style={{
                    padding: '0.65rem 0.9rem',
                    borderRadius: '12px 12px 12px 3px',
                    background: 'var(--panel2)',
                    color: 'var(--text-mute)',
                    fontSize: '0.875rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  }}>
                    <span className="spinner" style={{ width: 14, height: 14 }} />
                    {t('analyzer.analysingSending')}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Quick prompt chips */}
            <div style={{
              borderTop: '1px solid var(--border)',
              padding: '0.6rem 0.75rem 0',
              background: 'var(--panel)',
              display: 'flex',
              flexWrap: 'wrap',
              gap: '0.4rem',
            }}>
              {quickPrompts.map(prompt => (
                <button
                  key={prompt}
                  onClick={() => handleSend(prompt)}
                  disabled={sending || !modelName}
                  style={{
                    background: 'var(--surface)',
                    border: `1px solid ${ACCENT}50`,
                    borderRadius: 20,
                    padding: '0.25rem 0.65rem',
                    fontSize: '0.75rem',
                    color: sending || !modelName ? 'var(--text-mute)' : ACCENT,
                    cursor: sending || !modelName ? 'not-allowed' : 'pointer',
                    transition: 'background 0.15s, border-color 0.15s',
                    whiteSpace: 'nowrap',
                  }}
                  onMouseEnter={e => { if (!sending && modelName) e.currentTarget.style.background = `rgba(245,158,11,0.1)` }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)' }}
                >
                  {prompt}
                </button>
              ))}
            </div>

            {/* Input row */}
            <div style={{
              padding: '0.6rem 0.75rem 0.75rem',
              display: 'flex',
              gap: '0.5rem',
              background: 'var(--panel)',
            }}>
              <textarea
                rows={1}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder={modelName ? t('analyzer.askCustom') : t('analyzer.configureFirst')}
                disabled={sending || !modelName}
                style={{
                  flex: 1,
                  resize: 'none',
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  padding: '0.55rem 0.75rem',
                  color: 'var(--text)',
                  fontSize: '0.875rem',
                  outline: 'none',
                  fontFamily: 'inherit',
                  lineHeight: 1.5,
                }}
              />
              <button
                onClick={() => handleSend()}
                disabled={sending || !input.trim() || !modelName}
                style={{
                  background: sending || !input.trim() || !modelName ? 'var(--panel2)' : ACCENT,
                  color: sending || !input.trim() || !modelName ? 'var(--text-mute)' : '#000',
                  border: 'none',
                  borderRadius: 8,
                  padding: '0.55rem 1.1rem',
                  cursor: sending || !input.trim() || !modelName ? 'not-allowed' : 'pointer',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                  transition: 'background 0.15s',
                  whiteSpace: 'nowrap',
                }}
              >
                {t('common.send')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
