import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { AIStrategyChat } from './AIStrategyChat';

const API_BASE = import.meta.env.VITE_API_BASE || '';

// ─── Time helpers ─────────────────────────────────────────────────────────────
const minutesToTime = m => {
  const h = Math.floor(m / 60), min = m % 60;
  return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
};
const timeToMinutes = s => {
  const [h, m] = (s || '00:00').split(':').map(Number);
  return h * 60 + (m || 0);
};

// ─── Custom indicator expression tree helpers ─────────────────────────────────
const _pfx = (path, key) => path ? `${path}.${key}` : key;
const _PATH_LABELS = { cond_right: 'Threshold', cond_left: 'Left value', then: 'True value', 'else_': 'False value', lo: 'Min', hi: 'Max', value: 'Value', left: 'Left operand', right: 'Right operand' };
const _labelFromPath = path => {
  if (!path) return 'Value';
  const last = path.split('.').pop();
  return _PATH_LABELS[last] || last.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};
const _OPERAND_NUMERIC_PARAMS = ['period', 'fast', 'slow', 'signal', 'std_dev'];

function getEditableParams(expr, path = '') {
  const kind = expr?.node;
  const results = [];
  if (kind === 'const') {
    const k = path || 'value';
    results.push({ path: k, label: _labelFromPath(path), defaultValue: Number(expr.value), paramType: 'float' });
  } else if (kind === 'operand') {
    const op = expr.operand || {};
    const opType = (op.type || 'operand').toUpperCase();
    for (const param of _OPERAND_NUMERIC_PARAMS) {
      if (param in op) {
        results.push({ path: _pfx(path, `operand.${param}`), label: `${opType} ${param.replace(/_/g, ' ')}`, defaultValue: Number(op[param]), paramType: param === 'std_dev' ? 'float' : 'int' });
      }
    }
  } else if (kind === 'binop') {
    results.push(...getEditableParams(expr.left,  _pfx(path, 'left')));
    results.push(...getEditableParams(expr.right, _pfx(path, 'right')));
  } else if (kind === 'unop') {
    results.push(...getEditableParams(expr.operand, _pfx(path, 'operand')));
  } else if (kind === 'clamp') {
    results.push(...getEditableParams(expr.value, _pfx(path, 'value')));
    results.push(...getEditableParams(expr.lo,    _pfx(path, 'lo')));
    results.push(...getEditableParams(expr.hi,    _pfx(path, 'hi')));
  } else if (kind === 'ifelse') {
    results.push(...getEditableParams(expr.cond_left,  _pfx(path, 'cond_left')));
    results.push(...getEditableParams(expr.cond_right, _pfx(path, 'cond_right')));
    results.push(...getEditableParams(expr.then,       _pfx(path, 'then')));
    results.push(...getEditableParams(expr['else_'],   _pfx(path, 'else_')));
  }
  return results;
}

