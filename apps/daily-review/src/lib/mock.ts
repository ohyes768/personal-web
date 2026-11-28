// 后端未就绪时的开发兜底：设 NEXT_PUBLIC_DAILY_REVIEW_MOCK=1 后，
// fetch 失败自动回落到这份数据，方便脱离 8103 后端开发 / 演示布局。
import type {
  ActivityItem,
  ProjectSummary,
  ReportDetail,
  ReportMeta,
  ReportType,
  UsageData,
} from "./api";

const now = new Date();
const iso = (h: number, m: number) => {
  const d = new Date(now);
  d.setHours(h, m, 0, 0);
  return d.toISOString();
};

const items: ActivityItem[] = [
  {
    machine: "windows",
    kind: "session",
    project: "personal-web",
    title: "每日工作回顾服务设计评审",
    summary_text: "与用户拷问式评审架构方案，定稿设计文档；确定 NAS 服务 + Windows 采集器的方案 C。",
    started_at: iso(9, 10),
    ended_at: iso(10, 40),
  },
  {
    machine: "windows",
    kind: "commit",
    project: "personal-web",
    title: "docs: daily-review 设计定稿",
    summary_text: "提交设计文档与数据源口径表。",
    started_at: iso(10, 45),
    ended_at: iso(10, 46),
  },
  {
    machine: "windows",
    kind: "session",
    project: "task-board",
    title: "排期日历视图迭代",
    summary_text: "日历格增加 missed/running 状态 chip；修复合并单元格溢出。",
    started_at: iso(11, 0),
    ended_at: iso(12, 10),
  },
  {
    machine: "nas",
    kind: "session",
    project: "rss-relay",
    title: "RSS 转发失败重试排查",
    summary_text: "定位到上游 429，退避策略改为指数退避并落库重试队列。",
    started_at: iso(9, 30),
    ended_at: iso(10, 5),
  },
  {
    machine: "nas",
    kind: "commit",
    project: "rss-relay",
    title: "fix: 指数退避 + 重试队列",
    summary_text: "重试上限 5 次，超限进入死信并告警。",
    started_at: iso(10, 8),
    ended_at: iso(10, 9),
  },
  {
    machine: "nas",
    kind: "session",
    project: "index-trends",
    title: "周线通道阈值调参",
    summary_text: "对比 20/60 日通道在不同带宽下的信号频率，选定 2.5 倍标准差。",
    started_at: iso(14, 0),
    ended_at: iso(15, 20),
  },
];

export const mockProjects: ProjectSummary[] = [
  {
    project: "personal-web",
    last_activity: iso(1, 0),
    session_count: 6,
    commit_count: 14,
    task_board_count: 0,
    active_days: 5,
    total_count: 20,
    daily_counts: Array.from({ length: 14 }, (_, i) => ({
      day: iso(13 - i, 0),
      count: [2, 0, 1, 3, 1, 0, 0, 2, 1, 0, 4, 1, 2, 3][i],
    })),
    recent_summaries: [
      { title: "daily-review 设计定稿", summary_text: "", started_at: iso(1, 0), kind: "session", machine: "nas" },
      { title: "nginx 驾驶舱 KPI 调整", summary_text: "", started_at: iso(2, 0), kind: "session", machine: "nas" },
    ],
  },
  {
    project: "skills",
    last_activity: iso(2, 0),
    session_count: 3,
    commit_count: 1,
    task_board_count: 0,
    active_days: 2,
    total_count: 4,
    daily_counts: Array.from({ length: 14 }, (_, i) => ({
      day: iso(13 - i, 0),
      count: [1, 0, 0, 2, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0][i],
    })),
    recent_summaries: [
      { title: "理财筛选 skill 迭代", summary_text: "", started_at: iso(2, 0), kind: "session", machine: "nas" },
    ],
  },
];
;

export const mockReports: ReportMeta[] = [
  
  {
    id: "r-daily-1",
    report_type: "daily",
    period_start: "2026-11-27",
    period_end: "2026-11-27",
    generated_at: iso(9, 0),
    status: "done",
    summary_md:
      "## 今日工作\n\n- **personal-web**：daily-review 设计评审并定稿\n- **task-web**：日历视图状态 chip\n- **index-trends**：通道阈值调参收敛到 2.5σ",
  },
];

export const mockReportDetail = (id: string): ReportDetail => {
  const report = mockReports.find((r) => r.id === id) ?? mockReports[0];
  return {
    report,
    records: items.map(({ machine, kind, project, title, summary_text, started_at }) => ({
      machine,
      kind,
      project,
      title,
      summary_text,
      started_at,
    })),
  };
};

export const mockEnabled = () => process.env.NEXT_PUBLIC_DAILY_REVIEW_MOCK === "1";
export const mockType = (t: ReportType) => t;

// ---- usage mock：按日期做个稳定的伪随机量级，便于翻页时观察布局 ----

const bucket = (scale: number) => ({
  input_tokens: Math.round(82000 * scale),
  output_tokens: Math.round(14000 * scale),
  cache_read_tokens: Math.round(1250000 * scale),
  cache_write_tokens: Math.round(160000 * scale),
  reasoning_tokens: Math.round(32000 * scale),
  calls: Math.round(26 * scale),
  cost: Math.round(310 * scale) / 100,
});

export const mockUsage = (date: string): UsageData => {
  // 伪随机系数：同一日期取值稳定，不同日期有差异
  const seed = [...date].reduce((a, c) => a + c.charCodeAt(0), 0);
  const w = 0.6 + ((seed * 7) % 30) / 50;
  const n = 0.5 + ((seed * 13) % 30) / 60;
  const win = bucket(w);
  const nas = bucket(n);
  const sum = (a: typeof win, b: typeof win) => ({
    input_tokens: a.input_tokens + b.input_tokens,
    output_tokens: a.output_tokens + b.output_tokens,
    cache_read_tokens: a.cache_read_tokens + b.cache_read_tokens,
    cache_write_tokens: a.cache_write_tokens + b.cache_write_tokens,
    reasoning_tokens: a.reasoning_tokens + b.reasoning_tokens,
    calls: a.calls + b.calls,
    cost: Math.round((a.cost + b.cost) * 100) / 100,
  });
  return {
    date,
    totals: sum(win, nas),
    by_day_machine: [
      { date, machine: "windows", ...win },
      { date, machine: "nas", ...nas },
    ],
    by_model: [
      { machine: "windows", provider: "deepseek", model: "deepseek-chat", ...win },
      { machine: "nas", provider: "deepseek", model: "deepseek-reasoner", ...nas },
    ],
  };
};
