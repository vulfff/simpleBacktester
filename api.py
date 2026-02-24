from __future__ import annotations

import json
import os
import base64
import tempfile
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from actionmanager import ActionManager
from csvparser import CSVTickDataFeed
from engine import BacktestEngine
from portfolio import Portfolio
from strategy import create_strategy, list_strategies

app = FastAPI(title="Backtester API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BacktestRequest(BaseModel):
    csv_path: str
    column_map: Dict[str, str]
    symbol: Optional[str] = None
    time_format: Optional[str] = None
    strategy_name: str
    strategy_config: Dict[str, Any] = Field(default_factory=dict)
    starting_cash: float = 0.0


class BacktestResult(BaseModel):
    cash: float
    asset_value: float
    total_value: float
    positions: Dict[str, float]
    last_prices: Dict[str, float]


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/strategies")
def strategies() -> Dict[str, Any]:
    return {"strategies": list_strategies()}


@app.post("/backtest", response_model=BacktestResult)
def backtest(request: BacktestRequest) -> BacktestResult:
    return _run_backtest(
        csv_path=request.csv_path,
        column_map=request.column_map,
        symbol=request.symbol,
        time_format=request.time_format,
        strategy_name=request.strategy_name,
        strategy_config=request.strategy_config,
        starting_cash=request.starting_cash,
    )


@app.post("/backtest/upload", response_model=BacktestResult)
def backtest_upload(
    file: UploadFile = File(...),
    column_map: str = Form(...),
    strategy_name: str = Form(...),
    strategy_config: str = Form("{}"),
    symbol: Optional[str] = Form(None),
    time_format: Optional[str] = Form(None),
    starting_cash: float = Form(0.0),
) -> BacktestResult:
    try:
        column_map_dict = json.loads(column_map)
        strategy_config_dict = json.loads(strategy_config)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as handle:
            temp_path = handle.name
            handle.write(file.file.read())

        return _run_backtest(
            csv_path=temp_path,
            column_map=column_map_dict,
            symbol=symbol,
            time_format=time_format,
            strategy_name=strategy_name,
            strategy_config=strategy_config_dict,
            starting_cash=starting_cash,
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _run_backtest(
    csv_path: str,
    column_map: Dict[str, str],
    symbol: Optional[str],
    time_format: Optional[str],
    strategy_name: str,
    strategy_config: Dict[str, Any],
    starting_cash: float,
) -> BacktestResult:
    try:
        strategy = create_strategy(strategy_name, strategy_config)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    feed = CSVTickDataFeed(
        file_path=csv_path,
        column_map=column_map,
        symbol=symbol,
        time_format=time_format,
    )

    portfolio = Portfolio(starting_cash=starting_cash, cash=starting_cash)
    engine = BacktestEngine(
        data_feed=feed,
        strategy=strategy,
        action_manager=ActionManager(),
        portfolio=portfolio,
    )
    engine.run()

    return BacktestResult(
        cash=portfolio.cash,
        asset_value=portfolio.asset_value,
        total_value=portfolio.total_value(),
        positions=portfolio.positions,
        last_prices=portfolio.last_prices,
    )


from db import get_db_conn, create_tables, encrypt_with_password, decrypt_with_password


# ensure DB schema exists
create_tables()


@app.post('/keys/encrypt')
def keys_encrypt(payload: Dict[str, str]):
    pwd = payload.get('password')
    if not pwd:
        raise HTTPException(status_code=400, detail='Password required')
    data = payload.get('dataKey', '')
    model = payload.get('modelKey', '')
    return {'dataKey': encrypt_with_password(pwd, data), 'modelKey': encrypt_with_password(pwd, model)}


@app.post('/keys/decrypt')
def keys_decrypt(payload: Dict[str, str]):
    pwd = payload.get('password')
    if not pwd:
        raise HTTPException(status_code=400, detail='Password required')
    enc_data = payload.get('dataKey', '')
    enc_model = payload.get('modelKey', '')
    try:
        return {'dataKey': decrypt_with_password(pwd, enc_data), 'modelKey': decrypt_with_password(pwd, enc_model)}
    except ValueError:
        raise HTTPException(status_code=400, detail='Decryption failed')


@app.get('/db/strategies')
def db_get_strategies():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('SELECT id, name, logic, config FROM strategies ORDER BY id')
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {'strategies': rows}


@app.post('/db/strategies')
def db_post_strategies(payload: Dict[str, List[Dict[str, Any]]]):
    arr = payload.get('strategies', [])
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM strategies')
    for s in arr:
        cur.execute('INSERT INTO strategies (id, name, logic, config) VALUES (?, ?, ?, ?)',
                    (s.get('id'), s.get('name'), s.get('logic'), json.dumps(s.get('config') if isinstance(s.get('config'), dict) else s.get('config'))))
    conn.commit()
    conn.close()
    return {'status': 'ok', 'count': len(arr)}


@app.get('/db/indicators')
def db_get_indicators():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('SELECT id, name, expression FROM indicators ORDER BY id')
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {'indicators': rows}


@app.post('/db/indicators')
def db_post_indicators(payload: Dict[str, List[Dict[str, Any]]]):
    arr = payload.get('indicators', [])
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM indicators')
    for ind in arr:
        cur.execute('INSERT INTO indicators (id, name, expression) VALUES (?, ?, ?)',
                    (ind.get('id'), ind.get('name'), ind.get('expression')))
    conn.commit()
    conn.close()
    return {'status': 'ok', 'count': len(arr)}


@app.get('/db/api_keys')
def db_get_api_keys():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('SELECT id, service, model_name, data_key, model_key, protected FROM api_keys ORDER BY id LIMIT 1')
    row = cur.fetchone()
    conn.close()
    if not row:
        return {'api_key': None}
    return {'api_key': dict(row)}


@app.post('/db/api_keys')
def db_post_api_keys(payload: Dict[str, Any]):
    # payload: {service, model_name, dataKey, modelKey, protected(bool), password(optional)}
    service = payload.get('service', '')
    model_name = payload.get('model_name', '')
    data_key = payload.get('dataKey', '')
    model_key = payload.get('modelKey', '')
    protected = bool(payload.get('protected'))
    password = payload.get('password')

    if protected:
        if not password:
            raise HTTPException(status_code=400, detail='Password required to protect keys')
        # encrypt server-side
        data_key_enc = encrypt_with_password(password, data_key)
        model_key_enc = encrypt_with_password(password, model_key)
    else:
        data_key_enc = base64.b64encode(data_key.encode()).decode()
        model_key_enc = base64.b64encode(model_key.encode()).decode()

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM api_keys')
    cur.execute('INSERT INTO api_keys (service, model_name, data_key, model_key, protected) VALUES (?, ?, ?, ?, ?)',
                (service, model_name, data_key_enc, model_key_enc, 1 if protected else 0))
    conn.commit()
    conn.close()
    return {'status': 'ok'}