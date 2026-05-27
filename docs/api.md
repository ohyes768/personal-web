# 后端 API 接口文档

本文档描述了后端所有服务的 API 接口规范。

> **注意**: 各服务的详细 API 文档已独立到对应服务的 `docs/` 目录下。

| 服务 | 独立文档路径 |
|------|-------------|
| dividend-select | `backend/dividend-select/docs/api.md` |

本文档主要保留 API 接口汇总表和前端代理配置说明。

---

## 服务架构

| 服务名称 | 端口 | 说明 |
|---------|------|------|
| douyin-processor | 8093 | 抖音视频处理服务 |
| global-macro-fin | 8094 | 宏观经济数据服务 |
| dividend-select | 8092 | 股息率筛选服务 |

---

## 一、douyin-processor (抖音视频处理服务)

**服务地址**: `http://localhost:8093`

**基础路径**: 无

---

### 1. 根路径

获取服务信息。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | GET |
| 路径 | `/` |

**响应示例**

```json
{
  "service": "douyin-processor",
  "version": "1.0.0",
  "docs": "/docs",
  "health": "/health"
}
```

---

### 2. 健康检查

服务健康检查。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | GET |
| 路径 | `/health` |

**响应示例**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "processor_ready": true
}
```

---

### 3. 异步处理视频

异步处理所有视频，立即返回任务状态，后台继续处理。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/process/async` |

**响应**

```json
{
  "success": true,
  "message": "后台处理任务已启动",
  "data": {
    "total": 10,
    "pending": 5,
    "skip": 5
  }
}
```

---

### 4. 同步处理视频

同步处理所有视频，等待处理完成后返回结果。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/process` |

**响应**

```json
{
  "success": true,
  "message": "处理完成",
  "data": {
    "completed": 5,
    "failed": 1,
    "total": 6
  }
}
```

---

### 5. 获取视频列表

获取视频列表，支持分页和状态筛选。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | GET |
| 路径 | `/api/videos` |

**查询参数**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | int | 1 | 页码 |
| page_size | int | 20 | 每页数量（最大100） |
| status | string | - | 状态筛选：completed/processing/failed/pending |
| is_read | bool | - | 是否已读筛选 |

**响应**

```json
{
  "total_count": 10,
  "videos": [
    {
      "aweme_id": "730123456789",
      "status": "completed",
      "title": "视频标题",
      "author": "作者",
      "is_read": false,
      "created_at": "2026-03-05T10:00:00Z",
      "updated_at": "2026-03-05T10:05:00Z"
    }
  ],
  "page": 1,
  "page_size": 20
}
```

---

### 6. 获取视频详情

获取单个视频的详细信息。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | GET |
| 路径 | `/api/videos/{aweme_id}` |

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| aweme_id | string | 视频ID |

**响应**

```json
{
  "aweme_id": "730123456789",
  "status": "completed",
  "title": "视频标题",
  "author": "作者",
  "is_read": false,
  "created_at": "2026-03-05T10:00:00Z",
  "updated_at": "2026-03-05T10:05:00Z",
  "transcript": {
    "text": "转录文本内容...",
    "segments": [
      {
        "start": 0,
        "end": 5.2,
        "text": "第一句话"
      }
    ]
  },
  "summary": "视频摘要..."
}
```

---

### 7. 获取视频处理结果

获取视频的处理结果。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | GET |
| 路径 | `/api/videos/{aweme_id}/result` |

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| aweme_id | string | 视频ID |

**响应**

```json
{
  "aweme_id": "730123456789",
  "status": "completed",
  "result": {
    "transcript": {...},
    "summary": "...",
    "metadata": {...}
  }
}
```

---

### 8. 标记视频已读/未读

标记视频的已读状态。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/videos/{aweme_id}/read` |

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| aweme_id | string | 视频ID |

**请求体**

```json
{
  "is_read": true
}
```

**响应**

```json
{
  "success": true,
  "message": "视频状态已更新"
}
```

