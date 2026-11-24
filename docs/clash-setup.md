# 在 Clash 上部署 G1 ACQ

本文是 [README](../README.md) 第 3 节的展开版，覆盖旁路主机选址、证书、分流规则、验证与排错。

---

## 1. 结构回顾

Clash / mihomo **不含 MITM 与响应改写**，所以功能被拆成两半：

```text
┌──────────────┐   CONNECT one.google.com:443   ┌────────────────────────┐
│ 手机 Clash   │ ─────────────────────────────> │ G1 ACQ 旁路            │
│ (mihomo)     │                                │ mitmproxy + g1_addon   │
└──────────────┘ <───── 改写后的响应 ────────── └────────────────────────┘
        │                                                 │
        │ 其它域名走你自己的节点                            │ TLS
        ▼                                                 ▼
   互联网                                          one.google.com
```

手机侧只多了一条 `DOMAIN,one.google.com` 规则；旁路侧只处理这一个域名。

---

## 2. 旁路主机选址

| 方案 | 适用 | 注意 |
|---|---|---|
| **同一 Wi-Fi 的 Mac** | 临时调试、单人使用 | Clash 里填 Mac 的局域网 IP；macOS 防火墙需放行端口；离开 Wi-Fi 就失效 |
| **VPS** | 日常使用 | 需能从 VPS 访问 Google，否则加 `--upstream`；对外开放端口要做好访问控制 |
| **NAS / 树莓派 / 容器** | 家里常开 | 同上，注意别把 8080 暴露到公网 |

端口默认 `8080`，可用 `G1_PORT` 改：

```bash
G1_PORT=9090 ./run.sh
```

旁路**自己不需要 root**，也不会改系统路由。

### 2.1 旁路访问不了 Google 怎么办

让旁路复用你已有的代理出口：

```bash
G1_UPSTREAM=http://127.0.0.1:7890 ./run.sh
```

`--upstream` 支持 `http://`、`https://`、`socks5://` 等 mitmproxy 认可的写法。Docker 里访问宿主机代理用 `http://host.docker.internal:7890`。

### 2.2 安全提示

- 旁路是一个**明文 HTTP 代理**，只承载 `CONNECT one.google.com:443` 这一行，隧道里仍然是 TLS，没有明文业务数据。
- 但 CA 私钥就等于可以伪造任意站点证书，**不要**把 `~/.mitmproxy/mitmproxy-ca.pem` 泄露出去。
- 公网部署时建议在防火墙或反向代理后面加 IP 白名单，至少不要长期开放给所有人。

---

## 3. 证书

### 3.1 生成

首次 `./run.sh` 时，mitmproxy 自动在 `~/.mitmproxy/` 生成：

| 文件 | 用途 |
|---|---|
| `mitmproxy-ca.pem` | CA 私钥 + 证书，**保密** |
| `mitmproxy-ca-cert.pem` / `.cer` | 证书本体（PEM 编码） |
| `mitmproxy-ca-cert.p12` | PKCS#12 包装 |

### 3.2 导出给 iOS

iOS 对 `.cer` 的编码比较挑剔，而 mitmproxy 默认写的是 **PEM**。用内置命令转成 DER 最稳：

```bash
.venv/bin/python -m g1acq ca --out g1-acq-ca.der
```

输出会带上 SHA-256 指纹，装机后可以核对：

```text
wrote /path/g1-acq-ca.der (825 bytes)
SHA-256 4F:FD:...
```

把 `.der` 传到手机（AirDrop / 邮件 / 文件 App / 局域网 HTTP 都可以）。

### 3.3 在 iOS 上安装

1. **设置 → 通用 → VPN 与设备管理 → 已下载的描述文件** → 选择证书 → **安装**。
2. **设置 → 通用 → 关于本机 → 证书信任设置** → 打开该根证书的 **完全信任**。

第 2 步不做，浏览器和 App 仍会判定证书不可信。

### 3.4 用 mitm.it 快速下载（可选）

