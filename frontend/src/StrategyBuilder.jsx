import { useState, useCallback, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

// ─── Signal preset blocks ─────────────────────────────────────────────────────
const SIGNAL_BLOCKS = [
  {
    category: "Price Conditions",
    color: "#22d3ee",
    items: [
      { id: 'price_above_value', emoji: '📈', label: 'Price is above a value',        desc: 'Trigger when price exceeds a fixed number',
        left: { type: 'price', field: 'mid' }, operator: '>', right: { type: 'constant', value: 0 } },
      { id: 'price_below_value', emoji: '📉', label: 'Price is below a value',        desc: 'Trigger when price drops under a threshold',
        left: { type: 'price', field: 'mid' }, operator: '<', right: { type: 'constant', value: 0 } },
      { id: 'price_change_up',   emoji: '🚀', label: 'Price rose vs N bars ago',      desc: 'Detect recent upward movement',
        left: { type: 'price', field: 'mid' }, operator: '>', right: { type: 'lookback', field: 'mid', period: 1 } },
      { id: 'price_change_down', emoji: '🪂', label: 'Price fell vs N bars ago',      desc: 'Detect recent downward movement',
        left: { type: 'price', field: 'mid' }, operator: '<', right: { type: 'lookback', field: 'mid', period: 1 } },
    ]
  },
  {
    category: "Moving Averages",
    color: "#34d399",
    items: [
      { id: 'price_above_sma',  emoji: '〰️', label: 'Price above SMA',                  desc: 'Price above a simple moving average — bullish',
        left: { type: 'price', field: 'mid' }, operator: '>', right: { type: 'sma', field: 'mid', period: 20 } },
      { id: 'price_below_sma',  emoji: '〰️', label: 'Price below SMA',                  desc: 'Price below a moving average — bearish',
        left: { type: 'price', field: 'mid' }, operator: '<', right: { type: 'sma', field: 'mid', period: 20 } },
      { id: 'sma_cross_above',  emoji: '✂️', label: 'Fast SMA crosses above Slow SMA', desc: 'Golden cross — bullish momentum shift',
        left: { type: 'sma', field: 'mid', period: 10 }, operator: 'cross_above', right: { type: 'sma', field: 'mid', period: 50 } },
      { id: 'sma_cross_below',  emoji: '✂️', label: 'Fast SMA crosses below Slow SMA', desc: 'Death cross — bearish momentum shift',
        left: { type: 'sma', field: 'mid', period: 10 }, operator: 'cross_below', right: { type: 'sma', field: 'mid', period: 50 } },
      { id: 'ema_cross_above',  emoji: '⚡', label: 'Fast EMA crosses above Slow EMA', desc: 'Fast-reacting golden cross',
        left: { type: 'ema', field: 'mid', period: 9 }, operator: 'cross_above', right: { type: 'ema', field: 'mid', period: 21 } },
    ]
  },
  {
    category: "RSI",
    color: "#a78bfa",
    items: [
      { id: 'rsi_oversold',   emoji: '🔻', label: 'RSI below 30 (Oversold)',   desc: 'Potential bounce — asset may be oversold',
        left: { type: 'rsi', field: 'mid', period: 14 }, operator: '<', right: { type: 'constant', value: 30 } },
      { id: 'rsi_overbought', emoji: '🔺', label: 'RSI above 70 (Overbought)', desc: 'Potential pullback — asset may be overbought',
        left: { type: 'rsi', field: 'mid', period: 14 }, operator: '>', right: { type: 'constant', value: 70 } },
      { id: 'rsi_custom',     emoji: '🎛️', label: 'RSI vs custom value',       desc: 'Compare RSI to any number you choose',
        left: { type: 'rsi', field: 'mid', period: 14 }, operator: '>', right: { type: 'constant', value: 50 } },
    ]
  },
  {
    category: "MACD",
    color: "#fb923c",
    items: [
      { id: 'macd_cross',      emoji: '📡', label: 'MACD crosses above Signal', desc: 'Bullish MACD crossover',
        left: { type: 'macd', fast: 12, slow: 26, signal: 9, component: 'macd' }, operator: 'cross_above', right: { type: 'macd', fast: 12, slow: 26, signal: 9, component: 'signal' } },
      { id: 'macd_above_zero', emoji: '0️⃣', label: 'MACD above zero',           desc: 'MACD is positive — bullish trend',
        left: { type: 'macd', fast: 12, slow: 26, signal: 9, component: 'macd' }, operator: '>', right: { type: 'constant', value: 0 } },
    ]
  },
  {
    category: "Bollinger Bands",
    color: "#f472b6",
    items: [
      { id: 'bb_lower', emoji: '⬇️', label: 'Price below Lower Band', desc: 'Near lower band — potential bounce',
        left: { type: 'price', field: 'mid' }, operator: '<', right: { type: 'bollinger', field: 'mid', period: 20, std_dev: 2, component: 'lower' } },
      { id: 'bb_upper', emoji: '⬆️', label: 'Price above Upper Band', desc: 'Near upper band — potential reversal',
        left: { type: 'price', field: 'mid' }, operator: '>', right: { type: 'bollinger', field: 'mid', period: 20, std_dev: 2, component: 'upper' } },
    ]
  },
  {
    category: "Volume",
    color: "#f59e0b",
    items: [
      { id: 'volume_spike', emoji: '📊', label: 'Volume spike (above average)', desc: 'Volume higher than its moving average',
        left: { type: 'price', field: 'volume' }, operator: '>', right: { type: 'sma', field: 'volume', period: 20 } },
    ]
  },
];

const EXIT_BLOCKS = [
  {
    category: "Profit & Loss",
    color: "#34d399",
    items: [
      { id: 'take_profit_pct',  emoji: '🎯', label: 'Take profit at +X%',    desc: 'Exit when position profit reaches this percentage',
        kind: 'exit_condition', exitType: 'take_profit_pct', value: 5 },
      { id: 'stop_loss_pct',   emoji: '🛑', label: 'Stop loss at −X%',       desc: 'Exit when position loss reaches this percentage',
        kind: 'exit_condition', exitType: 'stop_loss_pct', value: 3 },
      { id: 'take_profit_abs', emoji: '💵', label: 'Take profit at +$X',     desc: 'Exit when absolute profit reaches this $ value',
        kind: 'exit_condition', exitType: 'take_profit_abs', value: 500 },
      { id: 'stop_loss_abs',   emoji: '💸', label: 'Stop loss at −$X',       desc: 'Exit when absolute loss reaches this $ value',
        kind: 'exit_condition', exitType: 'stop_loss_abs', value: 200 },
    ]
  },
  {
    category: "Time-Based",
    color: "#22d3ee",
    items: [
      { id: 'bars_held',   emoji: '⏱️', label: 'After N bars in trade',        desc: 'Exit after being in the position for N candles',
        kind: 'exit_condition', exitType: 'bars_held', value: 10 },
      { id: 'time_of_day', emoji: '🕐', label: 'At a specific hour (UTC)',     desc: 'Trigger at a certain hour of the day (0–23)',
        kind: 'exit_condition', exitType: 'time_of_day', value: 16 },
      { id: 'day_of_week', emoji: '📅', label: 'On a specific day of the week', desc: 'Trigger only on Mon / Tue / etc.',
        kind: 'exit_condition', exitType: 'day_of_week', value: 5 },
    ]
  },
];

const DOW = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];

