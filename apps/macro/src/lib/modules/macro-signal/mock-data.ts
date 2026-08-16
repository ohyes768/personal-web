/**
 * mock 数据 + 异步加载函数
 *
 * 数据结构对齐 demo v2 终稿:每个 group = { conclusion, total_score, indicators }
 * 2026-05 数据从 skill JSON 直接复制 conclusion + 指标值,指标带三时间
 * (data_date/analyzed_at/next_release_at+note,next_release 按后端 release_rules 推算)
 * 2026-04 / 2026-03:保留旧结构(仅 updated_at),验证前端 data_date ?? updated_at 兼容回退
 * 2026-03 risk_appetite 设为 { conclusion: null, total_score: null, indicators: [] } 演示空分组(total_score 未推送时不渲染徽章)
 *
 * loadMockSnapshot 用 setTimeout 300ms 模拟网络延迟,让 loading 态可见
 */
import type { MacroSignalSnapshot } from './types';

export const MOCK_AVAILABLE_MONTHS = ['2026-03', '2026-04', '2026-05'];

const MOCK_DATA: Record<string, MacroSignalSnapshot> = {
  '2026-05': {
    month: '2026-05',
    generated_at: '2026-05-22T07:28:47Z',
    groups: {
      monetary_policy: { conclusion: '适度宽松', total_score: 65, indicators: [
        { key: 'dr007',  value: 1.328, updated_at: '2026-05-21', data_date: '2026-05-21', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-05-25', next_release_note: 'DR007 每个工作日随银行间市场更新', frequency: 'daily' },
        { key: 'lpr_1y', value: 3.00,  updated_at: '2026-05-20', data_date: '2026-05-20', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-22', next_release_note: 'LPR 每月20日发布(节假日顺延)', frequency: 'monthly' },
        { key: 'mlf_1y', value: 2.00,  updated_at: '2026-05-15', data_date: '2026-05-15', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-15', next_release_note: 'MLF 每月中旬操作日公布', frequency: 'monthly' },
      ]},
      money_supply: { conclusion: '信用扩张', total_score: 72, indicators: [
        { key: 'm2_yoy',     value: 8.6, updated_at: '2026-05-13', data_date: '2026-05-13', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-12', next_release_note: '金融统计数据(M2/社融)约每月13日发布', frequency: 'monthly' },
        { key: 'm1_yoy',     value: 5.0, updated_at: '2026-05-13', data_date: '2026-05-13', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-12', next_release_note: '金融统计数据(M2/社融)约每月13日发布', frequency: 'monthly' },
        { key: 'social_yoy', value: 7.8, updated_at: '2026-05-13', data_date: '2026-05-13', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-12', next_release_note: '金融统计数据(M2/社融)约每月13日发布', frequency: 'monthly' },
      ]},
      entity_economy: { conclusion: '稳健', total_score: 55, indicators: [
        { key: 'pmi_manufacturing', value: 49.5, updated_at: '2026-04-30', data_date: '2026-04-30', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-05-31', next_release_note: '制造业 PMI 每月最后一日发布当月数据', frequency: 'monthly' },
        { key: 'industrial_yoy',    value: 5.6,  updated_at: '2026-05-13', data_date: '2026-05-13', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-12', next_release_note: '工业增加值等统计局数据约每月13日发布', frequency: 'monthly' },
        { key: 'fai_yoy',           value: 4.0,  updated_at: '2026-05-13', data_date: '2026-05-13', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-12', next_release_note: '固投/社零约每月13日发布', frequency: 'monthly' },
        { key: 'retail_yoy',        value: 4.8,  updated_at: '2026-05-13', data_date: '2026-05-13', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-12', next_release_note: '固投/社零约每月13日发布', frequency: 'monthly' },
        { key: 'electricity_yoy',   value: 3.5,  updated_at: '2026-05-20', data_date: '2026-05-20', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-19', next_release_note: '工业用电量约每月20日发布', frequency: 'monthly' },
        { key: 'railway_yoy',       value: null, updated_at: null },
      ]},
      inflation: { conclusion: '温和', total_score: 42, indicators: [
        { key: 'cpi_yoy',      value: 1.2, updated_at: '2026-05-10', data_date: '2026-05-10', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-09', next_release_note: 'CPI/PPI 约每月9日发布上月数据', frequency: 'monthly' },
        { key: 'ppi_yoy',      value: 2.8, updated_at: '2026-05-10', data_date: '2026-05-10', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-09', next_release_note: 'CPI/PPI 约每月9日发布上月数据', frequency: 'monthly' },
        { key: 'core_cpi_yoy', value: 1.2, updated_at: '2026-05-10', data_date: '2026-05-10', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-06-09', next_release_note: '核心 CPI 随 CPI 同步发布', frequency: 'monthly' },
      ]},
      exchange_rate: { conclusion: '外部中性', total_score: 45, indicators: [
        { key: 'dollar_index', value: 119.2825, updated_at: '2026-05-22', data_date: '2026-05-22', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-05-25', next_release_note: '美元指数每工作日更新(FRED 延迟约1天)', frequency: 'daily' },
        { key: 'usd_cny',      value: 6.8092,   updated_at: '2026-05-22', data_date: '2026-05-22', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-05-25', next_release_note: '汇率每工作日更新', frequency: 'daily' },
        { key: 'ted_spread',   value: -0.15,    updated_at: '2026-05-22', data_date: '2026-05-22', analyzed_at: '2026-05-22T07:28:47Z', next_release_at: '2026-05-25', next_release_note: 'TED 利差每工作日更新(FRED 延迟约1周)', frequency: 'daily' },
      ]},
      risk_appetite: { conclusion: '偏热', total_score: 75, indicators: [
        { key: 'total_amount_yi',   value: 50816.71, updated_at: '2026-05-22', data_date: '2026-05-22', analyzed_at: '2026-05-22T07:31:13Z', next_release_at: '2026-05-25', next_release_note: '两市成交额每交易日盘后更新', frequency: 'daily' },
        { key: 'turnover_rate',     value: 2.5297,   updated_at: '2026-05-22', data_date: '2026-05-22', analyzed_at: '2026-05-22T07:28:35Z', next_release_at: '2026-05-25', next_release_note: '换手率每交易日盘后更新', frequency: 'daily' },
        { key: 'margin_balance_yi', value: 28872.12, updated_at: '2026-05-22', data_date: '2026-05-22', analyzed_at: '2026-05-22T07:31:17Z', next_release_at: '2026-05-25', next_release_note: '融资余额次日 09:45 更新前一交易日', frequency: 'daily' },
      ]},
    },
  },
  '2026-04': {
    month: '2026-04',
    generated_at: '2026-04-22T07:28:47Z',
    groups: {
      monetary_policy: { conclusion: '适度宽松', total_score: 58.0, indicators: [
        { key: 'dr007',  value: 1.45, updated_at: '2026-04-21' },
        { key: 'lpr_1y', value: 3.00, updated_at: '2026-04-20' },
        { key: 'mlf_1y', value: 2.00, updated_at: '2026-04-15' },
      ]},
      money_supply: { conclusion: '平稳', total_score: 54.0, indicators: [
        { key: 'm2_yoy',     value: 7.8, updated_at: '2026-04-13' },
        { key: 'm1_yoy',     value: 4.5, updated_at: '2026-04-13' },
        { key: 'social_yoy', value: 7.5, updated_at: '2026-04-13' },
      ]},
      entity_economy: { conclusion: '稳健偏冷', total_score: 44.0, indicators: [
        { key: 'pmi_manufacturing', value: 50.4, updated_at: '2026-03-31' },
        { key: 'industrial_yoy',    value: 5.1,  updated_at: '2026-04-13' },
        { key: 'fai_yoy',           value: 4.2,  updated_at: '2026-04-13' },
        { key: 'retail_yoy',        value: 4.4,  updated_at: '2026-04-13' },
        { key: 'electricity_yoy',   value: 4.1,  updated_at: '2026-04-20' },
        { key: 'railway_yoy',       value: 1.2,  updated_at: '2026-04-07' },
      ]},
      inflation: { conclusion: '低通胀偏冷', total_score: 45.0, indicators: [
        { key: 'cpi_yoy',      value: 0.9, updated_at: '2026-04-10' },
        { key: 'ppi_yoy',      value: 2.3, updated_at: '2026-04-10' },
        { key: 'core_cpi_yoy', value: 1.0, updated_at: '2026-04-10' },
      ]},
      exchange_rate: { conclusion: '外部承压', total_score: 42.0, indicators: [
        { key: 'dollar_index', value: 122.50, updated_at: '2026-04-22' },
        { key: 'usd_cny',      value: 6.9500, updated_at: '2026-04-22' },
        { key: 'ted_spread',   value: 0.05,   updated_at: '2026-04-22' },
      ]},
      risk_appetite: { conclusion: '正常', total_score: 55.0, indicators: [
        { key: 'total_amount_yi',   value: 42000.0, updated_at: '2026-04-22' },
        { key: 'turnover_rate',     value: 2.10,    updated_at: '2026-04-22' },
        { key: 'margin_balance_yi', value: 27500.0, updated_at: '2026-04-22' },
      ]},
    },
  },
  '2026-03': {
    month: '2026-03',
    generated_at: '2026-03-22T07:28:47Z',
    groups: {
      monetary_policy: { conclusion: '适度宽松', total_score: 55.0, indicators: [
        { key: 'dr007',  value: 1.55, updated_at: '2026-03-21' },
        { key: 'lpr_1y', value: 3.10, updated_at: '2026-03-20' },
        { key: 'mlf_1y', value: 2.00, updated_at: '2026-03-15' },
      ]},
      money_supply: { conclusion: '平稳', total_score: 50.0, indicators: [
        { key: 'm2_yoy',     value: 7.2, updated_at: '2026-03-13' },
        { key: 'm1_yoy',     value: 3.8, updated_at: '2026-03-13' },
        { key: 'social_yoy', value: 7.0, updated_at: '2026-03-13' },
      ]},
      entity_economy: { conclusion: '偏冷', total_score: 40.0, indicators: [
        { key: 'pmi_manufacturing', value: 50.2, updated_at: '2026-02-28' },
        { key: 'industrial_yoy',    value: 4.5,  updated_at: '2026-03-13' },
        { key: 'fai_yoy',           value: 4.1,  updated_at: '2026-03-13' },
        { key: 'retail_yoy',        value: 3.7,  updated_at: '2026-03-13' },
        { key: 'electricity_yoy',   value: 2.8,  updated_at: '2026-03-20' },
        { key: 'railway_yoy',       value: -0.5, updated_at: '2026-03-07' },
      ]},
      inflation: { conclusion: '低通胀偏冷', total_score: 38.0, indicators: [
        { key: 'cpi_yoy',      value: 0.5, updated_at: '2026-03-10' },
        { key: 'ppi_yoy',      value: 1.8, updated_at: '2026-03-10' },
        { key: 'core_cpi_yoy', value: 0.8, updated_at: '2026-03-10' },
      ]},
      exchange_rate: { conclusion: '外部宽松', total_score: 62.0, indicators: [
        { key: 'dollar_index', value: 115.00, updated_at: '2026-03-22' },
        { key: 'usd_cny',      value: 6.7500, updated_at: '2026-03-22' },
        { key: 'ted_spread',   value: -0.20,  updated_at: '2026-03-22' },
      ]},
      // 3 月市场情绪数据缺失,演示空分组降级态
      risk_appetite: { conclusion: null, total_score: null, indicators: [] },
    },
  },
};

/**
 * mock 异步加载函数,模拟接口请求
 * @param month 'YYYY-MM'
 * @returns 该月份快照,月份不存在返回 null
 */
export function loadMockSnapshot(month: string): Promise<MacroSignalSnapshot | null> {
  return new Promise(resolve => {
    setTimeout(() => {
      resolve(MOCK_DATA[month] ?? null);
    }, 300);
  });
}
