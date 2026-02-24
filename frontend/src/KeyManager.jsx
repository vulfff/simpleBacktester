import { useEffect, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

// Fallback client-side crypto (AES-GCM) kept for environments without backend support.
async function deriveKey(password, salt) {
  const enc = new TextEncoder()
  const baseKey = await window.crypto.subtle.importKey('raw', enc.encode(password), { name: 'PBKDF2' }, false, ['deriveKey'])
  return window.crypto.subtle.deriveKey({ name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256' }, baseKey, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
}

async function encryptText(password, plaintext) {
  const salt = window.crypto.getRandomValues(new Uint8Array(16))
  const iv = window.crypto.getRandomValues(new Uint8Array(12))
  const key = await deriveKey(password, salt)
  const enc = new TextEncoder()
  const ct = await window.crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, enc.encode(plaintext))
  const combined = new Uint8Array(salt.byteLength + iv.byteLength + ct.byteLength)
  combined.set(salt, 0)
  combined.set(iv, salt.byteLength)
  combined.set(new Uint8Array(ct), salt.byteLength + iv.byteLength)
  return btoa(String.fromCharCode(...combined))
}

async function decryptText(password, b64) {
  try {
    const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
    const salt = raw.slice(0, 16)
    const iv = raw.slice(16, 28)
    const ct = raw.slice(28)
    const key = await deriveKey(password, salt)
    const pt = await window.crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct)
    return new TextDecoder().decode(pt)
  } catch (e) {
    throw new Error('Decryption failed')
  }
}

async function backendEncrypt(password, dataKeyPlain, modelKeyPlain) {
  try {
    const res = await fetch(`${API_BASE}/keys/encrypt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password, dataKey: dataKeyPlain, modelKey: modelKeyPlain }),
    })
    if (!res.ok) throw new Error('Backend encrypt failed')
    return await res.json()
  } catch (e) {
    throw e
  }
}

async function backendDecrypt(password, encDataKey, encModelKey) {
  try {
    const res = await fetch(`${API_BASE}/keys/decrypt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password, dataKey: encDataKey, modelKey: encModelKey }),
    })
    if (!res.ok) throw new Error('Backend decrypt failed')
    return await res.json()
  } catch (e) {
    throw e
  }
}

// Supported data providers for CSV/tick data
const DATA_PROVIDERS = [
  { id: 'alpha-vantage', label: 'Alpha Vantage' },
  { id: 'yahoo-finance', label: 'Yahoo Finance' },
  { id: 'iex-cloud', label: 'IEX Cloud' },
  { id: 'polygon', label: 'Polygon.io' },
  { id: 'finnhub', label: 'Finnhub' },
]