const ROLES = [
  { value: 'entry_long',  label: '🟢 Buy (Enter Long)',   color: '#34d399', bg: 'rgba(52,211,153,0.12)',  border: 'rgba(52,211,153,0.4)'  },
  { value: 'exit_long',   label: '🔴 Sell (Exit Long)',   color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.4)' },
  { value: 'entry_short', label: '🟠 Enter Short',        color: '#fb923c', bg: 'rgba(251,146,60,0.12)',  border: 'rgba(251,146,60,0.4)'  },
  { value: 'exit_short',  label: '🟣 Exit Short',         color: '#a78bfa', bg: 'rgba(167,139,250,0.12)', border: 'rgba(167,139,250,0.4)' },
];

const OPERATORS = [
  { value: '>',           label: 'is greater than' },
  { value: '>=',          label: 'is greater than or equal to' },
  { value: '<',           label: 'is less than' },
  { value: '<=',          label: 'is less than or equal to' },
  { value: '==',          label: 'equals' },
  { value: '!=',          label: 'does not equal' },
  { value: 'cross_above', label: '↗ crosses above' },
  { value: 'cross_below', label: '↘ crosses below' },
];

let _uid = 1;
const uid = () => String(_uid++);

function defaultCondition(template) {
  if (template?.kind === 'exit_condition') return { _id: uid(), kind: 'exit_condition', exitType: template.exitType, value: template.value, templateId: template.id, combiner: 'and' };
  return { _id: uid(), kind: 'signal', left: { ...(template?.left ?? { type: 'price', field: 'mid' }) }, operator: template?.operator ?? '>', right: { ...(template?.right ?? { type: 'constant', value: 0 }) }, templateId: template?.id ?? null, combiner: 'and' };
}