---

### 9. 删除视频

硬删除视频，无法恢复。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | DELETE |
| 路径 | `/api/videos/{aweme_id}` |

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| aweme_id | string | 视频ID |

**响应**

```json
{
  "success": true,
  "message": "视频已完全删除"
}
```

---

### 10. 获取处理统计信息

获取视频处理的统计信息。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | GET |
| 路径 | `/api/stats` |

**响应**

```json
{
  "total": 10,
  "completed": 5,
  "processing": 1,
  "failed": 1,
  "pending": 3,
  "success_rate": 0.83
}
```

---

## 二、global-macro-fin (宏观经济数据服务)

**服务地址**: `http://localhost:8094`

**基础路径**: `/api/macro`

---

### 数据范围说明

| 数据类型 | 期种 | 数据频率 | 说明 |
|---------|------|---------|------|
| 美国国债 | 3 个月、2 年、10 年 | 日级 | 美国国债收益率曲线 |
| 欧洲国债 | 3 个月、2 年、10 年 | 日级 | 德国国债收益率曲线 |
| 日本国债 | 10 年 | 日级 | 日本 10 年期国债收益率（注） |
| 汇率数据 | 美元指数、USD/CNY、USD/JPY、USD/EUR | 日级 | 主要货币汇率 |
| VIX | 恐慌指数 | 日级 | CBOE 波动率指数 |
| 资金流向 | 北向/南向净流入 | 日级 | 沪深港通资金流向 |
| 中国国债 | 10 年期 | 日级 | 中国国债收益率 |
| TED利差 | SOFR - DGS3MO | 日级 | 市场流动性指标 |

> **注**: 日本国债目前仅实现 10 年期数据。响应数据结构中保留 `3m` 和 `2y` 字段但返回空数组，待后续补充数据源。

> **注意**: 德债日债分析 Tab 使用月度数据（每月 1 号），美债汇率分析 Tab 使用日级数据。

---

### 1. 根路径

获取服务信息。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | GET |
| 路径 | `/` |

**响应示例**

```json
{
  "service": "global-macro-fin",
  "version": "1.0.0",
  "status": "running",
  "docs": "/docs"
}
```

---

### 2. 健康检查

服务健康检查，获取最后更新时间。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | GET |
| 路径 | `/api/macro/health` |

**响应**

```json
{
  "status": "healthy",
  "service": "global-macro-fin",
  "version": "1.0.0",
  "last_update": "2026-03-05"
}
```

---

### 3. 更新全部数据

n8n 调用此接口触发数据更新（美债 + 欧债 + 日债 + 汇率）。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/update` |

**响应**

```json
{
  "success": true,
  "message": "数据更新完成",
  "updated_at": "2026-03-05T12:00:00Z",
  "data": {
    "us_treasuries": {
      "m3": {
        "date": "2026-03-05",
        "value": 4.52
      },
      "y2": {
        "date": "2026-03-05",
        "value": 4.18
      },
      "y10": {
        "date": "2026-03-05",
        "value": 4.05
      }
    },
    "eu_treasuries": {
      "y10": {
        "date": "2026-03-05",
        "value": 2.45
      }
    },
    "jp_treasuries": {
      "y10": {
        "date": "2026-03-05",
        "value": 0.98
      }
    },
    "exchange_rates": {
      "dollar_index": {
        "date": "2026-03-05",
        "value": 104.5
      },
      "usd_cny": {
        "date": "2026-03-05",
        "value": 7.24
      },
      "usd_jpy": {
        "date": "2026-03-05",
        "value": 149.8
      },
      "usd_eur": {
        "date": "2026-03-05",
        "value": 0.92
      }
    }
  }
}
```

---

### 4. 获取美国国债历史数据

从 2000 年开始获取全部美国国债历史数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/fetch/us-treasuries/history` |

**响应**

