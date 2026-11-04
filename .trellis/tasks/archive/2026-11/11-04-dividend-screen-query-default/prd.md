# 修复筛选接口Query默认值异常

## 目标及已批准范围
用户要求修复并本地提交，不部署或推送。已复现POST /stocks/screen返回500：内部get_stocks调用省略codes，Query(None)默认对象流入strip造成AttributeError。评级分析也调用相同函数。

## 变更边界
仅将codes查询元数据移入Annotated并以普通None为默认值，保持HTTP查询校验和全量筛选语义；补充真实路由调用链与HTTP codes查询回归测试，同步快照缓存契约。无需更改筛选阈值、采集或前端。

## 验收
- POST /stocks/screen经过真实get_stocks和构建函数返回200，包含全采集池。
- 内部省略codes时默认不做代码筛选。
- HTTP codes前导零归一、交集筛选及非法输入422保持。
- 相关筛选、快照、评级测试通过，修复本地提交。

## 验证与根因记录
新增真实screen→get_stocks→构建链测试，修复前复现Query.strip异常，修复后200。snapshot_cache、screening_service、quality_api共87 passed，git diff --check通过。根因为新增默认参数未兼容内部Python调用，旧单测mock整个get_stocks掩盖问题；以Annotated元数据+普通None默认值及HTTP/内部链路双覆盖预防。用户最终要求仅本地修复并提交，未部署或推送。
