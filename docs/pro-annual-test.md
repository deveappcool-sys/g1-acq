# Pro 12 个月优惠测试与 SKU 采集

本文说明如何在 **iPhone + Clash + Google App** 环境下跑完一轮采集与改写，以及如何读懂报告里的每一个字段。部署步骤见 [clash-setup.md](clash-setup.md)。

> ⚠️ **仅供研究与兼容性测试。** 改写商品编号来观察商店行为可能违反 Google / Apple 的服务条款。请把这一轮当作只读观察：**看到收银台就记录，不要真正完成付款**，也不要用于获取未付费权益。

当前版本：项目 `8.2.0`，报告 `v8.2.0`，采集/改写脚本 `g1-acq-clash-v8.2`；映射表与上游 v7.6.0 同步。

---

## 1. 本轮目标

| 项 | 值 |
|---|---|
| 源商品 | `g1.ios.2tb.` 前缀的**原始 iOS 2TB 完整 SKU** |
| 目标候选 | `g1.2tb.ai.12months_ip_90p`（无 `.acq` 后缀） |
| 备用档 | 无 |
| 候选来源 | 用户截图指定（`user-specified`） |

截图里的价格标签是 `$1.99 × 12 months = $23.88/year`，表达的是连续 12 个月的月度优惠；`90p` 指 **90% off（约一折）**，不是实付九折。截图标题写的是 Pro 5TB，但本轮源商品仍是 `g1.ios.2tb.` 前缀，没有新增 5TB 前缀。

**截图是候选的来源，不是商品资料。** 商品名称、周期、初次与续费金额，以 App Store 实际返回为准。

---

## 2. 三档映射的判断逻辑

```text
原始响应正文
   │
   ├─ 采集：抓出所有 g1.* / com.google.one.* → 去重累计（最多 300 个）
   │
   └─ 仅当 URL 匹配 ^https://one.google.com/ai\? 时改写：
        g1.ios.2tb.*            → g1.2tb.ai.12months_ip_90p（固定）
        g1.ios.20tb.m.v2        → g1.20tb.1month_eft.acq        ┐ 按原文判断
        g1.ios.30tb.ai.pro.m    → g1.ai.ultra.1month_eft.acq    ┘
```

20TB / 30TB 的备用档判断，**只看原始正文**：

1. 该档 1 个月免费试用（`1month_eft`）出现在正文 → 用它。即使三个月 90p 同时出现，仍然用它。
2. 免费试用缺席、对应三个月 90p 出现 → 用 90p，该行记 `fallback=true`。
3. 两者都没出现 → 仍用 `1month_eft`。

20TB 只看 20TB 的目标，30TB 只看 30TB 的目标，互不影响。

这是**正文字符串判断**，不是向 App Store 查询目录。命中只说明替换成功。

---

## 3. 一轮完整操作

1. **确认服务在线**：Clash 已连接，`G1` 组是 `G1-MITM`，旁路进程在跑。
2. **先记录基线**：Safari 打开 `https://one.google.com/g1-sku-report`，记下 `scan.version`、`scannedResponses`、`matchedResponses`、`nonTextResponses` 与最新事件时间。
3. **打开方案**：Google App → Google One 管理 → 进入 2TB / Pro；需要核对旧映射时再打开 20TB / 30TB。
4. **等加载完成**，需要时切换月付 / 年付入口各看一遍（只有真正收到响应才会记录，不必完成购买）。
5. **刷新报告对照**：计数是否增长、最新事件状态是什么、候选清单有没有新编号。
6. **进入订阅流程**：核对 App Store 收银台的商品名称、周期、币种、初次金额、续费金额。**看到即记录，不要确认购买。**
7. **导出 JSON**：点报告里的「导出 JSON」，或直接打开 `https://one.google.com/g1-sku-report?format=json`。

### 3.1 采集为什么可能"没变化"

浏览器和 Google App 都会缓存。以下情况计数不会动，**不能据此判断服务失效**：

- 页面走的是缓存，没有发出新的网络请求；
- 响应里确实没有候选编号（状态 `no-skus`）；
- 收到的是重复编号（状态 `known-skus`，次数增加、条目不变）；
- 状态文件写入失败（日志 `saved=no`，旧计数保留）。

判断顺序应该是：先看日志有没有 `saved=no` / `SKU collection unavailable`，再看计数与最新事件时间，最后才是规则与证书。

---

## 4. 报告字段

### 4.1 顶层