```json
{
  "success": true,
  "message": "美国国债历史数据获取完成",
  "updated_at": "2026-03-05T12:00:00Z",
  "data": {
    "us_treasuries": {
      "m3": {...},
      "y2": {...},
      "y10": {...}
    }
  }
}
```

---

### 5. 增量更新美国国债数据

增量更新最近 7 天的美国国债数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/update/us-treasuries` |

**响应**

```json
{
  "success": true,
  "message": "美国国债数据增量更新完成",
  "updated_at": "2026-03-05T12:00:00Z",
  "data": {
    "us_treasuries": {
      "m3": {...},
      "y2": {...},
      "y10": {...}
    }
  }
}
```

---

### 6. 获取汇率历史数据

从 2000 年开始获取全部汇率历史数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/fetch/exchange-rates/history` |

**响应**

```json
{
  "success": true,
  "message": "汇率历史数据获取完成",
  "updated_at": "2026-03-05T12:00:00Z",
  "data": {
    "exchange_rates": {
      "dollar_index": {...},
      "usd_cny": {...},
      "usd_jpy": {...},
      "usd_eur": {...}
    }
  }
}
```

---

### 7. 增量更新汇率数据

增量更新最近 7 天的汇率数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/update/exchange-rates` |

**响应**

```json
{
  "success": true,
  "message": "汇率数据增量更新完成",
  "updated_at": "2026-03-05T12:00:00Z",
  "data": {
    "exchange_rates": {
      "dollar_index": {...},
      "usd_cny": {...},
      "usd_jpy": {...},
      "usd_eur": {...}
    }
  }
}
```

---

### 8. 获取欧洲国债历史数据

从 2000 年开始获取全部欧洲（德国）国债历史数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/fetch/eu-bonds/history` |

**响应**

```json
{
  "success": true,
  "message": "欧洲国债历史数据获取完成",
  "updated_at": "2026-03-05T12:00:00Z",
  "data": {
    "eu_treasuries": {
      "y10": {...}
    }
  }
}
```

---

### 9. 增量更新欧洲国债数据

增量更新最近 365 天的欧洲国债数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/update/eu-bonds` |

**响应**

```json
{
  "success": true,
  "message": "欧洲国债数据增量更新完成",
  "updated_at": "2026-03-05T12:00:00Z",
  "data": {
    "eu_treasuries": {
      "y10": {...}
    }
  }
}
```

---

### 10. 获取日本国债历史数据

从 2000 年开始获取全部日本国债历史数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/fetch/jp-bonds/history` |

**响应**

```json
{
  "success": true,
  "message": "日本国债历史数据获取完成",
  "updated_at": "2026-03-05T12:00:00Z",
  "data": {
    "jp_treasuries": {
      "y10": {...}
    }
  }
}
```

---

### 11. 增量更新日本国债数据

增量更新最近 365 天的日本国债数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/update/jp-bonds` |

**响应**

```json
{
  "success": true,
  "message": "日本国债数据增量更新完成",
  "updated_at": "2026-03-05T12:00:00Z",
  "data": {
    "jp_treasuries": {
      "y10": {...}
    }
  }
}
```

---

### 12. 查询宏观经济数据

前端调用此接口获取展示数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | GET |
| 路径 | `/api/macro/data` |

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start_date | string | 否 | 开始日期，格式：YYYY-MM-DD |
| end_date | string | 否 | 结束日期，格式：YYYY-MM-DD |

**响应**

```json
{
  "success": true,
  "message": "数据查询成功",
  "data": {
    "dates": ["2026-03-01", "2026-03-02"],
    "us_treasuries": {
      "3m": [4.48, 4.50],
      "2y": [4.15, 4.18],
      "10y": [4.02, 4.05]
    },
    "eu_treasuries": {
      "3m": [3.20, 3.22],
      "2y": [2.10, 2.12],
      "10y": [2.42, 2.45]
    },
    "jp_treasuries": {
      "3m": [0.50, 0.52],
      "2y": [0.70, 0.72],
      "10y": [0.95, 0.98]
    },
    "exchange_rates": {
      "dollar_index": [104.2, 104.5],
      "usd_cny": [7.21, 7.24],
      "usd_jpy": [149.5, 149.8],
      "usd_eur": [0.91, 0.92]
    },
    "vix": [18.5, 17.2],
    "fund_flow": {
      "north_net_flow": [45.2, 52.3],
      "north_buy": [null, null],
      "north_sell": [null, null],
      "south_net_flow": [-12.3, -15.2],
      "south_buy": [null, null],
      "south_sell": [null, null]
    },
    "china_bond": {
      "10y": [1.82, 1.85]
    },
    "ted_spread": {
      "sofr": [5.32, 5.35],
      "us_3m": [5.30, 5.32],
      "ted_spread": [0.02, 0.03]
    }
  }
}
```

---

### 13. 获取 VIX 历史数据

从 2000 年开始获取全部 VIX 历史数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/fetch/vix/history` |

