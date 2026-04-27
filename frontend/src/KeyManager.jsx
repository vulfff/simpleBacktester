import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

const API_BASE = import.meta.env.VITE_API_BASE || '';

// ── Provider / model metadata ─────────────────────────────────────────────────

const DATA_PROVIDERS = [
  { id: 'massive',       label: 'Massive',        assets: 'Stocks · Crypto · Forex · Options', rateLimits: '5 req/min free · Unlimited paid', tier: 'Free + Paid', keyHint: 'Alphanumeric key from dashboard', url: 'https://massive.com/dashboard', desc: 'Comprehensive market data. Free key on sign-up — no credit card.' },
  { id: 'alpha-vantage', label: 'Alpha Vantage',  assets: 'Stocks · Forex · Crypto',           rateLimits: '25 req/day free · 500+/min paid',  tier: 'Free + Paid', keyHint: 'Alphanumeric key',                url: 'https://www.alphavantage.co/support/#api-key', desc: 'Solid free tier for US stocks, forex and crypto.' },
  { id: 'polygon',       label: 'Polygon.io',     assets: 'Stocks · Options · Crypto · Forex', rateLimits: '5 req/min free · Unlimited paid',  tier: 'Free + Paid', keyHint: 'Alphanumeric key',                url: 'https://polygon.io/dashboard/signup', desc: 'Deep US market data. Rebranded to Massive (see above).' },
  { id: 'finnhub',       label: 'Finnhub',        assets: 'Stocks · Forex · Crypto',           rateLimits: '60 req/min free',                  tier: 'Free + Paid', keyHint: 'Alphanumeric key from dashboard', url: 'https://finnhub.io/register', desc: 'Real-time & historical data plus fundamentals.' },
  { id: 'iex-cloud',     label: 'IEX Cloud',      assets: 'Stocks · ETFs',                     rateLimits: '500K messages/mo free',            tier: 'Free + Paid', keyHint: 'Starts with pk_ or sk_',          url: 'https://iexcloud.io/cloud-login#/register', desc: 'High-quality US equity data.' },
];

