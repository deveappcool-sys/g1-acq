# 部署与排错

本文是 [README](../README.md) 的展开版：装在哪里、每一步应该看到什么、出问题怎么查。

> ⚠️ **仅供研究与兼容性测试。** 改写商品编号来观察商店行为可能违反 Google / Apple 的服务条款；请勿用于获取未付费权益，测试时不要真正完成购买。

---

## 1. 结构回顾

Clash 不含 MITM 与响应改写，所以功能被拆成两半：

```text
┌──────────────┐   CONNECT one.google.com:443   ┌────────────────────────┐
│ 手机 Clash   │ ─────────────────────────────> │ 旁路（本项目）          │
│ (mihomo)     │                                │ mitmproxy + g1_addon   │
└──────────────┘ <───── 改写后的响应 ────────── └────────────────────────┘
        │                                                 │
        │ 其它域名走你自己的节点（配了订阅时）              │ TLS
        ▼                                                 ▼
   互联网                                          one.google.com
```

手机侧只有一条 `DOMAIN,one.google.com` 规则，和一条丢掉该域名 QUIC 的 `AND` 规则。

---

## 2. 装在哪

| 方案 | 适用 | 注意 |
|---|---|---|
| **同一个 Wi-Fi 的 Mac** | 最省事 | 电脑得开着；换 Wi-Fi 后 IP 会变，控制台里的配置要重新生成一次 |
| **VPS** | 出门也要用 | 必须能从 VPS 访问 Google，否则加 `--upstream`；**对外开放端口一定要加认证** |
| **NAS / 树莓派 / Docker** | 家里常开 | 同上 |

旁路不需要 root，也不会改系统路由。

### 2.1 旁路自己上不了 Google

让它复用你已有的代理出口：

```bash
G1_UPSTREAM=http://127.0.0.1:7890 ./install.sh
```

或在启动时加 `--upstream`。Docker 里访问宿主机代理用 `http://host.docker.internal:7890`（Linux 还要加 `extra_hosts: ["host.docker.internal:host-gateway"]`）。

> **不要把上游设成一个会把 `one.google.com` 送回旁路的配置**，否则两个代理会互相转发成环，表现为一直超时。给上游那份配置单独加 `DOMAIN,one.google.com,DIRECT`。

---

## 3. 安装脚本做了什么

`./install.sh` 依次做四件事，每一步都打印在终端上：

1. 找一个 Python ≥ 3.12（本机没有就用 `uv` 下一个）
2. 建 `.venv`，装 `mitmproxy` 和 `segno`
3. 注册后台服务：macOS 用 launchd，Linux 用 systemd，都没有就 `nohup`
4. 跑自检，打印控制台地址和**二维码**

不想注册服务（比如只想先试试）：

```bash
G1_NO_SERVICE=1 ./install.sh
```

---

## 4. 手机侧

### 4.1 证书

控制台页面第一块就是它：

1. 点 **下载证书（.mobileconfig）**
2. 手机上点开文件 → **设置 → 通用 → VPN 与设备管理 → 已下载的描述文件** → 安装 → 输锁屏密码
3. **设置 → 通用 → 关于本机 → 证书信任设置** → 打开该证书的**完全信任**

第 3 步不做，等于没装，后面一定失败。

> 为什么一定要 `.mobileconfig` / 正确的 MIME：iOS 只有在文件被识别为"配置描述文件"时才给安装入口。用普通方法（`python -m http.server` 之类）下载 `.cer`，iOS 会把它当普通文件存进「文件」App，设置里根本不会出现安装项——这个坑本项目已经替你填了。

### 4.2 Clash 配置

页面第二块给两个选项：

| 选项 | 内容 |
|---|---|
| **只做 G1（其它直连）** | 只有旁路，`MATCH,DIRECT`。不需要任何机场节点，用来先把链路走通 |
| **生成带订阅的配置** | 粘你的订阅链接，生成带节点的完整配置；`PROXY` 默认选 `AUTO`（你的节点），只有 `one.google.com` 走旁路 |

生成后用 Clash 的「从 URL 导入」——把页面给出的地址复制过去，或者直接扫二维码。

> 订阅链接只在这台机器上使用，不会上传；生成完可以关掉控制台。

### 4.3 验证

| 步骤 | 期望 | 不对时看 |
|---|---|---|
| Clash 连上 | 状态栏出现 VPN 标识 | 配置没选中 |
| 打开 `https://one.google.com/g1-sku-report` | 显示「G1 ACQ 旁路已接管 · v8.1.0」 | 证书信任、规则顺序 |
| 打开 Google One 点一个方案 | 控制台「最近改写」出现数字 | 见第 6 节 |
| 点「订阅」 | 弹出 **App Store 的购买面板** | 见第 5 节 |

