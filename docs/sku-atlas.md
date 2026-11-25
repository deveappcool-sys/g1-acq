# 实测 SKU 清单

> 由 `python -m g1acq catalog --md` 从本地采集记录生成。
> **这是某个账号、某个地区、某个时刻被下发的清单，不是全球商品目录。**

- 数据来源：`~/.g1-acq/state.json`
- 编号总数：**45**，其中带折扣 **21**

## 带折扣的档位

| 档位 | 周期 | 促销期 | 优惠 | 编号 |
|---|---|---|---|---|
| 30gb | — | 2 个月 | 75% off | `g1.30gb.2month_ip_75p` |
| helium | — | 3 个月 | 75% off | `g1.helium.3months_ip_75p.acq` |
| 100gb | 月付 | 2 个月 | 75% off | `g1.ios.100gb.m.2month_ip_75p` |
| 2tb | 月付 | 2 个月 | 75% off | `g1.ios.2tb.m.2month_ip_75p` |
| 30gb | 月付 | 2 个月 | 75% off | `g1.ios.30gb.m.2month_ip_75p` |
| ai.2tb | 月付 | 3 个月 | 75% off | `g1.ios.ai.2tb.m.ip_3mo_75p.acq` |
| helium | 月付 | 3 个月 | 75% off | `g1.ios.helium.m.3month_ip_75p.acq` |
| 2tb.ai | — | 2 个月 | 50% off | `g1.2tb.ai.2months_ip_50p` |
| helium | 年付 | 12 个月 | 25% off | `g1.helium.annual.12months_ip_25p.acq` |
| ai.2tb | 年付 | 1 年 | 25% off | `g1.ios.ai.2tb.a.ip_1yr_25p.acq` |
| helium | 年付 | 1 年 | 25% off | `g1.ios.helium.a.ip_1yr_25p.acq` |
| 100gb | 年付 | 12 个月 | 10% off | `g1.100gb.annual.12months_ip_10p` |
| 200gb | 年付 | 12 个月 | 10% off | `g1.200gb.annual.12months_ip_10p` |
| 2tb | 年付 | 12 个月 | 10% off | `g1.2tb.annual.12months_ip_10p` |
| 30gb | 年付 | 1 年 | 10% off | `g1.30gb.annual.1year_ip_10p` |
| 100gb | 年付 | 12 个月 | 10% off | `g1.ios.100gb.a.12month_ip_10p` |
| 2tb | 年付 | 12 个月 | 10% off | `g1.ios.2tb.a.12month_ip_10p` |
| 30gb | 年付 | 12 个月 | 10% off | `g1.ios.30gb.a.12month_ip_10p` |
| 100gb | — | 2 个月 | 0.49 定价 | `g1.100gb.2months_ip.0.49` |
| 200gb | — | 2 个月 | 0.74 定价 | `g1.200gb.2months_ip.0.74` |
| 2tb | — | 2 个月 | 2.49 定价 | `g1.2tb.2months_ip.2.49` |

## 全部编号（含原价）

| 编号 | 档位 | 周期 | 优惠 |
|---|---|---|---|
| `g1.30gb.2month_ip_75p` | 30gb | — | 75% off |
| `g1.helium.3months_ip_75p.acq` | helium | — | 75% off |
| `g1.ios.100gb.m.2month_ip_75p` | 100gb | 月付 | 75% off |
| `g1.ios.2tb.m.2month_ip_75p` | 2tb | 月付 | 75% off |
| `g1.ios.30gb.m.2month_ip_75p` | 30gb | 月付 | 75% off |
| `g1.ios.ai.2tb.m.ip_3mo_75p.acq` | ai.2tb | 月付 | 75% off |
| `g1.ios.helium.m.3month_ip_75p.acq` | helium | 月付 | 75% off |
| `g1.2tb.ai.2months_ip_50p` | 2tb.ai | — | 50% off |
| `g1.helium.annual.12months_ip_25p.acq` | helium | 年付 | 25% off |
| `g1.ios.ai.2tb.a.ip_1yr_25p.acq` | ai.2tb | 年付 | 25% off |
| `g1.ios.helium.a.ip_1yr_25p.acq` | helium | 年付 | 25% off |
| `g1.100gb.annual.12months_ip_10p` | 100gb | 年付 | 10% off |
| `g1.200gb.annual.12months_ip_10p` | 200gb | 年付 | 10% off |
| `g1.2tb.annual.12months_ip_10p` | 2tb | 年付 | 10% off |
| `g1.30gb.annual.1year_ip_10p` | 30gb | 年付 | 10% off |
| `g1.ios.100gb.a.12month_ip_10p` | 100gb | 年付 | 10% off |
| `g1.ios.2tb.a.12month_ip_10p` | 2tb | 年付 | 10% off |
| `g1.ios.30gb.a.12month_ip_10p` | 30gb | 年付 | 10% off |
| `g1.100gb.2months_ip.0.49` | 100gb | — | 0.49 定价 |
| `g1.200gb.2months_ip.0.74` | 200gb | — | 0.74 定价 |
| `g1.2tb.2months_ip.2.49` | 2tb | — | 2.49 定价 |
| `com.google.one.generic` | generic | — | 原价 |
| `g1.100gb` | 100gb | — | 原价 |
| `g1.100gb.annual` | 100gb | 年付 | 原价 |
| `g1.10tb` | 10tb | — | 原价 |
| `g1.200gb` | 200gb | — | 原价 |
| `g1.200gb.annual` | 200gb | 年付 | 原价 |
| `g1.20tb.v2` | 20tb | — | 原价 |
| `g1.2tb` | 2tb | — | 原价 |
| `g1.2tb.ai` | 2tb.ai | — | 原价 |
| `g1.2tb.ai.annual` | 2tb.ai | 年付 | 原价 |
| `g1.2tb.annual` | 2tb | 年付 | 原价 |
| `g1.ai.pro` | ai.pro | — | 原价 |
| `g1.helium.a` | helium | 年付 | 原价 |
| `g1.helium.m` | helium | 月付 | 原价 |
| `g1.ios.100gb.a` | 100gb | 年付 | 原价 |
| `g1.ios.100gb.m` | 100gb | 月付 | 原价 |
| `g1.ios.20tb.m.v2` | 20tb | 月付 | 原价 |
| `g1.ios.2tb.a` | 2tb | 年付 | 原价 |
| `g1.ios.2tb.ai.a` | 2tb.ai | 年付 | 原价 |
| `g1.ios.2tb.ai.m` | 2tb.ai | 月付 | 原价 |
| `g1.ios.2tb.m` | 2tb | 月付 | 原价 |
| `g1.ios.30tb.ai.pro.m` | 30tb.ai.pro | 月付 | 原价 |
| `g1.ios.helium.a` | helium | 年付 | 原价 |
| `g1.ios.helium.m` | helium | 月付 | 原价 |

## 命名规律（据实测归纳）

```
g1[.ios].<档位>.<促销期>_ip_<折扣>p[.acq]
g1[.ios].<档位>[.<a|m>]          无折扣原价档
```

- `ios` 前缀 = iOS 内购商品；没有它的是网页/Play 族
- `a` = 年付，`m` = 月付
- `_ip_NNp` = 折扣百分比（`10p` 即 9 折，`90p` 即 1 折）
- `_ip.2.49` 这种写法是**绝对定价**，不是百分比
- `.acq` = acquisition 类促销后缀