function defaultRule(role = 'entry_long') {
  return { _id: uid(), name: role.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase()), role, conditions: [defaultCondition()], timing: 'on_change', quantity: 1 };
}

function serialiseOperand(o) {
  if (!o) return { type: 'constant', value: 0 };
  if (o.type === 'constant') return { type: 'constant', value: parseFloat(o.value) || 0 };
  return { ...o };
}

function serialiseCondition(c) {
  if (c.kind === 'exit_condition') return { kind: 'exit_condition', exitType: c.exitType, value: c.value, combiner: c.combiner || 'and' };
  const { _id, templateId, ...rest } = c;
  return { ...rest, left: serialiseOperand(rest.left), right: serialiseOperand(rest.right) };
}

function ruleSetToJson(name, rules) {
  return { name, rules: rules.map(({ _id, ...r }) => ({ ...r, conditions: r.conditions.map(serialiseCondition) })) };
}

function validateRules(rules) {
  const warnings = [];
  const roleMap = {};
  rules.forEach(r => { roleMap[r.role] = (roleMap[r.role] || 0) + 1; });
  if (roleMap['entry_long']  && !roleMap['exit_long'])   warnings.push('You have Buy (Long) rules but no Sell (Exit Long) rule. Positions will never close!');
  if (roleMap['exit_long']   && !roleMap['entry_long'])  warnings.push('You have Exit Long rules but no Entry Long rule — nothing will open the trade.');
  if (roleMap['entry_short'] && !roleMap['exit_short'])  warnings.push('You have Enter Short rules but no Exit Short rule. Short positions will never close!');
  if (roleMap['exit_short']  && !roleMap['entry_short']) warnings.push('You have Exit Short rules but no Enter Short rule — nothing will open the short.');
  rules.forEach(r => { if (r.conditions.length === 0) warnings.push(`Rule "${r.name}" has no conditions and will never fire.`); });
  return warnings;
}

const iStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 6, padding: '4px 9px', color: '#e5e7eb', fontSize: '0.83rem', width: 75, outline: 'none' };
const sStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 6, padding: '4px 9px', color: '#e5e7eb', fontSize: '0.83rem', outline: 'none' };
const PRICE_FIELDS = ['bid','ask','mid','volume'];

function OperandEditor({ operand, onChange, label }) {
  const TYPES = ['price','lookback','sma','ema','rsi','macd','bollinger','constant'];
  const TYPE_LABELS = { price:'Current Price', lookback:'Price N bars ago', sma:'SMA', ema:'EMA (Fast Average)', rsi:'RSI (0–100)', macd:'MACD', bollinger:'Bollinger Band', constant:'Fixed Number' };
  const set = (k, v) => onChange({ ...operand, [k]: v });
  return (
    <div style={{ background: '#0b1120', border: '1px solid #1e293b', borderRadius: 10, padding: '10px 14px' }}>
      <div style={{ fontSize: '0.67rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 8 }}>{label}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <select value={operand?.type || 'price'} style={sStyle} onChange={e => onChange({ type: e.target.value, field: 'mid', period: 14, value: 0 })}>
          {TYPES.map(t => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
        </select>
        {operand?.type === 'constant' && <input type="number" value={operand.value ?? 0} style={iStyle} onChange={e => set('value', parseFloat(e.target.value) || 0)} />}
        {['price','lookback','sma','ema','rsi','bollinger'].includes(operand?.type) && (
          <select value={operand.field || 'mid'} style={sStyle} onChange={e => set('field', e.target.value)}>
            {PRICE_FIELDS.map(f => <option key={f}>{f}</option>)}
          </select>
        )}
        {['lookback','sma','ema','rsi'].includes(operand?.type) && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ fontSize: '0.74rem', color: '#9ca3af' }}>{operand.type === 'lookback' ? 'bars ago:' : 'period:'}</span>
            <input type="number" value={operand.period || 14} min={1} style={iStyle} onChange={e => set('period', parseInt(e.target.value) || 1)} />
          </label>
        )}
        {operand?.type === 'bollinger' && <>
          <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ fontSize: '0.74rem', color: '#9ca3af' }}>period:</span>
            <input type="number" value={operand.period || 20} min={2} style={iStyle} onChange={e => set('period', parseInt(e.target.value) || 20)} />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ fontSize: '0.74rem', color: '#9ca3af' }}>σ:</span>
            <input type="number" value={operand.std_dev || 2} min={0.1} step={0.1} style={{ ...iStyle, width: 55 }} onChange={e => set('std_dev', parseFloat(e.target.value) || 2)} />
          </label>
          <select value={operand.component || 'upper'} style={sStyle} onChange={e => set('component', e.target.value)}>
            {['upper','middle','lower','width','pct_b'].map(c => <option key={c}>{c}</option>)}
          </select>
        </>}
        {operand?.type === 'macd' && <>
          {['fast','slow','signal'].map(k => (
            <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ fontSize: '0.74rem', color: '#9ca3af' }}>{k}:</span>
              <input type="number" value={operand[k] || (k==='fast'?12:k==='slow'?26:9)} min={1} style={iStyle} onChange={e => set(k, parseInt(e.target.value)||1)} />
            </label>
          ))}
          <select value={operand.component || 'macd'} style={sStyle} onChange={e => set('component', e.target.value)}>
            {['macd','signal','hist'].map(c => <option key={c}>{c}</option>)}
          </select>
        </>}
      </div>
    </div>
  );
}

