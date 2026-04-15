import { useState, useEffect, useCallback, useRef, useLayoutEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  LineChart, Line, AreaChart, Area,
  XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Brush,
} from 'recharts'

const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const RUN_COLORS = ['#3ab7f5', '#2fd89a', '#f9c74f', '#e879c0', '#fb923c']

const RUN_PROMPTS = [
  'Summarize the overall performance of this run.',
  'What caused the largest drawdown?',
  'Was the risk-adjusted return (Sharpe / Sortino) acceptable?',
  'How did this strategy compare to a buy-and-hold baseline?',
  'Were there any patterns in the winning vs. losing trades?',
  'Did the strategy have too few trades to be statistically meaningful?',
  'What execution or commission impact is visible in the results?',
  'What improvements would you suggest based on this run?',
]

const ANALYSIS_TEMPERATURE = 0.2

// ── helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v) {
  if (v == null || !isFinite(v)) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}
function fmtNum(v, dec = 2) {
  if (v == null || !isFinite(v)) return '—'
  return Number(v).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}
function fmtDate(iso) { return iso ? iso.slice(0, 10) : '—' }
function fmtRunDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso.slice(0, 16) }
}

function buildDrawdown(curve) {
  const hasAv = curve.some(pt => pt.asset_value != null)
  let peak = null
  let inPosition = false
  return curve.map(pt => {
    let drawdown = 0
    if (hasAv) {
      const av = pt.asset_value || 0
      if (av > 0) {
        if (!inPosition || peak === null) { peak = pt.equity; inPosition = true }
        else if (pt.equity > peak) peak = pt.equity
        drawdown = peak > 0 ? Math.round(((pt.equity - peak) / peak) * 10000) / 100 : 0
      } else {
        inPosition = false
      }
    } else {
      // Legacy fallback: rolling peak
      if (peak === null) peak = pt.equity
      else if (pt.equity > peak) peak = pt.equity
      drawdown = peak > 0 ? Math.round(((pt.equity - peak) / peak) * 10000) / 100 : 0
    }
    return { t: pt.t, drawdown }
  })
}

function thinSeries(arr, max = 400) {
  if (arr.length <= max) return arr
  const step = Math.ceil(arr.length / max)
  return arr.filter((_, i) => i % step === 0 || i === arr.length - 1)
}

function xTickFmt(v) { return String(v || '').slice(0, 10) }

