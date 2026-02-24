import { useEffect, useState } from 'react'

const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const TFS = ['1m','5m','15m','30m','1h','4h','1d','1w','1M']

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

  useEffect(() => {
    fetch(`${API}/db/strategies`).then(r=>r.json()).then(d => {
      const arr = (d.strategies||[]).map(s => ({
        ...s, config: (() => { try { return JSON.parse(s.config) } catch { return s.config } })()
      }))
      setStrategies(arr)
      if (arr.length) setSelId(arr[0].id)
    }).catch(()=>{})

    fetch(`${API}/db/api_keys`).then(r=>r.json())
      .then(d => setHasKey(!!(d.api_key?.data_key)))
      .catch(()=> setHasKey(false))
  }, [])

  const selected = strategies.find(s => s.id === selId)

  const run = async e => {
    e.preventDefault()
    setError(''); setResult(null)
    if (method==='upload' && !file)            return setError('Please select a CSV file.')
    if (method==='api' && !ticker)             return setError('Please enter a ticker symbol.')
    if (method==='api' && (!startDate||!endDate)) return setError('Please set start and end dates.')
    if (!selected)                             return setError('No strategy selected. Build one first.')
    setLoading(true)

    try {
      const form = new FormData()

      if (method === 'upload') {
        form.append('file', file)
      } else {
        // Fetch data from provider first
        const dr = await fetch(`${API}/data/fetch`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ticker, start_date: startDate, end_date: endDate, timeframe }),
        })
        if (!dr.ok) {
          const d = await dr.json().catch(()=>({}))
          throw new Error(d.detail || 'Failed to fetch market data.')
        }
        const fetched = await dr.json()
        form.append('data', JSON.stringify(fetched.rows || []))
      }

      form.append('column_map', JSON.stringify({
        time:'timestamp', bid:'bid', ask:'ask', volume:'volume', name:'symbol'
      }))
      form.append('strategies', JSON.stringify([selected]))
      form.append('starting_cash', cash || '10000')
      if (timeframe) form.append('timeframe', timeframe)

      const res = await fetch(`${API}/backtest/upload`, { method:'POST', body:form })
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

  return (
    <div className="view">
      <h2>Backtest</h2>
      <p>Run your strategy against historical data and see how it performs.</p>

      {/* API key warning */}
      {hasKey === false && method === 'api' && (
        <div className="alert alert-warn fade-up" style={{ marginBottom:14, cursor:'pointer' }}
          onClick={() => goTo?.('keys')}>
          <span>⚠️</span>
          <div>
            <strong>No data API key configured.</strong> You need a data provider key to
            fetch live market data. <span style={{textDecoration:'underline'}}>Click to set one up →</span>
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <form onSubmit={run}>

          {/* ── Strategy selector ── */}
          <div style={{ marginBottom: 18 }}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8 }}>
              <span className="field-label">Strategy</span>
              <button type="button" className="btn btn-ghost btn-sm"
                onClick={() => goTo?.('strategy')}>Manage strategies →</button>
            </div>
            {strategies.length === 0 ? (
              <div style={{ background:'rgba(124,134,247,0.07)', border:'1px dashed rgba(124,134,247,0.35)',
                borderRadius:'var(--r)', padding:'20px', textAlign:'center' }}>
                <div style={{ fontSize:'1.6rem', marginBottom:6 }}>🧩</div>
                <p style={{ color:'var(--text-mute)', margin:'0 0 10px', fontSize:'0.86rem' }}>No strategies yet.</p>
                <button type="button" className="btn btn-primary btn-sm btn-pill"
                  onClick={() => goTo?.('strategy')}>Open Strategy Builder</button>
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
                    {s.name || `Strategy ${s.id}`}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="divider" style={{ marginBottom:16 }} />

          {/* ── Data source ── */}
          <div style={{ marginBottom:16 }}>
            <div className="field-label" style={{ marginBottom:8 }}>Data Source</div>
            <div className="tab-strip" style={{ marginBottom:14, maxWidth:320 }}>
              <button type="button" className={`tab-btn${method==='upload'?' active':''}`}
                onClick={() => setMethod('upload')}>📂 Upload CSV</button>
              <button type="button" className={`tab-btn${method==='api'?' active':''}`}
                onClick={() => setMethod('api')}>🌐 Fetch from API</button>
            </div>

            {method === 'upload' ? (
              <div className="grid-2">
                <div className="field">
                  <label className="field-label">CSV File</label>
                  <label className={`upload-zone${file?' has-file':''}`}>
                    <span style={{ fontSize:'1.1rem' }}>{file ? '✅' : '📁'}</span>
                    <span style={{ fontSize:'0.84rem', color: file?'var(--green)':'var(--text-mute)' }}>
                      {file ? file.name : 'Click to select a CSV file'}
                    </span>
                    <input type="file" accept=".csv" style={{ display:'none' }}
                      onChange={e => setFile(e.target.files?.[0]||null)} />
                  </label>
                </div>
                <div className="field">
                  <label className="field-label">Timeframe</label>
                  <select value={timeframe} onChange={e=>setTimeframe(e.target.value)}>
                    <option value="">Auto-detect</option>
                    {TFS.map(t=><option key={t}>{t}</option>)}
                  </select>
                </div>
              </div>
            ) : (
              <div className="grid-auto">
                <div className="field">
                  <label className="field-label">Ticker</label>
                  <input value={ticker} onChange={e=>setTicker(e.target.value.toUpperCase())}
                    placeholder="e.g. BTCUSD, AAPL" />
                </div>
                <div className="field">
                  <label className="field-label">Start Date</label>
                  <input type="datetime-local" value={startDate} onChange={e=>setStartDate(e.target.value)} />
                </div>
                <div className="field">
                  <label className="field-label">End Date</label>
                  <input type="datetime-local" value={endDate} onChange={e=>setEndDate(e.target.value)} />
                </div>
                <div className="field">
                  <label className="field-label">Timeframe</label>
                  <select value={timeframe} onChange={e=>setTimeframe(e.target.value)}>
                    {TFS.map(t=><option key={t}>{t}</option>)}
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* ── Capital ── */}
          <div style={{ marginBottom:20, maxWidth:220 }}>
            <div className="field">
              <label className="field-label">Starting Capital ($)</label>
              <input type="number" value={cash} min="0" step="100"
                onChange={e=>setCash(e.target.value)} placeholder="10000" />
            </div>
          </div>

          <button type="submit" className="btn btn-primary btn-pill btn-lg"
            disabled={loading || strategies.length===0}>
            {loading ? <><span className="spinner" /> Running…</> : '▶  Run Backtest'}
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
                Backtest Results
              </div>
              <div style={{ fontSize:'0.76rem', color:'var(--text-mute)', marginTop:2 }}>
                {selected?.name} · {method==='api' ? ticker : file?.name}
                {result.trades > 0 && <> · {result.trades} trade{result.trades!==1?'s':''}</>}
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
            <StatCard emoji="💰" label="Final Value"    value={`$${fmt(result.total_value)}`}
              sub={`Started $${fmt(startCash)}`} color={positive?'var(--green)':'var(--red)'} />
            <StatCard emoji="🏦" label="Cash"           value={`$${fmt(result.cash)}`}
              sub="Uninvested"    color="var(--accent)" />
            <StatCard emoji="📊" label="Positions"      value={`$${fmt(result.asset_value)}`}
              sub="Market value"  color="var(--accent2)" />
            <StatCard emoji={positive?'📈':'📉'} label="P & L"
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
              <div className="field-label" style={{ marginBottom:8 }}>Open Positions</div>
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
                        {qty > 0 ? 'Long' : 'Short'} {Math.abs(qty)} @ ${fmt(px)}
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
              Raw JSON
            </summary>
            <pre style={{ marginTop:8 }}>{JSON.stringify(result, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  )
}