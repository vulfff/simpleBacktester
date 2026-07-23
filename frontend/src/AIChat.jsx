import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

const API_BASE = import.meta.env.VITE_API_BASE || '';

const STRATEGY_ACCENT = {
  solid: '#5f9fd6',
  badgeBg: 'rgba(95,159,214,0.15)',
  badgeBorder: 'rgba(95,159,214,0.3)',
  badgeText: '#a8cbe8',
  dataText: '#a8cbe8',
};

const INDICATOR_ACCENT = {
  solid: '#9678d8',
  badgeBg: 'rgba(150,120,216,0.15)',
  badgeBorder: 'rgba(150,120,216,0.3)',
  badgeText: '#c5b8ec',
  dataText: '#d4c9f0',
};

/**
 * Generic AI chat panel shared by the AI Strategy Builder and AI Indicator Builder.
 * All variant-specific behavior (endpoint, colors, i18n keys, request body, result
 * rendering) is supplied via props so each caller stays pixel/flow-identical to its
 * pre-merge standalone component.
 *
 * Props:
 * - endpoint: string - API path (relative to API_BASE) to POST the prompt to.
 * - accent: { solid, badgeBg, badgeBorder, badgeText, dataText } - variant color tokens.
 * - i18nPrefix: string - translation key namespace, e.g. 'aiStrategy'.
 * - headerEmoji: string - emoji shown in the header.
 * - showTemperature: bool - render the creativity/temperature slider in the header.
 * - showWarnings: bool - render a warnings bubble when result.warnings is non-empty.
 * - trackError: bool - also surface caught errors via the inline error banner.
 * - loadingKey: string - i18nPrefix-relative key for the spinner label.
 * - defaultErrorMessage: string - fallback error text when the API gives none.
 * - buildBody(prompt, temperature, lang): object - builds the POST body.
 * - resultMessageParams(result): object - i18next interpolation params for `${i18nPrefix}.generatedResult`.
 * - renderData(msg, t): node - renders the inline result preview under a message bubble.
 * - onResult(result): void - called with the parsed result on success.
 * - welcomeHint(t): Promise<string|null> - optional hook to append text to the welcome message on mount.
 */
export function AIChat({
  endpoint,
  accent,
  i18nPrefix,
  headerEmoji,
  showTemperature = false,
  showWarnings = false,
  trackError = false,
  loadingKey,
  defaultErrorMessage,
  buildBody,
  resultMessageParams,
  renderData,
  onResult,
  welcomeHint,
}) {
  const { t, i18n } = useTranslation();
  const [messages, setMessages] = useState([{ role: 'assistant', content: t(`${i18nPrefix}.welcome`) }]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [temperature, setTemperature] = useState(0.7);
  const [error, setError] = useState('');
  const [modelName, setModelName] = useState(undefined); // undefined = loading, null = none, string = configured
  const messagesEndRef = useRef(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/db/model-keys`)
      .then(r => r.json())
      .then(d => {
        const active = (d.keys || []).find(k => k.active);
        setModelName(active?.model_name || null);
      })
      .catch(() => setModelName(null));
  }, []);

  // Optional variant hook (AI Strategy Builder only) that appends a hint to the welcome message
  useEffect(() => {
    if (!welcomeHint) return;
    welcomeHint(t)
      .then(hint => {
        if (!hint) return;
        setMessages(prev => [{ ...prev[0], content: t(`${i18nPrefix}.welcome`) + hint }, ...prev.slice(1)]);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage = input.trim();
    setInput('');
    setError('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildBody(userMessage, temperature, i18n.language))
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || defaultErrorMessage);
      }

      const result = await response.json();

      // Add assistant response with generated result
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: t(`${i18nPrefix}.generatedResult`, resultMessageParams(result)),
          data: result
        }
      ]);

      // Pass generated result to parent
      if (onResult) {
        onResult(result);
      }

      // Show warnings if any
      if (showWarnings && result.warnings && result.warnings.length > 0) {
        const warningMsg = result.warnings.join('\n');
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: `⚠️ Warnings:\n${warningMsg}`, isWarning: true }
        ]);
      }
    } catch (err) {
      const errorMsg = err.message || 'Unknown error';
      if (trackError) setError(errorMsg);
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Error: ${errorMsg}`, isError: true }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const titleBlock = (
    <>
      <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#ece5d6', display: 'flex', alignItems: 'center', gap: 8 }}>
        {t(`${i18nPrefix}.title`)}
        {modelName ? (
          <span style={{ fontSize: '0.7rem', fontWeight: 500, padding: '2px 8px', borderRadius: 999, background: accent.badgeBg, border: `1px solid ${accent.badgeBorder}`, color: accent.badgeText }}>
            {modelName}
          </span>
        ) : modelName === null ? (
          <span style={{ fontSize: '0.7rem', fontWeight: 500, padding: '2px 8px', borderRadius: 999, background: 'rgba(240,166,60,0.15)', border: '1px solid rgba(240,166,60,0.3)', color: '#f3c057' }}>
            {t(`${i18nPrefix}.noModel`)}
          </span>
        ) : null}
      </div>
      <div style={{ fontSize: '0.72rem', color: '#a89c8a' }}>{t(`${i18nPrefix}.subtitle`)}</div>
    </>
  );

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: '#131110',
      border: '1px solid #262019',
      borderRadius: 8,
      overflow: 'hidden'
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px',
        background: '#1a1715',
        borderBottom: '1px solid #262019',
        display: 'flex',
        alignItems: 'center',
        ...(showTemperature ? { justifyContent: 'space-between', gap: 12 } : { gap: 8 })
      }}>
        {showTemperature ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
            <span style={{ fontSize: '1.2rem' }}>{headerEmoji}</span>
            <div>{titleBlock}</div>
          </div>
        ) : (
          <>
            <span style={{ fontSize: '1.2rem' }}>{headerEmoji}</span>
            <div>{titleBlock}</div>
          </>
        )}
        {showTemperature && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.75rem', color: '#a89c8a' }}>
            {t(`${i18nPrefix}.creativity`)}
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={temperature}
              onChange={e => setTemperature(parseFloat(e.target.value))}
              style={{ width: 60 }}
            />
            <span style={{ minWidth: 25, color: accent.solid }}>{temperature.toFixed(1)}</span>
          </label>
        )}
      </div>

      {/* Messages */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '12px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10
      }}>
        {messages.map((msg, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start'
            }}
          >
            <div
              style={{
                maxWidth: '85%',
                padding: '10px 14px',
                borderRadius: 10,
                fontSize: '0.85rem',
                lineHeight: '1.4',
                background: msg.role === 'user'
                  ? accent.solid
                  : msg.isError
                    ? 'rgba(226,96,78,0.12)'
                    : msg.isWarning
                      ? 'rgba(243,192,87,0.1)'
                      : '#262019',
                color: msg.role === 'user' ? '#131110' : msg.isError ? '#f0a99b' : msg.isWarning ? '#f3c057' : '#ece5d6',
                border: msg.isError ? '1px solid rgba(226,96,78,0.35)' : msg.isWarning ? '1px solid rgba(243,192,87,0.3)' : 'none',
                whiteSpace: 'pre-wrap'
              }}
            >
              {msg.content}
              {msg.data && (
                <div style={{
                  marginTop: 10,
                  padding: '10px',
                  background: 'rgba(0,0,0,0.3)',
                  borderRadius: 6,
                  fontSize: '0.75rem',
                  color: accent.dataText
                }}>
                  {renderData(msg, t)}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#a89c8a', fontSize: '0.85rem' }}>
            <span style={{ animation: 'spin 1s linear infinite' }}>⚙️</span>
            {t(`${i18nPrefix}.${loadingKey}`)}
            <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '12px 16px',
        borderTop: '1px solid #262019',
        background: '#131110'
      }}>
        {error && (
          <div style={{
            padding: '8px 12px',
            background: '#43201a',
            borderRadius: 6,
            fontSize: '0.75rem',
            color: '#f3c6ba',
            marginBottom: 8
          }}>
            {error}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), handleSend())}
            placeholder={t(`${i18nPrefix}.placeholder`)}
            disabled={loading}
            style={{
              flex: 1,
              padding: '10px 12px',
              background: '#262019',
              border: '1px solid #322b21',
              borderRadius: 8,
              color: '#ece5d6',
              fontSize: '0.85rem',
              outline: 'none'
            }}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            style={{
              padding: '10px 16px',
              background: loading || !input.trim() ? '#262019' : accent.solid,
              border: 'none',
              borderRadius: 8,
              color: loading || !input.trim() ? '#786d5e' : '#131110',
              cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
              fontSize: '0.85rem',
              fontWeight: 600
            }}
          >
            {t('common.send')}
          </button>
        </div>
      </div>
    </div>
  );
}