| 字段 | 含义 |
|---|---|
| `reportVersion` | 报告渲染版本，当前 `v8.2.0` |
| `configuredTarget` | 当前配置的 2TB 候选；用 `--target` 覆盖时会随之变化 |
| `storageAvailable` | 状态文件是否可读 |
| `schemaVersion` | 恒为 `1` |

### 4.2 `scan`（采集）

| 字段 | 含义 |
|---|---|
| `scan.version` | 生成该记录的采集器版本；当前 `g1-acq-clash-v8.0`，旧记录保留原值 |
| `scan.updatedAt` | 最近一次写入时间（UTC） |
| `scan.scannedResponses` | 累计处理的文本响应数（非文本不计入） |
| `scan.matchedResponses` | 至少识别出一个候选 ID 的响应数（重复 ID 也算） |
| `scan.nonTextResponses` | 累计非文本响应数 |
| `scan.truncated` | 是否曾达到 300 个 ID 上限 |
| `scan.limit` | 恒为 `300` |
| `scan.skus[]` | `{id, count, lastSeen}`，按 `id` 排序 |
| `scan.recentResponses[]` | 最多 10 条事件，JSON 按**旧 → 新**排列，HTML 表按**新 → 旧**展示 |

### 4.3 `scan.recentResponses[]` 事件

| 字段 | 含义 |
|---|---|
| `at` | 本次处理时间（UTC，毫秒） |
| `path` | 固定类别：`/`、`/ai`、`/plans`、`/_/…/data/batchexecute`、`[其他 one.google.com 路径]` |
| `bodyType` | `text` / `non-text` |
| `status` | 见下表 |
| `candidateCount` | 本响应内**去重后**的候选数 |
| `addedCount` | 本次新加入并保留的 ID 数 |
| `omittedCount` | 本次因 300 上限而丢弃的 ID 数 |

| `status` | 触发条件 |
|---|---|
| `new-skus` | `addedCount > 0`；即使同时有容量丢弃，仍用此状态 |
| `known-skus` | 识别到的 ID 都已存在，只更新次数与时间 |
| `no-skus` | 文本响应里没有候选 ID |
| `limit-reached` | `addedCount = 0` 且 `omittedCount > 0` |
| `non-text` | 响应不是可采集文本 |

### 4.4 `test`（最近一次 `/ai?` 执行）

| 字段 | 含义 |
|---|---|
| `test.version` | 生成该记录的脚本版本；当前 `g1-acq-clash-v8.0` |
| `test.updatedAt` | 执行时间（UTC） |
| `test.target` | 该次执行实际使用的 2TB 目标 |
| `test.targetOrigin` | `user-specified` / `pattern-derived` / `legacy`；新记录为 `user-specified` |
| `test.hitCount` | 三档总改写次数 |
| `test.annualHitCount` | 其中 2TB / Pro 改写次数（沿用旧字段名，不证明年付扣款） |
| `test.matchedFrom[]` | `{id, to, count, fallback}`，`to` 是该行实际目标 |
| `test.status` | `rewritten` / `no-match` / `non-text` |

> `configuredTarget` 是**当前配置**，`test.target` 是**最近一次执行时实际用的值**，两者可能不同（尤其是改过 `--target` 之后）。旧版本写入的记录会原样保留自己的 `target` 与 `targetOrigin`：`pro-annual-test-v1/v2` 与 `g1-acq-v7.0/v7.1` 若缺 `target`，按 `g1.2tb.ai.annual` 处理并标记 `legacy`。

---

## 5. 日志

旁路进程的日志是排错的第一手材料：

```text
[g1-acq] g1-acq-clash-v8.0 status=new-skus addedCount=4 candidates=4 omittedCount=0 occurrences=5 saved=yes
[g1-acq] g1.ios.2tb.monthly.v1 x2
[g1-acq] g1-acq-clash-v8.0 hits=4 annualHits=2
[g1-acq] g1.ios.2tb.monthly.v1 -> g1.2tb.ai.12months_ip_90p x2
[g1-acq] g1.ios.30tb.ai.pro.m -> g1.ai.ultra.3months_ip_90p.acq x1 fallback=g1.ai.ultra.3months_ip_90p.acq
[g1-sku-report] v8.2.0 html storage=ready candidates=4
```

| 标记 | 含义 |
|---|---|
| `saved=yes` / `saved=no` | 本次记录是否成功落盘 |
| `SKU collection unavailable` | 采集流程异常（存储不可用等） |
| `hits=N annualHits=N` | 三档总改写数 / 其中 2TB |
| `源 SKU -> 实际目标 xN` | 逐行目标与次数 |
| `fallback=<目标>` | 该行使用了备用档，后面跟的就是实际目标 |

