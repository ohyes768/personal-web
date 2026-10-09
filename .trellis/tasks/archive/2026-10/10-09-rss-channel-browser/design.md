# 设计
后端GET /api/posts新增channel查询，验证存在但允许停用，复用store.list_posts(channel=)保证筛选先于limit。
前端usePosts(limit,channel)支持代次标识/取消旧请求，切换时清旧结果；URL query为channel、show_disabled，缺省全部。读取浏览器地址+popstate，history.pushState保存选择以避免Next basePath重复，SSR初始与客户端一致并延迟首次读取。
频道清单用getChannels(true)，展示时默认仅enabled；直接访问停用频道时自动显示停用并允许浏览历史。非法频道校验等清单加载成功后再回退，加载失败不误判为未知。
频道少时横向标签，多于8时搜索+下拉。选中频道说明区复用CopyText/feedUrl；ApiGuideModal新增initialChannel用于预选。文章卡片新增channelTitle/onChannelSelect，点击阻止详情冒泡。
沿用纸色风格，管理入口复用现有订阅弹窗。刷新同时更新文章和频道清单。