**响应**

```json
{
  "success": true,
  "message": "VIX历史数据获取成功",
  "updated_at": "2026-03-29T12:00:00Z",
  "data": {
    "vix": {
      "date": "2026-03-28",
      "value": 18.5
    }
  }
}
```

---

### 14. 增量更新 VIX 数据

增量更新最近 7 天的 VIX 数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/update/vix` |

**响应**

```json
{
  "success": true,
  "message": "VIX数据增量更新成功",
  "updated_at": "2026-03-29T12:00:00Z",
  "data": {
    "vix": {
      "date": "2026-03-28",
      "value": 18.5
    }
  }
}
```

---

### 15. 获取资金流向历史数据

从 2014-11-17（沪港通开通日）开始获取全部资金流向历史数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/fetch/fund-flow/history` |

**响应**

```json
{
  "success": true,
  "message": "资金流向历史数据获取成功",
  "updated_at": "2026-03-29T12:00:00Z",
  "data": {
    "fund_flow": {
      "north": {
        "date": "2026-03-28",
        "net_flow": 52.3,
        "buy": null,
        "sell": null
      },
      "south": {
        "date": "2026-03-28",
        "net_flow": -15.2,
        "buy": null,
        "sell": null
      }
    }
  }
}
```

---

### 16. 增量更新资金流向数据

增量更新最近 7 天的资金流向数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/update/fund-flow` |

**响应**

```json
{
  "success": true,
  "message": "资金流向数据增量更新成功",
  "updated_at": "2026-03-29T12:00:00Z",
  "data": {
    "fund_flow": {
      "north": {
        "date": "2026-03-28",
        "net_flow": 52.3,
        "buy": null,
        "sell": null
      },
      "south": {
        "date": "2026-03-28",
        "net_flow": -15.2,
        "buy": null,
        "sell": null
      }
    }
  }
}
```

---

### 17. 获取资金流向累计数据

获取北向/南向资金 7 日和 30 日累计净流入。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | GET |
| 路径 | `/api/macro/fund-flow/cumulative` |

**响应**

```json
{
  "north_cumulative": {
    "date": "2026-03-28",
    "cum_7d": 358.5,
    "cum_30d": 1520.3
  },
  "south_cumulative": {
    "date": "2026-03-28",
    "cum_7d": -85.2,
    "cum_30d": -320.5
  }
}
```

---

### 18. 获取资金流向历史数据（图表用）

前端调用此接口获取图表展示数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | GET |
| 路径 | `/api/macro/fund-flow/history` |

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start_date | string | 否 | 开始日期，格式：YYYY-MM-DD |
| end_date | string | 否 | 结束日期，格式：YYYY-MM-DD |

**响应**

```json
{
  "data": [
    {
      "date": "2026-03-01",
      "north_net": 45.2,
      "north_buy": null,
      "north_sell": null,
      "south_net": -12.3,
      "south_buy": null,
      "south_sell": null
    }
  ]
}
```

---

### 19. 获取中国国债历史数据

从配置的开始日期获取全部中国国债历史数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/fetch/china-bonds/history` |