export function AIStrategyChat({ onStrategyGenerated }) {
  return (
    <AIChat
      endpoint="/api/ai/build-strategy"
      accent={STRATEGY_ACCENT}
      i18nPrefix="aiStrategy"
      headerEmoji="🤖"
      showTemperature
      showWarnings
      loadingKey="generatingStrategy"
      defaultErrorMessage="Failed to generate strategy"
      buildBody={(prompt, temperature, lang) => ({ prompt, temperature, language: lang })}
      resultMessageParams={result => ({ name: result.name, count: result.rules.length })}
      renderData={(msg, t) => (
        <>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{t('aiStrategy.strategyData')}</div>
          <pre style={{ margin: 0, overflow: 'auto', maxHeight: 150 }}>
            {JSON.stringify(msg.data, null, 2)}
          </pre>
        </>
      )}
      welcomeHint={async t => {
        const r = await fetch(`${API_BASE}/api/db/indicators`);
        const d = await r.json();
        const userInds = (d.indicators || []).filter(i => !i.is_builtin);
        if (userInds.length === 0) return null;
        const names = userInds.map(i => `"${i.name}"`).join(', ');
        return t('aiStrategy.customIndicatorHint', { count: userInds.length, names });
      }}
      onResult={onStrategyGenerated}
    />
  );
}

export function AIIndicatorChat({ onIndicatorGenerated }) {
  return (
    <AIChat
      endpoint="/api/ai/build-indicator"
      accent={INDICATOR_ACCENT}
      i18nPrefix="aiIndicator"
      headerEmoji="📊"
      trackError
      loadingKey="generatingIndicator"
      defaultErrorMessage="Failed to generate indicator"
      buildBody={(prompt, temperature, lang) => ({ prompt, language: lang })}
      resultMessageParams={result => ({ name: result.name, description: result.description })}
      renderData={msg => (
        <>
          <div style={{ fontWeight: 600, marginBottom: 4, color: msg.data.color }}>
            ■ {msg.data.name}
          </div>
          <pre style={{ margin: 0, overflow: 'auto', maxHeight: 150 }}>
            {JSON.stringify(msg.data.expr, null, 2)}
          </pre>
        </>
      )}
      onResult={onIndicatorGenerated}
    />
  );
}
