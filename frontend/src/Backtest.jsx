import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

const API = import.meta.env.VITE_API_BASE || ''
const TFS = ['1m','5m','15m','30m','1h','4h','1d','1w','1M']

// ── Ticker search combobox ─────────────────────────────────────────────────────
function TickerSearch({ value, onChange, disabled }) {
  const { t } = useTranslation()
  const [query, setQuery]       = useState(value)
  const [results, setResults]   = useState([])
  const [open, setOpen]         = useState(false)
  const [loading, setLoading]   = useState(false)
  const [cursor, setCursor]     = useState(-1)
  const debounceRef             = useRef(null)
  const containerRef            = useRef(null)

  // Sync external value changes (e.g. on reset)
  useEffect(() => { setQuery(value) }, [value])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = e => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const search = q => {
    clearTimeout(debounceRef.current)
    if (q.length < 2) { setResults([]); setOpen(false); return }
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const r = await fetch(`${API}/api/data/search-tickers?q=${encodeURIComponent(q)}`)
        if (!r.ok) { setResults([]); return }
        const d = await r.json()
        setResults(d.results || [])
        setOpen((d.results || []).length > 0)
        setCursor(-1)
      } catch { setResults([]) }
      finally { setLoading(false) }
    }, 300)
  }

  const select = item => {
    setQuery(item.symbol)
    onChange(item.symbol)
    setOpen(false)
    setResults([])
  }

  const handleKey = e => {
    if (!open) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(c + 1, results.length - 1)) }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)) }
    if (e.key === 'Enter' && cursor >= 0) { e.preventDefault(); select(results[cursor]) }
    if (e.key === 'Escape') { setOpen(false) }
  }

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      <div style={{ position: 'relative' }}>
        <input
          value={query}
          onChange={e => { const v = e.target.value.toUpperCase(); setQuery(v); onChange(v); search(v) }}
          onKeyDown={handleKey}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder={disabled ? t('backtest.tickerDisabled') : t('backtest.tickerPlaceholder')}
          disabled={disabled}
          style={{ paddingRight: loading ? 32 : undefined }}
        />
        {loading && (
          <span style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', fontSize: '0.75rem', color: '#6b7280' }}>⟳</span>
        )}
      </div>
      {open && results.length > 0 && (
        <div style={{
          position: 'absolute', zIndex: 100, top: 'calc(100% + 4px)', left: 0, right: 0,
          background: '#0f172a', border: '1px solid #334155', borderRadius: 8,
          boxShadow: '0 8px 24px rgba(0,0,0,0.5)', overflow: 'hidden',
          maxHeight: 260, overflowY: 'auto',
        }}>
          {results.slice(0, 10).map((r, i) => (
            <div key={r.symbol}
              onMouseDown={() => select(r)}
              onMouseEnter={() => setCursor(i)}
              style={{
                padding: '8px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10,
                background: i === cursor ? 'rgba(59,130,246,0.15)' : 'transparent',
                borderBottom: i < results.length - 1 ? '1px solid #1e293b' : 'none',
              }}>
              <span style={{ fontWeight: 700, fontSize: '0.85rem', color: '#e5e7eb', minWidth: 60 }}>{r.symbol}</span>
              <span style={{ fontSize: '0.78rem', color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Session data cache ────────────────────────────────────────────────────────
// Persists for the lifetime of the page; keys: "ticker|start|end|timeframe"
const dataCache = new Map()
const mkKey = (ticker, start, end, tf) => `${ticker}|${start}|${end}|${tf}`

const fmt  = n => typeof n === 'number' ? n.toLocaleString('en-US', { minimumFractionDigits:2, maximumFractionDigits:2 }) : '—'
const fmtP = (v, b) => b ? ((v - b) / Math.abs(b) * 100).toFixed(2) + '%' : '—'

function StatCard({ label, value, sub, color, emoji }) {
  return (
    <div className="stat-card" style={{ borderColor: `${color}22` }}>
      <div className="stat-label" style={{ display:'flex', alignItems:'center', gap:5 }}>
        <span>{emoji}</span>{label}
      </div>
      <div className="stat-value" style={{ color }}>{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

export default function Backtest({ goTo }) {
  const { t } = useTranslation()
  const [method,     setMethod]     = useState('upload')
  const [file,       setFile]       = useState(null)
  const [ticker,     setTicker]     = useState('')
  const [startDate,  setStartDate]  = useState('')
  const [endDate,    setEndDate]    = useState('')
  const [timeframe,  setTimeframe]  = useState('1d')
  const [cash,       setCash]       = useState('10000')
  const [strategies, setStrategies] = useState([])
  const [selId,      setSelId]      = useState(null)
  const [hasKey,     setHasKey]     = useState(null)
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState('')
  const [result,     setResult]     = useState(null)
  const [fromCache,  setFromCache]  = useState(null) // null=n/a, true=cache hit, false=fresh fetch
  // Advanced execution options
  const [showAdv,      setShowAdv]      = useState(false)
  const [sizingMode,   setSizingMode]   = useState('fixed')   // 'fixed' | 'all_in'
  const [leverage,     setLeverage]     = useState('1')
  const [commMode,     setCommMode]     = useState('none')    // 'none' | 'pct' | 'flat'
  const [commValue,    setCommValue]    = useState('0')
  const [allowFractional, setAllowFractional] = useState(false) // false=stocks/futures, true=crypto

  useEffect(() => {
    fetch(`${API}/api/db/strategies`).then(r=>r.json()).then(d => {
      const arr = (d.strategies||[]).map(s => ({
        ...s, config: (() => { try { return JSON.parse(s.config) } catch { return s.config } })()
      }))
      setStrategies(arr)
      if (arr.length) setSelId(arr[0].id)
    }).catch(()=>{})

    // Yahoo Finance is always available as a built-in fallback — API tab is always enabled
    setHasKey(true)
  }, [])

  const selected = strategies.find(s => s.id === selId)

  const run = async e => {
    e.preventDefault()
    setError(''); setResult(null)
    if (method==='upload' && !file)            return setError(t('backtest.errSelectFile'))
    if (method==='api' && !ticker)             return setError(t('backtest.errEnterTicker'))
    if (method==='api' && (!startDate||!endDate)) return setError(t('backtest.errSetDates'))
    if (!selected)                             return setError(t('backtest.errNoStrategy'))
    setLoading(true)

    try {
      const form = new FormData()

      if (method === 'upload') {
        form.append('file', file)
      } else {
        const key = mkKey(ticker, startDate, endDate, timeframe)
        let rows
        if (dataCache.has(key)) {
          rows = dataCache.get(key)
          setFromCache(true)
        } else {
          const dr = await fetch(`${API}/api/data/fetch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker, start_date: startDate, end_date: endDate, timeframe }),
          })
          if (!dr.ok) {
            const d = await dr.json().catch(()=>({}))
            throw new Error(d.detail || 'Failed to fetch market data.')
          }
          const fetched = await dr.json()
          rows = fetched.rows || []
          dataCache.set(key, rows)
          setFromCache(false)
        }
        form.append('data', JSON.stringify(rows))
      }

      form.append('column_map', JSON.stringify({
        time:'timestamp', open:'open', high:'high', low:'low', close:'close', volume:'volume', name:'symbol'
      }))
      form.append('strategies', JSON.stringify([selected]))
      form.append('starting_cash', cash || '10000')
      if (timeframe) form.append('timeframe', timeframe)
      // Advanced execution options
      form.append('sizing_mode',      sizingMode)
      form.append('leverage',         leverage || '1')
      form.append('commission_mode',  commMode)
      form.append('commission_value', commValue || '0')
      form.append('allow_fractional', allowFractional ? 'true' : 'false')

      const res = await fetch(`${API}/api/backtest/upload`, { method:'POST', body:form })
      if (!res.ok) {
        const d = await res.json().catch(()=>({}))
        throw new Error(d.detail || `Server error ${res.status}`)
      }
      setResult(await res.json())
    } catch(err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const startCash = parseFloat(cash) || 10000
  const pnl    = result ? result.total_value - startCash : 0
  const pnlPct = result ? fmtP(result.total_value, startCash) : '—'
  const positive = pnl >= 0

  // Cache status for current API params
  const currentKey   = mkKey(ticker, startDate, endDate, timeframe)
  const hasCached    = method === 'api' && ticker && startDate && endDate && dataCache.has(currentKey)
  const cachedBars   = hasCached ? dataCache.get(currentKey).length : 0

  return (
    <div className="view">
      <h2>{t('backtest.title')}</h2>
      <p>{t('backtest.subtitle')}</p>


      <div className="card" style={{ marginBottom: 16 }}>
        <form onSubmit={run}>

          {/* ── Strategy selector ── */}
          <div style={{ marginBottom: 18 }}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8 }}>
              <span className="field-label">{t('backtest.strategy')}</span>
              <button type="button" className="btn btn-ghost btn-sm"
                onClick={() => goTo?.('strategy')}>{t('backtest.manageStrategies')}</button>
            </div>
            {strategies.length === 0 ? (
              <div style={{ background:'rgba(124,134,247,0.07)', border:'1px dashed rgba(124,134,247,0.35)',
                borderRadius:'var(--r)', padding:'20px', textAlign:'center' }}>
                <div style={{ fontSize:'1.6rem', marginBottom:6 }}>🧩</div>
                <p style={{ color:'var(--text-mute)', margin:'0 0 10px', fontSize:'0.86rem' }}>{t('backtest.noStrategiesTitle')}</p>
                <button type="button" className="btn btn-primary btn-sm btn-pill"
                  onClick={() => goTo?.('strategy')}>{t('backtest.openStrategyBuilder')}</button>
              </div>
            ) : (
              <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                {strategies.map(s => (
                  <button type="button" key={s.id}
                    onClick={() => setSelId(s.id)}
                    style={{
                      padding:'6px 14px', borderRadius:'var(--r)', fontSize:'0.84rem',
                      fontWeight: s.id===selId ? 700 : 500, cursor:'pointer', transition:'all 0.15s',
                      background: s.id===selId ? 'rgba(124,134,247,0.12)' : 'var(--surface)',
                      border: s.id===selId ? '1px solid rgba(124,134,247,0.45)' : '1px solid var(--border)',
                      color: s.id===selId ? 'var(--accent2)' : 'var(--text-soft)',
                    }}>
                    {s.name || t('backtest.strategyFallback', { id: s.id })}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="divider" style={{ marginBottom:16 }} />

          {/* ── Data source ── */}
          <div style={{ marginBottom:16 }}>
            <div className="field-label" style={{ marginBottom:8 }}>{t('backtest.dataSource')}</div>
            <div className="tab-strip" style={{ marginBottom:14, maxWidth:320 }}>
              <button type="button" className={`tab-btn${method==='upload'?' active':''}`}
                onClick={() => setMethod('upload')}>📂 {t('backtest.uploadCsv')}</button>
              <button type="button" className={`tab-btn${method==='api'?' active':''}`}
                onClick={() => setMethod('api')}>🌐 {t('backtest.fetchFromApi')}</button>
            </div>

            {method === 'upload' ? (
              <div className="grid-2">
                <div className="field">
                  <label className="field-label">{t('backtest.csvFile')}</label>
                  <label className={`upload-zone${file?' has-file':''}`}>
                    <span style={{ fontSize:'1.1rem' }}>{file ? '✅' : '📁'}</span>
                    <span style={{ fontSize:'0.84rem', color: file?'var(--green)':'var(--text-mute)' }}>
                      {file ? file.name : t('backtest.clickToSelect')}
                    </span>
                    <input type="file" accept=".csv" style={{ display:'none' }}
                      onChange={e => setFile(e.target.files?.[0]||null)} />
                  </label>
                </div>
                <div className="field">
                  <label className="field-label">{t('backtest.timeframe')}</label>
                  <select value={timeframe} onChange={e=>setTimeframe(e.target.value)}>
                    <option value="">{t('backtest.autoDetect')}</option>
                    {TFS.map(tf=><option key={tf}>{tf}</option>)}
                  </select>
                </div>
              </div>
            ) : (
              <>
              <div className="grid-auto">
                <div className="field">
                  <label className="field-label">{t('backtest.ticker')}</label>
                  <TickerSearch value={ticker} onChange={setTicker} disabled={!hasKey} />
                </div>
                <div className="field">
                  <label className="field-label">{t('backtest.startDate')}</label>
                  <input type="datetime-local" value={startDate} onChange={e=>setStartDate(e.target.value)} />
                </div>
                <div className="field">
                  <label className="field-label">{t('backtest.endDate')}</label>
                  <input type="datetime-local" value={endDate} onChange={e=>setEndDate(e.target.value)} />
                </div>
                <div className="field">
                  <label className="field-label">{t('backtest.timeframe')}</label>
                  <select value={timeframe} onChange={e=>setTimeframe(e.target.value)}>
                    {TFS.map(tf=><option key={tf}>{tf}</option>)}
                  </select>
                </div>
              </div>
              {/* Cache status badge */}
              {hasCached && (
                <div style={{ display:'flex', alignItems:'center', gap:8, marginTop:8 }}>
                  <span style={{ fontSize:'0.75rem', padding:'2px 10px', borderRadius:999,
                    background:'rgba(52,211,153,0.1)', border:'1px solid rgba(52,211,153,0.25)', color:'#34d399' }}>
                    {t('backtest.barsCached', { count: cachedBars.toLocaleString() })}
                  </span>
                  <button type="button"
                    style={{ fontSize:'0.72rem', background:'transparent', border:'1px solid #334155',
                      borderRadius:6, color:'#6b7280', cursor:'pointer', padding:'2px 8px' }}
                    onClick={() => { dataCache.delete(currentKey); setFromCache(null) }}>
                    {t('backtest.reFetch')}
                  </button>
                </div>
              )}
              </>
            )}
          </div>

          {/* ── Capital ── */}
          <div style={{ marginBottom:16, maxWidth:220 }}>
            <div className="field">
              <label className="field-label">{t('backtest.startingCapital')}</label>
              <input type="number" value={cash} min="0" step="100"
                onChange={e=>setCash(e.target.value)} placeholder="10000" />
            </div>
          </div>

          {/* ── Advanced Settings ── */}
          <div style={{ marginBottom:20 }}>
            <button type="button"
              onClick={() => setShowAdv(v => !v)}
              style={{
                background:'none', border:'none', cursor:'pointer', padding:0,
                color:'var(--text-mute)', fontSize:'0.82rem', display:'flex',
                alignItems:'center', gap:5, userSelect:'none',
              }}>
              <span style={{ fontSize:'0.7rem' }}>{showAdv ? '▾' : '▸'}</span>
              {t('backtest.advancedSettings')}
            </button>

            {showAdv && (
              <div style={{
                marginTop:12, padding:'14px 16px', borderRadius:'var(--r)',
                background:'var(--surface)', border:'1px solid var(--border)',
                display:'flex', flexDirection:'column', gap:16,
              }}>

                {/* Position sizing */}
                <div>
                  <div className="field-label" style={{ marginBottom:8 }}>{t('backtest.positionSizing')}</div>
                  <div style={{ display:'flex', gap:6, marginBottom: sizingMode==='all_in' ? 10 : 0 }}>
                    {[['fixed', t('backtest.fixedQty')], ['all_in', t('backtest.allIn')]].map(([v,label]) => (
                      <button key={v} type="button"
                        onClick={() => setSizingMode(v)}
                        style={{
                          padding:'5px 14px', borderRadius:'var(--r)', fontSize:'0.82rem',
                          cursor:'pointer', transition:'all 0.15s',
                          background: sizingMode===v ? 'rgba(124,134,247,0.12)' : 'var(--panel)',
                          border: sizingMode===v ? '1px solid rgba(124,134,247,0.45)' : '1px solid var(--border)',
                          color: sizingMode===v ? 'var(--accent2)' : 'var(--text-soft)',
                          fontWeight: sizingMode===v ? 700 : 400,
                        }}>
                        {label}
                      </button>
                    ))}
                  </div>
                  {sizingMode === 'fixed' && (
                    <div style={{ fontSize:'0.76rem', color:'var(--text-mute)', marginTop:4 }}>
                      {t('backtest.fixedQtyDesc')}
                    </div>
                  )}
                  {sizingMode === 'all_in' && (
                    <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                      <div className="field" style={{ maxWidth:140, marginBottom:0 }}>
                        <label className="field-label">{t('backtest.leverage')}</label>
                        <input type="number" value={leverage} min="0.1" max="100" step="0.1"
                          onChange={e => setLeverage(e.target.value)} />
                      </div>
                      <div style={{ fontSize:'0.76rem', color:'var(--text-mute)', paddingTop:18 }}>
                        {t('backtest.allInDescPlain', { leverage })}
                      </div>
                    </div>
                  )}
                </div>

                {/* Commission */}
                <div>
                  <div className="field-label" style={{ marginBottom:8 }}>{t('backtest.commissionOverride')}</div>
                  <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                    <select value={commMode} onChange={e => setCommMode(e.target.value)}
                      className="inp" style={{ maxWidth:160 }}>
                      <option value="none">{t('backtest.commNone')}</option>
                      <option value="pct">{t('backtest.commPct')}</option>
                      <option value="flat">{t('backtest.commFlat')}</option>
                    </select>
                    {commMode !== 'none' && (
                      <>
                        <input type="number" value={commValue} min="0" step="0.001"
                          onChange={e => setCommValue(e.target.value)}
                          placeholder={commMode==='pct' ? '0.1' : '1.00'}
                          className="inp" style={{ maxWidth:100 }} />
                        <span style={{ fontSize:'0.8rem', color:'var(--text-mute)' }}>
                          {commMode === 'pct' ? t('backtest.pctPerFill') : t('backtest.dollarPerFill')}
                        </span>
                      </>
                    )}
                  </div>
                </div>

                {/* Share Type */}
                <div>
                  <div className="field-label" style={{ marginBottom:8 }}>{t('backtest.shareType')}</div>
                  <div style={{ display:'flex', gap:6 }}>
                    {[[false, t('backtest.stocksFutures')], [true, t('backtest.crypto')]].map(([val, label]) => (
                      <button key={String(val)} type="button"
                        onClick={() => setAllowFractional(val)}
                        style={{
                          padding:'5px 14px', borderRadius:'var(--r)', fontSize:'0.82rem',
                          cursor:'pointer', transition:'all 0.15s',
                          background: allowFractional===val ? 'rgba(124,134,247,0.12)' : 'var(--panel)',
                          border: allowFractional===val ? '1px solid rgba(124,134,247,0.45)' : '1px solid var(--border)',
                          color: allowFractional===val ? 'var(--accent2)' : 'var(--text-soft)',
                          fontWeight: allowFractional===val ? 700 : 400,
                        }}>
                        {label}
                      </button>
                    ))}
                  </div>
                  <div style={{ fontSize:'0.76rem', color:'var(--text-mute)', marginTop:4 }}>
                    {allowFractional
                      ? t('backtest.fractionalDesc')
                      : t('backtest.wholeUnitDesc')}
                  </div>
                </div>

              </div>
            )}
          </div>

          <button type="submit" className="btn btn-primary btn-pill btn-lg"
            disabled={loading || strategies.length===0}>
            {loading ? <><span className="spinner" /> {t('backtest.running')}</> : t('backtest.runBacktest')}
          </button>
        </form>

        {error && (
          <div className="alert alert-error fade-up" style={{ marginTop:14 }}>
            <span>⚠️</span><span>{error}</span>
          </div>
        )}
      </div>

      {/* ── Results ── */}
      {result && (
        <div className="card fade-up">
          {/* header row */}
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
            flexWrap:'wrap', gap:10, marginBottom:18 }}>
            <div>
              <div style={{ fontWeight:800, fontSize:'1.05rem', color:'var(--text)' }}>
                {t('backtest.results')}
              </div>
              <div style={{ fontSize:'0.76rem', color:'var(--text-mute)', marginTop:2 }}>
                {selected?.name} · {method==='api' ? ticker : file?.name}
                {result.trades > 0 && <> · {t('backtest.tradeCount', { count: result.trades })}</>}
                {fromCache === true  && <> · <span style={{ color:'#34d399' }}>{t('backtest.cachedData')}</span></>}
                {fromCache === false && <> · <span style={{ color:'#60a5fa' }}>{t('backtest.freshFetch')}</span></>}
              </div>
            </div>
            <div style={{
              display:'flex', alignItems:'center', gap:7, padding:'5px 14px',
              borderRadius:999,
              background: positive?'rgba(47,216,154,0.09)':'rgba(244,114,106,0.09)',
              border: `1px solid ${positive?'rgba(47,216,154,0.3)':'rgba(244,114,106,0.3)'}`,
            }}>
              <span>{positive?'📈':'📉'}</span>
              <span style={{ fontWeight:800, color: positive?'var(--green)':'var(--red)' }}>
                {positive?'+':''}{fmt(pnl)} ({pnlPct})
              </span>
            </div>
          </div>

          {/* stat cards */}
          <div className="grid-4" style={{ marginBottom:16 }}>
            <StatCard emoji="💰" label={t('backtest.finalValue')}    value={`$${fmt(result.total_value)}`}
              sub={t('backtest.started', { value: fmt(startCash) })} color={positive?'var(--green)':'var(--red)'} />
            <StatCard emoji="🏦" label={t('backtest.cash')}           value={`$${fmt(result.cash)}`}
              sub={t('backtest.uninvested')}    color="var(--accent)" />
            <StatCard emoji="📊" label={t('backtest.positions')}      value={`$${fmt(result.asset_value)}`}
              sub={t('backtest.marketValue')}  color="var(--accent2)" />
            <StatCard emoji={positive?'📈':'📉'} label={t('backtest.pnl')}
              value={`${positive?'+':''}$${fmt(pnl)}`}
              sub={pnlPct} color={positive?'var(--green)':'var(--red)'} />
          </div>

          {/* warnings */}
          {(result.warnings||[]).map((w,i) => (
            <div key={i} className="alert alert-warn" style={{ marginBottom:8, fontSize:'0.82rem' }}>
              ⚠️ {w}
            </div>
          ))}

          {/* positions */}
          {Object.keys(result.positions||{}).length > 0 && (
            <div style={{ marginBottom:14 }}>
              <div className="field-label" style={{ marginBottom:8 }}>{t('backtest.openPositions')}</div>
              {Object.entries(result.positions).map(([sym, qty]) => {
                const px = result.last_prices?.[sym] ?? 0
                const val = qty * px
                return (
                  <div key={sym} style={{
                    display:'flex', alignItems:'center', gap:10,
                    background:'var(--surface)', border:'1px solid var(--border)',
                    borderRadius:'var(--r)', padding:'9px 14px', marginBottom:5
                  }}>
                    <div style={{ width:30, height:30, borderRadius:'50%', fontSize:'0.72rem', fontWeight:800,
                      background:'rgba(58,183,245,0.1)', border:'1px solid rgba(58,183,245,0.25)',
                      display:'flex', alignItems:'center', justifyContent:'center', color:'var(--accent)', flexShrink:0 }}>
                      {sym.slice(0,2).toUpperCase()}
                    </div>
                    <div style={{ flex:1 }}>
                      <div style={{ fontWeight:700, fontSize:'0.88rem' }}>{sym}</div>
                      <div style={{ fontSize:'0.73rem', color:'var(--text-mute)' }}>
                        {qty > 0 ? t('backtest.long') : t('backtest.short')} {Math.abs(qty)} @ ${fmt(px)}
                      </div>
                    </div>
                    <div style={{ fontWeight:700, color: val>=0?'var(--green)':'var(--red)' }}>
                      ${fmt(Math.abs(val))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          <details>
            <summary style={{ fontSize:'0.75rem', color:'var(--text-mute)', cursor:'pointer', userSelect:'none' }}>
              {t('common.rawJson')}
            </summary>
            <pre style={{ marginTop:8 }}>{JSON.stringify(result, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  )
}