const AI_MODELS = [
  // Anthropic — verified from official SDK (Apr 2026)
  { id: 'claude-opus-4-7',              label: 'Claude Opus 4.7',            provider: 'anthropic', providerLabel: 'Anthropic', desc: 'Most capable Anthropic model. Best for complex reasoning and agentic coding.',  keyHint: 'Starts with sk-ant-', url: 'https://console.anthropic.com/' },
  { id: 'claude-sonnet-4-6',            label: 'Claude Sonnet 4.6',          provider: 'anthropic', providerLabel: 'Anthropic', desc: 'Best speed/intelligence balance. Recommended for most tasks.',                  keyHint: 'Starts with sk-ant-', url: 'https://console.anthropic.com/' },
  { id: 'claude-haiku-4-5-20251001',    label: 'Claude Haiku 4.5',           provider: 'anthropic', providerLabel: 'Anthropic', desc: 'Fastest Anthropic model with near-frontier intelligence.',                      keyHint: 'Starts with sk-ant-', url: 'https://console.anthropic.com/' },
  { id: 'claude-opus-4-6',              label: 'Claude Opus 4.6',            provider: 'anthropic', providerLabel: 'Anthropic', desc: 'Previous Opus. Still highly capable.',                                          keyHint: 'Starts with sk-ant-', url: 'https://console.anthropic.com/' },
  { id: 'claude-sonnet-4-5-20250929',   label: 'Claude Sonnet 4.5',          provider: 'anthropic', providerLabel: 'Anthropic', desc: 'Previous Sonnet. Fast and reliable.',                                           keyHint: 'Starts with sk-ant-', url: 'https://console.anthropic.com/' },
  // OpenAI — verified from official openai-python SDK (Apr 2026)
  { id: 'gpt-5.4',                      label: 'GPT-5.4',                    provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Latest OpenAI flagship. Highest capability.',                                   keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'gpt-5.4-mini',                 label: 'GPT-5.4 Mini',               provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Affordable GPT-5.4 variant. Great speed/cost ratio.',                          keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'gpt-5.4-nano',                 label: 'GPT-5.4 Nano',               provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Cheapest GPT-5.4. Best for high-volume tasks.',                                 keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'gpt-5',                        label: 'GPT-5',                      provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Stable GPT-5 generation. Strong all-round performance.',                        keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'gpt-5-mini',                   label: 'GPT-5 Mini',                 provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Affordable GPT-5. Good for most strategy tasks.',                               keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'gpt-4.1',                      label: 'GPT-4.1',                    provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Reliable GPT-4.1 series. Proven for instruction following.',                    keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'gpt-4.1-mini',                 label: 'GPT-4.1 Mini',               provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Fast and affordable GPT-4.1 variant.',                                          keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'gpt-4o',                       label: 'GPT-4o',                     provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Multimodal model. Still widely used.',                                          keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'o4-mini',                      label: 'o4-mini',                    provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Best reasoning per dollar. Great for complex analysis.',                        keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'o3',                           label: 'o3',                         provider: 'openai',    providerLabel: 'OpenAI',    desc: 'OpenAI o3 reasoning model.',                                                    keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'o3-mini',                      label: 'o3-mini',                    provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Efficient o3 reasoning model.',                                                 keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  // xAI — verified from LiteLLM source + xAI docs (Apr 2026)
  { id: 'grok-4',                       label: 'Grok-4',                     provider: 'grok',      providerLabel: 'xAI',       desc: 'xAI Grok-4 flagship model.',                                                    keyHint: 'Starts with xai-',    url: 'https://console.x.ai' },
  { id: 'grok-4-1-fast-non-reasoning',  label: 'Grok-4.1 Fast',              provider: 'grok',      providerLabel: 'xAI',       desc: 'Fast Grok-4.1 for agentic tasks. 2M context window.',                          keyHint: 'Starts with xai-',    url: 'https://console.x.ai' },
  { id: 'grok-4-1-fast-reasoning',      label: 'Grok-4.1 Fast (Reasoning)',  provider: 'grok',      providerLabel: 'xAI',       desc: 'Grok-4.1 with reasoning. Best for complex analysis tasks.',                    keyHint: 'Starts with xai-',    url: 'https://console.x.ai' },
  { id: 'grok-3',                       label: 'Grok-3',                     provider: 'grok',      providerLabel: 'xAI',       desc: 'Previous Grok generation. Stable and well-tested.',                             keyHint: 'Starts with xai-',    url: 'https://console.x.ai' },
  { id: 'grok-3-mini',                  label: 'Grok-3 Mini',                provider: 'grok',      providerLabel: 'xAI',       desc: 'Lightweight Grok-3 variant.',                                                   keyHint: 'Starts with xai-',    url: 'https://console.x.ai' },
  // Google — verified from official Gemini API docs (Apr 2026)
  { id: 'gemini-3.1-pro-preview',       label: 'Gemini 3.1 Pro (Preview)',   provider: 'gemini',    providerLabel: 'Google',    desc: 'Latest Gemini. Advanced reasoning and agentic capabilities.',                   keyHint: 'Starts with AIza',    url: 'https://aistudio.google.com/app/apikey' },
  { id: 'gemini-3-flash-preview',       label: 'Gemini 3 Flash (Preview)',   provider: 'gemini',    providerLabel: 'Google',    desc: 'Frontier performance at lower cost.',                                            keyHint: 'Starts with AIza',    url: 'https://aistudio.google.com/app/apikey' },
  { id: 'gemini-3.1-flash-lite-preview',label: 'Gemini 3.1 Flash Lite (Preview)', provider: 'gemini', providerLabel: 'Google', desc: 'Fast and budget-friendly Gemini 3.',                                            keyHint: 'Starts with AIza',    url: 'https://aistudio.google.com/app/apikey' },
  { id: 'gemini-2.5-pro',               label: 'Gemini 2.5 Pro',             provider: 'gemini',    providerLabel: 'Google',    desc: 'Stable, most advanced Gemini 2.5. Best price-performance for reasoning.',      keyHint: 'Starts with AIza',    url: 'https://aistudio.google.com/app/apikey' },
  { id: 'gemini-2.5-flash',             label: 'Gemini 2.5 Flash',           provider: 'gemini',    providerLabel: 'Google',    desc: 'Stable fast Gemini 2.5. Best for most tasks.',                                  keyHint: 'Starts with AIza',    url: 'https://aistudio.google.com/app/apikey' },
  { id: 'gemini-2.5-flash-lite',        label: 'Gemini 2.5 Flash Lite',      provider: 'gemini',    providerLabel: 'Google',    desc: 'Fastest and cheapest stable Gemini.',                                           keyHint: 'Starts with AIza',    url: 'https://aistudio.google.com/app/apikey' },
];

const PROVIDER_COLORS = { anthropic: '#f59e0b', openai: '#10b981', grok: '#8b5cf6', gemini: '#3b82f6' };

/** Infer AI provider from API key prefix. Returns null if unrecognised. */
function inferProviderFromKey(key) {
  const k = key.trim();
  if (k.startsWith('sk-ant-'))  return 'anthropic'; // must precede 'sk-' check
  if (k.startsWith('xai-'))     return 'grok';
  if (k.startsWith('AIza'))     return 'gemini';
  if (k.startsWith('sk-'))      return 'openai';
  return null;
}

const sStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '8px 12px', color: '#e5e7eb', fontSize: '0.88rem', width: '100%', outline: 'none' };
const iStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '8px 12px', color: '#e5e7eb', fontSize: '0.88rem', width: '100%', outline: 'none', fontFamily: 'ui-monospace, monospace' };

