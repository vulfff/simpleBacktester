import { useState, useRef, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export function AIIndicatorChat({ onIndicatorGenerated }) {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hi! Describe a technical indicator you want to create, and I\'ll generate the expression tree. For example: "RSI oversold signal that returns 1 when RSI(14) is below 30" or "Moving average distance measured as percentage"' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const messagesEndRef = useRef(null);

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
      const response = await fetch(`${API_BASE}/ai/build-indicator`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: userMessage
        })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to generate indicator');
      }

      const result = await response.json();

      // Add assistant response with generated indicator
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `Generated indicator: "${result.name}"\n${result.description}`,
          data: result
        }
      ]);

      // Pass generated indicator to parent
      if (onIndicatorGenerated) {
        onIndicatorGenerated(result);
      }
    } catch (err) {
      const errorMsg = err.message || 'Unknown error';
      setError(errorMsg);
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Error: ${errorMsg}`, isError: true }
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: '#0b1120',
      border: '1px solid #1e293b',
      borderRadius: 12,
      overflow: 'hidden'
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px',
        background: '#111827',
        borderBottom: '1px solid #1e293b',
        display: 'flex',
        alignItems: 'center',
        gap: 8
      }}>
        <span style={{ fontSize: '1.2rem' }}>📊</span>
        <div>
          <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#e5e7eb' }}>AI Indicator Builder</div>
          <div style={{ fontSize: '0.72rem', color: '#9ca3af' }}>Natural language → Expression trees</div>
        </div>
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
                  ? '#8b5cf6'
                  : msg.isError
                    ? '#ef4444'
                    : '#1e293b',
                color: msg.role === 'user' || msg.isError ? '#ffffff' : '#e5e7eb',
                border: msg.isError ? '1px solid #7f1d1d' : 'none',
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
                  color: '#d8b4fe'
                }}>
                  <div style={{ fontWeight: 600, marginBottom: 4, color: msg.data.color }}>
                    ■ {msg.data.name}
                  </div>
                  <pre style={{ margin: 0, overflow: 'auto', maxHeight: 150 }}>
                    {JSON.stringify(msg.data.expr, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#9ca3af', fontSize: '0.85rem' }}>
            <span style={{ animation: 'spin 1s linear infinite' }}>⚙️</span>
            Generating indicator…
            <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '12px 16px',
        borderTop: '1px solid #1e293b',
        background: '#0f1419'
      }}>
        {error && (
          <div style={{
            padding: '8px 12px',
            background: '#7f1d1d',
            borderRadius: 6,
            fontSize: '0.75rem',
            color: '#fecaca',
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
            placeholder="Describe an indicator…"
            disabled={loading}
            style={{
              flex: 1,
              padding: '10px 12px',
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 8,
              color: '#e5e7eb',
              fontSize: '0.85rem',
              outline: 'none'
            }}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            style={{
              padding: '10px 16px',
              background: loading || !input.trim() ? '#1e293b' : '#8b5cf6',
              border: 'none',
              borderRadius: 8,
              color: loading || !input.trim() ? '#6b7280' : '#ffffff',
              cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
              fontSize: '0.85rem',
              fontWeight: 600
            }}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