**响应**

```json
{
  "success": true,
  "message": "中国国债历史数据获取成功",
  "updated_at": "2026-03-29T12:00:00Z",
  "data": {
    "china_bond_10y": {
      "date": "2026-03-28",
      "value": 1.85
    }
  }
}
```

---

### 20. 增量更新中国国债数据

增量更新最近 7 天的中国国债数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/update/china-bonds` |

**响应**

```json
{
  "success": true,
  "message": "中国国债数据增量更新成功",
  "updated_at": "2026-03-29T12:00:00Z",
  "data": {
    "china_bond_10y": {
      "date": "2026-03-28",
      "value": 1.85
    }
  }
}
```

---

### 21. 获取 TED 利差历史数据

从 2012-01-01 开始获取全部 TED 利差历史数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/fetch/ted-spread/history` |

**响应**

```json
{
  "success": true,
  "message": "TED利差历史数据获取成功",
  "updated_at": "2026-03-29T12:00:00Z",
  "data": {
    "ted_spread": {
      "date": "2026-03-28",
      "sofr": 5.35,
      "us_3m": 5.32,
      "ted_spread": 0.03
    }
  }
}
```

---

### 22. 增量更新 TED 利差数据

增量更新最近 7 天的 TED 利差数据。

**请求**

| 属性 | 值 |
|------|-----|
| 方法 | POST |
| 路径 | `/api/macro/update/ted-spread` |

**响应**

```json
{
  "success": true,
  "message": "TED利差数据增量更新成功",
  "updated_at": "2026-03-29T12:00:00Z",
  "data": {
    "ted_spread": {
      "date": "2026-03-28",
      "sofr": 5.35,
      "us_3m": 5.32,
      "ted_spread": 0.03
    }
  }
}
```

---

## 数据模型

### 国债数据 (TreasuryData)

```typescript
interface TreasuryData {
  date: string;           // YYYY-MM-DD
  value: number | null;   // 收益率值
}
```

### 美国国债 (USTreasuries)

```typescript
interface USTreasuries {
  m3: TreasuryData;   // 3个月期国债
  y2: TreasuryData;   // 2年期国债
  y10: TreasuryData;  // 10年期国债
}
```

### 欧洲国债 (EUTreasuries)

```typescript
interface EUTreasuries {
  y10: TreasuryData;  // 10年期德国国债
}
```

### 日本国债 (JPTreasuries)

```typescript
interface JPTreasuries {
  y10: TreasuryData;  // 10年期日本国债
}
```

### 汇率数据 (ExchangeRateData)

```typescript
interface ExchangeRateData {
  date: string;           // YYYY-MM-DD
  value: number | null;   // 汇率值
}
```

### 汇率 (ExchangeRates)

```typescript
interface ExchangeRates {
  dollar_index: ExchangeRateData;  // 美元指数
  usd_cny: ExchangeRateData;       // 美元兑人民币
  usd_jpy: ExchangeRateData;       // 美元兑日元
  usd_eur: ExchangeRateData;       // 美元兑欧元
}
```

### 通用响应 (UpdateResponse)

```typescript
interface UpdateResponse {
  success: boolean;
  message: string;
  data?: {
    us_treasuries?: USTreasuries;
    eu_treasuries?: EUTreasuries;
    jp_treasuries?: JPTreasuries;
    exchange_rates?: ExchangeRates;
    vix?: VIXData;
    fund_flow?: FundFlow;
    china_bond_10y?: ChinaBondData;
    ted_spread?: TedSpreadData;
  };
  updated_at?: string;   // ISO 8601 格式
  error_code?: string;
}
```

### VIX 数据 (VIXData)

```typescript
interface VIXData {
  date: string;           // YYYY-MM-DD
  value: number | null;   // VIX 恐慌指数值
}
```