// ── Shared sub-components ─────────────────────────────────────────────────────

function ActiveDot({ active }) {
  return (
    <span style={{
      width: 8, height: 8, borderRadius: '50%', flexShrink: 0, marginTop: 1,
      background: active ? '#34d399' : '#334155',
      boxShadow: active ? '0 0 6px rgba(52,211,153,0.6)' : 'none',
    }} />
  );
}

function KeyRow({ label, sublabel, active, protected: isProtected, onActivate, onDelete }) {
  const { t } = useTranslation()
  const [confirmDel, setConfirmDel] = useState(false);
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
      background: active ? 'rgba(52,211,153,0.05)' : '#0b1120',
      border: `1px solid ${active ? 'rgba(52,211,153,0.25)' : '#1e293b'}`,
      borderRadius: 8, marginBottom: 6,
    }}>
      <ActiveDot active={active} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: '0.87rem', fontWeight: 600, color: active ? '#e2e8f0' : '#94a3b8' }}>{label}</span>
          {isProtected ? (
            <span style={{ fontSize: '0.62rem', fontWeight: 700, padding: '1px 6px', borderRadius: 999,
              background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#f87171' }}>
              PW
            </span>
          ) : (
            <span style={{ fontSize: '0.62rem', fontWeight: 700, padding: '1px 6px', borderRadius: 999,
              background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.3)', color: '#a5b4fc' }}>
              OS
            </span>
          )}
        </div>
        {sublabel && <div style={{ fontSize: '0.72rem', color: '#4b5563', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sublabel}</div>}
      </div>
      {active ? (
        <span style={{ fontSize: '0.68rem', fontWeight: 700, padding: '2px 8px', borderRadius: 999,
          background: 'rgba(52,211,153,0.12)', border: '1px solid rgba(52,211,153,0.3)', color: '#34d399' }}>
          {t('common.active')}
        </span>
      ) : (
        <button onClick={onActivate}
          style={{ fontSize: '0.75rem', background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)',
            borderRadius: 6, color: '#93c5fd', cursor: 'pointer', padding: '3px 10px', whiteSpace: 'nowrap' }}>
          {t('common.useThis')}
        </button>
      )}
      {confirmDel ? (
        <>
          <button onClick={onDelete}
            style={{ fontSize: '0.72rem', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)',
              borderRadius: 6, color: '#f87171', cursor: 'pointer', padding: '3px 8px' }}>{t('common.confirm')}</button>
          <button onClick={() => setConfirmDel(false)}
            style={{ fontSize: '0.72rem', background: 'transparent', border: '1px solid #334155',
              borderRadius: 6, color: '#6b7280', cursor: 'pointer', padding: '3px 8px' }}>{t('common.cancel')}</button>
        </>
      ) : (
        <button onClick={() => setConfirmDel(true)}
          style={{ fontSize: '0.72rem', background: 'transparent', border: '1px solid #1e293b',
            borderRadius: 6, color: '#4b5563', cursor: 'pointer', padding: '3px 8px', lineHeight: 1 }}>×</button>
      )}
    </div>
  );
}