---

## 5. 为什么页面价格不变

这是设计如此，不是失败。

Google One 页面上的价格是 **Google 写在响应里的文字**；本项目只替换**商品 ID**，不碰价格字段。改写的作用是让 App 拿着另一个商品 ID 去问 App Store。

所以：

- 页面上的价格 → **永远是原价**
- App Store 购买面板里的价格 → **按改写后的商品 ID 由 Apple 返回**

判定点只有一个：**点订阅后弹出的那个白色系统面板**。它里面的商品名和金额才是结果。

| 面板里显示 | 结论 |
|---|---|
| 对应折扣档的商品和金额 | 改写成功，商品存在 |
| 原价商品 | Apple 目录里没有这个 ID |
| 「商品不可用」 | 同上，ID 不存在 |

---

## 6. 排错

### 6.1 先跑自检

```bash
./.venv/bin/python -m g1acq doctor
```

它检查五个部件：旁路端口、控制台端口、状态文件、采集与最近改写、根证书，外加当前局域网地址。把输出贴出来即可（不含私钥和账号信息）。

### 6.2 对照表

| 现象 | 常见原因 | 处理 |
|---|---|---|
| 控制台打不开 | 服务没起 / 不在同一 Wi-Fi / IP 变了 | `doctor` 看端口；重新扫码 |
| 报告页报证书错误 | 没开「完全信任」 | 回到 4.1 第 3 步 |
| 报告页显示 Google 404 | 请求没进旁路：规则没生效或配置没选中 | 检查 `DOMAIN,one.google.com,G1` 是否在 `MATCH` 之前 |
| 控制台「手机连过」一直是 0 | Clash 没连 / 节点地址不对 | 重新生成配置并导入 |
| 采集有数字，最近改写为空 | 还没走到内购流程（`/ai?` 路径） | 打开 Google One 的原生方案页，而不是浏览器网页版 |
| 有改写但价格不变 | **正常**，见第 5 节 | 看 App Store 面板 |
| `saved=no` | 状态文件写不进去 | 检查 `~/.g1-acq/` 权限、磁盘 |
| Clash 报 407 | 旁路开了认证但节点没填凭据 | `G1-MITM` 里补 `username`/`password` |
| 换 Wi-Fi 后失效 | IP 变了 | 回控制台重新生成配置；长期方案是路由器给这台机器绑定固定 IP |

### 6.3 日志

```bash
tail -f ~/Library/Logs/g1-acq.log     # macOS
journalctl --user -u g1-acq -f        # Linux systemd
```

关键行：

```
[g1-acq] g1-acq-clash-v8.0 status=new-skus addedCount=11 ...
[g1-acq] g1-acq-clash-v8.0 hits=59 annualHits=30
[g1-acq] g1.ios.20tb.m.v2 -> g1.20tb.3months_ip_90p.acq x19
```

---

## 7. 安全

- 旁路默认**不开认证**，因为目标场景是"自己的机器 + 自己的局域网"。同一 Wi-Fi 下别人能拿它当代理、能读报告页，**不要把 8080 暴露到公网**。
- 真要放到 VPS：

  ```bash
  G1_AUTH=用户名:密码 ./install.sh
  ```

  生成的 Clash 配置会自动带上同样的凭据（控制台生成时也会带上）。
- `allow_hosts` 只决定**哪些域名会被解密**，不决定**能代理到哪里**。
- CA 私钥 `~/.mitmproxy/mitmproxy-ca.pem` 等同于可以伪造任意站点证书，别泄露、别提交。
- 控制台只暴露四个路由（页面、证书、生成的配置、状态），不能被用来读取任意文件。

---

## 8. 运维命令

```bash
# 自检
./.venv/bin/python -m g1acq doctor

# 控制台地址 + 二维码
./.venv/bin/python -m g1acq url

# 看报告
./.venv/bin/python -m g1acq report --state ~/.g1-acq/state.json
./.venv/bin/python -m g1acq report --state ~/.g1-acq/state.json --html

# 清空本工具的两份记录
./.venv/bin/python -m g1acq clear --state ~/.g1-acq/state.json

# 导出证书 DER
./.venv/bin/python -m g1acq ca --out g1-acq-ca.der

# 换一个 2TB 候选（不改代码）
./.venv/bin/python -m g1acq serve --target g1.2tb.ai.other_ip_90p

# 关掉控制台
./.venv/bin/python -m g1acq serve --console 0
```

停服务：

```bash
launchctl bootout gui/$(id -u)/com.g1acq.sidecar   # macOS
systemctl --user disable --now g1-acq               # Linux
```
