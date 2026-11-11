# 第7批收尾与主线审阅边界

2026-11-10。Room8 V1保持原归档与原视频，不重渲染。本批落实deploy发布实现、release兼容入口、tests分组离线入口及部署保护，不迁移旧F6/F7/F8-C、不重构网页或导入数据。

| 已落地位置 | 兼容/保留内容 |
| --- | --- |
| deploy/scripts及生产模板 | release的PowerShell命令继续使用；输出仍为release/out；模板/保护shell保留受校验的兼容副本 |
| tests/{backend,engine,tools,deploy} | 四组显式模块注册；原test用例实体、fixture和unittest模块路径保留，不重复定义测试类 |
| tests/run_regression.py | 只执行离线清单，真实集成环境开关冲突即拒绝；报告新建不覆盖 |
| test/test_api.py | 写真实timeline的旧测试增加显式开关，不修改旧接口/业务行为 |

部署前原先只查Legacy状态，现在也拒绝任何房间任务的created/preparing/rendering/encoding状态。损坏JSON停止，不自动清理过期状态。只读检查与部署之间仍有竞争窗口；真正部署时应人工冻结任务提交，不宣称已建立跨进程原子调度器。

本批没有改引擎40份源码/预设清单、Backend业务、房间几何、SQL、端口、卷挂载或GPU风格。打包读取deploy生产模板，但其字节与原release一致；root Dockerfile/开发Compose继续作为入口。完整本地测试报告位于忽略目录release/out，不上传私有诊断/模型/视频。

最终离线回归295项：293通过、2项跳过，新增16项全部通过；镜像测试目录白名单调整后另有3项契约复核通过。40份引擎/预设和24份V1备份SHA不变；4份PowerShell语法与BOM、shell LF、Python3.11语法及文档链接检查通过。实际解释器为本地Python3.13/Pydantic2.10.6；两项跳过为真实PostgreSQL与可选Matplotlib。报告路径见[test/README](../test/README.md)。

## 本批之后的必要动作

1. 审阅本批diff和离线回归后，由用户提交独立第7批提交，不混入网页任务。
2. 在合并前重新获取GitHub main最新引用并审阅差异。当前仅检查本地main与本地origin/main均为d5a5e42，main是整理分支祖先，分支较其多29个提交；本轮尚未实时查询远端main，不能据此保证未来无冲突。
3. 对照Room8 V1归档、R3与40份源码清单；迁移后源码属于新任务版本，不能换签名继续V1历史任务。用户审核后再决定PR/合并与标签，不自动merge、打tag或推送。
4. 远端复验使用完整源码检出与原依赖；先核对帮助/导入和部署配置，另行安排运行验收。Windows模拟GPU/视频测试不能替代远端；无需为本轮整理重做V1视频。

测试实体继续留在test、根Dockerfile/开发Compose保留是本轮明确的兼容选择，不把它们宣称为已全量物理迁移。后续功能开发时可逐组迁移并保持旧接口；它们不是当前合并必须清空的目录。数据库真实导入、新版MinIO登记、网页与Hybrid继续独立排期。