---

## 6. 逐项判断

| 观察 | 结论与下一步 |
|---|---|
| 报告页打不开 / 证书错误 | 根证书未装或未开启完全信任，见 [clash-setup.md §3](clash-setup.md#3-证书) |
| 报告页是 Google 普通页面或 404 | 请求没进旁路：查规则顺序、`G1` 组选择、`G1-MITM` 地址 |
| `scan.version` 为空 | 还没有任何记录写入；先浏览方案页 |
| `scan.version` 是旧版本 | 记录来自旧采集器，比较计数与时间后重新打开方案页 |
| 计数增长、状态 `known-skus` | 收到的是重复编号，次数会涨、条目不变，属正常 |
| 计数、时间、事件全部不变 | 本轮没有写入新记录；先查日志 `saved=no`，再查缓存与规则 |
| 状态 `no-skus` | 响应里没有候选字符串，核对页面与 `one.google.com/` 范围 |
| 状态 `non-text` | 响应不是文本，只增加非文本计数 |
| 状态 `limit-reached` | 已满 300 上限；需要继续采集时先导出再 `?clear=1` |
| `hits>0` 但 `annualHits=0` | 只命中 20TB / 30TB，看 `matchedFrom` 各行的 `id` / `to` |
| `status=no-match`、`hitCount=0` | 三档都没命中，响应原样返回 |
| 某行 `fallback=true` | 该档免费试用未出现在原文，用了对应的三个月 90p |
| App Store 报错或没有商品 | 记录该档实际 `to` 与收银台提示；文本替换成功 ≠ 商品存在 |
| 商品名称/周期/金额与预期不同 | 以 App Store 返回为准，候选名里的 `12months`、`90p` 不代表实际周期与价格 |

---

## 7. 清理

只有确实要重置历史时才清理，且先导出 JSON：

```bash
# 命令行
.venv/bin/python -m g1acq clear --state ~/.g1-acq/state.json

# 或者浏览器
https://one.google.com/g1-sku-report?clear=1
```

清理只影响 `g1.sku.scan.v1` 与 `g1.pro.annual.test.v1` 两个键，不动其它数据。清完回到不带 `clear=1` 的报告地址，避免刷新时再次清空。

---

## 8. 实机记录模板

```text
采集 / 测试时间（含时区）：[填写]
iOS / Google App / Clash 版本：[填写]
旁路版本：8.2.0
旁路主机与地址：[填写 例如 192.168.1.10:8080]
Clash 配置来源：[控制台生成（只做 G1 / 带订阅）/ 手动合并片段]
G1 组当前选择：[G1-MITM / DIRECT]
证书安装与完全信任：[是 / 否]
报告页标记：[填写实际显示；应为 "G1 ACQ 旁路已接管 · v8.2.0"]
reportVersion：[填写；当前 v8.2.0]
scan.version：[填写实际保存值]
打开方案前 scannedResponses / matchedResponses / nonTextResponses：[填写]
打开方案后 scannedResponses / matchedResponses / nonTextResponses：[填写]
打开方案前最近事件时间：[填写]
打开方案后最近事件时间：[填写]
最新事件 at / path / bodyType / status：[填写]
最新事件 candidateCount / addedCount / omittedCount：[填写]
configuredTarget：g1.2tb.ai.12months_ip_90p
候选来源：用户截图指定（user-specified）
截图价格标签：$1.99 × 12 months = $23.88/year（12 个月合计标签）
截图折扣含义：90p = 90% off，约一折
候选验证状态：待 App Store 实际返回商品
最近一次执行 test.version / test.updatedAt：[填写]
test.target / test.targetOrigin：[填写]
test.matchedFrom：[填写 {id, to, count, fallback}]
test.hitCount / test.annualHitCount / test.status：[填写]
采集到的原始 iOS 2TB 完整 SKU：[填写原文；未出现记 "未采集到"]
采集到的 20TB / 30TB 完整 SKU：[填写原文；未出现记 "未采集到"]
是否拉起 App Store 收银台：[填写]
App Store 商品名称 / 订阅周期 / 币种 / 初次金额 / 续费金额：[填写]
实际错误提示：[填写原文；无则记 "无"]
是否实际完成购买：[填写]
购买后 Google One 账户显示的权益：[仅在实际购买后填写]
本轮导出的 JSON 文件：[填写]
```