// ── Tooltip ───────────────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const trades  = payload[0]?.payload?.tradeMarker
  return (
    <div style={{
      background: 'var(--panel2)', border: '1px solid var(--border)',
      borderRadius: 10, padding: '8px 14px', fontSize: '0.78rem',
    }}>
      <div style={{ color: 'var(--text-mute)', marginBottom: 4 }}>{label?.slice(0, 10)}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.color, fontWeight: 600, lineHeight: 1.7 }}>
          {p.name}:{' '}
          {typeof p.value === 'number'
            ? String(p.dataKey).startsWith('equity')
              ? fmtPct(p.value)
              : p.dataKey === 'price'
                ? `$${fmtNum(p.value)}`
                : `${fmtNum(p.value)}%`
            : p.value}
        </div>
      ))}
      {trades?.length > 0 && (
        <div style={{ marginTop: 6, borderTop: '1px solid var(--border)', paddingTop: 5 }}>
          {trades.map((t, i) => {
            const isBuy = t.action === 'buy' || t.action === 'cover'
            return (
              <div key={i} style={{ color: isBuy ? 'var(--green)' : 'var(--red)', fontSize: '0.74rem', lineHeight: 1.5 }}>
                <span style={{ opacity: 0.7, marginRight: 4 }}>{t.symbol}</span>
                {t.action.toUpperCase()} {fmtNum(t.qty)} @ ${fmtNum(t.price)}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Metrics grid ──────────────────────────────────────────────────────────────

function MetricsGrid({ metrics }) {
  const { t } = useTranslation()
  const [activeTooltip, setActiveTooltip] = useState(null)
  if (!metrics) return null
  const m = metrics
  const cards = [
    { label: t('analytics.totalReturn'),  value: fmtPct(m.total_return_pct),  pos: m.total_return_pct >= 0,
      desc: t('analytics.totalReturnDesc') },
    { label: t('analytics.cagr'),          value: fmtPct(m.cagr_pct),          pos: m.cagr_pct >= 0,
      desc: t('analytics.cagrDesc') },
    { label: t('analytics.maxDrawdown'),  value: fmtPct(m.max_drawdown_pct),  pos: false, red: true,
      desc: t('analytics.maxDrawdownDesc') },
    { label: t('analytics.sharpeRatio'),  value: fmtNum(m.sharpe_ratio),      pos: m.sharpe_ratio >= 0,
      desc: t('analytics.sharpeRatioDesc') },
    { label: t('analytics.winRate'),      value: fmtPct(m.win_rate_pct),      pos: m.win_rate_pct >= 50,
      desc: t('analytics.winRateDesc') },
    { label: t('analytics.profitFactor'), value: isFinite(m.profit_factor) ? fmtNum(m.profit_factor) : '∞', pos: m.profit_factor >= 1,
      desc: t('analytics.profitFactorDesc') },
    { label: t('analytics.sortinoRatio'), value: fmtNum(m.sortino_ratio),     pos: m.sortino_ratio >= 0,
      desc: t('analytics.sortinoRatioDesc') },
    { label: t('analytics.calmarRatio'),  value: fmtNum(m.calmar_ratio),      pos: m.calmar_ratio >= 0,
      desc: t('analytics.calmarRatioDesc') },
    { label: t('analytics.totalTrades'),  value: String(m.total_trades ?? '—'), pos: true,
      desc: t('analytics.totalTradesDesc') },
    { label: t('analytics.avgTrade'),     value: fmtPct(m.avg_trade_pct),     pos: m.avg_trade_pct >= 0,
      desc: t('analytics.avgTradeDesc') },
    { label: t('analytics.avgBarsHeld'), value: fmtNum(m.avg_bars_held, 1),  pos: true,
      desc: t('analytics.avgBarsHeldDesc') },
  ]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
      {cards.map(c => (
        <div key={c.label} className="stat-card" style={{ position: 'relative' }}>
          <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {c.label}
            <button
              onMouseEnter={() => setActiveTooltip(c.label)}
              onMouseLeave={() => setActiveTooltip(null)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: '0 2px', fontSize: '0.68rem', color: 'var(--text-mute)',
                lineHeight: 1, flexShrink: 0,
              }}
              aria-label={`Info: ${c.label}`}
            >ℹ</button>
          </div>
          {activeTooltip === c.label && (
            <div style={{
              position: 'absolute', bottom: '100%', left: 0, right: 0,
              background: 'var(--panel2)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '6px 10px', fontSize: '0.73rem',
              color: 'var(--text-soft)', zIndex: 100, lineHeight: 1.45,
              boxShadow: '0 4px 12px rgba(0,0,0,0.3)', marginBottom: 4,
              pointerEvents: 'none',
            }}>
              {c.desc}
            </div>
          )}
          <div className="stat-value" style={{
            color: c.red ? 'var(--red)' : c.pos ? 'var(--green)' : 'var(--red)',
            fontSize: '1.1rem',
          }}>
            {c.value}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Trade log ─────────────────────────────────────────────────────────────────

function TradeLog({ trades }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  if (!trades?.length) return (
    <p style={{ color: 'var(--text-mute)', fontSize: '0.82rem' }}>{t('analytics.noTrades')}</p>
  )
  return (
    <div>
      <button className="btn btn-sm btn-ghost" onClick={() => setOpen(o => !o)} style={{ marginBottom: 8 }}>
        {open ? '▲' : '▼'} {t('analytics.tradeLogBtn', { count: trades.length })}
      </button>
      {open && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-mute)' }}>
                {[t('analytics.thTime'), 'Time', t('analytics.thAction'), t('analytics.thSymbol'), t('analytics.thQty'), t('analytics.thPrice')].map(h => (
                  <th key={h} style={{ padding: '5px 10px', textAlign: 'left', fontWeight: 700 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map((t, i) => {
                const isBuy = t.action === 'buy' || t.action === 'cover'
                return (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)', color: isBuy ? 'var(--green)' : 'var(--red)' }}>
                    <td style={{ padding: '4px 10px', color: 'var(--text-mute)' }}>{i + 1}</td>
                    <td style={{ padding: '4px 10px', color: 'var(--text-mute)', fontSize: '0.72rem', whiteSpace: 'nowrap' }}>{t.t ? String(t.t).slice(0, 19) : '—'}</td>
                    <td style={{ padding: '4px 10px', fontWeight: 700, textTransform: 'uppercase', fontSize: '0.72rem' }}>{t.action}</td>
                    <td style={{ padding: '4px 10px', color: 'var(--text-soft)' }}>{t.symbol}</td>
                    <td style={{ padding: '4px 10px' }}>{fmtNum(t.qty)}</td>
                    <td style={{ padding: '4px 10px' }}>${fmtNum(t.price)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Execution param badges ────────────────────────────────────────────────────

function ExecBadges({ params }) {
  const { t } = useTranslation()
  if (!params) return null
  const badges = []
  if (params.sizing_mode === 'all_in') {
    const lev = params.leverage && params.leverage !== 1 ? ` ${params.leverage}×` : ''
    badges.push({ label: `${t('analytics.allInBadge')}${lev}`, color: '#a78bfa' })
  }
  if (params.commission_mode === 'pct')
    badges.push({ label: t('analytics.pctCommission', { value: params.commission_value }), color: '#60a5fa' })
  if (params.commission_mode === 'flat')
    badges.push({ label: t('analytics.flatCommission', { value: params.commission_value }), color: '#60a5fa' })
  if (!badges.length) return null
  return (
    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 6 }}>
      {badges.map(b => (
        <span key={b.label} style={{
          fontSize: '0.7rem', padding: '2px 8px', borderRadius: 999, fontWeight: 600,
          background: b.color + '18', border: `1px solid ${b.color}44`, color: b.color,
        }}>{b.label}</span>
      ))}
    </div>
  )
}

// ── Run card (sidebar) ────────────────────────────────────────────────────────

function RunCard({
  run, isSelected, isCompared, isDeleteSelected, compareColor,
  onSelect, onToggleCompare, onToggleDelete, onDelete,
}) {
  const { t } = useTranslation()
  const m   = run.metrics || {}
  const ret = m.total_return_pct ?? 0

  return (
    <div
      onClick={() => onSelect(run.id)}
      style={{
        background:   isSelected ? 'rgba(58,183,245,0.08)' : 'var(--surface)',
        border:       `1px solid ${isDeleteSelected ? 'rgba(244,114,106,0.5)' : isSelected ? 'var(--accent)' : 'var(--border)'}`,
        borderLeft:   compareColor        ? `3px solid ${compareColor}`
                    : isDeleteSelected    ? '3px solid var(--red)'
                    : undefined,
        borderRadius: 10, padding: '10px 12px', cursor: 'pointer',
        marginBottom: 6, transition: 'all 0.15s',
      }}
    >
      {/* Name row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{
          fontSize: '0.8rem', fontWeight: 700, color: 'var(--text)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 140,
        }}>
          {run.strategy_name}
        </span>
        <button
          className="btn btn-sm btn-ghost btn-icon"
          onClick={e => { e.stopPropagation(); onDelete(run.id) }}
          title={t('analytics.deleteRun')}
          style={{ fontSize: '0.9rem', padding: '2px 5px', color: 'var(--text-mute)', flexShrink: 0 }}
        >🗑</button>
      </div>

      {/* Ticker + dates */}
      <div style={{ fontSize: '0.69rem', color: 'var(--text-mute)', marginBottom: 3 }}>
        {run.ticker && (
          <span style={{ marginRight: 6, color: 'var(--accent)', fontWeight: 700 }}>{run.ticker}</span>
        )}
        {run.start_date && <span>{fmtDate(run.start_date)} → {fmtDate(run.end_date)}</span>}
      </div>

      {/* Capital + timeframe */}
      <div style={{ fontSize: '0.68rem', color: 'var(--text-mute)', marginBottom: 5 }}>
        ${fmtNum(run.starting_cash, 0)} · {run.timeframe || '—'}
      </div>

      {/* Return + trade count */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 7 }}>
        <span style={{ fontSize: '0.9rem', fontWeight: 800, color: ret >= 0 ? 'var(--green)' : 'var(--red)' }}>
          {fmtPct(ret)}
        </span>
        <span style={{ fontSize: '0.68rem', color: 'var(--text-mute)' }}>
          {m.total_trades ?? 0} {t('analytics.trades')}
        </span>
      </div>

      {/* Compare + Select-for-delete toggles */}
      <div style={{ display: 'flex', gap: 14 }}>
        <div
          onClick={e => { e.stopPropagation(); onToggleCompare(run.id) }}
          style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}
        >
          <div style={{
            width: 13, height: 13, borderRadius: 3, flexShrink: 0, transition: 'all 0.15s',
            border:      `1.5px solid ${isCompared ? compareColor || 'var(--accent)' : 'var(--border)'}`,
            background:  isCompared ? compareColor || 'var(--accent)' : 'transparent',
          }} />
          <span style={{ fontSize: '0.67rem', color: 'var(--text-mute)' }}>{t('analytics.compare')}</span>
        </div>

        <div
          onClick={e => { e.stopPropagation(); onToggleDelete(run.id) }}
          style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}
        >
          <div style={{
            width: 13, height: 13, borderRadius: 3, flexShrink: 0, transition: 'all 0.15s',
            border:     `1.5px solid ${isDeleteSelected ? 'var(--red)' : 'var(--border)'}`,
            background: isDeleteSelected ? 'rgba(244,114,106,0.25)' : 'transparent',
          }} />
          <span style={{ fontSize: '0.67rem', color: 'var(--text-mute)' }}>{t('analytics.select')}</span>
        </div>
      </div>

      <div style={{ fontSize: '0.61rem', color: 'var(--text-mute)', marginTop: 5 }}>
        {fmtRunDate(run.run_at)}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Analytics() {
  const { t, i18n } = useTranslation()
  const [runs,        setRuns]        = useState([])
  const [selectedId,  setSelectedId]  = useState(null)
  const [selectedRun, setSelectedRun] = useState(null)
  const [compareIds,  setCompareIds]  = useState([])
  const [compareData, setCompareData] = useState({})
  const _compareFetching = useRef(new Set())  // guard against duplicate fetches
  const [deleteIds,        setDeleteIds]        = useState([])
  const [chartTab,         setChartTab]         = useState('equity')
  const [search,           setSearch]           = useState('')
  const [loading,          setLoading]          = useState(false)
  const [loadingRuns,      setLoadingRuns]      = useState(true)
  const [error,            setError]            = useState(null)
  const [aiModel,          setAiModel]          = useState(null)
  const [analysisMessages, setAnalysisMessages] = useState([])
  const [analysisPending,  setAnalysisPending]  = useState(false)
  const [analysisInput,    setAnalysisInput]    = useState('')
  const analysisEndRef = useRef(null)

  useEffect(() => { fetchRuns() }, [])

  // Fetch active AI model for the analysis tab badge/guard
  useEffect(() => {
    fetch(`${API}/db/model-keys`)
      .then(r => r.json())
      .then(d => {
        const active = d.keys?.find(k => k.active)
        setAiModel(active?.model_name || null)
      })
      .catch(() => {})
  }, [])

  // Reset analysis chat when a different run is selected
  useEffect(() => {
    setAnalysisMessages([])
    setAnalysisInput('')
  }, [selectedId])

  async function fetchRuns() {
    setLoadingRuns(true)
    try {
      const r = await fetch(`${API}/db/runs`)
      const j = await r.json()
      setRuns(j.runs || [])
    } catch (e) {
      setError(t('analytics.failedLoadRuns', { message: e.message }))
    } finally {
      setLoadingRuns(false)
    }
  }

  // Client-side filter by strategy name or ticker
  const filteredRuns = search.trim()
    ? runs.filter(r =>
        r.strategy_name?.toLowerCase().includes(search.toLowerCase()) ||
        r.ticker?.toLowerCase().includes(search.toLowerCase()))
    : runs

  // ── select a run for detail view ─────────────────────────────────────────

  const selectRun = useCallback(async (id) => {
    if (selectedId === id) return
    setSelectedId(id)
    setSelectedRun(null)
    setLoading(true)
    try {
      const r = await fetch(`${API}/db/runs/${id}`)
      setSelectedRun(await r.json())
    } catch (e) {
      setError(t('analytics.failedLoadRun', { message: e.message }))
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  // ── compare ───────────────────────────────────────────────────────────────

  const toggleCompare = useCallback(async (id) => {
    if (compareIds.includes(id)) {
      setCompareIds(p => p.filter(x => x !== id))
      setCompareData(p => { const c = { ...p }; delete c[id]; return c })
      return
    }
    if (compareIds.length >= 5) return
    setCompareIds(p => [...p, id])
    // Guard: skip fetch if already in-flight or already loaded (stale closure fix)
    setCompareData(prev => {
      if (prev[id] || _compareFetching.current.has(id)) return prev
      _compareFetching.current.add(id)
      fetch(`${API}/db/runs/${id}`)
        .then(r => r.json())
        .then(j => setCompareData(p => ({ ...p, [id]: j })))
        .catch(() => {})
        .finally(() => _compareFetching.current.delete(id))
      return prev
    })
  }, [compareIds])

  // ── multi-select for deletion ─────────────────────────────────────────────

  const toggleDelete = useCallback((id) => {
    setDeleteIds(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id])
  }, [])

  // ── single delete ─────────────────────────────────────────────────────────

  const deleteRun = useCallback(async (id) => {
    if (!confirm(t('analytics.confirmDelete'))) return
    try {
      const r = await fetch(`${API}/db/runs/${id}`, { method: 'DELETE' })
      if (!r.ok) throw new Error((await r.json()).detail || 'Delete failed')
      setRuns(p => p.filter(r => r.id !== id))
      if (selectedId === id) { setSelectedId(null); setSelectedRun(null) }
      setCompareIds(p => p.filter(x => x !== id))
      setCompareData(p => { const c = { ...p }; delete c[id]; return c })
      setDeleteIds(p => p.filter(x => x !== id))
    } catch (e) { alert(e.message || 'Failed to delete run.') }
  }, [selectedId])

  // ── batch delete ──────────────────────────────────────────────────────────

  const deleteBatch = useCallback(async () => {
    if (!deleteIds.length) return
    const n = deleteIds.length
    if (!confirm(t('analytics.confirmDeleteBatch', { count: n }))) return
    try {
      const r = await fetch(`${API}/db/runs/batch-delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: deleteIds }),
      })
      if (!r.ok) throw new Error((await r.json()).detail || 'Batch delete failed')
      setRuns(p => p.filter(r => !deleteIds.includes(r.id)))
      if (deleteIds.includes(selectedId)) { setSelectedId(null); setSelectedRun(null) }
      setCompareIds(p => p.filter(x => !deleteIds.includes(x)))
      setCompareData(p => { const c = { ...p }; deleteIds.forEach(id => delete c[id]); return c })
      setDeleteIds([])
    } catch { alert('Failed to delete selected runs.') }
  }, [deleteIds, selectedId])

  // ── delete all ────────────────────────────────────────────────────────────

  const deleteAll = useCallback(async () => {
    if (!runs.length) return
    if (!confirm(t('analytics.confirmDeleteAll', { count: runs.length }))) return
    try {
      const r = await fetch(`${API}/db/runs`, { method: 'DELETE' })
      if (!r.ok) throw new Error((await r.json()).detail || 'Delete all failed')
      setRuns([])
      setSelectedId(null); setSelectedRun(null)
      setCompareIds([]); setCompareData({})
      setDeleteIds([])
    } catch { alert('Failed to delete all runs.') }
  }, [runs.length])

  // ── AI run analysis ───────────────────────────────────────────────────────

  async function sendAnalysis(text) {
    if (!text.trim() || analysisPending || !selectedRun) return
    const userMsg = { role: 'user', content: text.trim() }
    const next = [...analysisMessages, userMsg]
    setAnalysisMessages(next)
    setAnalysisInput('')
    setAnalysisPending(true)
    try {
      const r = await fetch(`${API}/ai/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject_type: 'run',
          subject_id: selectedRun.id,
          messages: next,
          temperature: ANALYSIS_TEMPERATURE,
          language: i18n.language,
        }),
      })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || 'Analysis failed')
      setAnalysisMessages(prev => [...prev, { role: 'assistant', content: j.reply }])
    } catch (e) {
      setAnalysisMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e.message}` }])
    } finally {
      setAnalysisPending(false)
    }
  }

  // Auto-scroll chat to bottom on new messages
  useLayoutEffect(() => {
    if (chartTab === 'ai') analysisEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [analysisMessages, chartTab])

  // ── chart data ────────────────────────────────────────────────────────────

  function allChartRuns() {
    return [
      selectedRun && { run: selectedRun, colorIdx: 0 },
      ...compareIds
        .filter(id => id !== selectedId && compareData[id])
        .map((id, i) => ({ run: compareData[id], colorIdx: i + 1 })),
    ].filter(Boolean)
  }

  function buildEquityChart() {
    const all = allChartRuns()
    if (!all.length) return []
    const primaryStartCash = all[0].run.starting_cash || 1
    const curve = thinSeries(all[0].run.equity_curve || [])

    // Map each trade to its nearest curve index (handles thinSeries gaps)
    const trades = selectedRun?.trade_log || []
    const tradeByIndex = {}
    for (const t of trades) {
      if (!t.t) continue
      const tradeMs = new Date(t.t).getTime()
      let closestIdx = 0, closestDiff = Infinity
      for (let i = 0; i < curve.length; i++) {
        const diff = Math.abs(new Date(curve[i].t).getTime() - tradeMs)
        if (diff < closestDiff) { closestDiff = diff; closestIdx = i }
      }
      if (!tradeByIndex[closestIdx]) tradeByIndex[closestIdx] = []
      tradeByIndex[closestIdx].push(t)
    }

    return curve.map((pt, i) => {
      const out = {
        t: pt.t,
        equity_0: ((pt.equity / primaryStartCash) - 1) * 100,
      }
      all.slice(1).forEach(({ run }, j) => {
        const c2       = run.equity_curve || []
        const startCash = run.starting_cash || 1
        const idx      = Math.round((i / curve.length) * c2.length)
        const eq       = c2[Math.min(idx, c2.length - 1)]?.equity ?? null
        out[`equity_${j + 1}`] = eq != null ? ((eq / startCash) - 1) * 100 : null
      })
      if (tradeByIndex[i]) out.tradeMarker = tradeByIndex[i]
      return out
    })
  }

  function buildPriceChart() {
    if (!selectedRun?.equity_curve?.length) return []
    const curve = thinSeries(selectedRun.equity_curve)
    const trades = selectedRun?.trade_log || []
    const tradeByIndex = {}
    for (const t of trades) {
      if (!t.t) continue
      const tradeMs = new Date(t.t).getTime()
      let closestIdx = 0, closestDiff = Infinity
      for (let i = 0; i < curve.length; i++) {
        const diff = Math.abs(new Date(curve[i].t).getTime() - tradeMs)
        if (diff < closestDiff) { closestDiff = diff; closestIdx = i }
      }
      if (!tradeByIndex[closestIdx]) tradeByIndex[closestIdx] = []
      tradeByIndex[closestIdx].push(t)
    }
    return curve.map((pt, i) => {
      const out = { t: pt.t, price: pt.price ?? null }
      if (tradeByIndex[i]) out.tradeMarker = tradeByIndex[i]
      return out
    })
  }

  function buildDrawdownChart() {
    const all = allChartRuns()
    if (!all.length) return []
    const dd0 = buildDrawdown(thinSeries(all[0].run.equity_curve || []))
    return dd0.map((pt, i) => {
      const out = { t: pt.t, dd_0: pt.drawdown }
      all.slice(1).forEach(({ run }, j) => {
        const dd2 = buildDrawdown(thinSeries(run.equity_curve || []))
        out[`dd_${j + 1}`] = dd2[Math.min(i, dd2.length - 1)]?.drawdown ?? null
      })
      return out
    })
  }

  const chartRunOrder = [
    selectedRun && { id: selectedId, name: selectedRun.strategy_name || 'Run', colorIdx: 0 },
    ...compareIds
      .filter(id => id !== selectedId && compareData[id])
      .map((id, i) => ({ id, name: compareData[id].strategy_name || `Run ${id}`, colorIdx: i + 1 })),
  ].filter(Boolean)

  const equityData   = buildEquityChart()
  const drawdownData = buildDrawdownChart()
  const priceData    = buildPriceChart()
  const hasChart     = equityData.length > 0

  // params stored at save time (includes execution settings)
  const params = selectedRun?.params || {}

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', minHeight: '70vh' }}>

      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <div style={{
        width: 256, flexShrink: 0,
        background: 'var(--panel)', border: '1px solid var(--border)',
        borderRadius: 'var(--r-lg)', padding: 14,
        position: 'sticky', top: 70, maxHeight: 'calc(100vh - 90px)',
        display: 'flex', flexDirection: 'column', gap: 0,
      }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--text-mute)' }}>
            {t('analytics.savedRuns')}
            {runs.length > 0 && (
              <span style={{ color: 'var(--text-soft)', marginLeft: 5, fontWeight: 500 }}>({runs.length})</span>
            )}
          </span>
          <button className="btn btn-sm btn-ghost btn-icon" onClick={fetchRuns} title={t('analytics.refreshList')}>↻</button>
        </div>

        {/* Search */}
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={t('analytics.searchPlaceholder')}
          style={{ marginBottom: 10, fontSize: '0.8rem', padding: '6px 10px' }}
        />

        {/* Run list */}
        <div style={{ flex: 1, overflowY: 'auto', marginRight: -4, paddingRight: 4 }}>
          {loadingRuns && (
            <p style={{ color: 'var(--text-mute)', fontSize: '0.8rem' }}>{t('analytics.loadingRuns')}</p>
          )}
          {!loadingRuns && !filteredRuns.length && (
            <p style={{ color: 'var(--text-mute)', fontSize: '0.8rem', lineHeight: 1.5 }}>
              {search.trim() ? t('analytics.noMatchingRuns') : t('analytics.noRunsYet')}
            </p>
          )}
          {filteredRuns.map(run => {
            const cmpIdx = compareIds.indexOf(run.id)
            return (
              <RunCard
                key={run.id}
                run={run}
                isSelected={run.id === selectedId}
                isCompared={cmpIdx >= 0}
                isDeleteSelected={deleteIds.includes(run.id)}
                compareColor={cmpIdx >= 0 ? RUN_COLORS[cmpIdx] : null}
                onSelect={selectRun}
                onToggleCompare={toggleCompare}
                onToggleDelete={toggleDelete}
                onDelete={deleteRun}
              />
            )
          })}
        </div>

        {/* Bulk action footer */}
        <div style={{ paddingTop: 10, borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {deleteIds.length > 0 && (
            <button className="btn btn-danger btn-sm btn-pill" onClick={deleteBatch}>
              {t('analytics.deleteSelected', { count: deleteIds.length })}
            </button>
          )}
          {runs.length > 0 && (
            <button
              onClick={deleteAll}
              style={{
                background: 'none',
                border: '1px solid rgba(244,114,106,0.3)',
                borderRadius: 'var(--r)',
                color: 'var(--red)',
                fontSize: '0.75rem',
                padding: '5px 10px',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {t('analytics.deleteAllRuns')}
            </button>
          )}
        </div>
      </div>

      {/* ── Main detail area ─────────────────────────────────────────────── */}
      <div style={{ flex: 1, minWidth: 0 }}>

        {/* Empty state */}
        {!selectedRun && !loading && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', minHeight: 380,
            color: 'var(--text-mute)', textAlign: 'center', gap: 12,
          }}>
            <div style={{ fontSize: '3rem' }}>📈</div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-soft)' }}>
              {t('analytics.selectRunTitle')}
            </div>
            <div style={{ fontSize: '0.85rem' }}>
              {t('analytics.selectRunDesc')}
            </div>
          </div>
        )}

        {/* Loading spinner */}
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 40, color: 'var(--text-mute)' }}>
            <span className="spinner" /> {t('analytics.loadingRunData')}
          </div>
        )}

        {selectedRun && !loading && (
          <>
            {/* ── Run header ────────────────────────────────────────────── */}
            <div className="card" style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {/* Strategy name */}
                  <div style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '-0.02em', marginBottom: 6 }}>
                    {selectedRun.strategy_name}
                  </div>

                  {/* Core run metadata */}
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-mute)', display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 4 }}>
                    {selectedRun.ticker && (
                      <span>
                        <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{selectedRun.ticker}</span>
                      </span>
                    )}
                    {selectedRun.timeframe && (
                      <span>{t('analytics.timeframe')}: <strong style={{ color: 'var(--text-soft)' }}>{selectedRun.timeframe}</strong></span>
                    )}
                    {selectedRun.start_date && (
                      <span>{fmtDate(selectedRun.start_date)} → {fmtDate(selectedRun.end_date)}</span>
                    )}
                    <span>
                      {t('analytics.capital')}: <strong style={{ color: 'var(--text-soft)' }}>${fmtNum(selectedRun.starting_cash, 0)}</strong>
                    </span>
                    <span style={{ color: 'var(--text-mute)' }}>
                      {fmtRunDate(selectedRun.run_at)}
                    </span>
                  </div>

                  {/* Execution settings badges (all_in, no_rebuy, commission) */}
                  <ExecBadges params={params} />
                </div>

                {/* Warmup badge */}
                <div style={{ flexShrink: 0 }}>
                  {(selectedRun.warmup_bars > 0 || params.warmup_bars > 0) && (
                    <span style={{
                      fontSize: '0.72rem',
                      background: 'rgba(58,183,245,0.1)', color: 'var(--accent)',
                      borderRadius: 6, padding: '3px 8px',
                    }}>
                      {t('analytics.barWarmup', { count: selectedRun.warmup_bars || params.warmup_bars })}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* ── Metrics ───────────────────────────────────────────────── */}
            <div style={{ marginBottom: 14 }}>
              <MetricsGrid metrics={selectedRun.metrics} />
            </div>

            {/* ── Chart ─────────────────────────────────────────────────── */}
            <div className="card" style={{ marginBottom: 14 }}>
              {/* Tab strip + compare legend */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
                <div className="tab-strip" style={{ width: 'auto' }}>
                  {[{ id: 'equity', label: t('analytics.equityCurve') }, { id: 'drawdown', label: t('analytics.drawdown') }, { id: 'price', label: t('analytics.assetPrice') }, { id: 'ai', label: t('analytics.aiAnalysis') }].map(tab => (
                    <button key={tab.id}
                      className={`tab-btn${chartTab === tab.id ? ' active' : ''}`}
                      onClick={() => setChartTab(tab.id)}
                      style={{ flex: 'none', padding: '5px 18px', ...(tab.id === 'ai' && chartTab !== 'ai' ? { color: '#f59e0b' } : {}) }}>
                      {tab.label}
                    </button>
                  ))}
                </div>
                {chartRunOrder.length > 1 && (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    {chartRunOrder.map(r => (
                      <span key={r.id} style={{ fontSize: '0.72rem', color: RUN_COLORS[r.colorIdx], fontWeight: 700 }}>
                        ● {r.name}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Equity curve */}
              {chartTab === 'equity' && hasChart && (
                <ResponsiveContainer width="100%" height={360}>
                  <LineChart data={equityData} margin={{ top: 4, right: 10, left: 0, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="t" tickFormatter={xTickFmt} tick={{ fontSize: 10, fill: 'var(--text-mute)' }} minTickGap={60} />
                    <YAxis
                      tick={{ fontSize: 10, fill: 'var(--text-mute)' }}
                      tickFormatter={v => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`}
                      width={60}
                      label={{ value: t('analytics.returnPct'), angle: -90, position: 'insideLeft', offset: 14, fontSize: 10, fill: 'var(--text-mute)' }}
                    />
                    <Tooltip content={<ChartTooltip />} />
                    {chartRunOrder.map(r => (
                      <Line key={r.id} type="monotone" dataKey={`equity_${r.colorIdx}`}
                        name={r.name} stroke={RUN_COLORS[r.colorIdx]} strokeWidth={2} connectNulls
                        dot={r.colorIdx === 0
                          ? (props) => {
                              const { cx, cy, payload } = props
                              if (payload.tradeMarker) {
                                const isBuy = payload.tradeMarker[0].action === 'buy' || payload.tradeMarker[0].action === 'cover'
                                return (
                                  <circle key={`trade-${cx}-${cy}`} cx={cx} cy={cy} r={5}
                                    fill={isBuy ? 'var(--green)' : 'var(--red)'}
                                    stroke="var(--panel2)" strokeWidth={1.5} />
                                )
                              }
                              return null
                            }
                          : false
                        }
                        activeDot={r.colorIdx === 0 ? { r: 7 } : false}
                      />
                    ))}
                    <Brush dataKey="t" height={20} stroke="var(--border)" fill="var(--panel2)"
                      travellerWidth={6} tickFormatter={xTickFmt} />
                  </LineChart>
                </ResponsiveContainer>
              )}

              {/* Drawdown */}
              {chartTab === 'drawdown' && hasChart && (
                <ResponsiveContainer width="100%" height={360}>
                  <AreaChart data={drawdownData} margin={{ top: 4, right: 10, left: 0, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="t" tickFormatter={xTickFmt} tick={{ fontSize: 10, fill: 'var(--text-mute)' }} minTickGap={60} />
                    <YAxis
                      tick={{ fontSize: 10, fill: 'var(--text-mute)' }}
                      tickFormatter={v => `${v.toFixed(1)}%`}
                      width={60}
                      label={{ value: t('analytics.drawdownPct'), angle: -90, position: 'insideLeft', offset: 14, fontSize: 10, fill: 'var(--text-mute)' }}
                    />
                    <Tooltip content={<ChartTooltip />} />
                    {chartRunOrder.map(r => (
                      <Area key={r.id} type="monotone" dataKey={`dd_${r.colorIdx}`}
                        name={r.name} stroke={RUN_COLORS[r.colorIdx]}
                        fill={RUN_COLORS[r.colorIdx] + '22'} strokeWidth={2} dot={false} connectNulls />
                    ))}
                    <Brush dataKey="t" height={20} stroke="var(--border)" fill="var(--panel2)"
                      travellerWidth={6} tickFormatter={xTickFmt} />
                  </AreaChart>
                </ResponsiveContainer>
              )}

              {/* Asset Price */}
              {chartTab === 'price' && hasChart && (
                <ResponsiveContainer width="100%" height={360}>
                  <LineChart data={priceData} margin={{ top: 4, right: 10, left: 0, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="t" tickFormatter={xTickFmt} tick={{ fontSize: 10, fill: 'var(--text-mute)' }} minTickGap={60} />
                    <YAxis
                      tick={{ fontSize: 10, fill: 'var(--text-mute)' }}
                      tickFormatter={v => `$${fmtNum(v)}`}
                      width={72}
                      domain={['auto', 'auto']}
                      label={{ value: t('analytics.priceDollar'), angle: -90, position: 'insideLeft', offset: 14, fontSize: 10, fill: 'var(--text-mute)' }}
                    />
                    <Tooltip content={<ChartTooltip />} />
                    <Line type="monotone" dataKey="price" name={selectedRun?.ticker || 'Price'}
                      stroke="var(--accent)" strokeWidth={2} connectNulls
                      dot={(props) => {
                        const { cx, cy, payload } = props
                        if (payload.tradeMarker) {
                          const isBuy = payload.tradeMarker[0].action === 'buy' || payload.tradeMarker[0].action === 'cover'
                          return (
                            <circle key={`price-trade-${cx}-${cy}`} cx={cx} cy={cy} r={5}
                              fill={isBuy ? 'var(--green)' : 'var(--red)'}
                              stroke="var(--panel2)" strokeWidth={1.5} />
                          )
                        }
                        return null
                      }}
                      activeDot={{ r: 7 }}
                    />
                    <Brush dataKey="t" height={20} stroke="var(--border)" fill="var(--panel2)"
                      travellerWidth={6} tickFormatter={xTickFmt} />
                  </LineChart>
                </ResponsiveContainer>
              )}

              {/* AI Analysis chat */}
              {chartTab === 'ai' && (
                <div style={{ display: 'flex', flexDirection: 'column', height: 480 }}>
                  {!aiModel ? (
                    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 8, color: 'var(--text-mute)' }}>
                      <div style={{ fontSize: '1.5rem' }}>🤖</div>
                      <div style={{ fontSize: '0.85rem' }}>{t('analytics.noAiModel')}</div>
                    </div>
                  ) : (
                    <>
                      {/* Messages area */}
                      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10, paddingBottom: 4 }}>
                        {analysisMessages.length === 0 && (
                          <div style={{ padding: '8px 0' }}>
                            <div style={{ fontSize: '0.78rem', color: 'var(--text-mute)', marginBottom: 10 }}>
                              Ask the AI analyst about this run. Using <strong style={{ color: 'var(--text-soft)' }}>{aiModel}</strong> · temp {ANALYSIS_TEMPERATURE}
                            </div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                              {RUN_PROMPTS.map(p => (
                                <button key={p}
                                  className="btn btn-sm"
                                  style={{ fontSize: '0.75rem', background: 'var(--panel2)', border: '1px solid var(--border)', borderRadius: 20, padding: '4px 12px', cursor: 'pointer', textAlign: 'left' }}
                                  onClick={() => sendAnalysis(p)}
                                >
                                  {p}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        {analysisMessages.map((msg, i) => (
                          <div key={i} style={{
                            display: 'flex',
                            justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                          }}>
                            <div style={{
                              maxWidth: '85%',
                              padding: '8px 13px',
                              borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                              background: msg.role === 'user' ? 'var(--accent)' : 'var(--panel2)',
                              color: msg.role === 'user' ? '#fff' : 'var(--text)',
                              fontSize: '0.82rem',
                              lineHeight: 1.55,
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word',
                            }}>
                              {msg.content}
                            </div>
                          </div>
                        ))}

                        {analysisPending && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-mute)', fontSize: '0.8rem' }}>
                            <span className="spinner" style={{ width: 14, height: 14 }} /> {t('analytics.analyzing')}
                          </div>
                        )}
                        <div ref={analysisEndRef} />
                      </div>

                      {/* Input row */}
                      <div style={{ display: 'flex', gap: 8, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
                        <input
                          value={analysisInput}
                          onChange={e => setAnalysisInput(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAnalysis(analysisInput) } }}
                          placeholder={t('analytics.askAboutRun')}
                          disabled={analysisPending}
                          style={{ flex: 1, fontSize: '0.85rem', padding: '7px 12px', borderRadius: 'var(--r)', border: '1px solid var(--border)', background: 'var(--panel2)', color: 'var(--text)' }}
                        />
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => sendAnalysis(analysisInput)}
                          disabled={analysisPending || !analysisInput.trim()}
                          style={{ flexShrink: 0 }}
                        >
                          {t('common.send')}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}

              {!hasChart && chartTab !== 'ai' && (
                <div style={{ textAlign: 'center', color: 'var(--text-mute)', padding: 40 }}>
                  {t('analytics.noEquityCurve')}
                </div>
              )}
            </div>

            {/* ── Trade log ─────────────────────────────────────────────── */}
            <div className="card">
              <div style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--text-mute)', marginBottom: 10 }}>
                {t('analytics.tradeLog')}
              </div>
              <TradeLog trades={selectedRun.trade_log} />
            </div>
          </>
        )}

        {error && (
          <div className="alert alert-error" style={{ marginTop: 12 }}>{error}</div>
        )}
      </div>
    </div>
  )
}