// ── Data Provider panel ───────────────────────────────────────────────────────

function DataProviderPanel() {
  const { t } = useTranslation();
  const [keys, setKeys]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [service, setService]   = useState('');
  const [apiKey, setApiKey]     = useState('');
  const [label, setLabel]       = useState('');
  const [protect, setProtect]   = useState(false);
  const [password, setPassword] = useState('');
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState('');

  const load = () => {
    setLoading(true);
    fetch(`${API_BASE}/api/db/data-keys`)
      .then(r => r.json())
      .then(d => setKeys(d.keys || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const provider = DATA_PROVIDERS.find(p => p.id === service);

  const save = async () => {
    if (!service) { setError(t('keys.chooseProvider')); return; }
    if (!apiKey) { setError(t('keys.pasteKey')); return; }
    setError(''); setSaving(true);
    try {
      const r = await fetch(`${API_BASE}/api/db/data-keys`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service, key: apiKey, protected: protect, password: protect ? password : undefined, label, activate: true }),
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Save failed'); }
      setApiKey(''); setLabel(''); setService(''); setProtect(false); setPassword('');
      load();
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const activate = async id => {
    try {
      const r = await fetch(`${API_BASE}/api/db/data-keys/${id}/activate`, { method: 'POST' });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Activate failed'); }
      load();
    } catch (e) { setError(e.message); }
  };

  const remove = async id => {
    try {
      const r = await fetch(`${API_BASE}/api/db/data-keys/${id}`, { method: 'DELETE' });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Delete failed'); }
      load();
    } catch (e) { setError(e.message); }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#e5e7eb' }}>{t('keys.dataProvidersTitle')}</h3>
        <span style={{ fontSize: '0.72rem', color: '#4b5563' }}>{t('keys.saved', { count: keys.length })}</span>
      </div>
      <p style={{ fontSize: '0.83rem', color: '#6b7280', margin: '0 0 16px' }}>
        {t('keys.dataProvidersDesc')}
      </p>

      {/* Saved key list */}
      {loading ? (
        <div style={{ color: '#4b5563', fontSize: '0.83rem', padding: '12px 0' }}>{t('common.loading')}</div>
      ) : keys.length === 0 ? (
        <div style={{ color: '#4b5563', fontSize: '0.83rem', padding: '10px 14px', background: '#0b1120', borderRadius: 8, marginBottom: 16, border: '1px dashed #1e293b' }}>
          {t('keys.noDataKeys')}
        </div>
      ) : (
        <div style={{ marginBottom: 16 }}>
          {keys.map(k => {
            const meta = DATA_PROVIDERS.find(p => p.id === k.service);
            return (
              <KeyRow key={k.id}
                label={meta?.label || k.service}
                sublabel={k.label || meta?.assets}
                active={!!k.active}
                protected={!!k.protected}
                onActivate={() => activate(k.id)}
                onDelete={() => remove(k.id)} />
            );
          })}
        </div>
      )}

      {/* Add new key form */}
      <div style={{ background: '#0b1120', border: '1px solid #1e293b', borderRadius: 10, padding: '14px' }}>
        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#6b7280', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t('keys.addNew')}</div>

        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>{t('keys.provider')}</label>
          <select value={service} style={sStyle} onChange={e => setService(e.target.value)}>
            <option value="">{t('keys.selectProvider')}</option>
            {DATA_PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
          {provider && (
            <div style={{ marginTop: 6, fontSize: '0.75rem', color: '#6b7280', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <span>📊 {provider.assets}</span>
              <span>⚡ {provider.rateLimits}</span>
              {provider.url && (
                <a href={provider.url} target="_blank" rel="noopener noreferrer"
                  style={{ color: '#22d3ee', textDecoration: 'none' }}>{t('keys.getKey')}</a>
              )}
            </div>
          )}
        </div>

        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>{t('keys.apiKey')}</label>
          <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
            style={iStyle} placeholder={provider?.keyHint || t('keys.pasteApiKey')} autoComplete="off" />
        </div>

        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>{t('keys.label')} <span style={{ fontWeight: 400, color: '#4b5563' }}>{t('keys.labelOptional')}</span></label>
          <input value={label} onChange={e => setLabel(e.target.value)}
            style={sStyle} placeholder={t('keys.labelPlaceholder')} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: protect ? 10 : 14 }}>
          <input type="checkbox" id="dp-protect" checked={protect} onChange={e => setProtect(e.target.checked)} style={{ cursor: 'pointer' }} />
          <label htmlFor="dp-protect" style={{ fontSize: '0.83rem', color: '#9ca3af', cursor: 'pointer' }}>{t('keys.encryptWithPassword')}</label>
        </div>
        {protect && (
          <div style={{ marginBottom: 14 }}>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              style={iStyle} placeholder={t('keys.choosePassword')} />
          </div>
        )}

        {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 7, padding: '7px 12px', color: '#fca5a5', fontSize: '0.82rem', marginBottom: 10 }}>{error}</div>}

        <button onClick={save} disabled={saving}
          style={{ background: saving ? '#1e293b' : 'linear-gradient(135deg,#6366f1,#22d3ee)', border: 'none', borderRadius: 999, padding: '8px 20px', color: '#0f172a', fontWeight: 700, cursor: saving ? 'not-allowed' : 'pointer', fontSize: '0.87rem', opacity: saving ? 0.7 : 1 }}>
          {saving ? t('common.saving') : t('keys.saveAndActivate')}
        </button>
      </div>
    </div>
  );
}

// ── AI Model panel ────────────────────────────────────────────────────────────

function AIModelPanel() {
  const { t } = useTranslation();
  const [keys, setKeys]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [modelName, setModelName] = useState('');
  const [apiKey, setApiKey]     = useState('');
  const [label, setLabel]       = useState('');
  const [protect, setProtect]   = useState(false);
  const [password, setPassword] = useState('');
  const [saving, setSaving]           = useState(false);
  const [error, setError]             = useState('');
  const [detectedProvider, setDetectedProvider] = useState(null);
  const [fetchedModels, setFetchedModels]       = useState([]);
  const [fetching, setFetching]                 = useState(false);
  const [fetchError, setFetchError]             = useState('');
  const [customModelId, setCustomModelId]       = useState('');

  const load = () => {
    setLoading(true);
    fetch(`${API_BASE}/api/db/model-keys`)
      .then(r => r.json())
      .then(d => setKeys(d.keys || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const selectedModel = AI_MODELS.find(m => m.id === modelName);

  // Group models by provider for <optgroup>
  const byProvider = AI_MODELS.reduce((acc, m) => {
    (acc[m.providerLabel] = acc[m.providerLabel] || []).push(m);
    return acc;
  }, {});

  const effectiveModelName = modelName === '__custom__' ? customModelId.trim() : modelName;

  const save = async () => {
    if (!modelName) { setError(t('keys.chooseModel')); return; }
    if (modelName === '__custom__' && !customModelId.trim()) { setError(t('keys.enterCustomModel')); return; }
    if (!apiKey) { setError(t('keys.pasteKey')); return; }
    const knownModel = AI_MODELS.find(m => m.id === effectiveModelName);
    const providerToSave = knownModel?.provider || detectedProvider || '';
    if (!providerToSave) { setError('Could not detect provider from API key prefix. Paste your key first.'); return; }
    // validate that key provider matches selected model provider (only for known models)
    if (knownModel?.provider && detectedProvider && knownModel.provider !== detectedProvider) {
      setError(t('keys.providerMismatch', { model: effectiveModelName, expected: knownModel.providerLabel, detected: detectedProvider }));
      return;
    }
    setError(''); setSaving(true);
    try {
      const r = await fetch(`${API_BASE}/api/db/model-keys`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: effectiveModelName, provider: providerToSave, key: apiKey, protected: protect, password: protect ? password : undefined, label, activate: true }),
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Save failed'); }
      setApiKey(''); setLabel(''); setModelName(''); setProtect(false); setPassword('');
      setDetectedProvider(null); setFetchedModels([]); setFetchError(''); setCustomModelId('');
      load();
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const activate = async id => {
    try {
      const r = await fetch(`${API_BASE}/api/db/model-keys/${id}/activate`, { method: 'POST' });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Activate failed'); }
      load();
    } catch (e) { setError(e.message); }
  };

  const remove = async id => {
    try {
      const r = await fetch(`${API_BASE}/api/db/model-keys/${id}`, { method: 'DELETE' });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Delete failed'); }
      load();
    } catch (e) { setError(e.message); }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#e5e7eb' }}>{t('keys.aiModelsTitle')}</h3>
        <span style={{ fontSize: '0.72rem', color: '#4b5563' }}>{t('keys.saved', { count: keys.length })}</span>
      </div>
      <p style={{ fontSize: '0.83rem', color: '#6b7280', margin: '0 0 16px' }}>
        {t('keys.aiModelsDesc')}
      </p>

      {/* Saved key list */}
      {loading ? (
        <div style={{ color: '#4b5563', fontSize: '0.83rem', padding: '12px 0' }}>{t('common.loading')}</div>
      ) : keys.length === 0 ? (
        <div style={{ color: '#4b5563', fontSize: '0.83rem', padding: '10px 14px', background: '#0b1120', borderRadius: 8, marginBottom: 16, border: '1px dashed #1e293b' }}>
          {t('keys.noAiKeys')}
        </div>
      ) : (
        <div style={{ marginBottom: 16 }}>
          {keys.map(k => {
            const meta = AI_MODELS.find(m => m.id === k.model_name);
            const provColor = PROVIDER_COLORS[k.provider] || '#6b7280';
            return (
              <KeyRow key={k.id}
                label={meta?.label || k.model_name}
                sublabel={
                  <span>
                    {k.label ? <>{k.label} · </> : null}
                    <span style={{ color: provColor }}>{meta?.providerLabel || k.provider}</span>
                  </span>
                }
                active={!!k.active}
                protected={!!k.protected}
                onActivate={() => activate(k.id)}
                onDelete={() => remove(k.id)} />
            );
          })}
        </div>
      )}

      {/* Add new key form */}
      <div style={{ background: '#0b1120', border: '1px solid #1e293b', borderRadius: 10, padding: '14px' }}>
        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#6b7280', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t('keys.addNew')}</div>

        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>{t('keys.model')}</label>
          <select value={modelName} style={sStyle} onChange={e => { setModelName(e.target.value); setCustomModelId(''); }}>
            <option value="">{t('keys.selectModel')}</option>
            {Object.entries(byProvider).map(([prov, models]) => (
              <optgroup key={prov} label={prov}>
                {models.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
              </optgroup>
            ))}
            <option value="__custom__">— Enter custom model ID —</option>
          </select>
          {modelName === '__custom__' && (
            <div style={{ marginTop: 8 }}>
              <input
                value={customModelId}
                onChange={e => setCustomModelId(e.target.value)}
                style={{ ...iStyle, fontFamily: 'ui-monospace, monospace' }}
                placeholder="e.g. gpt-5, claude-opus-5-0, grok-4 …"
                autoComplete="off"
              />
              <div style={{ marginTop: 4, fontSize: '0.72rem', color: '#4b5563' }}>
                Provider will be inferred from the API key prefix you paste below.
              </div>
            </div>
          )}
          {selectedModel && (
            <div style={{ marginTop: 6, fontSize: '0.75rem', color: '#6b7280', display: 'flex', gap: 10, alignItems: 'center' }}>
              <span style={{ color: PROVIDER_COLORS[selectedModel.provider] || '#6b7280', fontWeight: 600 }}>{selectedModel.providerLabel}</span>
              <span>{selectedModel.desc}</span>
              <a href={selectedModel.url} target="_blank" rel="noopener noreferrer"
                style={{ color: '#a78bfa', textDecoration: 'none', whiteSpace: 'nowrap' }}>{t('keys.getKey')}</a>
            </div>
          )}
        </div>

        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>{t('keys.apiKey')}</label>
          <input type="password" value={apiKey}
            onChange={e => {
              const val = e.target.value;
              setApiKey(val);
              const inferred = inferProviderFromKey(val);
              setDetectedProvider(inferred);
              setFetchedModels([]);
              setFetchError('');
            }}
            style={iStyle} placeholder={selectedModel?.keyHint || t('keys.pasteApiKeyAutoDetect')} autoComplete="off" />
        </div>

        {/* Auto-detected provider + fetch button */}
        {detectedProvider && !fetchedModels.length && (
          <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{
              fontSize: '0.74rem', padding: '2px 10px', borderRadius: 999,
              background: `${PROVIDER_COLORS[detectedProvider]}22`,
              border: `1px solid ${PROVIDER_COLORS[detectedProvider]}55`,
              color: PROVIDER_COLORS[detectedProvider], fontWeight: 600,
            }}>
              {t('keys.keyDetected', { provider: detectedProvider.charAt(0).toUpperCase() + detectedProvider.slice(1) })}
            </span>
            <button
              onClick={async () => {
                setFetching(true); setFetchError('');
                try {
                  const r = await fetch(`${API_BASE}/api/ai/list-models`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ provider: detectedProvider, api_key: apiKey }),
                  });
                  const d = await r.json();
                  if (!r.ok) throw new Error(d.detail || 'Fetch failed');
                  setFetchedModels(d.models || []);
                } catch (e) { setFetchError(e.message); }
                finally { setFetching(false); }
              }}
              disabled={fetching}
              style={{
                fontSize: '0.74rem', background: 'rgba(99,102,241,0.1)',
                border: '1px solid rgba(99,102,241,0.35)', borderRadius: 6,
                color: '#a5b4fc', cursor: fetching ? 'not-allowed' : 'pointer',
                padding: '3px 12px', opacity: fetching ? 0.6 : 1,
              }}>
              {fetching ? t('keys.fetchingModels') : t('keys.fetchModels')}
            </button>
            {fetchError && <span style={{ fontSize: '0.72rem', color: '#f87171' }}>{fetchError}</span>}
          </div>
        )}

        {/* Live model list fetched from provider API */}
        {fetchedModels.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>
              {t('keys.modelsOnAccount')} <span style={{ fontWeight: 400, color: '#4b5563' }}>{t('keys.modelsFound', { count: fetchedModels.length })}</span>
            </label>
            <select value={modelName} style={sStyle} onChange={e => { setModelName(e.target.value); setCustomModelId(''); }}>
              <option value="">{t('keys.selectAModel')}</option>
              {fetchedModels.map(id => {
                const known = AI_MODELS.find(m => m.id === id);
                return <option key={id} value={id}>{known ? known.label : id}</option>;
              })}
              <option value="__custom__">— Enter custom model ID —</option>
            </select>
            <div style={{ marginTop: 4, fontSize: '0.72rem', color: '#4b5563' }}>
              {t('keys.fetchedLive')}
            </div>
          </div>
        )}

        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>{t('keys.label')} <span style={{ fontWeight: 400, color: '#4b5563' }}>{t('keys.labelOptional')}</span></label>
          <input value={label} onChange={e => setLabel(e.target.value)}
            style={sStyle} placeholder={t('keys.labelPlaceholder')} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: protect ? 10 : 14 }}>
          <input type="checkbox" id="ai-protect" checked={protect} onChange={e => setProtect(e.target.checked)} style={{ cursor: 'pointer' }} />
          <label htmlFor="ai-protect" style={{ fontSize: '0.83rem', color: '#9ca3af', cursor: 'pointer' }}>{t('keys.encryptWithPassword')}</label>
        </div>
        {protect && (
          <div style={{ marginBottom: 14 }}>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              style={iStyle} placeholder={t('keys.choosePassword')} />
          </div>
        )}

        {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 7, padding: '7px 12px', color: '#fca5a5', fontSize: '0.82rem', marginBottom: 10 }}>{error}</div>}

        <button onClick={save} disabled={saving}
          style={{ background: saving ? '#1e293b' : 'linear-gradient(135deg,#a78bfa,#22d3ee)', border: 'none', borderRadius: 999, padding: '8px 20px', color: '#0f172a', fontWeight: 700, cursor: saving ? 'not-allowed' : 'pointer', fontSize: '0.87rem', opacity: saving ? 0.7 : 1 }}>
          {saving ? t('common.saving') : t('keys.saveAndActivate')}
        </button>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function KeyManager() {
  const { t } = useTranslation();
  const [tab, setTab] = useState('data');

  const tabs = [
    { id: 'data', label: t('keys.dataProviders'), desc: t('keys.forMarketData') },
    { id: 'ai',   label: t('keys.aiModels'),      desc: t('keys.forAiFeatures') },
  ];

  return (
    <div className="view">
      <h2>{t('keys.title')}</h2>
      <p>{t('keys.subtitle')}</p>

      <div style={{ display: 'flex', gap: 10, margin: '1.5rem 0', background: '#0f172a', padding: 6, borderRadius: 14, border: '1px solid #1f2937', width: 'fit-content' }}>
        {tabs.map(tb => (
          <button key={tb.id} onClick={() => setTab(tb.id)}
            style={{
              background: tab === tb.id ? '#1e293b' : 'transparent',
              border: tab === tb.id ? '1px solid #334155' : '1px solid transparent',
              borderRadius: 10, padding: '8px 18px', cursor: 'pointer',
              color: tab === tb.id ? '#e5e7eb' : '#6b7280', fontSize: '0.87rem', fontWeight: tab === tb.id ? 700 : 400,
              transition: 'all 0.2s',
            }}>
            {tb.label}
            <div style={{ fontSize: '0.67rem', color: tab === tb.id ? '#9ca3af' : '#4b5563', fontWeight: 400 }}>{tb.desc}</div>
          </button>
        ))}
      </div>

      <div style={{ background: '#111827', border: '1px solid #1f2937', borderRadius: 16, padding: '1.5rem', maxWidth: 580 }}>
        {tab === 'data' && <DataProviderPanel />}
        {tab === 'ai'   && <AIModelPanel />}
      </div>
    </div>
  );
}
