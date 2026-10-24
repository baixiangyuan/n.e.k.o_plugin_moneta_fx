"""MONETA FX — N.E.K.O. plugin entry class.

Ports the MONETA FX fictional forex room into a normal ``plugin`` package:
a shared invented market, multi-account trading with margin/swap/liquidation,
a developer market-control console, and a Hosted TSX terminal.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from plugin.sdk.plugin import (
    Err,
    NekoPluginBase,
    Ok,
    SdkError,
    lifecycle,
    neko_plugin,
    plugin_entry,
    timer_interval,
    tr,
    ui,
)

try:  # 作为插件包导入（plugin.plugins.moneta_fx）
    from .auth import SESSION_COOKIE as SESSION_COOKIE
    from .engine import (
        LEVERAGE_CHOICES as LEVERAGE_CHOICES,
    )
    from .engine import (
        TradeError as TradeError,
    )
    from .engine import (
        estimate_order as estimate_order,
    )
    from .engine import (
        metrics as metrics,
    )
    from .engine import (
        validate_settings as validate_settings,
    )
    from .market import (
        MAJORS as MAJORS,
    )
    from .market import (
        OFFLINE_SYMBOLS as OFFLINE_SYMBOLS,
    )
    from .market import (
        WATCHLIST as WATCHLIST,
    )
    from .market import (
        digits as digits,
    )
    from .market import (
        pip_size as pip_size,
    )
    from .market import (
        symbol_name as symbol_name,
    )
    from .world import MarketRuntime as MarketRuntime
    from .world import Session as Session
except ImportError:  # 平铺导入（本地测试、云端服务端）
    from auth import SESSION_COOKIE as SESSION_COOKIE  # type: ignore
    from engine import (  # type: ignore
        LEVERAGE_CHOICES as LEVERAGE_CHOICES,
    )
    from engine import (
        TradeError as TradeError,
    )
    from engine import (
        estimate_order as estimate_order,
    )
    from engine import (
        metrics as metrics,
    )
    from engine import (
        validate_settings as validate_settings,
    )
    from market import (  # type: ignore
        MAJORS as MAJORS,
    )
    from market import (
        OFFLINE_SYMBOLS as OFFLINE_SYMBOLS,
    )
    from market import (
        WATCHLIST as WATCHLIST,
    )
    from market import (
        digits as digits,
    )
    from market import (
        pip_size as pip_size,
    )
    from market import (
        symbol_name as symbol_name,
    )
    from world import MarketRuntime as MarketRuntime  # type: ignore
    from world import Session as Session

DEVELOPER_KEY_NAME = "developer_key"
DEFAULT_DEVELOPER_KEY = "moneta-dev-key"


def _runtime_config(plugin: "MonetaFxPlugin") -> Dict[str, Any]:
    return plugin._moneta_settings


@neko_plugin
class MonetaFxPlugin(NekoPluginBase):
    """Shared fictional forex market with per-account trading."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.logger = ctx.logger
        self._runtime: Optional[MarketRuntime] = None
        self._sessions: Dict[str, Session] = {}
        self._moneta_settings: Dict[str, Any] = {
            "initial_balance": 100000.0,
            "tick_interval_ms": 500,
            "persist_interval_ms": 5000,
            "developer_key": DEFAULT_DEVELOPER_KEY,
        }
        self._lock_token = "moneta_fx.runtime"

    # ── lifecycle ───────────────────────────────────────────────────────
    @lifecycle(id="startup")
    async def on_startup(self, **_):
        settings = await self._load_settings()
        self._runtime = MarketRuntime(
            initial_balance=float(settings.get("initial_balance", 100000.0)),
            tick_interval_ms=int(settings.get("tick_interval_ms", 500)),
            persist_interval_ms=int(settings.get("persist_interval_ms", 5000)),
        )
        raw = await self._load_world_state()
        if raw:
            try:
                self._runtime.load(raw, saved_at_ms=raw.get("_savedAt"))
            except TradeError as error:
                self.logger.warning("MONETA FX 存档无法读取，已重新开局：%s", error)
        self._runtime.start()
        self.logger.info(
            "MONETA FX 已启动 · %d 个货币对 · %d 个账户",
            len(OFFLINE_SYMBOLS),
            len(self._runtime.world.users),
        )
        return Ok({"status": "ready", "symbols": len(OFFLINE_SYMBOLS)})

    @lifecycle(id="shutdown")
    async def on_shutdown(self, **_):
        if self._runtime:
            self._runtime.stop()
            await self._save_world_state()
        return Ok({"status": "stopped"})

    @lifecycle(id="config_change")
    async def on_config_change(self, old_config, new_config, **_):
        settings = dict(self._moneta_settings)
        moneta = (new_config or {}).get("moneta", {}) if isinstance(new_config, dict) else {}
        if isinstance(moneta, dict):
            settings.update({k: v for k, v in moneta.items() if v is not None})
        self._moneta_settings = settings
        if self._runtime is not None:
            self._runtime.initial_balance = float(settings.get("initial_balance", 100000.0))
            self._runtime.tick_interval_ms = int(settings.get("tick_interval_ms", 500))
            self._runtime.persist_interval_ms = int(settings.get("persist_interval_ms", 5000))
        return Ok({"status": "config_updated"})

    # ── persistence helpers ─────────────────────────────────────────────
    async def _load_settings(self) -> Dict[str, Any]:
        try:
            config = await self.config.dump()
        except Exception:  # pragma: no cover - defensive
            return dict(self._moneta_settings)
        moneta = config.get("moneta") if isinstance(config, dict) else None
        if isinstance(moneta, dict):
            self._moneta_settings.update({k: v for k, v in moneta.items() if v is not None})
        return self._moneta_settings

    async def _load_world_state(self) -> Optional[Dict[str, Any]]:
        try:
            from plugin.sdk.plugin import unwrap_or

            raw = unwrap_or(await self.store.get("world"), None)
        except Exception:  # pragma: no cover - defensive
            return None
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                return None
        return raw if isinstance(raw, dict) else None

    async def _save_world_state(self) -> None:
        if not self._runtime:
            return
        state = self._runtime.snapshot_state()
        state["_savedAt"] = self._runtime.world.market.time
        try:
            from plugin.sdk.plugin import unwrap_or

            unwrap_or(await self.store.set("world", state), None)
        except Exception as error:  # pragma: no cover - defensive
            self.logger.warning("MONETA FX 存档写入失败：%s", error)

    @timer_interval(id="autosave", seconds=5, name="MONETA FX 自动存档", auto_start=True)
    async def autosave(self, **_):
        await self._save_world_state()
        return Ok({"saved": True})

    # ── session helpers ─────────────────────────────────────────────────
    @property
    def runtime(self) -> MarketRuntime:
        if self._runtime is None:
            raise SdkError("插件尚未启动，请先启动 MONETA FX")
        return self._runtime

    def _bind(self, session_key: str, user_id: Optional[str]) -> Session:
        session = self._sessions.get(session_key)
        if session is None:
            session = Session(user_id, self.runtime.world)
            self._sessions[session_key] = session
        session.user_id = user_id
        session.world = self.runtime.world
        return session

    def _require(self, session: Session) -> Dict[str, Any]:
        user = session.user
        if user is None:
            raise TradeError("请先登录虚构市场账户", status=401)
        return user

    # ── Hosted UI context ───────────────────────────────────────────────
    @ui.context(id="terminal", title="MONETA FX 交易终端")
    async def terminal_context(self) -> Dict[str, Any]:
        """State payload for the Hosted TSX panel."""

        runtime = self.runtime
        market = runtime.world.market
        quotes = runtime.all_quotes()
        return {
            "market": {
                "time": market.time,
                "paused": runtime.world.paused,
                "speed": runtime.world.speed,
                "event": market.event,
                "revision": runtime.world.revision,
            },
            "watchlist": WATCHLIST,
            "majors": MAJORS,
            "symbolCount": len(OFFLINE_SYMBOLS),
            "quotes": {symbol: _public_quote(q) for symbol, q in quotes.items() if symbol in WATCHLIST},
            "initialBalance": runtime.initial_balance,
            "version": "1.0.0",
        }

    # ── entries: identity ───────────────────────────────────────────────
    @plugin_entry(
        id="login",
        name=tr("entries.login.name", default="登录共享市场"),
        description=tr("entries.login.description", default="用普通账户登录共享虚构市场。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string", "description": tr("fields.sessionKey", default="面板实例标识")},
                "username": {"type": "string", "description": tr("fields.username", default="用户名")},
                "password": {"type": "string", "description": tr("fields.password", default="密码")},
            },
            "required": ["username", "password"],
        },
        llm_result_fields=["message", "user"],
    )
    async def login(self, username: str, password: str, session_key: str = "default", **_):
        try:
            result = self.runtime.login(username, password)
            self._bind(session_key, result["user"]["id"])
            return Ok({"message": f"已登录 · {result['user']['username']}", "user": result["user"]})
        except TradeError as error:
            return Err(SdkError(str(error)))

    @plugin_entry(
        id="register",
        name=tr("entries.register.name", default="注册普通账户"),
        description=tr("entries.register.description", default="创建新的普通账户并获得模拟资金。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string", "description": tr("fields.sessionKey", default="面板实例标识")},
                "username": {"type": "string", "description": tr("fields.username", default="用户名")},
                "password": {"type": "string", "description": tr("fields.password", default="密码")},
            },
            "required": ["username", "password"],
        },
        llm_result_fields=["message", "user"],
    )
    async def register(self, username: str, password: str, session_key: str = "default", **_):
        try:
            result = self.runtime.register(username, password)
            self._bind(session_key, result["user"]["id"])
            return Ok({"message": f"账户已创建 · {result['user']['username']}", "user": result["user"]})
        except TradeError as error:
            return Err(SdkError(str(error)))

    @plugin_entry(
        id="developer_login",
        name=tr("entries.developerLogin.name", default="开发者登录"),
        description=tr("entries.developerLogin.description", default="用开发者密钥登录，获得行情控制台权限。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string", "description": tr("fields.sessionKey", default="面板实例标识")},
                "key": {"type": "string", "description": tr("fields.developerKey", default="开发者密钥")},
            },
            "required": ["key"],
        },
        llm_result_fields=["message", "user"],
    )
    async def developer_login(self, key: str, session_key: str = "default", **_):
        try:
            result = self.runtime.developer_login(key, self._moneta_settings.get("developer_key", DEFAULT_DEVELOPER_KEY))
            self._bind(session_key, result["user"]["id"])
            return Ok({"message": "开发者已登录", "user": result["user"]})
        except TradeError as error:
            return Err(SdkError(str(error)))

    @plugin_entry(
        id="logout",
        name=tr("entries.logout.name", default="退出登录"),
        description=tr("entries.logout.description", default="退出当前共享账户。"),
        input_schema={
            "type": "object",
            "properties": {"session_key": {"type": "string", "description": tr("fields.sessionKey", default="面板实例标识")}},
        },
        llm_result_fields=["message"],
    )
    async def logout(self, session_key: str = "default", **_):
        session = self._sessions.get(session_key)
        if session and session.user_id:
            self.runtime.logout_user(session.user_id)
            session.user_id = None
        return Ok({"message": "已退出登录"})

    @plugin_entry(
        id="session",
        name=tr("entries.session.name", default="当前会话"),
        description=tr("entries.session.description", default="查询当前登录的账户。"),
        input_schema={
            "type": "object",
            "properties": {"session_key": {"type": "string", "description": tr("fields.sessionKey", default="面板实例标识")}},
        },
        llm_result_fields=["user"],
    )
    async def session(self, session_key: str = "default", **_):
        session = self._sessions.get(session_key)
        user = self.runtime.world.find(session.user_id) if session and session.user_id else None
        return Ok({"user": MarketRuntime.profile(user)})

    # ── entries: market data ────────────────────────────────────────────
    @plugin_entry(
        id="state",
        name=tr("entries.state.name", default="账户快照"),
        description=tr("entries.state.description", default="读取账户、报价、K 线和市场状态。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string", "description": tr("fields.sessionKey", default="面板实例标识")},
                "symbol": {"type": "string", "description": tr("fields.symbol", default="货币对，例如 EUR/USD")},
            },
        },
        llm_result_fields=["market", "selected"],
    )
    async def state(self, session_key: str = "default", symbol: str = "EUR/USD", **_):
        session = self._sessions.get(session_key) or self._bind(session_key, None)
        user = self.runtime.world.find(session.user_id) if session.user_id else None
        if user is None:
            return Ok({"market": self.runtime.admin_snapshot(), "user": None, "selected": symbol})
        try:
            snapshot = self.runtime.snapshot(user, symbol)
        except TradeError as error:
            return Err(SdkError(str(error)))
        snapshot["selected"] = symbol
        return Ok(snapshot)

    @plugin_entry(
        id="quotes",
        name=tr("entries.quotes.name", default="批量报价"),
        description=tr("entries.quotes.description", default="读取多个货币对的当前报价。"),
        input_schema={
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": tr("fields.symbols", default="货币对列表")},
            },
        },
        llm_result_fields=["quotes"],
    )
    async def quotes(self, symbols: Optional[List[str]] = None, **_):
        wanted = symbols if symbols else WATCHLIST
        if len(wanted) > 12:
            wanted = wanted[:12]
        quotes = self.runtime.all_quotes()
        return Ok({"quotes": {s: _public_quote(quotes[s]) for s in wanted if s in quotes}, "time": self.runtime.world.market.time})

    @plugin_entry(
        id="symbols",
        name=tr("entries.symbols.name", default="货币对目录"),
        description=tr("entries.symbols.description", default="列出所有可交易的虚构货币对。"),
        llm_result_fields=["count"],
    )
    async def symbols(self, **_):
        return Ok({
            "symbols": OFFLINE_SYMBOLS,
            "watchlist": WATCHLIST,
            "count": len(OFFLINE_SYMBOLS),
        })

    # ── entries: trading ────────────────────────────────────────────────
    @plugin_entry(
        id="order",
        name=tr("entries.order.name", default="下单"),
        description=tr("entries.order.description", default="市价、限价或突破下单。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string", "description": tr("fields.sessionKey", default="面板实例标识")},
                "symbol": {"type": "string"},
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "type": {"type": "string", "enum": ["market", "limit", "stop"]},
                "lots": {"type": "number"},
                "price": {"type": "number"},
                "sl": {"type": "number"},
                "tp": {"type": "number"},
            },
            "required": ["symbol", "side", "type", "lots"],
        },
        llm_result_fields=["message", "account"],
    )
    async def order(self, symbol: str, side: str, type: str, lots: float,
                    price: Optional[float] = None, sl: Optional[float] = None, tp: Optional[float] = None,
                    session_key: str = "default", **_):
        session = self._sessions.get(session_key) or self._bind(session_key, None)
        try:
            user = self._require(session)
            order = {"symbol": symbol, "side": side, "type": type, "lots": lots, "price": price, "sl": sl, "tp": tp}
            snapshot = self.runtime.trade(user, {
                "action": "order",
                "order": order,
                "requestId": _request_id(),
                "accountId": user["id"],
            })
            return Ok({"message": f"{'买入' if side == 'buy' else '卖出'} {symbol} {lots:.2f} 手", "account": snapshot["book"]["account"]})
        except TradeError as error:
            return Err(SdkError(str(error)))

    @plugin_entry(
        id="close",
        name=tr("entries.close.name", default="平仓"),
        description=tr("entries.close.description", default="全部或部分平仓。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string"},
                "id": {"type": "string", "description": tr("fields.positionId", default="持仓 ID")},
                "lots": {"type": "number", "description": tr("fields.lots", default="平仓手数，留空为全部")},
            },
            "required": ["id"],
        },
        llm_result_fields=["message"],
    )
    async def close(self, id: str, lots: Optional[float] = None, session_key: str = "default", **_):
        session = self._sessions.get(session_key) or self._bind(session_key, None)
        try:
            user = self._require(session)
            body = {"action": "close", "id": id, "requestId": _request_id(), "accountId": user["id"]}
            if lots is not None:
                body["lots"] = lots
            snapshot = self.runtime.trade(user, body)
            return Ok({"message": "已平仓", "account": snapshot["book"]["account"]})
        except TradeError as error:
            return Err(SdkError(str(error)))

    @plugin_entry(
        id="close_all",
        name=tr("entries.closeAll.name", default="全部平仓"),
        description=tr("entries.closeAll.description", default="关闭当前账户的所有持仓。"),
        input_schema={
            "type": "object",
            "properties": {"session_key": {"type": "string"}},
        },
        llm_result_fields=["message"],
    )
    async def close_all(self, session_key: str = "default", **_):
        session = self._sessions.get(session_key) or self._bind(session_key, None)
        try:
            user = self._require(session)
            snapshot = self.runtime.trade(user, {"action": "closeAll", "requestId": _request_id(), "accountId": user["id"]})
            return Ok({"message": "已全部平仓", "account": snapshot["book"]["account"]})
        except TradeError as error:
            return Err(SdkError(str(error)))

    @plugin_entry(
        id="modify",
        name=tr("entries.modify.name", default="修改止损止盈"),
        description=tr("entries.modify.description", default="设置或清除持仓的止损止盈。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string"},
                "id": {"type": "string"},
                "sl": {"type": "number"},
                "tp": {"type": "number"},
            },
            "required": ["id"],
        },
        llm_result_fields=["message"],
    )
    async def modify(self, id: str, sl: Optional[float] = None, tp: Optional[float] = None, session_key: str = "default", **_):
        session = self._sessions.get(session_key) or self._bind(session_key, None)
        try:
            user = self._require(session)
            snapshot = self.runtime.trade(user, {"action": "modify", "id": id, "sl": sl, "tp": tp, "requestId": _request_id(), "accountId": user["id"]})
            return Ok({"message": "止损止盈已更新", "account": snapshot["book"]["account"]})
        except TradeError as error:
            return Err(SdkError(str(error)))

    @plugin_entry(
        id="cancel",
        name=tr("entries.cancel.name", default="撤销挂单"),
        description=tr("entries.cancel.description", default="撤销一笔未成交的挂单。"),
        input_schema={
            "type": "object",
            "properties": {"session_key": {"type": "string"}, "id": {"type": "string"}},
            "required": ["id"],
        },
        llm_result_fields=["message"],
    )
    async def cancel(self, id: str, session_key: str = "default", **_):
        session = self._sessions.get(session_key) or self._bind(session_key, None)
        try:
            user = self._require(session)
            snapshot = self.runtime.trade(user, {"action": "cancel", "id": id, "requestId": _request_id(), "accountId": user["id"]})
            return Ok({"message": "已撤销挂单", "account": snapshot["book"]["account"]})
        except TradeError as error:
            return Err(SdkError(str(error)))

    @plugin_entry(
        id="estimate",
        name=tr("entries.estimate.name", default="预估下单成本"),
        description=tr("entries.estimate.description", default="计算保证金、佣金、点差与风险回报。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string"},
                "symbol": {"type": "string"},
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "type": {"type": "string", "enum": ["market", "limit", "stop"]},
                "lots": {"type": "number"},
                "price": {"type": "number"},
                "sl": {"type": "number"},
                "tp": {"type": "number"},
            },
            "required": ["symbol", "side", "type", "lots"],
        },
        llm_result_fields=["estimate"],
    )
    async def estimate(self, symbol: str, side: str, type: str, lots: float,
                       price: Optional[float] = None, sl: Optional[float] = None, tp: Optional[float] = None,
                       session_key: str = "default", **_):

        session = self._sessions.get(session_key) or self._bind(session_key, None)
        user = self.runtime.world.find(session.user_id) if session.user_id else None
        if user is None:
            return Err(SdkError("请先登录虚构市场账户"))
        order = {"symbol": symbol, "side": side, "type": type, "lots": lots, "price": price, "sl": sl, "tp": tp}
        try:
            return Ok({"estimate": estimate_order(user["account"], order, self.runtime.all_quotes())})
        except TradeError as error:
            return Err(SdkError(str(error)))

    # ── entries: market control ─────────────────────────────────────────
    @plugin_entry(
        id="control",
        name=tr("entries.control.name", default="行情控制"),
        description=tr("entries.control.description", default="开发者专属：改价、编排走势、时钟、波动与事件。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string"},
                "kind": {"type": "string", "enum": ["clock", "price", "trend", "cancel-trends", "volatility", "event"]},
                "symbol": {"type": "string"},
                "price": {"type": "number"},
                "currency": {"type": "string"},
                "percent": {"type": "number"},
                "seconds": {"type": "number"},
                "speed": {"type": "number"},
                "paused": {"type": "boolean"},
                "value": {"type": "number"},
                "event": {"type": "string", "enum": ["dollar", "euro", "yen", "storm"]},
            },
            "required": ["kind"],
        },
        llm_result_fields=["message"],
    )
    async def control(self, kind: str, session_key: str = "default", **kwargs):
        session = self._sessions.get(session_key) or self._bind(session_key, None)
        try:
            user = self._require(session)
            body = {"kind": kind}
            body.update({k: v for k, v in kwargs.items() if v is not None})
            self.runtime.control(user, body)
            return Ok({"message": "行情控制已生效"})
        except TradeError as error:
            return Err(SdkError(str(error)))

    @plugin_entry(
        id="admin",
        name=tr("entries.admin.name", default="账户管理"),
        description=tr("entries.admin.description", default="开发者专属：查看账户、持仓、流水并调度资金。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string"},
                "view": {"type": "string", "enum": ["accounts", "account", "ledger"]},
                "accountId": {"type": "string"},
                "limit": {"type": "integer"},
                "before": {"type": "integer"},
            },
        },
        llm_result_fields=["totals"],
    )
    async def admin(self, view: str = "accounts", accountId: Optional[str] = None,
                    limit: int = 100, before: Optional[int] = None, session_key: str = "default", **_):
        session = self._sessions.get(session_key) or self._bind(session_key, None)
        try:
            user = self._require(session)
            if user["role"] != "developer":
                raise TradeError("只有管理员可以管理账户和资金", status=403)
            if view == "account":
                return Ok(self.runtime.admin_account_detail(accountId, limit=limit, before=before))
            if view == "ledger":
                return Ok(self.runtime.admin_ledger(account_id=accountId, limit=limit, before=before))
            return Ok(self.runtime.admin_accounts())
        except TradeError as error:
            return Err(SdkError(str(error)))

    @plugin_entry(
        id="fund",
        name=tr("entries.fund.name", default="资金调度"),
        description=tr("entries.fund.description", default="开发者专属：入金、扣款或转账。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string"},
                "requestId": {"type": "string"},
                "kind": {"type": "string", "enum": ["credit", "debit", "transfer"]},
                "accountId": {"type": "string"},
                "destinationId": {"type": "string"},
                "amount": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["requestId", "kind", "accountId", "amount", "reason"],
        },
        llm_result_fields=["message"],
    )
    async def fund(self, requestId: str, kind: str, accountId: str, amount: float, reason: str,
                   destinationId: Optional[str] = None, session_key: str = "default", **_):
        session = self._sessions.get(session_key) or self._bind(session_key, None)
        try:
            user = self._require(session)
            if user["role"] != "developer":
                raise TradeError("只有管理员可以管理账户和资金", status=403)
            body = {"requestId": requestId, "kind": kind, "accountId": accountId, "amount": amount, "reason": reason}
            if destinationId:
                body["destinationId"] = destinationId
            result = self.runtime.fund(user, body)
            return Ok({"message": "资金调度已执行", "entry": result["entry"], "duplicate": result["duplicate"]})
        except TradeError as error:
            return Err(SdkError(str(error)))

    @plugin_entry(
        id="report",
        name=tr("entries.report.name", default="账户分析"),
        description=tr("entries.report.description", default="统计已实现盈亏、胜率、盈利因子与回撤。"),
        input_schema={
            "type": "object",
            "properties": {"session_key": {"type": "string"}},
        },
        llm_result_fields=["report"],
    )
    async def report(self, session_key: str = "default", **_):

        session = self._sessions.get(session_key) or self._bind(session_key, None)
        user = self.runtime.world.find(session.user_id) if session.user_id else None
        if user is None:
            return Err(SdkError("请先登录虚构市场账户"))
        account = user["account"]
        history = account["history"]
        total = sum(t["netPnl"] for t in history)
        wins = sum(1 for t in history if t["netPnl"] > 0)
        gains = sum(max(0.0, t["netPnl"]) for t in history)
        losses = sum(max(0.0, -t["netPnl"]) for t in history)
        curve = list(account["equityCurve"]) + [{"time": self.runtime.world.market.time, "value": metrics(account, self.runtime.all_quotes())["equity"]}]
        peak = curve[0]["value"]
        drawdown = 0.0
        for point in curve:
            peak = max(peak, point["value"])
            if peak > 0:
                drawdown = max(drawdown, (peak - point["value"]) / peak * 100)
        return Ok({
            "report": {
                "netPnl": total,
                "winRate": (wins / len(history) * 100) if history else None,
                "profitFactor": (gains / losses) if losses else (float("inf") if gains else None),
                "maxDrawdown": drawdown,
                "trades": len(history),
                "equity": metrics(account, self.runtime.all_quotes())["equity"],
                "initialBalance": account["initialBalance"],
                "curve": curve,
            }
        })

    @plugin_entry(
        id="settings",
        name=tr("entries.settings.name", default="交易参数"),
        description=tr("entries.settings.description", default="查看或修改杠杆、点差、滑点、佣金与隔夜费。"),
        input_schema={
            "type": "object",
            "properties": {
                "session_key": {"type": "string"},
                "leverage": {"type": "number"},
                "spreadMultiplier": {"type": "number"},
                "slippage": {"type": "number"},
                "commission": {"type": "number"},
                "swapLong": {"type": "number"},
                "swapShort": {"type": "number"},
            },
        },
        llm_result_fields=["settings"],
    )
    async def settings(self, session_key: str = "default", **kwargs):

        session = self._sessions.get(session_key) or self._bind(session_key, None)
        user = self.runtime.world.find(session.user_id) if session.user_id else None
        if user is None:
            return Err(SdkError("请先登录虚构市场账户"))
        account = user["account"]
        if not kwargs:
            return Ok({"settings": account["settings"]})
        candidate = dict(account["settings"])
        candidate.update({k: v for k, v in kwargs.items() if v is not None})
        if not validate_settings(candidate):
            return Err(SdkError("交易参数超出允许范围"))
        if candidate["leverage"] != account["settings"]["leverage"] and (account["positions"] or account["pending"]):
            return Err(SdkError("仅空仓且无挂单时可修改杠杆"))
        account["settings"] = candidate
        return Ok({"settings": candidate})

    # ── entries: reference ──────────────────────────────────────────────
    @plugin_entry(
        id="pip_info",
        name=tr("entries.pipInfo.name", default="货币对信息"),
        description=tr("entries.pipInfo.description", default="查询货币对的点值、小数位与中文名。"),
        input_schema={
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
        llm_result_fields=["info"],
    )
    async def pip_info(self, symbol: str, **_):
        if symbol not in OFFLINE_SYMBOLS:
            return Err(SdkError("不支持的虚构货币对"))
        return Ok({
            "info": {
                "symbol": symbol,
                "name": symbol_name(symbol),
                "pipSize": pip_size(symbol),
                "digits": digits(symbol),
            }
        })


def _public_quote(quote: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": quote["symbol"],
        "mid": quote["mid"],
        "bid": quote["bid"],
        "ask": quote["ask"],
        "time": quote["time"],
        "marketOpen": quote["marketOpen"],
    }


def _request_id() -> str:
    import uuid

    return str(uuid.uuid4())
