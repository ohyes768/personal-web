"use client";

// 今日总览：日期可切换的双机活动时间线
import { useState } from "react";
import { useToday } from "@/lib/hooks";
import { addDays, todayStr } from "@/lib/time";
import { MachineTimeline } from "@/components/MachineTimeline";
import { Empty, ErrorState, Loading } from "@/components/States";

export default function TodayPage() {
  const [date, setDate] = useState(todayStr());
  const { data, loading, error, reload } = useToday(date);

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <button
          onClick={() => setDate(addDays(date, -1))}
          className="w-8 h-8 rounded-md border border-gray-300 bg-white hover:bg-gray-50 cursor-pointer"
          aria-label="前一天"
        >
          ‹
        </button>
        <input
          type="date"
          value={date}
          max={todayStr()}
          onChange={(e) => e.target.value && setDate(e.target.value)}
          className="px-2 py-1.5 text-sm rounded-md border border-gray-300"
        />
        <button
          onClick={() => setDate(addDays(date, 1))}
          disabled={date >= todayStr()}
          className="w-8 h-8 rounded-md border border-gray-300 bg-white hover:bg-gray-50 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="后一天"
        >
          ›
        </button>
        {date !== todayStr() && (
          <button
            onClick={() => setDate(todayStr())}
            className="px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white hover:bg-gray-50 cursor-pointer"
          >
            今天
          </button>
        )}
      </div>

      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data || data.items.length === 0 ? (
        <Empty hint="这一天没有记录活动" />
      ) : (
        <MachineTimeline items={data.items} />
      )}
    </div>
  );
}