临时在 Clash 规则最前面加一条：

```yaml
- DOMAIN,mitm.it,G1
```

然后在 Safari 打开 `http://mitm.it`，选 Apple 下载。装完**记得删掉这条规则**，否则 `mitm.it` 会一直绕到旁路。

mitm.it 是明文 HTTP，旁路的 `allow_hosts` 只限制 TLS 拦截，不影响它。

### 3.5 删除证书

**设置 → 通用 → VPN 与设备管理** 移除描述文件，再到证书信任设置里关掉信任。

---

## 4. Clash 配置

### 4.1 用完整配置

[`clash/g1-acq.yaml`](../clash/g1-acq.yaml) 是一份可直接运行的 mihomo 配置，需要改两处：

```yaml
proxies:
  - name: "G1-MITM"
    type: http
    server: 192.168.1.10   # 旁路主机地址
    port: 8080             # 旁路监听端口
    tls: false             # 保持 false

  - name: "YOUR-NODE"      # 换成你自己的节点
    type: trojan
    server: ...
```

导入方式取决于客户端版本，一般是「配置 → 添加 → 从文件 / 从 URL 导入」。

### 4.2 合并到现有配置

用 [`clash/g1-acq.snippet.yaml`](../clash/g1-acq.snippet.yaml)，把三段分别抄进你配置的 `proxies:`、`proxy-groups:`、`rules:`：

```yaml
proxies:
  - name: "G1-MITM"
    type: http
    server: 192.168.1.10
    port: 8080
    tls: false
    udp: false

proxy-groups:
  - name: "G1"
    type: select
    proxies: ["G1-MITM", "DIRECT"]

rules:
  - AND,((NETWORK,udp),(DST-PORT,443),(DOMAIN,one.google.com)),REJECT-DROP
  - DOMAIN,one.google.com,G1
  - DOMAIN-SUFFIX,one.google.com,G1
```

**顺序是唯一容易出错的地方**：这三条必须在你最后那条 `MATCH`（或 `FINAL`）之前，否则 `one.google.com` 会被前面的兜底规则接走。

### 4.3 每条规则的作用

| 规则 | 作用 |
|---|---|
| `AND,((NETWORK,udp),(DST-PORT,443),(DOMAIN,one.google.com)),REJECT-DROP` | 丢弃该域名的 QUIC，让客户端回退到 TCP，旁路才看得到响应。`REJECT-DROP` 是 mihomo 里对应 Shadowrocket `REJECT-NO-DROP` 的策略：静默丢包，客户端会快速回退而不是直接报错 |
| `DOMAIN,one.google.com,G1` | 把目标域名交给旁路 |
| `DOMAIN-SUFFIX,one.google.com,G1` | 兜底，覆盖未走 SNI 的连接；不匹配时无副作用 |

> Shadowrocket 版丢弃的是**全局** UDP 443，会影响其它 App 的 HTTP/3。本版把它限定在 `one.google.com`，是刻意的改进。想恢复全局行为，把第三条条件去掉即可。

### 4.4 DNS 与 sniffer

配置里保留了 `enhanced-mode: fake-ip` 和 `sniffer.enable: true`：

- **fake-ip** 让规则引擎始终知道域名，`DOMAIN,one.google.com` 才可靠。
- **sniffer** 在 App 直接连 IP 时把域名找回来。

不要给 `one.google.com` 加 `fake-ip-filter`，那会让域名规则退化成 IP 规则。

### 4.5 代理组 `G1`

`G1` 是一个 `select` 组，默认选 `G1-MITM`。切到 `DIRECT` 就等于关掉改写，方便随时对比和回滚。

---

## 5. 验证清单

按顺序做，每步都有可观察结果：