### 资金流向数据 (FundFlowData)

```typescript
interface FundFlowData {
  date: string;              // YYYY-MM-DD
  net_flow: number | null;   // 净流入（亿元）
  buy: number | null;        // 买入额（亿元）
  sell: number | null;       // 卖出额（亿元）
}
```

### 资金流向 (FundFlow)

```typescript
interface FundFlow {
  north: FundFlowData;   // 北向资金（港股通→A股）
  south: FundFlowData;   // 南向资金（A股→港股通）
}
```

### 资金流向累计数据 (FundFlowCumulativeData)

```typescript
interface FundFlowCumulativeData {
  date: string;            // YYYY-MM-DD
  cum_7d: number | null;   // 7日累计净流入（亿元）
  cum_30d: number | null;   // 30日累计净流入（亿元）
}
```

### 中国国债数据 (ChinaBondData)

```typescript
interface ChinaBondData {
  date: string;           // YYYY-MM-DD
  value: number | null;   // 10年期国债收益率（%）
}
```

### TED 利差数据 (TedSpreadData)

```typescript
interface TedSpreadData {
  date: string;           // YYYY-MM-DD
  sofr: number | null;    // SOFR 利率（%）
  us_3m: number | null;   // 美国3个月国债收益率（%）
  ted_spread: number | null;  // TED利差 = SOFR - DGS3MO（%）
}
```

### 数据查询响应 (DataResponse)

```typescript
interface DataResponse {
  success: boolean;
  message: string;
  data?: {
    us_treasuries?: {
      m3: TreasuryData[];
      y2: TreasuryData[];
      y10: TreasuryData[];
    };
    eu_treasuries?: {
      y10: TreasuryData[];
    };
    jp_treasuries?: {
      y10: TreasuryData[];
    };
    exchange_rates?: {
      dollar_index: ExchangeRateData[];
      usd_cny: ExchangeRateData[];
      usd_jpy: ExchangeRateData[];
      usd_eur: ExchangeRateData[];
    };
  };
  error_code?: string;
}
```

### 经济数据响应 (EconomicDataResponse)

```typescript
interface EconomicDataResponse {
  dates: string[];         // 日期数组，格式：YYYY-MM-DD
  us_treasuries: {
    '3m': number[];        // 美国 3 个月期国债收益率
    '2y': number[];        // 美国 2 年期国债收益率
    '10y': number[];       // 美国 10 年期国债收益率
  };
  eu_treasuries: {
    '3m': number[];        // 欧洲 3 个月期国债收益率
    '2y': number[];        // 欧洲 2 年期国债收益率
    '10y': number[];       // 欧洲 10 年期国债收益率
  };
  jp_treasuries: {
    '3m': number[];        // 日本 3 个月期国债收益率
    '2y': number[];        // 日本 2 年期国债收益率
    '10y': number[];       // 日本 10 年期国债收益率
  };
  exchange_rates?: {
    dollar_index: number[];  // 美元指数
    usd_cny: number[];       // 美元兑人民币
    usd_jpy: number[];       // 美元兑日元
    usd_eur: number[];       // 美元兑欧元
  };
}
```

> **注意**: 数据格式已更新为日期数组 + 数值数组的形式，不再使用对象数组。

---

## API 接口汇总表