function ExitConditionEditor({ cond, onChange }) {
  const meta = {
    take_profit_pct:  { pre: 'Take profit at +', suf: '% profit',            min: 0.1, step: 0.1 },
    stop_loss_pct:    { pre: 'Stop loss at −',   suf: '% loss',              min: 0.1, step: 0.1 },
    take_profit_abs:  { pre: 'Take profit at +$', suf: ' profit',            min: 1,   step: 1 },
    stop_loss_abs:    { pre: 'Stop loss at −$',   suf: ' loss',              min: 1,   step: 1 },
    bars_held:        { pre: 'Exit after',        suf: ' bars in trade',     min: 1,   step: 1 },
    time_of_day:      { pre: 'At hour',           suf: ':00 UTC  (0–23)',    min: 0,   step: 1, max: 23 },
    day_of_week:      { pre: 'On',                suf: '',                   isDow: true },
  }[cond.exitType] || { pre: 'Value:', suf: '', min: 0, step: 1 };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
      <span style={{ fontSize: '0.85rem', color: '#9ca3af' }}>{meta.pre}</span>
      {meta.isDow ? (
        <select value={cond.value} style={sStyle} onChange={e => onChange({ ...cond, value: parseInt(e.target.value) })}>
          {DOW.map((d, i) => <option key={i} value={i}>{d}</option>)}
        </select>
      ) : (
        <input type="number" value={cond.value} min={meta.min} max={meta.max} step={meta.step} style={{ ...iStyle, width: 90 }}
          onChange={e => onChange({ ...cond, value: parseFloat(e.target.value) || 0 })} />
      )}
      {meta.suf && <span style={{ fontSize: '0.85rem', color: '#9ca3af' }}>{meta.suf}</span>}
    </div>
  );
}

