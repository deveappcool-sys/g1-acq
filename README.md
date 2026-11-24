# g1-acq · Clash 版

Google One（iOS）订阅入口的**商品 ID 改写与被动采集**工具，用于 **Clash - Rule Based Proxy**（mihomo 内核）及其它 mihomo 客户端。

本仓库是从 Shadowrocket 版 `g1-acq` v7.5.0 **完全改造**而来：不再有 `.sgmodule` 和 `http-response` 脚本，改由 **Clash 配置** 负责分流、**旁路服务** 负责改写。

---

## 1. 先说清楚：为什么不是一个 YAML 就够

Clash / mihomo 是**规则分流器**：它决定一条连接走哪个出口，但**不会解密 TLS，也没有响应体改写能力**。Clash Verge 的「重写 / MITM」功能请求（[clash-verge-rev#727](https://github.com/clash-verge-rev/clash-verge-rev/issues/727)）至今没有实现，mihomo 官方能力表里也只有规则、DNS、TUN、sniffer、代理协议这些。

而本项目的核心动作是「把 `one.google.com` 响应正文里的 SKU 字符串换掉」。这一步必须在**持有该域名 TLS 会话的一端**完成，所以只能落在 Clash 之外。

因此本项目的形态是两部分协同：

| 部分 | 运行位置 | 职责 |
|---|---|---|
| [`clash/g1-acq.yaml`](clash/g1-acq.yaml) | 手机上的 Clash | 把 `one.google.com` **一条域名**送到旁路；丢弃该域名的 QUIC，促使回退到 TCP |
| [`g1_addon.py`](g1_addon.py) + [`g1acq/`](g1acq/) | Mac / VPS / NAS / 容器 | 终止 TLS、执行三档改写、被动采集 SKU、提供本地报告页 |

```text
iPhone (Google App)
   │  普通流量 ──> Clash 规则 ──> 你自己的节点 ──> 互联网
   │
   └─ one.google.com ──> 规则 DOMAIN,one.google.com,G1
                          │
                          ▼
                    G1 ACQ 旁路（mitmproxy 插件）
                          │  改写 SKU 后
                          ▼
                    one.google.com（真实站点）
```

**你的机场节点不会被改动**：只有 `one.google.com` 会进入解密范围，转发链路上其它域名照旧直连或走节点。

---

## 2. 三档映射

旁路先从 `https://one.google.com/` 的原始文字响应里采集候选 SKU，然后**只对匹配 `/ai?` 的响应**按完整源 SKU 执行映射：

| 正文中的完整源 SKU | 默认目标 | 备用目标 |
|---|---|---|
| `g1.ios.2tb.` 前缀的完整 SKU | `g1.2tb.ai.12months_ip_90p`（用户指定候选） | 无 |
| `g1.ios.20tb.m.v2` | `g1.20tb.3months_ip_90p.acq` | `g1.20tb.3months_ip_75p.acq` |
| `g1.ios.30tb.ai.pro.m` | `g1.ai.ultra.3months_ip_90p.acq` | `g1.ai.ultra.3months_ip_75p.acq` |

- 2TB 档**固定**替换为候选，没有备用档，也不要求目标先出现在正文里。
- 20TB / 30TB 各自独立判断：正文里出现该档 90p 就用 90p；90p 缺席而对应 75p 出现时用 75p（记录 `fallback=true`）；两者都没有时仍用 90p。
- 判断依据是**响应正文字符串**，不是向 App Store 查询商品目录。三档都没命中时响应原样返回。

> 2TB 候选来自用户截图，`90p` 表示 90% off（约一折），不是实付九折。截图里的 `$1.99 × 12 months = $23.88/year` 是 12 个月合计标签，不是一次扣款证据。**商品是否真实存在、价格与周期以 App Store 收银台为准。**

---

## 3. 快速开始

需要三样东西：一台能被手机访问的机器、这份仓库、以及手机上一个已工作的 Clash 配置。

### 3.1 启动旁路

在 Mac / Linux / NAS 上：

```bash
git clone <this-repo> g1-acq && cd g1-acq

# 用 uv（推荐）
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt

# 或者用系统 Python
# python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

./run.sh                       # 监听 0.0.0.0:8080
```

也可以直接用 Docker：

```bash
docker compose up -d
```

首次启动时 mitmproxy 会在 `~/.mitmproxy/` 生成根证书，这个证书之后要装到手机上。

如果旁路主机**自己上不了 Google**（例如国内 VPS），让它复用你已有的代理：

```bash
G1_UPSTREAM=http://127.0.0.1:7890 ./run.sh
```

### 3.2 把根证书装到手机

iOS 必须信任这张 CA，否则 `one.google.com` 的页面会直接报错。

```bash
# 在旁路主机上导出 DER（iOS / Android 都认这个格式）
.venv/bin/python -m g1acq ca --out g1-acq-ca.der
```

导出的 `g1-acq-ca.der` 通过 AirDrop / 文件传输发到手机，然后：

1. iOS **设置 → 通用 → VPN 与设备管理**，安装这个描述文件；或
2. **设置 → 已下载描述文件** → 安装。

安装后在 iOS **设置 → 通用 → 关于本机 → 证书信任设置** 中打开 **完全信任**（这一步不做等于没装）。

> 便捷方式：临时在 Clash 规则里加一条 `DOMAIN,mitm.it,G1`，用 Safari 打开 `http://mitm.it` 下载。mitmproxy 默认导出的 `.cer` 是 **PEM 编码**，个别 iOS 版本会提示「无法验证」——遇到就用上面的 DER 方式。

### 3.3 导入 Clash 配置

打开 [`clash/g1-acq.yaml`](clash/g1-acq.yaml)，改两个地方：

```yaml
proxies:
  - name: "G1-MITM"
    type: http
    server: 192.168.1.10      # ← 旁路主机的局域网 IP 或公网地址
    port: 8080                # ← run.sh 的监听端口

  - name: "YOUR-NODE"         # ← 换成你自己的节点
    type: trojan
    ...
```

然后在 Clash 里新建配置并导入这份 YAML（客户端菜单名各版本略有差异，通常在「配置 → 添加 / 从文件导入」）。

**已经有配置、不想换掉？** 用 [`clash/g1-acq.snippet.yaml`](clash/g1-acq.snippet.yaml)：把 `proxies`、`proxy-groups`、`rules` 三段分别抄进你现有配置的对应段落。**三条 G1 规则必须放在你最后那条 `MATCH` 之前**，否则 `one.google.com` 永远轮不到它们。

### 3.4 验证

1. Clash 连上后，在 Safari 打开：

   ```text
   https://one.google.com/g1-sku-report
   ```

2. 应该看到 **「G1 ACQ 旁路已接管 · v8.0.0」** 标记和「导出 JSON」按钮。看到 Google 的普通页面或 404，说明请求没走到旁路，回到 [3.3](#33-导入-clash-配置) 检查规则顺序。
3. 打开 Google App → Google One 管理 → 进入 2TB / Pro 方案。
4. 回到报告页刷新：`已扫描文本响应` 增长，`浏览页面时采集到的候选 SKU` 里出现原始 `g1.*` 编号。
5. 再进一次该方案，看 App Store 收银台显示的商品名称、周期与金额。

旁路启动日志里可以直接看到执行结果：

```text
[g1-acq] g1-acq-clash-v8.0 status=new-skus addedCount=4 candidates=4 omittedCount=0 occurrences=5 saved=yes
[g1-acq] g1-acq-clash-v8.0 hits=4 annualHits=2
[g1-acq] g1.ios.2tb.monthly.v1 -> g1.2tb.ai.12months_ip_90p x1
```

详细部署与排错见 **[docs/clash-setup.md](docs/clash-setup.md)**；实机核对流程与全部字段见 **[docs/pro-annual-test.md](docs/pro-annual-test.md)**。

---

## 4. 本地报告

`https://one.google.com/g1-sku-report` 由旁路服务应答，**不是 Google 的页面**，地址栏沿用 Google 域名：

| 地址 | 内容 |
|---|---|
| `/g1-sku-report` | HTML 报告：采集计数、最近 10 次响应、最近一次三档映射、候选 SKU 清单 |
| `/g1-sku-report?format=json` | `g1-sku-report.json` 下载响应 |
| `/g1-sku-report?clear=1` | 清空本工具的两份记录（手动操作） |

也可以在旁路主机上直接看：

```bash
.venv/bin/python -m g1acq report --state ~/.g1-acq/state.json        # JSON
.venv/bin/python -m g1acq report --state ~/.g1-acq/state.json --html # 报告页
.venv/bin/python -m g1acq clear  --state ~/.g1-acq/state.json
```

记录保存在**旁路主机**的 `~/.g1-acq/state.json`，键名与 Shadowrocket 版一致（`g1.sku.scan.v1`、`g1.pro.annual.test.v1`，`schemaVersion: 1`）。

| 键 | 内容 |
|---|---|
| `g1.sku.scan.v1` | 候选 ID、累计次数、最近发现时间、采集版本、文字/命中/非文本响应计数、上限状态、最多 10 条脱敏响应事件 |
| `g1.pro.annual.test.v1` | 最近一次 `/ai?` 执行记录：版本、三档命中源 ID 与逐行实际目标、2TB 目标、总改写数、2TB 改写数、时间、状态 |

**不保存**完整响应正文、请求头、响应头、query 或完整 URL；响应事件只保留时间、固定类别路径与计数。旁路服务**没有网络上报**逻辑。

---

## 5. 关闭与回滚

- **临时关掉改写**：在 Clash 里把代理组 `G1` 切换到 `DIRECT`，`one.google.com` 就恢复直连。
- **彻底移除**：删掉配置文件里的 `G1-MITM`、`G1` 组和三条规则即可；旁路服务不再收到流量。
- **删掉证书**：iOS **设置 → 通用 → VPN 与设备管理** 移除描述文件，并在证书信任设置里关闭。

---

## 6. 离线验证

```bash
uv pip install --python .venv/bin/python pytest pyyaml
.venv/bin/python -m pytest
```

用 `python3 -m venv .venv` 建的虚拟环境自带 pip，把第一行换成 `.venv/bin/pip install pytest pyyaml` 即可。

76 个测试分四层：

| 层 | 内容 |
|---|---|
| 单元 / 契约 | 三档完整编号匹配、2TB 固定候选、20TB/30TB 的 90p 优先与 75p 独立回退、目标与备用均缺失时用默认 90p、URL 范围、零命中、采集去重与 300 上限、最近 10 条事件、脱敏、旧记录兼容、报告字段与 HTML 转义 |
| mitmproxy 层 | gzip / br 解压后改写并保持压缩、二进制响应对待、超限正文、报告页接管、合成响应不被二次扫描、钩子异常不外抛 |
| Clash 配置 | `mihomo -t` 真实解析、每条规则的出口都存在、`one.google.com` 规则在 `MATCH` 之前、QUIC 守卫的四个条件、G1 是纯 HTTP 代理、snippet 与完整配置一致 |
| 端到端 | 起一个假 Google（TLS）+ CONNECT 转发器，跑真实 `mitmdump` 与真实 `mihomo`，验证 `客户端 → mihomo → 旁路 → 上游` 整条链路能改写出三档目标，并验证规则命中日志 |

缺少 `mitmdump` / `openssl` / `mihomo` 时对应用例自动 skip。测试中的源编号是合成样本，不构成商店上架或实机购买证据。

---

## 7. 文件说明

| 文件 | 用途 |
|---|---|
| [`clash/g1-acq.yaml`](clash/g1-acq.yaml) | 完整 mihomo 配置：代理、策略组、QUIC 守卫、`one.google.com` 分流 |
| [`clash/g1-acq.snippet.yaml`](clash/g1-acq.snippet.yaml) | 合并到现有配置用的三段片段 |
| [`g1_addon.py`](g1_addon.py) | mitmproxy 插件入口：响应改写 + 报告页接管 |
| [`g1acq/config.py`](g1acq/config.py) | 三档映射、版本号、存储键、上限等**唯一事实来源** |
| [`g1acq/collector.py`](g1acq/collector.py) | 被动采集、去重、300 上限、响应活动事件 |
| [`g1acq/rewriter.py`](g1acq/rewriter.py) | 三档改写与执行记录 |
| [`g1acq/report.py`](g1acq/report.py) | HTML 报告与 JSON 导出 |
| [`g1acq/store.py`](g1acq/store.py) | 原子写入的本地键值存储 |
| [`g1acq/launch.py`](g1acq/launch.py) | mitmdump 命令行构造（`run.sh`、CLI、测试共用） |
| [`docs/clash-setup.md`](docs/clash-setup.md) | 部署、证书、分流、排错 |
| [`docs/pro-annual-test.md`](docs/pro-annual-test.md) | 实机核对流程、字段字典、记录模板 |

---

## 8. 边界与隐私

- **改写范围**：只有 `https://one.google.com/` 的响应会被读取；只有 `^https://one.google.com/ai\?` 会被改写。`one.google.com.evil` 之类不会匹配。
- **解密范围**：旁路只对 `one.google.com` 做 TLS 拦截（`allow_hosts` 限制），其它流量原样隧道转发。
- **权限**：旁路不申请定位、相册、通知；不需要 root。iOS 侧只需一次描述文件与证书信任。
- **全局影响**：本版把 QUIC 拦截**限定在 `one.google.com`**，不再像 Shadowrocket 版那样丢弃全局 UDP 443，其它 App 的 HTTP/3 不受影响。
- **不算证据的地方**：命中计数只证明字符串替换成功，不证明 App Store 接受该商品，也不证明订阅周期或权益。采集清单只包含服务器实际下发的编号，不是完整商品目录；旁路自己生成的替换目标不会写回清单。
