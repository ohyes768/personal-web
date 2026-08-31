/**
 * 定时任务 update 端点 → 指标说明
 * 与 backend/macro/src/scheduler/scheduler.json 的 targets 对齐；新增端点时同步更新。
 */
export interface UpdateEndpointMeta {
  /** 对应指标/数据内容（历史明细「指标」列） */
  label: string;
  /** 数据来源简述（可选，tooltip） */
  source?: string;
}

export const UPDATE_ENDPOINT_LABELS: Record<string, UpdateEndpointMeta> = {
  '/update/china-bonds': {
    label: '中债收益率',
    source: '中债登',
  },
  '/update/dr007': {
    label: 'DR007 质押回购利率',
    source: '中国货币网',
  },
  '/update/fund-flow': {
    label: '北向/南向资金流向',
    source: '东方财富',
  },
  '/update/volume': {
    label: '两市成交额',
    source: '沪深交易所官方 API',
  },
  '/update/turnover': {
    label: '两市加权换手率',
    source: '沪深交易所官方 API',
  },
  '/update/margin': {
    label: '融资余额',
    source: 'akshare',
  },
  '/update/us-treasuries': {
    label: '美国国债收益率',
    source: 'FRED',
  },
  '/update/exchange-rates': {
    label: '主要汇率',
    source: '阿里云行情 API',
  },
  '/update/eu-bonds': {
    label: '欧洲（德国）国债收益率',
    source: 'OECD',
  },
  '/update/jp-bonds': {
    label: '日本国债收益率',
    source: 'OECD',
  },
  '/update/vix': {
    label: 'VIX 恐慌指数',
    source: 'FRED',
  },
  '/update/tga': {
    label: 'TGA 账户余额',
    source: 'FRED',
  },
  '/update/hibor': {
    label: 'HIBOR 隔夜拆息',
    source: 'HKMA',
  },
  '/update/ted-spread': {
    label: 'TED 利差',
    source: 'FRED',
  },
  '/update/commodities': {
    label: '商品（黄金/白银/原油/铜）',
    source: '阿里云行情 API',
  },
  '/update/indices': {
    label: '全球股指（恒生/上证/标普/纳指/道指）',
    source: '阿里云行情 API',
  },
};

/** 历史明细表展示用；未知端点回退为路径本身 */
export function getUpdateEndpointLabel(path: string): string {
  return UPDATE_ENDPOINT_LABELS[path]?.label ?? path;
}

export function getUpdateEndpointSource(path: string): string | undefined {
  return UPDATE_ENDPOINT_LABELS[path]?.source;
}