| 服务 | 序号 | 路径 | 方法 | 功能 |
|------|------|------|------|------|
| **douyin-processor** (8093) | 1 | `/` | GET | 根路径服务信息 |
| | 2 | `/health` | GET | 健康检查 |
| | 3 | `/api/process/async` | POST | 异步处理视频 |
| | 4 | `/api/process` | POST | 同步处理视频 |
| | 5 | `/api/videos` | GET | 获取视频列表 |
| | 6 | `/api/videos/{aweme_id}` | GET | 获取视频详情 |
| | 7 | `/api/videos/{aweme_id}/result` | GET | 获取视频处理结果 |
| | 8 | `/api/videos/{aweme_id}/read` | POST | 标记已读/未读 |
| | 9 | `/api/videos/{aweme_id}` | DELETE | 删除视频 |
| | 10 | `/api/stats` | GET | 获取统计信息 |
| **global-macro-fin** (8094) | 1 | `/` | GET | 根路径服务信息 |
| | 2 | `/api/macro/health` | GET | 健康检查 |
| | 3 | `/api/macro/update` | POST | 更新全部数据 |
| | 4 | `/api/macro/data` | GET | 查询宏观经济数据 |
| | 5 | `/api/macro/fetch/us-treasuries/history` | POST | 获取美债历史数据 |
| | 6 | `/api/macro/update/us-treasuries` | POST | 增量更新美债 |
| | 7 | `/api/macro/fetch/exchange-rates/history` | POST | 获取汇率历史数据 |
| | 8 | `/api/macro/update/exchange-rates` | POST | 增量更新汇率 |
| | 9 | `/api/macro/fetch/eu-bonds/history` | POST | 获取欧债历史数据 |
| | 10 | `/api/macro/update/eu-bonds` | POST | 增量更新欧债 |
| | 11 | `/api/macro/fetch/jp-bonds/history` | POST | 获取日债历史数据 |
| | 12 | `/api/macro/update/jp-bonds` | POST | 增量更新日债 |
| | 13 | `/api/macro/fetch/vix/history` | POST | 获取VIX历史数据 |
| | 14 | `/api/macro/update/vix` | POST | 增量更新VIX |
| | 15 | `/api/macro/fetch/fund-flow/history` | POST | 获取资金流向历史数据 |
| | 16 | `/api/macro/update/fund-flow` | POST | 增量更新资金流向 |
| | 17 | `/api/macro/fund-flow/cumulative` | GET | 获取资金累计流入 |
| | 18 | `/api/macro/fund-flow/history` | GET | 获取资金流向图表数据 |
| | 19 | `/api/macro/fetch/china-bonds/history` | POST | 获取中国国债历史数据 |
| | 20 | `/api/macro/update/china-bonds` | POST | 增量更新中国国债 |
| | 21 | `/api/macro/fetch/ted-spread/history` | POST | 获取TED利差历史数据 |
| | 22 | `/api/macro/update/ted-spread` | POST | 增量更新TED利差 |

**总计**: douyin-processor 10 个接口 + global-macro-fin 22 个接口 = 32 个接口

---

## 前端 API 代理

### API 路径映射

前端通过 Next.js API Routes 代理请求到后端服务，避免跨域问题。

| 前端路径 | 代理目标 | 说明 |
|---------|---------|------|
| `/api/dividend/*` | `http://localhost:8092/api/*` | 股息率筛选服务 |
| `/api/macro/*` | `http://localhost:8094/api/macro/*` | 宏观经济数据服务 |
| `/api/douyin/*` | `http://localhost:8093/api/*` | 抖音视频处理服务 |
| `/api/news/*` | 外部新闻 API | 新闻数据聚合 |

### 数据格式变更说明

**v2.0 数据格式** (当前版本):

```typescript
{
  dates: string[],
  us_treasuries: { '3m': number[], '2y': number[], '10y': number[] },
  eu_treasuries: { '3m': number[], '2y': number[], '10y': number[] },
  jp_treasuries: { '3m': number[], '2y': number[], '10y': number[] },
  exchange_rates: { dollar_index: number[], usd_cny: number[], ... }
}
```

**v1.0 数据格式** (已废弃):

```typescript
{
  us_treasuries: { m3: {date, value}[], y2: {...}[], y10: {...}[] },
  eu_treasuries: { y10: {...}[] },
  jp_treasuries: { y10: {...}[] },
  exchange_rates: { dollar_index: {date, value}[], ... }
}
```

> 迁移指南：旧格式使用对象数组，新格式使用平行数组（日期数组 + 数值数组）。