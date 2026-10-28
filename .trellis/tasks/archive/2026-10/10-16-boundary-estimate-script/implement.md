# implement — estimate_boundaries.py

前置:工作区可能有其他会话的未提交改动,动工前 `git status` 核对,只提交本任务文件。

## 步骤

1. **依赖与基线**:backend/housing-map 加入 shapely 依赖(uv);跑 `python -m pytest tests/ -v` 记录基线。
   验证:uv lock 更新,基线通过。
2. **名单与 CLI 骨架**:目标派生函数 + argparse(`--ids/--apply/--selection/--api/--token`);输出目录创建。
   验证:空跑列出 12 个目标小区(与 research/no-boundary.json 一致)。
3. **坐标转换对**:WGS84↔GCJ02 互逆函数 + 往返测试 + 对照既有小区点位(偏差 <5m)。
   验证:pytest 新增用例通过。
4. **Overpass 客户端**:镜像 fallback + 10s 间隔 + 7 天缓存 + 重查查询构造;mock 测试。
   验证:pytest 通过;真实跑 1 个小区拿到建筑响应并落缓存。
5. **挑楼聚类 + 轮廓生成**:名称/距离/连通簇 + buffer 填缝 + simplify;合成 fixture 测试。
   验证:pytest 通过。
6. **候选输出 + 预览 HTML**:candidates.geojson + estimate_preview.html 模板。
   验证:浏览器打开预览,12 个候选/定位点/灰轮廓齐全,勾选导出 selected.json 成功。
7. **--apply**:读 selection → 调上传接口 → 逐条打印结果;接口未就绪时明确报错。
   验证:对本地后端(接口任务完成)上传成功,重复执行幂等。
8. **端到端**:真实跑 12 个小区 → 人工预览勾选 → apply → 本地 `GET /api/map/communities` 出现新轮廓。
   验证:用户看预览确认;Overpass 失败小区有失败清单。

## 检查点

- 每步完成即跑对应验证;第 5 步(算法)与第 7 步(apply)是重点 review 门。
- 全程不改动 data/ 正式数据文件(apply 走接口)。

## 回滚点

- 任何一步失败:脚本文件未合入正式数据链路,删除 estimate_out/ 与脚本即可,无状态残留。