| 步骤 | 期望结果 | 不通过时看 |
|---|---|---|
| 旁路启动 | 日志出现 `[g1-acq] 8.0.0 ready: target=... state=...` | 端口占用、依赖没装 |
| 旁路可达 | 旁路主机上 `curl -sS -k --proxy http://127.0.0.1:8080 https://one.google.com/g1-sku-report` 返回报告 HTML | 服务没起、`allow_hosts` 写错 |
| Clash 规则命中 | 手机上打开报告页，用 `mihomo` 日志能看到 `match Domain(one.google.com) using G1[G1-MITM]` | 规则顺序、`G1-MITM` 地址写错 |
| 报告页接管 | Safari 显示「G1 ACQ 旁路已接管 · v8.0.0」 | 证书未信任、规则未命中 |
| 改写生效 | 打开 Google One 方案页后，旁路日志出现 `hits=N` | 页面被缓存、URL 不是 `/ai?` |

一条命令检查旁路本身是否正常（在旁路主机上执行，不经过手机）：

```bash
curl -sS -k --proxy http://127.0.0.1:8080 https://one.google.com/g1-sku-report | head -c 120
```

---

## 6. 排错表

| 现象 | 常见原因 | 处理 |
|---|---|---|
| Safari 打开报告页失败（证书错误 / 连接中断） | 根证书没装或没开「完全信任」 | 回到 [第 3 节](#3-证书) 重装并开启信任 |
| 报告页显示 Google 普通页面或 404 | 请求没走到旁路 | 检查 `DOMAIN,one.google.com,G1` 是否在 `MATCH` 之前、`G1` 组是否选了 `G1-MITM` |
| 报告页正常，但计数一直不涨 | 页面被缓存；或 App 用的不是 `one.google.com` | 关掉 Google App 后台重进；抓 `mihomo` 日志确认实际域名 |
| 计数涨，但 `skus` 一直是旧编号 | 服务器下发的是重复编号 | 看最近一条事件是否 `known-skus`；重复只加次数不加条目 |
| `non-text` 一直增加 | 响应是二进制或被 gzip/br 之外的编码包装 | 本版支持 gzip/deflate/br/zstd；异常编码会记为 `non-text` |
| `hits` 有值但 `annualHits=0` | 只命中了 20TB / 30TB | 看 `matchedFrom` 每行的 `id` 与 `to` |
| App Store 打开后商品不存在或报错 | 文本替换成功 ≠ 商品存在 | 记录该档实际目标 `to` 与收银台提示，两者分别记录 |
| 改完后其它 App 的 HTTP/3 正常，但本功能无效 | QUIC 没被拦住，页面走了 UDP | 确认 `AND` 规则在 `DOMAIN` 规则**之前**，且 `REJECT-DROP` 拼写正确 |
| `saved=no` | 状态文件写不进去 | 检查 `~/.g1-acq/` 权限、磁盘空间；Docker 下检查卷挂载 |

---

## 7. 数据与隐私

- 状态文件：`~/.g1-acq/state.json`（可用 `G1_STATE` 改）。
- 只保存：候选 ID、次数、最近发现时间、计数、最多 10 条脱敏事件（时间 / 固定类别路径 / 正文类型 / 计数）。
- 不保存：响应正文、请求头、响应头、query、完整 URL。
- 不联网上报：旁路只做改写与本地落盘。
- 单租户：一个旁路实例对应一份记录。多台设备共用同一旁路会共用同一份清单；需要隔离时，每台设备单独跑一个实例（不同 `--port` 与 `--state`）。

---

## 8. 运维命令

```bash
# 看报告
.venv/bin/python -m g1acq report --state ~/.g1-acq/state.json
.venv/bin/python -m g1acq report --state ~/.g1-acq/state.json --html

# 清空本工具的两份记录
.venv/bin/python -m g1acq clear --state ~/.g1-acq/state.json

# 导出 DER 证书
.venv/bin/python -m g1acq ca --out g1-acq-ca.der

# 换一个 2TB 候选（不改代码）
G1_TARGET=g1.2tb.ai.other_ip_90p ./run.sh
```

`--target` / `G1_TARGET` 只影响 2TB 档的目标，20TB / 30TB 映射保持不变。报告里的 `configuredTarget` 会反映当前配置。