// Supported AI models
const AI_MODELS = [
  { id: 'gpt-4', label: 'GPT-4 (OpenAI)' },
  { id: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo (OpenAI)' },
  { id: 'claude-3-opus', label: 'Claude 3 Opus (Anthropic)' },
  { id: 'claude-3-sonnet', label: 'Claude 3 Sonnet (Anthropic)' },
  { id: 'claude-3-haiku', label: 'Claude 3 Haiku (Anthropic)' },
]

function KeyManager() {
  const [dataService, setDataService] = useState('')
  const [dataKey, setDataKey] = useState('')
  const [modelName, setModelName] = useState('')
  const [modelKey, setModelKey] = useState('')
  const [protectedFlag, setProtectedFlag] = useState(false)
  const [password, setPassword] = useState('')
  const [showing, setShowing] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    // load saved api keys from DB
    fetch(`${API_BASE}/db/api_keys`)
      .then((r) => r.json())
      .then((d) => {
        if (d.api_key) {
          const a = d.api_key
          setDataService(a.service || '')
          setModelName(a.model_name || '')
          setProtectedFlag(Boolean(a.protected))
          // do not reveal keys automatically; store encoded values in state placeholders
          setDataKey(a.data_key || '')
          setModelKey(a.model_key || '')
        }
      })
      .catch(() => {})
  }, [])

  // Save keys: prefer to have backend perform encryption; fall back to client-side when unavailable.
  const saveKeys = async () => {
    setError('')
    try {
      if (protectedFlag) {
        if (!password) throw new Error('Set a password to protect keys')
        // ask backend to store encrypted values (backend will encrypt using provided password)
        const res = await fetch(`${API_BASE}/db/api_keys`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ service: dataService, model_name: modelName, dataKey: dataKey, modelKey: modelKey, protected: true, password }),
        })
        if (!res.ok) throw new Error('Failed to save keys')
      } else {
        // store base64-hidden on server
        const res = await fetch(`${API_BASE}/db/api_keys`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ service: dataService, model_name: modelName, dataKey: dataKey, modelKey: modelKey, protected: false }),
        })
        if (!res.ok) throw new Error('Failed to save keys')
      }
      setShowing(false)
      setPassword('')
      alert('Keys saved')
    } catch (e) { setError(e.message) }
  }

  const revealKeys = async () => {
    setError('')
    try {
      // fetch stored record from server
      const res = await fetch(`${API_BASE}/db/api_keys`)
      if (!res.ok) throw new Error('Failed to fetch stored keys')
      const data = await res.json()
      const rec = data.api_key
      if (!rec) { setError('No keys stored'); return }
      if (rec.protected) {
        if (!password) throw new Error('Enter password to reveal keys')
        // use backend decrypt endpoint
        try {
          const dec = await backendDecrypt(password, rec.data_key, rec.model_key)
          setDataKey(dec.dataKey || '')
          setModelKey(dec.modelKey || '')
        } catch (e) {
          // fallback to client-side decryption (if stored format matches)
          const d = await decryptText(password, rec.data_key)
          const m = await decryptText(password, rec.model_key)
          setDataKey(d)
          setModelKey(m)
        }
      } else {
        setDataKey(atob(rec.data_key || ''))
        setModelKey(atob(rec.model_key || ''))
      }
      setShowing(true)
    } catch (e) { setError(e.message) }
  }

  const hideKeys = () => {
    // clear in-memory copies but keep stored values
    setDataKey('')
    setModelKey('')
    setShowing(false)
    setPassword('')
  }

  return (
    <div className="view">
      <h2>Key Manager</h2>
      <p>Store data API key and AI model key. Optionally protect with a password.</p>

      <div className="card">
        <label className="field">
          <span>Data Provider</span>
          <select value={dataService} onChange={(e) => setDataService(e.target.value)}>
            <option value="">-- Select a data provider --</option>
            {DATA_PROVIDERS.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Data API key</span>
          <input value={dataKey} onChange={(e) => setDataKey(e.target.value)} placeholder="hidden" type={showing ? 'text' : 'password'} />
        </label>

        <label className="field">
          <span>AI Model</span>
          <select value={modelName} onChange={(e) => setModelName(e.target.value)}>
            <option value="">-- Select an AI model --</option>
            {AI_MODELS.map((model) => (
              <option key={model.id} value={model.id}>
                {model.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Model API key</span>
          <input value={modelKey} onChange={(e) => setModelKey(e.target.value)} placeholder="hidden" type={showing ? 'text' : 'password'} />
        </label>

        <label className="field">
          <input type="checkbox" checked={protectedFlag} onChange={(e) => setProtectedFlag(e.target.checked)} /> Protect keys with password
        </label>

        {protectedFlag && (
          <label className="field">
            <span>Password</span>
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
          </label>
        )}

        <div style={{display: 'flex', gap: 8}}>
          <button onClick={saveKeys} className="primary">Save Keys</button>
          {!showing ? (
            <button onClick={revealKeys}>Reveal (enter password if protected)</button>
          ) : (
            <button onClick={hideKeys}>Hide</button>
          )}
        </div>

        {error && <div className="alert error">{error}</div>}
      </div>
    </div>
  )
}

export default KeyManager