// ─── Signal preset blocks ─────────────────────────────────────────────────────
const SIGNAL_BLOCKS = [
  {
    category: "Price Conditions",
    color: "#22d3ee",
    items: [
      { id: 'price_above_value', emoji: '📈', label: 'Price is above a value',        desc: 'Trigger when price exceeds a fixed number',
        left: { type: 'price', field: 'close' }, operator: '>', right: { type: 'constant', value: 0 } },
      { id: 'price_below_value', emoji: '📉', label: 'Price is below a value',        desc: 'Trigger when price drops under a threshold',
        left: { type: 'price', field: 'close' }, operator: '<', right: { type: 'constant', value: 0 } },
      { id: 'price_change_up',   emoji: '🚀', label: 'Price rose vs N bars ago',      desc: 'Detect recent upward movement',
        left: { type: 'price', field: 'close' }, operator: '>', right: { type: 'lookback', field: 'close', period: 1 } },
      { id: 'price_change_down', emoji: '🪂', label: 'Price fell vs N bars ago',      desc: 'Detect recent downward movement',
        left: { type: 'price', field: 'close' }, operator: '<', right: { type: 'lookback', field: 'close', period: 1 } },
    ]
  },
  {
    category: "Moving Averages",
    color: "#34d399",
    items: [
      { id: 'price_above_sma',  emoji: '〰️', label: 'Price above SMA',                  desc: 'Price above a simple moving average — bullish',
        left: { type: 'price', field: 'close' }, operator: '>', right: { type: 'sma', field: 'close', period: 20 } },
      { id: 'price_below_sma',  emoji: '〰️', label: 'Price below SMA',                  desc: 'Price below a moving average — bearish',
        left: { type: 'price', field: 'close' }, operator: '<', right: { type: 'sma', field: 'close', period: 20 } },
      { id: 'sma_cross_above',  emoji: '✂️', label: 'Fast SMA crosses above Slow SMA', desc: 'Golden cross — bullish momentum shift',
        left: { type: 'sma', field: 'close', period: 10 }, operator: 'cross_above', right: { type: 'sma', field: 'close', period: 50 } },
      { id: 'sma_cross_below',  emoji: '✂️', label: 'Fast SMA crosses below Slow SMA', desc: 'Death cross — bearish momentum shift',
        left: { type: 'sma', field: 'close', period: 10 }, operator: 'cross_below', right: { type: 'sma', field: 'close', period: 50 } },
      { id: 'ema_cross_above',  emoji: '⚡', label: 'Fast EMA crosses above Slow EMA', desc: 'Fast-reacting golden cross',
        left: { type: 'ema', field: 'close', period: 9 }, operator: 'cross_above', right: { type: 'ema', field: 'close', period: 21 } },
    ]
  },
  {
    category: "RSI",
    color: "#a78bfa",
    items: [
      { id: 'rsi_oversold',   emoji: '🔻', label: 'RSI below 30 (Oversold)',   desc: 'Potential bounce — asset may be oversold',
        left: { type: 'rsi', field: 'close', period: 14 }, operator: '<', right: { type: 'constant', value: 30 } },
      { id: 'rsi_overbought', emoji: '🔺', label: 'RSI above 70 (Overbought)', desc: 'Potential pullback — asset may be overbought',
        left: { type: 'rsi', field: 'close', period: 14 }, operator: '>', right: { type: 'constant', value: 70 } },
      { id: 'rsi_custom',     emoji: '🎛️', label: 'RSI vs custom value',       desc: 'Compare RSI to any number you choose',
        left: { type: 'rsi', field: 'close', period: 14 }, operator: '>', right: { type: 'constant', value: 50 } },
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
        left: { type: 'price', field: 'close' }, operator: '<', right: { type: 'bollinger', field: 'close', period: 20, std_dev: 2, component: 'lower' } },
      { id: 'bb_upper', emoji: '⬆️', label: 'Price above Upper Band', desc: 'Near upper band — potential reversal',
        left: { type: 'price', field: 'close' }, operator: '>', right: { type: 'bollinger', field: 'close', period: 20, std_dev: 2, component: 'upper' } },
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
  {
    category: "Time-Based Signals",
    color: "#818cf8",
    items: [
      { id: 'after_time',  emoji: '⏰', label: 'After a specific time',  desc: 'Signal fires only at or after this time of day (UTC)',
        left: { type: 'time_of_day' }, operator: '>=', right: { type: 'constant', value: 570 } },
      { id: 'before_time', emoji: '⌚', label: 'Before a specific time', desc: 'Signal fires only before this time of day (UTC)',
        left: { type: 'time_of_day' }, operator: '<',  right: { type: 'constant', value: 960 } },
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
      { id: 'stop_loss_pct',   emoji: '🛑', label: 'Stop loss at -X%',       desc: 'Exit when position loss reaches this percentage',
        kind: 'exit_condition', exitType: 'stop_loss_pct', value: 3 },
      { id: 'take_profit_abs', emoji: '💵', label: 'Take profit at +$X',     desc: 'Exit when absolute profit reaches this $ value',
        kind: 'exit_condition', exitType: 'take_profit_abs', value: 500 },
      { id: 'stop_loss_abs',   emoji: '💸', label: 'Stop loss at -$X',       desc: 'Exit when absolute loss reaches this $ value',
        kind: 'exit_condition', exitType: 'stop_loss_abs', value: 200 },
    ]
  },
  {
    category: "Time-Based",
    color: "#22d3ee",
    items: [
      { id: 'bars_held',   emoji: '⏱️', label: 'After N bars in trade',        desc: 'Exit after being in the position for N candles',
        kind: 'exit_condition', exitType: 'bars_held', value: 10 },
      { id: 'time_of_day', emoji: '🕐', label: 'At a specific hour (UTC)',     desc: 'Trigger at a certain hour of the day (0-23)',
        kind: 'exit_condition', exitType: 'time_of_day', value: 16 },
      { id: 'day_of_week', emoji: '📅', label: 'On a specific day of the week', desc: 'Trigger only on Mon / Tue / etc.',
        kind: 'exit_condition', exitType: 'day_of_week', value: 5 }, // ISO: 5=Friday
    ]
  },
];

const DOW = [null,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']; // ISO weekday: 1=Mon..7=Sun

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

// ─── i18n category key map ────────────────────────────────────────────────────
const _CAT_KEYS = {
  'Price Conditions':  'sigCatPriceConditions',
  'Moving Averages':   'sigCatMovingAverages',
  'RSI':               'sigCatRSI',
  'MACD':              'sigCatMACD',
  'Bollinger Bands':   'sigCatBollingerBands',
  'Volume':            'sigCatVolume',
  'Time-Based Signals':'sigCatTimeBasedSignals',
  'Profit & Loss':     'exitCatProfitLoss',
  'Time-Based':        'exitCatTimeBased',
};

const getSignalBlocks = t => SIGNAL_BLOCKS.map(cat => ({
  ...cat,
  category: t(`strategy.${_CAT_KEYS[cat.category]}`, { defaultValue: cat.category }),
  items: cat.items.map(item => ({
    ...item,
    label: t(`strategy.sigLabel_${item.id}`, { defaultValue: item.label }),
    desc:  t(`strategy.sigDesc_${item.id}`,  { defaultValue: item.desc }),
  })),
}));

const getExitBlocks = t => EXIT_BLOCKS.map(cat => ({
  ...cat,
  category: t(`strategy.${_CAT_KEYS[cat.category]}`, { defaultValue: cat.category }),
  items: cat.items.map(item => ({
    ...item,
    label: t(`strategy.exitLabel_${item.id}`, { defaultValue: item.label }),
    desc:  t(`strategy.exitDesc_${item.id}`,  { defaultValue: item.desc }),
  })),
}));

const getRoles = t => [
  { value: 'entry_long',  label: t('strategy.buyLong'),        color: '#34d399', bg: 'rgba(52,211,153,0.12)',  border: 'rgba(52,211,153,0.4)'  },
  { value: 'exit_long',   label: t('strategy.sellLong'),       color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.4)' },
  { value: 'entry_short', label: t('strategy.enterShort'),     color: '#fb923c', bg: 'rgba(251,146,60,0.12)',  border: 'rgba(251,146,60,0.4)'  },
  { value: 'exit_short',  label: t('strategy.exitShortLabel'), color: '#a78bfa', bg: 'rgba(167,139,250,0.12)', border: 'rgba(167,139,250,0.4)' },
];

const getOperators = t => [
  { value: '>',           label: t('strategy.opGt') },
  { value: '>=',          label: t('strategy.opGte') },
  { value: '<',           label: t('strategy.opLt') },
  { value: '<=',          label: t('strategy.opLte') },
  { value: '==',          label: t('strategy.opEq') },
  { value: '!=',          label: t('strategy.opNeq') },
  { value: 'cross_above', label: t('strategy.opCrossAbove') },
  { value: 'cross_below', label: t('strategy.opCrossBelow') },
];

const getDow = t => [null,
  t('strategy.dowMon'), t('strategy.dowTue'), t('strategy.dowWed'),
  t('strategy.dowThu'), t('strategy.dowFri'), t('strategy.dowSat'), t('strategy.dowSun'),
];

let _uid = 1;
const uid = () => String(_uid++);

function defaultCondition(template) {
  if (template?.kind === 'exit_condition') return { _id: uid(), kind: 'exit_condition', exitType: template.exitType, value: template.value, templateId: template.id, combiner: 'and' };
  return { _id: uid(), kind: 'signal', left: { ...(template?.left ?? { type: 'price', field: 'close' }) }, operator: template?.operator ?? '>', right: { ...(template?.right ?? { type: 'constant', value: 0 }) }, templateId: template?.id ?? null, combiner: 'and' };
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

function validateRules(rules, t) {
  const warnings = [];
  const roleMap = {};
  rules.forEach(r => { roleMap[r.role] = (roleMap[r.role] || 0) + 1; });
  if (roleMap['entry_long']  && !roleMap['exit_long'])   warnings.push(t('strategy.warnBuyNoSell'));
  if (roleMap['exit_long']   && !roleMap['entry_long'])  warnings.push(t('strategy.warnSellNoBuy'));
  if (roleMap['entry_short'] && !roleMap['exit_short'])  warnings.push(t('strategy.warnShortNoExit'));
  if (roleMap['exit_short']  && !roleMap['entry_short']) warnings.push(t('strategy.warnExitNoShort'));
  rules.forEach(r => { if (r.conditions.length === 0) warnings.push(t('strategy.warnNoConditions', { name: r.name })); });
  return warnings;
}

function inflateStrategyConfig(configStr) {
  try {
    const parsed = typeof configStr === 'string' ? JSON.parse(configStr) : configStr;
    const ruleSet = parsed.rule_set;
    if (!ruleSet) return null;
    return {
      name: ruleSet.name || 'Loaded Strategy',
      rules: (ruleSet.rules || []).map(r => ({
        _id: uid(),
        name: r.name || 'Rule',
        role: r.role || 'entry_long',
        conditions: (r.conditions || []).map(c => ({ _id: uid(), ...c })),
        timing: r.timing || 'on_change',
        quantity: r.quantity ?? 1,
      })),
    };
  } catch {
    return null;
  }
}

const iStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 6, padding: '4px 9px', color: '#e5e7eb', fontSize: '0.83rem', width: 75, outline: 'none' };
const sStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 6, padding: '4px 9px', color: '#e5e7eb', fontSize: '0.83rem', outline: 'none' };
const PRICE_FIELDS = ['close','high','low','volume'];

function OperandEditor({ operand, onChange, label, isTimeSide }) {
  const { t } = useTranslation();
  const TYPES = ['price','lookback','sma','ema','rsi','macd','bollinger','highest_high','lowest_low','atr','typical_price','time_of_day','constant'];
  const TYPE_LABELS = {
    price:         t('strategy.typePrice'),
    lookback:      t('strategy.typeLookback'),
    sma:           t('strategy.typeSma'),
    ema:           t('strategy.typeEma'),
    rsi:           t('strategy.typeRsi'),
    macd:          t('strategy.typeMacd'),
    bollinger:     t('strategy.typeBollinger'),
    highest_high:  t('strategy.typeHighestHigh'),
    lowest_low:    t('strategy.typeLowestLow'),
    atr:           t('strategy.typeAtr'),
    typical_price: t('strategy.typeTypicalPrice'),
    time_of_day:   t('strategy.typeTimeOfDay'),
    constant:      t('strategy.typeConstant'),
  };
  const set = (k, v) => onChange({ ...operand, [k]: v });
  return (
    <div style={{ background: '#0b1120', border: '1px solid #1e293b', borderRadius: 10, padding: '10px 14px' }}>
      <div style={{ fontSize: '0.67rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 8 }}>{label}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <select value={operand?.type || 'price'} style={sStyle} onChange={e => {
          const t = e.target.value;
          const defaults = { type: t, field: t === 'highest_high' ? 'high' : t === 'lowest_low' ? 'low' : 'close', period: t === 'bollinger' ? 20 : 14, value: 0, ...(t === 'bollinger' ? { std_dev: 2, component: 'upper' } : {}), ...(t === 'macd' ? { fast: 12, slow: 26, signal: 9, component: 'macd' } : {}) };
          onChange(defaults);
        }}>
          {TYPES.map(t => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
        </select>
        {operand?.type === 'constant' && !isTimeSide && <input type="number" value={operand.value ?? 0} style={iStyle} onChange={e => set('value', parseFloat(e.target.value) || 0)} />}
        {operand?.type === 'constant' && isTimeSide && (
          <input type="time" value={minutesToTime(operand.value ?? 0)} style={{ ...iStyle, width: 90 }}
            onChange={e => set('value', timeToMinutes(e.target.value))} />
        )}
        {operand?.type === 'time_of_day' && <span style={{ fontSize: '0.74rem', color: '#818cf8' }}>{t('strategy.minutesSinceMidnight')}</span>}
        {['price','lookback','sma','ema','rsi','bollinger','highest_high','lowest_low'].includes(operand?.type) && (
          <select value={operand.field || 'close'} style={sStyle} onChange={e => set('field', e.target.value)}>
            {PRICE_FIELDS.map(f => <option key={f}>{f}</option>)}
          </select>
        )}
        {['lookback','sma','ema','rsi','highest_high','lowest_low','atr'].includes(operand?.type) && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ fontSize: '0.74rem', color: '#9ca3af' }}>{operand.type === 'lookback' ? t('strategy.barsAgo') : t('strategy.period')}</span>
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
  const { t } = useTranslation();
  const meta = {
    take_profit_pct: { pre: t('strategy.exitMeta_take_profit_pct_pre'), suf: t('strategy.exitMeta_take_profit_pct_suf'), min: 0.1, step: 0.1 },
    stop_loss_pct:   { pre: t('strategy.exitMeta_stop_loss_pct_pre'),   suf: t('strategy.exitMeta_stop_loss_pct_suf'),   min: 0.1, step: 0.1 },
    take_profit_abs: { pre: t('strategy.exitMeta_take_profit_abs_pre'), suf: t('strategy.exitMeta_take_profit_abs_suf'), min: 1,   step: 1 },
    stop_loss_abs:   { pre: t('strategy.exitMeta_stop_loss_abs_pre'),   suf: t('strategy.exitMeta_stop_loss_abs_suf'),   min: 1,   step: 1 },
    bars_held:       { pre: t('strategy.exitMeta_bars_held_pre'),       suf: t('strategy.exitMeta_bars_held_suf'),       min: 1,   step: 1 },
    time_of_day:     { pre: t('strategy.exitMeta_time_of_day_pre'),     suf: t('strategy.exitMeta_time_of_day_suf'),     min: 0,   step: 1, max: 23 },
    day_of_week:     { pre: t('strategy.exitMeta_day_of_week_pre'),     suf: '',                                         isDow: true },
  }[cond.exitType] || { pre: 'Value:', suf: '', min: 0, step: 1 };

  const dow = getDow(t);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
      <span style={{ fontSize: '0.85rem', color: '#9ca3af' }}>{meta.pre}</span>
      {meta.isDow ? (
        <select value={cond.value} style={sStyle} onChange={e => onChange({ ...cond, value: parseInt(e.target.value) })}>
          {dow.map((d, i) => d && <option key={i} value={i}>{d}</option>)}
        </select>
      ) : (
        <input type="number" value={cond.value} min={meta.min} max={meta.max} step={meta.step} style={{ ...iStyle, width: 90 }}
          onChange={e => onChange({ ...cond, value: parseFloat(e.target.value) || 0 })} />
      )}
      {meta.suf && <span style={{ fontSize: '0.85rem', color: '#9ca3af' }}>{meta.suf}</span>}
    </div>
  );
}

function CustomOperandPanel({ operand, onChange, customIndicators, label = 'Left side' }) {
  const { t } = useTranslation();
  const ind = customIndicators.find(i => i.name === operand.name);
  const params = ind ? getEditableParams(ind.expr?.expr) : [];
  const overrides = operand.overrides || {};
  return (
    <div style={{ background: '#0b1120', border: '1px solid #1e293b', borderRadius: 10, padding: '10px 14px' }}>
      <div style={{ fontSize: '0.67rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 8 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: params.length ? 10 : 0 }}>
        <span style={{ fontSize: '0.9rem' }}>🔷</span>
        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#22d3ee' }}>{operand.name}</span>
        <span style={{ fontSize: '0.72rem', color: '#4b5563', marginLeft: 2 }}>{t('strategy.customIndicator')}</span>
      </div>
      {params.length === 0 && (
        <div style={{ fontSize: '0.75rem', color: '#6b7280', fontStyle: 'italic' }}>{t('strategy.noAdjustableParams')}</div>
      )}
      {params.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {params.map(p => (
            <label key={p.path} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ fontSize: '0.74rem', color: '#9ca3af' }}>{p.label}:</span>
              <input
                type="number"
                step={p.paramType === 'int' ? 1 : 0.01}
                value={overrides[p.path] ?? p.defaultValue}
                style={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 6, padding: '4px 9px', color: '#e5e7eb', fontSize: '0.83rem', width: 75, outline: 'none' }}
                onChange={e => {
                  const raw = e.target.value;
                  const v = p.paramType === 'int' ? (parseInt(raw) || p.defaultValue) : (parseFloat(raw) || p.defaultValue);
                  onChange({ ...operand, overrides: { ...overrides, [p.path]: v } });
                }}
              />
              {overrides[p.path] !== undefined && overrides[p.path] !== p.defaultValue && (
                <span style={{ fontSize: '0.68rem', color: '#6b7280' }}>{t('strategy.default', { value: p.defaultValue })}</span>
              )}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function ConditionCard({ cond, onChange, onRemove, total, showCombiner, customIndicators }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const signalBlocks = getSignalBlocks(t);
  const exitBlocks   = getExitBlocks(t);
  const allBlocks    = [...signalBlocks, ...exitBlocks];
  const allItems     = allBlocks.flatMap(c => c.items);
  const template     = allItems.find(i => i.id === cond.templateId);
  const catColor     = template ? allBlocks.find(c => c.items.some(i => i.id === cond.templateId))?.color : '#6b7280';
  const operators    = getOperators(t);
  const dow          = getDow(t);

  const timeLeft  = cond.left?.type  === 'time_of_day';
  const timeRight = cond.right?.type === 'time_of_day';

  const labelOp = (o, isTimePaired) => {
    if (!o) return '?';
    if (o.type === 'constant' && isTimePaired) return minutesToTime(o.value ?? 0);
    const m = {
      price:         o => t('strategy.condPrice', { field: o.field || 'close' }),
      lookback:      o => t('strategy.condLookback', { field: o.field || 'close', period: o.period || 1 }),
      sma:           o => `SMA(${o.period || 20})`,
      ema:           o => `EMA(${o.period || 20})`,
      rsi:           o => `RSI(${o.period || 14})`,
      macd:          o => `MACD ${o.component || ''}`,
      bollinger:     o => `BB ${o.component || ''}`,
      highest_high:  o => `HH(${o.period || 14})`,
      lowest_low:    o => `LL(${o.period || 14})`,
      atr:           o => `ATR(${o.period || 14})`,
      typical_price: () => t('strategy.condTypicalPrice'),
      time_of_day:   () => t('strategy.condTimeOfDay'),
      constant:      o => String(o.value ?? 0),
      custom: o => {
        const ov = o.overrides && Object.keys(o.overrides).length;
        const suffix = ov ? ` ${t(ov > 1 ? 'strategy.condOverrides' : 'strategy.condOverride', { count: ov })}` : '';
        return `🔷 ${o.name || '?'}${suffix}`;
      },
    };
    return (m[o.type] || (() => o.type))(o);
  };

  const summary = cond.kind === 'exit_condition'
    ? `${t(`strategy.exitLabel_${cond.exitType}`, { defaultValue: (cond.exitType || '').replace(/_/g, ' ') })} = ${cond.exitType === 'day_of_week' ? (dow[cond.value] || cond.value) : cond.value}`
    : `${labelOp(cond.left, timeRight)} ${operators.find(o => o.value === cond.operator)?.label ?? cond.operator} ${labelOp(cond.right, timeLeft)}`;

  return (
    <>
      {showCombiner && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '6px 0' }}>
          <div style={{ flex: 1, height: 1, background: '#1f2937' }} />
          <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.1em', color: '#22d3ee', padding: '2px 10px', background: 'rgba(34,211,238,0.1)', borderRadius: 999, border: '1px solid rgba(34,211,238,0.2)' }}>{t('strategy.andCombiner')}</span>
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
            onClick={() => setExpanded(e => !e)}>{expanded ? t('strategy.less') : t('strategy.edit')}</button>
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
                {cond.left?.type === 'custom'
                  ? <CustomOperandPanel operand={cond.left} onChange={v => onChange({ ...cond, left: v })} customIndicators={customIndicators} />
                  : <OperandEditor operand={cond.left} onChange={v => onChange({ ...cond, left: v })} label={t('strategy.leftSide')} isTimeSide={timeRight} />
                }
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ flex: 1, height: 1, background: '#1f2937' }} />
                  <select value={cond.operator} style={sStyle} onChange={e => onChange({ ...cond, operator: e.target.value })}>
                    {operators.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                  <div style={{ flex: 1, height: 1, background: '#1f2937' }} />
                </div>
                {cond.right?.type === 'custom'
                  ? <CustomOperandPanel operand={cond.right} onChange={v => onChange({ ...cond, right: v })} customIndicators={customIndicators} label="Right side" />
                  : <OperandEditor operand={cond.right} onChange={v => onChange({ ...cond, right: v })} label={t('strategy.rightSide')} isTimeSide={timeLeft} />
                }
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

function RuleEditor({ rule, onChange, onDelete, customIndicators }) {
  const { t } = useTranslation();
  const roles        = getRoles(t);
  const signalBlocks = getSignalBlocks(t);
  const exitBlocks   = getExitBlocks(t);
  const role = roles.find(r => r.value === rule.role);
  const [showPicker, setShowPicker] = useState(false);
  const [pickerTab, setPickerTab]   = useState('signal');
  const isExitRole = rule.role.startsWith('exit_');

  const addCondFromBlock = (item) => { onChange({ ...rule, conditions: [...rule.conditions, defaultCondition(item)] }); setShowPicker(false); };
  const addBlankCondition = () => { onChange({ ...rule, conditions: [...rule.conditions, defaultCondition()] }); setShowPicker(false); };
  const updateCond = (id, upd) => onChange({ ...rule, conditions: rule.conditions.map(c => c._id === id ? upd : c) });
  const removeCond = (id) => onChange({ ...rule, conditions: rule.conditions.filter(c => c._id !== id) });

  return (
    <div style={{ background: '#111827', border: '1px solid #1f2937', borderRadius: 16, overflow: 'hidden', boxShadow: '0 4px 20px rgba(0,0,0,0.3)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 20px', background: '#0f172a', borderBottom: '1px solid #1f2937', flexWrap: 'wrap', flexShrink: 0 }}>
        <input value={rule.name} onChange={e => onChange({ ...rule, name: e.target.value })}
          style={{ flex: 1, minWidth: 120, background: 'transparent', border: 'none', color: '#e5e7eb', fontSize: '1rem', fontWeight: 700, outline: 'none' }} />
        <select value={rule.role}
          style={{ ...sStyle, fontWeight: 700, color: role?.color, background: role?.bg, border: `1px solid ${role?.border}` }}
          onChange={e => onChange({ ...rule, role: e.target.value })}>
          {roles.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
        {onDelete && (
          <button type="button" onClick={onDelete}
            style={{ background: 'transparent', border: '1px solid #ef444455', borderRadius: 8, color: '#ef4444', cursor: 'pointer', padding: '5px 12px', fontSize: '0.78rem' }}>
            {t('common.delete')}
          </button>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '10px 20px', background: '#0b1120', borderBottom: '1px solid #1f2937', flexWrap: 'wrap', flexShrink: 0 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6b7280' }}>{t('strategy.fire')}</span>
          <select value={rule.timing} style={sStyle} onChange={e => onChange({ ...rule, timing: e.target.value })}>
            <option value="on_change">{t('strategy.onSignalChange')}</option>
            <option value="every_tick">{t('strategy.everyTick')}</option>
          </select>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6b7280' }}>{t('strategy.quantity')}</span>
          <input type="number" value={rule.quantity} min={0.01} step={0.01} style={iStyle}
            onChange={e => onChange({ ...rule, quantity: parseFloat(e.target.value) || 1 })} />
        </label>
      </div>

      <div style={{ padding: '16px 20px' }}>
        <div style={{ fontSize: '0.68rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 12 }}>
          {t('strategy.conditions')} {rule.conditions.length > 1 && <span style={{ color: '#4b5563', fontWeight: 400 }}>— {t('strategy.condCombiner')}</span>}
        </div>

        {rule.conditions.map((cond, idx) => (
          <ConditionCard key={cond._id}
            cond={cond}
            total={rule.conditions.length}
            showCombiner={idx > 0}
            onChange={u => updateCond(cond._id, u)}
            onRemove={() => removeCond(cond._id)}
            customIndicators={customIndicators}
          />
        ))}

        <div style={{ marginTop: 10 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button"
              style={{ flex: 1, background: '#0f172a', border: '1px dashed #334155', borderRadius: 10, padding: '10px', color: '#9ca3af', cursor: 'pointer', fontSize: '0.82rem', transition: 'all 0.2s' }}
              onMouseEnter={e => { e.currentTarget.style.borderColor='#22d3ee'; e.currentTarget.style.color='#22d3ee'; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor='#334155'; e.currentTarget.style.color='#9ca3af'; }}
              onClick={() => { setShowPicker(p=>!p); setPickerTab('signal'); }}>
              {t('strategy.signalCondition')}
            </button>
            <button type="button"
              style={{ flex: 1, background: '#0f172a', border: '1px dashed #34d39955', borderRadius: 10, padding: '10px', color: '#34d39988', cursor: 'pointer', fontSize: '0.82rem', transition: 'all 0.2s' }}
              onMouseEnter={e => { e.currentTarget.style.background='rgba(52,211,153,0.05)'; e.currentTarget.style.color='#34d399'; }}
              onMouseLeave={e => { e.currentTarget.style.background='#0f172a'; e.currentTarget.style.color='#34d39988'; }}
              onClick={() => { setShowPicker(p=>!p); setPickerTab('exit'); }}>
              {t('strategy.plExit')}
            </button>
            <button type="button"
              style={{ background: '#0f172a', border: '1px dashed #334155', borderRadius: 10, padding: '10px 14px', color: '#6b7280', cursor: 'pointer', fontSize: '0.82rem' }}
              onClick={addBlankCondition}>
              {t('strategy.blank')}
            </button>
          </div>

          {showPicker && (
            <div style={{ background: '#0f172a', border: '1px solid #1f2937', borderRadius: 14, padding: '12px', marginTop: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <div style={{ display: 'flex', gap: 4, background: '#111827', borderRadius: 8, padding: 3 }}>
                  {[{ id:'signal', label: t('strategy.pickerSignal') },{ id:'exit', label: t('strategy.pickerExit') }].map(tab => (
                    <button key={tab.id} type="button"
                      style={{ padding: '4px 12px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: '0.78rem', fontWeight: 700,
                        background: pickerTab===tab.id?'#1e293b':'transparent', color: pickerTab===tab.id?'#e5e7eb':'#6b7280' }}
                      onClick={() => setPickerTab(tab.id)}>{tab.label}</button>
                  ))}
                </div>
                <button type="button" style={{ background:'transparent', border:'none', color:'#6b7280', cursor:'pointer', fontSize:'1.1rem' }} onClick={() => setShowPicker(false)}>✕</button>
              </div>

              {pickerTab === 'signal' && signalBlocks.map(cat => (
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

              {pickerTab === 'exit' && exitBlocks.map(cat => (
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
                  <div style={{ fontSize: '0.67rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#22d3ee', marginBottom: 6 }}>{t('strategy.myCustomIndicators')}</div>
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
  const { t } = useTranslation();
  const [ruleSetName, setRuleSetName] = useState('My Strategy');
  const [rules, setRules]             = useState([defaultRule('entry_long'), defaultRule('exit_long')]);
  const [selectedRole, setSelectedRole] = useState('entry_long');
  const [activeId, setActiveId]       = useState(() => rules[0]?._id ?? null);
  const [saving, setSaving]           = useState(false);
  const [showJson, setShowJson]       = useState(false);
  const [customIndicators, setCIs]    = useState([]);
  const [mode, setMode]               = useState('build'); // 'build' | 'ai-strategy' | 'ai-indicator'
  const [aiGeneratedStrategy, setAiGeneratedStrategy] = useState(null);
  const [aiWarnings, setAiWarnings]   = useState([]);
  const [savedStrategies, setSavedStrategies] = useState([]);
  const [showLoad, setShowLoad]       = useState(false);
  const [loadedStrategyId, setLoadedStrategyId] = useState(null);
  const [loadedStrategyIsBuiltin, setLoadedStrategyIsBuiltin] = useState(false);

  useEffect(() => { fetch(`${API_BASE}/api/db/indicators`).then(r=>r.json()).then(d=>setCIs(d.indicators||[])).catch(()=>{}); }, []);
  useEffect(() => { fetch(`${API_BASE}/api/db/strategies`).then(r=>r.json()).then(d=>setSavedStrategies(d.strategies||[])).catch(()=>{}); }, []);

  // Auto-correct selectedRole whenever rules change: if selectedRole has no rules but others do, switch to the first available role
  useEffect(() => {
    if (rules.length > 0 && !rules.some(r => r.role === selectedRole)) {
      const first = rules[0];
      setSelectedRole(first.role);
      setActiveId(first._id);
    }
  }, [rules, selectedRole]);

  const addRule = (role = 'entry_long') => { const r = defaultRule(role); setRules(p=>[...p,r]); setActiveId(r._id); setSelectedRole(role); };
  const updateRule = useCallback(u => setRules(p => p.map(r => r._id===u._id?u:r)), []);
  const deleteRule = id => {
    const rest = rules.filter(r => r._id !== id);
    setRules(rest);
    if (activeId === id) {
      const currentRole = rules.find(r => r._id === id)?.role;
      const sameRoleRules = rest.filter(r => r.role === currentRole);
      setActiveId(sameRoleRules.length > 0 ? sameRoleRules[0]._id : (rest[0]?._id ?? null));
    }
  };

  // Handle AI-generated strategies
  const handleStrategyGenerated = (aiResult) => {
    setAiGeneratedStrategy(aiResult);
    setAiWarnings(aiResult.warnings || []);
  };

  const loadAiStrategyIntoBuilder = () => {
    if (!aiGeneratedStrategy) return;
    const convertedRules = (aiGeneratedStrategy.rules || []).map(r => ({
      _id: uid(),
      name: r.name,
      role: r.role,
      conditions: (r.conditions || []).map(c => ({ _id: uid(), ...c })),
      timing: r.timing || 'on_change',
      quantity: r.quantity || 1
    }));
    if (convertedRules.length > 0) {
      setRules(convertedRules);
      setRuleSetName(aiGeneratedStrategy.name || 'AI Strategy');
      setActiveId(convertedRules[0]._id);
      setSelectedRole(convertedRules[0].role);
    }
    setMode('build');
  };

  const saveAiStrategy = async () => {
    if (!aiGeneratedStrategy) return;
    try {
      const name = aiGeneratedStrategy.name || 'AI Strategy';
      const aiPayload = { name, rules: aiGeneratedStrategy.rules || [] };
      const aiConfigStr = JSON.stringify({ rule_set: aiPayload });
      await fetch(`${API_BASE}/api/db/strategies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategies: [{ name, logic: 'rule_based', config: aiConfigStr }] })
      });
      const fullEntry = { name, logic: 'rule_based', config: { rule_set: aiPayload } };
      setSavedStrategies(prev => {
        const idx = prev.findIndex(s => s.name === name);
        if (idx >= 0) { const next = [...prev]; next[idx] = fullEntry; return next; }
        return [...prev, fullEntry];
      });
      alert(t('strategy.strategySaved'));
    } catch { alert(t('strategy.failedSave')); }
  };

  const payload = ruleSetToJson(ruleSetName, rules);
  const warnings = validateRules(rules, t);
  const activeRule = rules.find(r => r._id === activeId);
  const rulesForRole = rules.filter(r => r.role === selectedRole);

  const save = async () => {
    if (rules.length === 0) {
      if (loadedStrategyId && !loadedStrategyIsBuiltin) {
        await deleteLoadedStrategy();
      }
      return;
    }
    setSaving(true);
    try {
      const configStr = JSON.stringify({ rule_set: payload });
      const r = await fetch(`${API_BASE}/api/db/strategies`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ strategies:[{ name:ruleSetName, logic:'rule_based', config:configStr }] }) });
      if (!r.ok) throw new Error('Save failed');
      // Re-fetch to get server-assigned id so delete works without a page refresh
      const fresh = await fetch(`${API_BASE}/api/db/strategies`).then(r => r.json());
      setSavedStrategies(fresh.strategies || []);
      const saved = (fresh.strategies || []).find(s => s.name === ruleSetName);
      if (saved?.id) setLoadedStrategyId(saved.id);
      alert(t('strategy.strategySaved'));
    } catch { alert(t('strategy.failedSave')); }
    finally { setSaving(false); }
  };

  const loadStrategy = (s) => {
    const inflated = inflateStrategyConfig(s.config);
    if (!inflated || !inflated.rules.length) { alert(t('strategy.couldNotLoad')); return; }
    setRuleSetName(inflated.name);
    setRules(inflated.rules);
    setActiveId(inflated.rules[0]._id);
    setSelectedRole(inflated.rules[0].role);
    setLoadedStrategyId(s.id ?? null);
    setLoadedStrategyIsBuiltin(!!s.is_builtin);
    setShowLoad(false);
    setMode('build');
  };

  const deleteLoadedStrategy = async () => {
    if (!loadedStrategyId) return;
    if (!window.confirm(t('strategy.deleteConfirm', { name: ruleSetName }))) return;
    await fetch(`${API_BASE}/api/db/strategies/${loadedStrategyId}`, { method: 'DELETE' });
    setSavedStrategies(prev => prev.filter(s => s.id !== loadedStrategyId));
    setLoadedStrategyId(null);
    setLoadedStrategyIsBuiltin(false);
    setRules([]);
    setRuleSetName('My Strategy');
  };

  const roleGroups = [
    { label: t('strategy.entryLong'),  color: '#34d399', role: 'entry_long',  description: t('strategy.entryLongDesc') },
    { label: t('strategy.exitLong'),   color: '#f87171', role: 'exit_long',   description: t('strategy.exitLongDesc') },
    { label: t('strategy.entryShort'), color: '#fb923c', role: 'entry_short', description: t('strategy.entryShortDesc') },
    { label: t('strategy.exitShort'),  color: '#a78bfa', role: 'exit_short',  description: t('strategy.exitShortDesc') },
  ];

  const pillStyle = { border: '1px solid #334155', borderRadius: 999, padding: '6px 14px', background: '#0f172a', color: '#9ca3af', cursor: 'pointer', fontSize: '0.82rem', transition: 'all 0.15s', outline: 'none', fontWeight: 500 };

  return (
    <div className="view">
      <h2>{t('strategy.title')}</h2>
      <p>{t('strategy.subtitle')}</p>

      {/* Mode selector */}
      <div className="tab-strip" style={{ margin: '1.5rem 0 1rem', width: 'fit-content' }}>
        <button className={`tab-btn${mode === 'build' ? ' active' : ''}`} onClick={() => setMode('build')}>
          {t('strategy.manualBuilder')}
        </button>
        <button className={`tab-btn${mode === 'ai-strategy' ? ' active' : ''}`} onClick={() => setMode('ai-strategy')}>
          {t('strategy.aiStrategy')}
        </button>
      </div>

      {/* AI Strategy Mode */}
      {mode === 'ai-strategy' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20, minHeight: 600 }}>
          <AIStrategyChat onStrategyGenerated={handleStrategyGenerated} />
          <div style={{ background: '#0b1120', border: '1px solid #1e293b', borderRadius: 12, padding: 16, overflow: 'auto' }}>
            {aiGeneratedStrategy ? (
              <>
                <div style={{ marginBottom: 16 }}>
                  <h3 style={{ fontSize: '1rem', color: '#e5e7eb', marginBottom: 8 }}>{t('strategy.generatedStrategy')}</h3>
                  <div style={{ fontSize: '0.85rem', color: '#9ca3af', marginBottom: 12 }}>
                    {t('strategy.name')}: <strong style={{ color: '#e5e7eb' }}>{aiGeneratedStrategy.name}</strong>
                  </div>
                  <div style={{ fontSize: '0.85rem', marginBottom: 16 }}>
                    {t('strategy.rules')}: <strong style={{ color: '#3b82f6' }}>{aiGeneratedStrategy.rules?.length || 0}</strong>
                  </div>
                </div>
                {aiWarnings.length > 0 && (
                  <div style={{ marginBottom: 16, padding: 12, background: 'rgba(245,158,11,0.08)', borderRadius: 8, border: '1px solid rgba(245,158,11,0.3)' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fbbf24', marginBottom: 8 }}>⚠️ Warnings:</div>
                    {aiWarnings.map((w, i) => (
                      <div key={i} style={{ fontSize: '0.8rem', color: '#fcd34d', marginBottom: 4 }}>• {w}</div>
                    ))}
                  </div>
                )}
                <pre style={{ background: '#000000', padding: 12, borderRadius: 8, color: '#93c5fd', fontSize: '0.7rem', overflow: 'auto', maxHeight: 260 }}>
                  {JSON.stringify(aiGeneratedStrategy, null, 2)}
                </pre>
                <button className="btn btn-primary" style={{ marginTop: 12, width: '100%' }}
                  onClick={saveAiStrategy}>
                  {t('strategy.saveStrategy')}
                </button>
                <button className="btn" style={{ marginTop: 8, width: '100%' }}
                  onClick={loadAiStrategyIntoBuilder}>
                  {t('strategy.editInBuilder')}
                </button>
              </>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#4b5563' }}>
                {t('strategy.generatedWillAppear')}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Manual Builder Mode */}
      {mode === 'build' && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '1.5rem 0 1rem', flexWrap: 'wrap' }}>
            <input value={ruleSetName} onChange={e => setRuleSetName(e.target.value)}
              style={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 10, padding: '7px 14px', color: '#e5e7eb', fontSize: '1rem', fontWeight: 700, outline: 'none', minWidth: 160 }} />
            <button type="button" style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, padding: '7px 14px', color: '#9ca3af', cursor: 'pointer', fontSize: '0.82rem' }}
              onClick={() => setShowJson(s=>!s)}>{showJson ? t('strategy.hideJson') : t('strategy.viewJson')}</button>

            {/* Load Strategy dropdown */}
            <div style={{ position: 'relative' }}>
              <button type="button"
                style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, padding: '7px 14px', color: '#9ca3af', cursor: 'pointer', fontSize: '0.82rem' }}
                onClick={() => setShowLoad(s => !s)}>
                {t('strategy.loadStrategy')}
              </button>
              {showLoad && (
                <div style={{ position: 'absolute', zIndex: 50, top: 'calc(100% + 4px)', left: 0, background: '#0f172a', border: '1px solid #1f2937', borderRadius: 12, padding: '6px', minWidth: 240, maxHeight: 320, overflowY: 'auto', boxShadow: '0 16px 48px rgba(0,0,0,0.7)' }}>
                  <div style={{ fontSize: '0.67rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6b7280', padding: '4px 8px 8px' }}>{t('strategy.savedStrategies')}</div>
                  {savedStrategies.length === 0 ? (
                    <div style={{ padding: '8px 12px', fontSize: '0.82rem', color: '#4b5563' }}>{t('strategy.noStrategiesSaved')}</div>
                  ) : savedStrategies.map((s, i) => (
                    <div key={s.id ?? i}
                      style={{ padding: '8px 12px', borderRadius: 8, cursor: 'pointer', fontSize: '0.85rem', color: '#e5e7eb', transition: 'background 0.15s' }}
                      onMouseEnter={e => e.currentTarget.style.background = '#1f2937'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      onClick={() => loadStrategy(s)}>
                      {s.name}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
              {loadedStrategyId && !loadedStrategyIsBuiltin && (
                <button type="button" className="btn btn-danger btn-pill" onClick={deleteLoadedStrategy}>
                  {t('strategy.deleteStrategy')}
                </button>
              )}
              <button type="button" className="btn btn-primary btn-pill"
                onClick={save} disabled={saving}>{saving ? <><span className="spinner" /> {t('common.saving')}</> : t('strategy.saveStrategy')}</button>
            </div>
          </div>

          {rules.length === 0 ? (
            <div style={{ background: '#111827', border: '1px solid #1f2937', borderRadius: 16, padding: '3rem 2rem', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 300, color: '#4b5563', gap: 16, marginTop: '1.5rem' }}>
              <span style={{ fontSize: '2.5rem' }}>◇</span>
              <span style={{ fontSize: '1rem' }}>{t('strategy.noRulesYet')}</span>
              <div style={{ display: 'flex', gap: 10 }}>
                <button type="button" onClick={() => addRule('entry_long')}
                  style={{ padding: '8px 18px', background: 'linear-gradient(135deg,#34d399,#22d3ee)', border: 'none', borderRadius: 8, color: '#0f172a', fontWeight: 700, cursor: 'pointer', fontSize: '0.9rem' }}>
                  {t('strategy.entryRule')}
                </button>
                <button type="button" onClick={() => addRule('exit_long')}
                  style={{ padding: '8px 18px', background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#9ca3af', cursor: 'pointer', fontSize: '0.9rem' }}>
                  {t('strategy.exitRule')}
                </button>
              </div>
            </div>
          ) : (<>

          {warnings.map((w, i) => (
            <div key={i} className="alert alert-warn" style={{ marginBottom: 8 }}>⚠️ {w}</div>
          ))}

          {showJson && (
            <div style={{ background: '#0b1120', border: '1px dashed #334155', borderRadius: 12, padding: '1rem', marginBottom: 16, overflow: 'auto' }}>
              <pre style={{ margin: 0, fontSize: '0.75rem', color: '#93c5fd', fontFamily: 'ui-monospace, monospace' }}>{JSON.stringify(payload, null, 2)}</pre>
            </div>
          )}

          {/* Role selector pills */}
          <div style={{ display: 'flex', gap: 8, margin: '1.5rem 0 1.5rem', flexWrap: 'wrap' }}>
            {roleGroups.map(g => {
              const count = rules.filter(r => r.role === g.role).length;
              return (
                <button key={g.role}
                  onClick={() => { setSelectedRole(g.role); const first = rules.find(r => r.role === g.role); if(first) setActiveId(first._id); }}
                  style={{ 
                    ...pillStyle,
                    background: selectedRole === g.role ? `${g.color}22` : '#0f172a',
                    borderColor: selectedRole === g.role ? g.color : '#334155',
                    color: selectedRole === g.role ? g.color : '#9ca3af',
                  }}>
                  {g.label} <span style={{ fontSize: '0.7rem', marginLeft: 6, opacity: 0.7 }}>({count})</span>
                </button>
              );
            })}
          </div>

          {/* Main canvas area */}
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 16 }}>
            {rulesForRole.length === 0 ? (
              <div style={{ 
                background: '#111827', 
                border: '1px solid #1f2937', 
                borderRadius: 16, 
                padding: '3rem 2rem',
                display: 'flex', 
                flexDirection: 'column', 
                alignItems: 'center', 
                justifyContent: 'center', 
                minHeight: 300,
                color: '#4b5563', 
                gap: 12 
              }}>
                <span style={{ fontSize: '2.5rem' }}>◇</span>
                <span style={{ fontSize: '1rem' }}>{t('strategy.noRulesForRole')}</span>
                <button type="button"
                  onClick={() => addRule(selectedRole)}
                  style={{
                    marginTop: 12,
                    padding: '8px 16px',
                    background: 'linear-gradient(135deg, #6366f1, #22d3ee)',
                    border: 'none',
                    borderRadius: 8,
                    color: '#0f172a',
                    fontWeight: 700,
                    cursor: 'pointer',
                    fontSize: '0.9rem'
                  }}>
                  {t('strategy.createRule')}
                </button>
              </div>
            ) : (
              <div>
                {rulesForRole.map((r, idx) => (
                  <div key={r._id}>
                    {idx > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '12px 0' }}>
                        <div style={{ flex: 1, height: 1, background: '#1f2937' }} />
                        <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.1em', color: '#fb923c', padding: '2px 10px', background: 'rgba(251,146,60,0.1)', borderRadius: 999, border: '1px solid rgba(251,146,60,0.2)' }}>{t('strategy.orCombiner')}</span>
                        <div style={{ flex: 1, height: 1, background: '#1f2937' }} />
                      </div>
                    )}
                    <RuleEditor
                      rule={r}
                      onChange={updateRule}
                      onDelete={rulesForRole.length > 1 ? () => deleteRule(r._id) : null}
                      customIndicators={customIndicators}
                    />
                  </div>
                ))}
                <button type="button" className="btn" onClick={() => addRule(selectedRole)}
                  style={{ width: '100%', marginTop: 16, borderStyle: 'dashed' }}>
                  {t('strategy.addAnotherRule')}
                </button>
              </div>
            )}
          </div>
          </>)}
        </>
      )}
    </div>
  );
}