/**
 * 表格头组件
 */
'use client';

export function TableHeader() {
  const columns = [
    { key: 'code', label: '股票代码', width: 'w-24' },
    { key: 'name', label: '股票名称', width: 'w-32' },
    { key: 'avg_yield_3y', label: '3年平均股息率', width: 'w-32' },
    { key: 'actions', label: '操作', width: 'w-64' },
  ];

  return (
    <thead className="bg-gray-800">
      <tr>
        {columns.map((col) => (
          <th
            key={col.key}
            className={`${col.width} px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider`}
          >
            {col.label}
          </th>
        ))}
      </tr>
    </thead>
  );
}