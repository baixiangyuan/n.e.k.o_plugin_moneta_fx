# MONETA FX · N.E.K.O. 插件

虚构外汇模拟交易室，做成一个 N.E.K.O. `plugin` 包：共享虚构市场、市价/限价/突破单、
止损止盈、保证金与强平、隔夜费、K 线图与账户分析，外加开发者行情控制台。

> 全部行情、资金与成交均为虚构游戏数据，不对应任何真实市场，不构成投资建议。

配套的独立服务端在另一个仓库
[`moneta-fx-server`](https://github.com/baixiangyuan/moneta-fx-server)：
原版网页 UI 1:1 + FastAPI 后端，插件可选择连它来共享同一套账户。

---

## 一、目录结构

本仓库根目录**就是插件目录**（仓库名 `n.e.k.o_plugin_moneta_fx`，目录名与插件 ID 一致）：

```text
n.e.k.o_plugin_moneta_fx/
├── plugin.toml            ← 清单：id / name / entry / UI / i18n / 运行时
├── __init__.py            ← 惰性导出 MonetaFxPlugin（裸 import 不拉 SDK）
├── plugin.py              ← 插件类：生命周期、入口、@ui.action、@ui.context
├── cloud.py               ← 云端后端 HTTP 客户端（可选，仅标准库）
├── market.py              ← 虚构市场模型
├── engine.py              ← 交易引擎：下单/保证金/隔夜/强平
├── store.py               ← 共享市场存档结构与校验
├── auth.py                ← 会话、口令散列、登录限流
├── world.py               ← 共享运行时：行情、账户、管理、资金调度
├── ui/panel.tsx           ← Hosted TSX 交易终端
├── docs/quickstart.md     ← 使用指南
├── i18n/{zh-CN,en}.json   ← 插件文案
├── config.schema.json     ← 通用配置页表单
├── config.example.toml    ← 运行配置模板
├── tests/                 ← 单元测试（78 项）+ 本地 SDK stub
└── .github/workflows/     ← 插件市场 verify / release
```

---

## 二、作为 N.E.K.O. 插件安装

### 开发模式（推荐先这样验证）

1. 打开安装版 N.E.K.O. 的插件管理器 → 左侧「服务器日志」下方的「开发模式」→ 开启开关。
2. 点击「加载未打包插件」，选择包含 `plugin.toml` 的目录：
   `C:\Users\ADMIN\Downloads\neko-moneta-fx\moneta_fx`
   网页端要填**运行后端的机器上的绝对路径**。
3. 点击「校验」，核对名称、ID、版本、入口和路径，再点「加载未打包插件」。
4. 在自己编辑器里改文件，点卡片上的「重载」；改依赖需要重启插件。
5. 点「打包」下载 `.neko-plugin`，在另一套 N.E.K.O. 的普通导入入口安装验证。

### 源码版

把整个 `moneta_fx` 目录复制到 N.E.K.O. 源码的 `plugin/plugins/moneta_fx/`，然后：

```bash
uv run neko-plugin check moneta_fx
cd frontend/plugin-manager
npm run check-hosted-tsx -- plugin/plugins/moneta_fx
```

> 源码目录名必须与插件 ID 一致（都是 `moneta_fx`），否则打包器不会改写源码，安装会按 ID 另建目录。

### 配置

在插件管理器的配置页（或运行时 `plugin.toml` 的 `[moneta]` 段）里改：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `initial_balance` | `100000` | 新账户初始模拟资金 |
| `tick_interval_ms` | `500` | 市场心跳间隔 |
| `persist_interval_ms` | `5000` | 自动存档间隔 |
| `developer_key` | `moneta-dev-key` | 开发者密钥，**上线前必须改** |
| `server_url` | `""` | 云端后端地址，留空 = 本地离线模式 |
| `use_cloud` | `false` | 置 `true` 且填了 `server_url` 时走云端 |

#### 连接云端后端

插件**默认连到已部署的服务端**（`http://8.152.0.186:4173`），装上去就能操作云端共享账户。要改成本地离线模式，在插件管理器的配置页把 `server_url` 改成 `""`、`use_cloud` 改成 `false`。

生效后：

- 注册 / 登录 / 下单 / 平仓 / 改单 / 撤单 / 账户分析全部打到服务端
- N.E.K.O. 面板和浏览器端看到的是**同一个世界**，账户、持仓、行情共享
- 行情控制台、账户管理、资金调度需要先用服务端的 `MONETA_DEVELOPER_KEY`
  或 `MONETA_ADMIN_PASSWORD` 登录
- 本地不再自动存档（数据在服务端）
- 服务端不可达时自动回退本地模式，不影响插件启动

两种模式的返回结果都带 `mode` 字段（`"cloud"` / `"local"`），便于区分当前连的是哪套后端。

---

## 三、云端服务端（另一个仓库）

服务端不在本仓库，在
[`baixiangyuan/moneta-fx-server`](https://github.com/baixiangyuan/moneta-fx-server)。
那里有原版网页 UI 1:1、FastAPI 后端、Docker 与一键部署脚本。插件只是可选的
客户端——不装服务端也能完全离线玩。

部署好之后，把地址填进插件配置：

```toml
[moneta]
server_url = "http://your-server:4173"
use_cloud = true
```

> ⚠️ 服务端目前是**明文 HTTP**。如果部署在公网，注册和登录的密码会以明文
> 传输，中间链路上的任何人都能截获。请只在不信任度可控的网络里用，
> 或者自己加一层 HTTPS 反向代理（Caddy 三行配置即可自动签证书）。

---

## 四、两种模式

| 模式 | 配置 | 行情来源 | 账户保存 |
| --- | --- | --- | --- |
| 本地离线（默认） | `server_url` 留空 | 插件进程内生成 | N.E.K.O. 插件存储 |
| 云端共享 | `server_url` + `use_cloud = true` | 服务端统一生成 | 服务端 `MONETA_DATA_DIR` |

云端模式下，N.E.K.O. 面板与浏览器端访问同一个世界：同一账户、同一持仓、同一行情，
开发者控制台与资金调度在两端都可用。

---

## 五、交易规则（与原版一致）

- **杠杆** 1:10 / 1:20 / 1:30 / 1:50 / 1:100 / 1:200 / 1:500，仅空仓且无挂单时可改。
- **点差** 按货币对动态计算：主要货币对 1.2 点基准，自选 2.4，其他 6， JPY 报价 >100 的 80；可用倍率 0.5–10 调整。
- **滑点** 市价成交在 0 至上限之间随机产生不利滑点（默认 0.3 点）。
- **佣金** 每手每边收取一次（默认 3 USD），部分平仓按实际手数收取。
- **隔夜费** UTC 22:00 结算，周三三倍，周末不结算；多单默认 -6、空单 +1.5 USD/手。
- **保证金** `手数 × 100000 × 基础货币USD价值 / 杠杆`；可用保证金不足拒绝成交。
- **强平** 保证金水平低于 50% 时，按浮动盈亏从亏到盈依次强平。
- **挂单** 限价单与突破单方向规则与原版一致；触发后按挂单价成交（限价单取更优价）。
- **幂等** 每笔交易带 `requestId`，同一编号重复提交不会重复执行。

---

## 六、开发者控制台

在共享模式登录开发者账户后可见：

- **直接调整价格**：单次可调至当前价的 50%–200%，相关交叉汇率联动。
- **编排走势**：以当前价为起点，保留过程波动，在指定模拟秒内到达目标（幅度 ±30%，时长 5 秒–24 小时）。
- **时间与波动**：1× / 5× / 20× / 100× 倍速；暂停时钟（仍可交易）；波动强度 1–20。
- **虚构事件**：美元突然走强、欧元利好、日元干预冲击、流动性风暴。
- **账户管理**：查看普通账户、持仓、挂单、成交历史、操作记录；入金 / 扣款 / 转账，全部留痕。

---

## 七、测试

```bash
# 全部单元测试（79 项，无需 N.E.K.O. 环境）
uv run --python 3.12 --with pytest --with packaging python -m pytest -c pytest.ini -q
```

覆盖引擎（下单/保证金/止盈止损/强平/幂等）、共享运行时（账户/行情控制/资金调度/
存档/停机补绘）、云端客户端（URL 拼装、cookie、错误透传，用假 urlopen 不打真网络）、
以及清单/配置/schema/UI 动作声明的一致性检查。

CI 侧除了跑 manifest 与 Hosted TSX 校验，还会执行插件市场的 verify 与 release
两个 workflow。

---

## 八、与原版的差异

| 项目 | 原版 | 移植版 |
| --- | --- | --- |
| 行情源 | Twelve Data 真实参考价 + 本地虚构 | 纯虚构（服务端或本地生成），无外部依赖 |
| 后端语言 | Node.js | Python |
| 账户体系 | scrypt + Cookie + 登录限流 | scrypt + Cookie + 登录限流（逻辑一致） |
| 停机补绘 | `resume-market.mjs` 只补图表 | 同逻辑移植到 `market.resume_market` |
| 隧道 | `cloudflared` 随包分发 | 需自行准备隧道工具 |
| UI | 原版 HTML/CSS/JS | 云端服务端 1:1 复用；插件面板为 Hosted TSX 重绘 |

---

## 九、安全提醒

- **开发者密钥**：清单里的 `developer_key = "moneta-dev-key"` 是公开的示例值。
  首次启动时如果还是这个值，插件会自动生成随机密钥并持久化，密钥会打进日志——
  请记下。想自己定就在插件配置里设置 `developer_key`。
- **云端模式走明文 HTTP**：注册和登录的密码在网络上可被截获。公网部署请自行加
  HTTPS 反向代理，或只在可信网络里用。
- **服务端的 `MONETA_ADMIN_PASSWORD` 与 `MONETA_DEVELOPER_KEY`** 在部署前必须改，
  见 `moneta-fx-server` 仓库的部署脚本。
- 登录接口有每地址 15 次 / 10 分钟的限制；口令使用 scrypt 散列，不落明文。
- 全部数据都是模拟数据，但仍建议不要把服务端直接暴露在公网而不加认证。