function ConditionCard({ cond, onChange, onRemove, total, showCombiner }) {
  const [expanded, setExpanded] = useState(false);
  const allItems = [...SIGNAL_BLOCKS, ...EXIT_BLOCKS].flatMap(c => c.items);
  const template = allItems.find(i => i.id === cond.templateId);
  const catColor = template ? [...SIGNAL_BLOCKS, ...EXIT_BLOCKS].find(c => c.items.some(i => i.id === cond.templateId))?.color : '#6b7280';

  const labelOp = (o) => {
    if (!o) return '?';
    const m = { price: o=>`${o.field||'mid'} price`, lookback: o=>`${o.field||'mid'} ${o.period||1}b ago`, sma: o=>`SMA(${o.period||20})`, ema: o=>`EMA(${o.period||20})`, rsi: o=>`RSI(${o.period||14})`, macd: o=>`MACD ${o.component||''}`, bollinger: o=>`BB ${o.component||''}`, constant: o=>String(o.value??0) };
    return (m[o.type] || (() => o.type))(o);
  };
  const summary = cond.kind === 'exit_condition'
    ? `${(cond.exitType||'').replace(/_/g,' ')} = ${cond.exitType === 'day_of_week' ? DOW[cond.value] : cond.value}`
    : `${labelOp(cond.left)} ${OPERATORS.find(o=>o.value===cond.operator)?.label??cond.operator} ${labelOp(cond.right)}`;

  return (
    <>
      {showCombiner && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '6px 0' }}>
          <div style={{ flex: 1, height: 1, background: '#1f2937' }} />
          <div style={{ display: 'flex', gap: 3, background: '#0f172a', border: '1px solid #1f2937', borderRadius: 999, padding: '3px' }}>
            {['and','or'].map(v => (
              <button key={v} type="button" onClick={() => onChange({ ...cond, combiner: v })}
                style={{ padding: '2px 12px', borderRadius: 999, fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.1em', cursor: 'pointer', border: 'none', transition: 'all 0.15s',
                  background: (cond.combiner||'and') === v ? (v==='and'?'rgba(34,211,238,0.2)':'rgba(245,158,11,0.2)') : 'transparent',
                  color: (cond.combiner||'and') === v ? (v==='and'?'#22d3ee':'#f59e0b') : '#4b5563' }}>
                {v.toUpperCase()}
              </button>
            ))}
          </div>
          <div style={{ flex: 1, height: 1, background: '#1f2937' }} />
        </div>
      )}
      <div style={{ background: '#111827', border: `1px solid ${catColor||'#1f2937'}44`, borderRadius: 12, padding: '12px 16px', marginBottom: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {template && <span style={{ fontSize: '1.05rem' }}>{template.emoji}</span>}
          <div style={{ flex: 1, minWidth: 0 }}>
            {template && <div style={{ fontSize: '0.73rem', fontWeight: 700, color: catColor, marginBottom: 1 }}>{template.label}</div>}
            <div style={{ fontSize: '0.78rem', color: '#9ca3af', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{summary}</div>
          </div>
          <button type="button" style={{ background: 'transparent', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: '0.75rem', padding: '2px 6px' }}
            onClick={() => setExpanded(e => !e)}>{expanded ? '▲' : '▼ edit'}</button>
          {total > 1 && (
            <button type="button" style={{ background: 'transparent', border: '1px solid #ef444455', borderRadius: 6, color: '#ef4444', cursor: 'pointer', padding: '2px 7px', fontSize: '0.75rem' }}
              onClick={onRemove}>✕</button>
          )}
        </div>
        {expanded && (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #1f2937' }}>
            {cond.kind === 'exit_condition' ? (
              <ExitConditionEditor cond={cond} onChange={onChange} />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <OperandEditor operand={cond.left}  onChange={v => onChange({ ...cond, left: v })}  label="Left side" />
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ flex: 1, height: 1, background: '#1f2937' }} />
                  <select value={cond.operator} style={sStyle} onChange={e => onChange({ ...cond, operator: e.target.value })}>
                    {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                  <div style={{ flex: 1, height: 1, background: '#1f2937' }} />
                </div>
                <OperandEditor operand={cond.right} onChange={v => onChange({ ...cond, right: v })} label="Right side" />
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

function RuleEditor({ rule, onChange, onDelete, customIndicators }) {
  const role = ROLES.find(r => r.value === rule.role);
  const [showPicker, setShowPicker] = useState(false);
  const [pickerTab, setPickerTab]   = useState('signal');
  const isExitRole = rule.role.startsWith('exit_');

  const addCondFromBlock = (item) => { onChange({ ...rule, conditions: [...rule.conditions, defaultCondition(item)] }); setShowPicker(false); };
  const addBlankCondition = () => { onChange({ ...rule, conditions: [...rule.conditions, defaultCondition()] }); setShowPicker(false); };
  const updateCond = (id, upd) => onChange({ ...rule, conditions: rule.conditions.map(c => c._id === id ? upd : c) });
  const removeCond = (id) => onChange({ ...rule, conditions: rule.conditions.filter(c => c._id !== id) });

  return (
    <div style={{ background: '#111827', border: '1px solid #1f2937', borderRadius: 16, overflow: 'hidden', boxShadow: '0 4px 20px rgba(0,0,0,0.3)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 20px', background: '#0f172a', borderBottom: '1px solid #1f2937', flexWrap: 'wrap' }}>
        <input value={rule.name} onChange={e => onChange({ ...rule, name: e.target.value })}
          style={{ flex: 1, minWidth: 120, background: 'transparent', border: 'none', color: '#e5e7eb', fontSize: '1rem', fontWeight: 700, outline: 'none' }} />
        <select value={rule.role}
          style={{ ...sStyle, fontWeight: 700, color: role?.color, background: role?.bg, border: `1px solid ${role?.border}` }}
          onChange={e => onChange({ ...rule, role: e.target.value })}>
          {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
        <button type="button" onClick={onDelete}
          style={{ background: 'transparent', border: '1px solid #ef444455', borderRadius: 8, color: '#ef4444', cursor: 'pointer', padding: '5px 12px', fontSize: '0.78rem' }}>
          Delete
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '10px 20px', background: '#0b1120', borderBottom: '1px solid #1f2937', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6b7280' }}>Fire</span>
          <select value={rule.timing} style={sStyle} onChange={e => onChange({ ...rule, timing: e.target.value })}>
            <option value="on_change">Only when signal changes</option>
            <option value="every_tick">Every tick while true</option>
          </select>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6b7280' }}>Quantity</span>
          <input type="number" value={rule.quantity} min={0.01} step={0.01} style={iStyle}
            onChange={e => onChange({ ...rule, quantity: parseFloat(e.target.value) || 1 })} />
        </label>
      </div>

      <div style={{ padding: '16px 20px' }}>
        <div style={{ fontSize: '0.68rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 12 }}>
          Conditions {rule.conditions.length > 1 && <span style={{ color: '#4b5563', fontWeight: 400 }}>— AND/OR between each pair</span>}
        </div>

        {rule.conditions.map((cond, idx) => (
          <ConditionCard key={cond._id}
            cond={cond}
            total={rule.conditions.length}
            showCombiner={idx > 0}
            onChange={u => updateCond(cond._id, u)}
            onRemove={() => removeCond(cond._id)}
          />
        ))}

        <div style={{ position: 'relative', marginTop: 10 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button"
              style={{ flex: 1, background: '#0f172a', border: '1px dashed #334155', borderRadius: 10, padding: '10px', color: '#9ca3af', cursor: 'pointer', fontSize: '0.82rem', transition: 'all 0.2s' }}
              onMouseEnter={e => { e.currentTarget.style.borderColor='#22d3ee'; e.currentTarget.style.color='#22d3ee'; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor='#334155'; e.currentTarget.style.color='#9ca3af'; }}
              onClick={() => { setShowPicker(p=>!p); setPickerTab('signal'); }}>
              🔍 Signal condition
            </button>
            <button type="button"
              style={{ flex: 1, background: '#0f172a', border: '1px dashed #34d39955', borderRadius: 10, padding: '10px', color: '#34d39988', cursor: 'pointer', fontSize: '0.82rem', transition: 'all 0.2s' }}
              onMouseEnter={e => { e.currentTarget.style.background='rgba(52,211,153,0.05)'; e.currentTarget.style.color='#34d399'; }}
              onMouseLeave={e => { e.currentTarget.style.background='#0f172a'; e.currentTarget.style.color='#34d39988'; }}
              onClick={() => { setShowPicker(p=>!p); setPickerTab('exit'); }}>
              🎯 P&L / Time exit
            </button>
            <button type="button"
              style={{ background: '#0f172a', border: '1px dashed #334155', borderRadius: 10, padding: '10px 14px', color: '#6b7280', cursor: 'pointer', fontSize: '0.82rem' }}
              onClick={addBlankCondition}>
              + Blank
            </button>
          </div>

          {showPicker && (
            <div style={{ position: 'absolute', zIndex: 20, top: '100%', left: 0, right: 0, background: '#0f172a', border: '1px solid #1f2937', borderRadius: 14, padding: '12px', marginTop: 6, maxHeight: 400, overflowY: 'auto', boxShadow: '0 16px 48px rgba(0,0,0,0.7)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <div style={{ display: 'flex', gap: 4, background: '#111827', borderRadius: 8, padding: 3 }}>
                  {[{ id:'signal', label:'📊 Signal' },{ id:'exit', label:'🎯 Exit / P&L' }].map(t => (
                    <button key={t.id} type="button"
                      style={{ padding: '4px 12px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: '0.78rem', fontWeight: 700,
                        background: pickerTab===t.id?'#1e293b':'transparent', color: pickerTab===t.id?'#e5e7eb':'#6b7280' }}
                      onClick={() => setPickerTab(t.id)}>{t.label}</button>
                  ))}
                </div>
                <button type="button" style={{ background:'transparent', border:'none', color:'#6b7280', cursor:'pointer', fontSize:'1.1rem' }} onClick={() => setShowPicker(false)}>✕</button>
              </div>

              {pickerTab === 'signal' && SIGNAL_BLOCKS.map(cat => (
                <div key={cat.category} style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: '0.67rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: cat.color, marginBottom: 6 }}>{cat.category}</div>
                  {cat.items.map(item => (
                    <div key={item.id}
                      style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 9, cursor: 'pointer', marginBottom: 3, transition: 'background 0.15s' }}
                      onMouseEnter={e => e.currentTarget.style.background='#1f2937'}
                      onMouseLeave={e => e.currentTarget.style.background='transparent'}
                      onClick={() => addCondFromBlock(item)}>
                      <span style={{ fontSize: '1rem' }}>{item.emoji}</span>
                      <div>
                        <div style={{ fontSize: '0.83rem', fontWeight: 600, color: '#e5e7eb' }}>{item.label}</div>
                        <div style={{ fontSize: '0.72rem', color: '#6b7280' }}>{item.desc}</div>
                      </div>
                    </div>
                  ))}
                </div>
              ))}

              {pickerTab === 'exit' && EXIT_BLOCKS.map(cat => (
                <div key={cat.category} style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: '0.67rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: cat.color, marginBottom: 6 }}>{cat.category}</div>
                  {cat.items.map(item => (
                    <div key={item.id}
                      style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 9, cursor: 'pointer', marginBottom: 3, transition: 'background 0.15s' }}
                      onMouseEnter={e => e.currentTarget.style.background='#1f2937'}
                      onMouseLeave={e => e.currentTarget.style.background='transparent'}
                      onClick={() => addCondFromBlock(item)}>
                      <span style={{ fontSize: '1rem' }}>{item.emoji}</span>
                      <div>
                        <div style={{ fontSize: '0.83rem', fontWeight: 600, color: '#e5e7eb' }}>{item.label}</div>
                        <div style={{ fontSize: '0.72rem', color: '#6b7280' }}>{item.desc}</div>
                      </div>
                    </div>
                  ))}
                </div>
              ))}

              {pickerTab === 'signal' && customIndicators.length > 0 && (
                <div>
                  <div style={{ fontSize: '0.67rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#22d3ee', marginBottom: 6 }}>My Custom Indicators</div>
                  {customIndicators.map(ind => (
                    <div key={ind.name}
                      style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 9, cursor: 'pointer', marginBottom: 3, transition: 'background 0.15s' }}
                      onMouseEnter={e => e.currentTarget.style.background='#1f2937'}
                      onMouseLeave={e => e.currentTarget.style.background='transparent'}
                      onClick={() => addCondFromBlock({ id: `custom_${ind.name}`, emoji: '🔷', label: ind.name, desc: ind.description || '', left: { type: 'custom', name: ind.name }, operator: '>', right: { type: 'constant', value: 0 } })}>
                      <span style={{ width: 10, height: 10, borderRadius: '50%', background: ind.color||'#22d3ee', display: 'inline-block', flexShrink: 0 }} />
                      <div>
                        <div style={{ fontSize: '0.83rem', fontWeight: 600, color: '#e5e7eb' }}>{ind.name}</div>
                        {ind.description && <div style={{ fontSize: '0.72rem', color: '#6b7280' }}>{ind.description}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function StrategyBuilder() {
  const [ruleSetName, setRuleSetName] = useState('My Strategy');
  const [rules, setRules]             = useState([defaultRule('entry_long'), defaultRule('exit_long')]);
  const [activeId, setActiveId]       = useState(rules[0]._id);
  const [saving, setSaving]           = useState(false);
  const [showJson, setShowJson]       = useState(false);
  const [customIndicators, setCIs]    = useState([]);

  useEffect(() => { fetch(`${API_BASE}/db/indicators`).then(r=>r.json()).then(d=>setCIs(d.indicators||[])).catch(()=>{}); }, []);

  const addRule = (role = 'entry_long') => { const r = defaultRule(role); setRules(p=>[...p,r]); setActiveId(r._id); };
  const updateRule = useCallback(u => setRules(p => p.map(r => r._id===u._id?u:r)), []);
  const deleteRule = id => { const rest = rules.filter(r=>r._id!==id); setRules(rest); if(activeId===id) setActiveId(rest[0]?._id??null); };

  const payload = ruleSetToJson(ruleSetName, rules);
  const warnings = validateRules(rules);
  const activeRule = rules.find(r => r._id === activeId);

  const save = async () => {
    setSaving(true);
    try {
      await fetch(`${API_BASE}/db/strategies`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ strategies:[{ name:ruleSetName, logic:'rule_based', config:JSON.stringify({ rule_set:payload }) }] }) });
      alert('Strategy saved!');
    } catch { alert('Failed to save.'); }
    finally { setSaving(false); }
  };

  const roleGroups = [
    { label: 'Long Entry (Buy)',  color: '#34d399', role: 'entry_long'  },
    { label: 'Long Exit (Sell)',  color: '#f87171', role: 'exit_long'   },
    { label: 'Short Entry',       color: '#fb923c', role: 'entry_short' },
    { label: 'Short Exit',        color: '#a78bfa', role: 'exit_short'  },
  ];

  return (
    <div className="view">
      <h2>Strategy Builder</h2>
      <p>Build trading rules. Every entry needs a matching exit rule — warnings will appear if something is missing.</p>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '1.5rem 0 1rem', flexWrap: 'wrap' }}>
        <input value={ruleSetName} onChange={e => setRuleSetName(e.target.value)}
          style={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 10, padding: '7px 14px', color: '#e5e7eb', fontSize: '1rem', fontWeight: 700, outline: 'none', minWidth: 160 }} />
        <button type="button" style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, padding: '7px 14px', color: '#9ca3af', cursor: 'pointer', fontSize: '0.82rem' }}
          onClick={() => setShowJson(s=>!s)}>{showJson ? 'Hide JSON' : 'View JSON'}</button>
        <button type="button" style={{ marginLeft: 'auto', background: saving?'#1e293b':'linear-gradient(135deg,#6366f1,#22d3ee)', border: 'none', borderRadius: 999, padding: '8px 20px', color: '#0f172a', fontWeight: 700, cursor: 'pointer', fontSize: '0.9rem' }}
          onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save Strategy'}</button>
      </div>

      {warnings.map((w, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 10, padding: '10px 14px', marginBottom: 8, fontSize: '0.84rem', color: '#fbbf24' }}>
          ⚠️ {w}
        </div>
      ))}

      {showJson && (
        <div style={{ background: '#0b1120', border: '1px dashed #334155', borderRadius: 12, padding: '1rem', marginBottom: 16, overflow: 'auto' }}>
          <pre style={{ margin: 0, fontSize: '0.75rem', color: '#93c5fd', fontFamily: 'ui-monospace, monospace' }}>{JSON.stringify(payload, null, 2)}</pre>
        </div>
      )}

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <aside style={{ flexShrink: 0, width: 200, background: '#111827', border: '1px solid #1f2937', borderRadius: 16, padding: '1rem', position: 'sticky', top: 0 }}>
          {roleGroups.map(g => {
            const groupRules = rules.filter(r => r.role === g.role);
            return (
              <div key={g.role} style={{ marginBottom: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 }}>
                  <span style={{ fontSize: '0.67rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: g.color }}>{g.label}</span>
                  <button type="button" onClick={() => addRule(g.role)}
                    style={{ background: 'transparent', border: 'none', color: g.color, cursor: 'pointer', fontSize: '0.72rem', padding: '0 2px' }}>+ Add</button>
                </div>
                {groupRules.map(r => (
                  <div key={r._id}
                    style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', marginBottom: 2, transition: 'background 0.15s',
                      background: r._id===activeId?`${g.color}18`:'transparent', borderLeft: `2px solid ${r._id===activeId?g.color:'transparent'}` }}
                    onClick={() => setActiveId(r._id)}>
                    <span style={{ flex: 1, fontSize: '0.79rem', color: r._id===activeId?'#e5e7eb':'#9ca3af', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
                    <span style={{ fontSize: '0.63rem', color: '#4b5563' }}>{r.conditions.length}c</span>
                  </div>
                ))}
                {groupRules.length === 0 && <div style={{ fontSize: '0.73rem', color: '#374151', padding: '3px 6px', fontStyle: 'italic' }}>None</div>}
              </div>
            );
          })}
        </aside>

        <div style={{ flex: 1, minWidth: 0 }}>
          {!activeRule ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 200, color: '#4b5563', gap: 8 }}>
              <span style={{ fontSize: '2rem' }}>◇</span>
              <span>Select a rule from the sidebar</span>
            </div>
          ) : (
            <RuleEditor key={activeRule._id} rule={activeRule} onChange={updateRule} onDelete={() => deleteRule(activeRule._id)} customIndicators={customIndicators} />
          )}
        </div>
      </div>
    </div>
  );
}