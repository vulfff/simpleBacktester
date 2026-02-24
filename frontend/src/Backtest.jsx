import { useEffect, useMemo, useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const DEFAULT_COLUMN_MAP = {
  time: 'timestamp',
  bid: 'bid',
  ask: 'ask',
  volume: 'volume',
  name: 'symbol',
}

const DATA_METHODS = [
  { name: 'upload', label: 'Upload CSV File' },
  { name: 'api', label: 'Fetch from API' },
]

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M']

function Backtest({ goTo }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  
  // Data method selection
  const [dataMethod, setDataMethod] = useState('upload')
  
  // API fetch fields
  const [ticker, setTicker] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [timeframe, setTimeframe] = useState('1h')

  // Strategy slots loaded from backend DB (edited via Strategy Builder)
  const [selectedStrategies, setSelectedStrategies] = useState([])

  useEffect(() => {
    fetch(`${API_BASE}/db/strategies`)
      .then((r) => r.json())
      .then((d) => {
        if (d.strategies) {
          const parsed = d.strategies.map((s) => ({
            id: s.id,
            name: s.name,
            logic: s.logic,
            config: (() => {
              try { return JSON.parse(s.config) } catch { return s.config }
            })(),
          }))
          setSelectedStrategies(parsed)
          if (!selectedStrategyId && parsed.length) setSelectedStrategyId(parsed[0].id)
        }
      })
      .catch(() => {})
  }, [])

  const [columnMap, setColumnMap] = useState(
    JSON.stringify(DEFAULT_COLUMN_MAP, null, 2),
  )
  const [symbol, setSymbol] = useState('')
  const [timeFormat, setTimeFormat] = useState('')
  const [startingCash, setStartingCash] = useState('0')
  const [file, setFile] = useState(null)
  const [selectedStrategyId, setSelectedStrategyId] = useState(() => {
    try {
      const raw = localStorage.getItem('selectedStrategies')
      const arr = raw ? JSON.parse(raw) : []
      if (arr.length && arr[0]?.id) return arr[0].id
    } catch {}
    return null
  })

  const fetchDataFromAPI = async () => {
    if (!ticker) {
      setError('Please enter a ticker symbol.')
      return null
    }
    if (!startDate || !endDate) {
      setError('Please select start and end dates.')
      return null
    }

    try {
      const response = await fetch(`${API_BASE}/data/fetch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ticker,
          start_date: startDate,
          end_date: endDate,
          timeframe,
        }),
      })

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}))
        throw new Error(detail.detail || 'Failed to fetch data from API.')
      }

      const data = await response.json()
      return data
    } catch (err) {
      setError(err.message)
      return null
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setResult(null)

    // Validate based on data method
    if (dataMethod === 'upload' && !file) {
      setError('Please select a CSV file.')
      return
    }

    // Use selected strategies from DB-loaded state (managed in Strategy Builder)
    let strategiesToSend = []
    try {
      const arr = selectedStrategies || []
      if (!arr || arr.length === 0) {
        setError('No strategy slots found. Open Strategy Builder to create one.')
        return
      }
      const chosen = arr.find(s => s.id === selectedStrategyId) || arr[0]
      if (!chosen) {
        setError('No strategy selected. Open Strategy Builder to create one.')
        return
      }
      if (!chosen.name) {
        setError('Selected strategy has no type/name. Edit it in Strategy Builder.')
        return
      }
      try { JSON.parse(typeof chosen.config === 'string' ? chosen.config : JSON.stringify(chosen.config) || '{}') } catch (err) {
        setError(`Strategy config must be valid JSON for strategy ${chosen.id}.`)
        return
      }
      strategiesToSend = [chosen]
    } catch (e) { setError('Failed to load selected strategy'); return }

    let columnMapValue
    try {
      columnMapValue = JSON.parse(columnMap)
    } catch (err) {
      setError('Column map must be valid JSON.')
      return
    }

    setLoading(true)
    try {
      let backtestData

      if (dataMethod === 'api') {
        // Fetch data from API first
        backtestData = await fetchDataFromAPI()
        if (!backtestData) {
          setLoading(false)
          return
        }
      }

      const formData = new FormData()
      
      if (dataMethod === 'upload') {
        formData.append('file', file)
      } else {
        formData.append('data', JSON.stringify(backtestData))
      }
      
      formData.append('column_map', JSON.stringify(columnMapValue))
      formData.append('strategies', JSON.stringify(strategiesToSend))
      if (symbol) formData.append('symbol', symbol)
      if (timeFormat) formData.append('time_format', timeFormat)
      formData.append('starting_cash', startingCash)

      const response = await fetch(`${API_BASE}/backtest/upload`, {
        method: 'POST',
        body: formData,
      })
      
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}))
        throw new Error(detail.detail || 'Backtest failed.')
      }
      
      const data = await response.json()
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="view">
      <header className="header">
        <h2>Backtester - Run Backtest</h2>
        <p>Use the Strategy Builder to manage strategies.</p>
      </header>

      <form className="card" onSubmit={handleSubmit}>
        <div className="grid">
          <label className="field">
            <span>Strategy</span>
            <select
              value={selectedStrategyId ?? ''}
              onChange={(e) => setSelectedStrategyId(Number(e.target.value) || null)}
              onFocus={async () => {
                // ensure latest slots from DB; if no valid named strategies, redirect to builder
                try {
                  const res = await fetch(`${API_BASE}/db/strategies`)
                  const data = await res.json()
                  const arr = data.strategies || []
                  const hasNamed = arr.some(s => s && s.name)
                  if (!hasNamed && typeof goTo === 'function') goTo('strategy')
                  else setSelectedStrategies(arr.map(s => ({ id: s.id, name: s.name, logic: s.logic, config: (() => { try { return JSON.parse(s.config) } catch { return s.config } })() })))
                } catch {
                  if (typeof goTo === 'function') goTo('strategy')
                }
              }}
            >
              <option value="">Choose strategy (click to manage)</option>
              {selectedStrategies.map((s) => (
                <option key={s.id} value={s.id}>{s.name || `(slot ${s.id})`}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="grid">
          <label className="field">
            <span>Data Source</span>
            <select
              value={dataMethod}
              onChange={(e) => setDataMethod(e.target.value)}
            >
              {DATA_METHODS.map((method) => (
                <option key={method.name} value={method.name}>
                  {method.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="data-method-container">
          <div className="grid">
            {dataMethod === 'upload' ? (
              <>
                <label className="field">
                  <span>CSV File</span>
                  <input
                    type="file"
                    accept=".csv"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                  />
                </label>

                <label className="field">
                  <span>Symbol override (optional)</span>
                  <input
                    type="text"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    placeholder="BTCUSD"
                  />
                </label>

                <label className="field">
                  <span>Time format (optional)</span>
                  <input
                    type="text"
                    value={timeFormat}
                    onChange={(e) => setTimeFormat(e.target.value)}
                    placeholder="%Y-%m-%d %H:%M:%S"
                  />
                </label>

                <label className="field">
                  <span>Timeframe (optional)</span>
                  <select
                    value={timeframe}
                    onChange={(e) => setTimeframe(e.target.value)}
                  >
                    <option value="">Select timeframe</option>
                    {TIMEFRAMES.map((tf) => (
                      <option key={tf} value={tf}>
                        {tf}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : (
              <>
                <label className="field">
                  <span>Ticker Symbol</span>
                  <input
                    type="text"
                    value={ticker}
                    onChange={(e) => setTicker(e.target.value)}
                    placeholder="BTCUSD"
                    required
                  />
                </label>

                <label className="field">
                  <span>Start Date</span>
                  <input
                    type="datetime-local"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    required
                  />
                </label>

                <label className="field">
                  <span>End Date</span>
                  <input
                    type="datetime-local"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    required
                  />
                </label>

                <label className="field">
                  <span>Timeframe</span>
                  <select
                    value={timeframe}
                    onChange={(e) => setTimeframe(e.target.value)}
                  >
                    {TIMEFRAMES.map((tf) => (
                      <option key={tf} value={tf}>
                        {tf}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
          </div>
        </div>

        <div className="grid">
          <label className="field">
            <span>Starting cash</span>
            <input
              type="number"
              value={startingCash}
              onChange={(e) => setStartingCash(e.target.value)}
              min="0"
              step="0.01"
            />
          </label>
        </div>

        <div className="two-column">
          {dataMethod === 'upload' && (
            <label className="field">
              <span>Column map (JSON)</span>
              <textarea
                value={columnMap}
                onChange={(e) => setColumnMap(e.target.value)}
                rows={10}
              />
            </label>
          )}
        </div>

        <button className="primary" type="submit" disabled={loading}>
          {loading ? 'Running...' : 'Run backtest'}
        </button>
      </form>

      {error && <div className="alert error">{error}</div>}

      {result && (
        <div className="card result">
          <h2>Result</h2>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}

export default Backtest
