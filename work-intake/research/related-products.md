# 同类产品、技术路径与本轮吸收

核查日期：2026-10-17。针对“理解日本个人工作 → 调查环境 → 推荐既有能力 → 经用户选择部署”检索。实际阅读了以下原始仓库文档、部分代码及许可证；没有安装或执行第三方项目，也没有完成全仓安全审计。检索包含任务推荐、个性化、Skill/MCP 发现、公开信息研究等英文关键词。本轮不构成穷尽性竞品调查。

## 结论

**核心零件乃至部分组合已经有人做过。** 不能把“让 Codex 搜索免费 Agent”“按用户推荐技能”“共享能力的企业控制台”作为尚无人实现的创新。更具体的机会假设是：日本工作语境、少量问答、复用用户既有工具、可理解的选择与权限说明，以及从个人有效使用到企业配置服务。是否明显更容易用、是否能降低培训成本，还需要用户测试。

## 直接与部分重合

| 项目 | 重合与技术路径 | 对本轮的取舍 |
|---|---|---|
| [Skill Recommender](https://github.com/JasperHye/skill-recommender) | **直接重合能力推荐。** SKILL.md 交给宿主理解与搜索，本地 Python 做候选过滤与状态；支持手动与可选每日推荐。 | 路线证明轻量实现可行，也降低了此部分的新颖性。保留任务驱动、确定性校验；不照搬热门推荐、种草和大量候选策略。 |
| [Vercel Skills](https://github.com/vercel-labs/skills) | **能力池技术零件。** CLI 发现和安装 Skills，适配多宿主；TypeScript 搜索入口调用 skills.sh API，安装器负责项目／全局目录和链接／复制。 | 技能搜索和多宿主安装不值得重写。当前先用宿主搜索完成任务；需要规模化安装时再评估CLI。它是Vercel官方项目，不是Codex第一方插件。 |
| [OpenWork](https://github.com/different-ai/openwork) | **与未来控制台直接重合。** 文档提供从 Codex／Claude Code 通过 MCP 搜索、执行共享能力的入口和组织管理。另有基于OpenCode的桌面形态。 | 未来“一个控制台管理共享能力”已不是空白；当前不为此新增组织账号、服务端或桌面软件。 |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | **长期记忆／Skills／定时的部分重合。** 独立运行时，文档描述学习循环、记忆、消息网关及定时任务。 | 理解其渐进加载技能与状态设计；本轮不替换用户已在用的Codex，不引入完整运行时。 |
| [GPT Researcher](https://github.com/assafelovic/gpt-researcher/blob/main/docs/docs/gpt-researcher/getting-started/introduction.md) | **对外调查的技术参考。** 先生成研究问题，再搜集、跟踪来源、综合报告。 | 借鉴研究问题与来源分离；其完整依赖栈比当前宿主搜索方案重，不在两天内引入。文档性能与成本数字未独立验证，不用于本产品估算。 |

公司商业产品还有大塚商会、SoftBank、KDDI、Slack 等相邻供应，详见 [会社调查](jphacks-2026.md)。这意味着需求方向有现有供应，不能据此证明我们会获得付费客户。

## 读到了哪些实现

下列链接为读取时的分支路径，分支会变化。SHA是读取到的文件 blob 标识，不是整仓 commit。未固定版本前不做可复现部署声明。

| 仓库／文件 | 阅读所得 | 本轮状态 |
|---|---|---|
| Skill Recommender [SKILL.md](https://github.com/JasperHye/skill-recommender/blob/main/SKILL.md)，blob `4048f574dd3fb595d3aa78aba6a2ca1e7959f634` | 理解、搜索、判断交给宿主；helper保持小；按实际宿主能力适配 | 支持我们复用宿主而不另开模型API；未执行其安装后指令 |
| [candidate_filter.py](https://github.com/JasperHye/skill-recommender/blob/main/scripts/candidate_filter.py)，blob `e329a238a4c1d04c9039d7712ee4e40f088f9a80` | 存在跨来源去重、冷却与已装过滤；过滤和语言判断分离 | 独立实现候选ID与规范URL重复检测；未复制该脚本 |
| [security.py](https://github.com/JasperHye/skill-recommender/blob/main/scripts/security.py)，blob `8cb83ccd55156604a71daa4b7b73374107184215` | 有来源、元数据、模式匹配等检查 | 我们使用显式证据缺口；不把规则扫描或来源名转换成“已安全审计”结论 |
| Vercel [src/find.ts](https://github.com/vercel-labs/skills/blob/main/src/find.ts)，blob `9fe60ce81be21a65508299b469519af4b67155b2` | 搜索与结果归一化；检索有外部API数据流 | 目录结果只作发现线索，候选还需打开原始来源核查 |
| [src/installer.ts](https://github.com/vercel-labs/skills/blob/main/src/installer.ts)，blob `fb4abfbdd11e9c3878fea343e1b8bd9095eed5bc` | 项目／全局与复制／链接分开，包含路径处理 | 保持当前项目目录隔离；本轮不新增通用安装器 |
| OpenWork [tool-catalog.ts](https://github.com/different-ai/openwork/blob/dev/packages/enterprise-mcp-client/src/tool-catalog.ts)，blob `54d1fcd332ec042d333a7fd47f14feb3ceb52f32` | 工具目录分页、数量／字节／schema限制、重复与游标循环检查 | 吸收有界候选与显式失败原则；当前JSON输入与候选数已有限制；未实现远程MCP目录客户端 |
| Hermes [tools/skills_tool.py](https://github.com/NousResearch/hermes-agent/blob/main/tools/skills_tool.py) | 列表与技能全文分开，支持渐进加载；检查技能相对路径 | 继续按任务加载项目Skill，避免每轮读完整生态目录 |
| Hermes [cron/scheduler.py](https://github.com/NousResearch/hermes-agent/blob/main/cron/scheduler.py) | 定时运行涉及网关、锁、并发与任务生命周期 | 证实后台调度不是一句提示词；本轮没有后台任务，不宣称已自动周报 |
| GPT Researcher [requirements.txt](https://github.com/assafelovic/gpt-researcher/blob/main/requirements.txt) | 包含Web框架、模型SDK、研究与文档相关依赖 | 当前标准库＋宿主工具更符合本轮轻量目标；未装其依赖 |

## 许可证与接入条件

- Skill Recommender、Vercel Skills、Hermes 的根 LICENSE 均已读到MIT。商业复用代码仍需保留适用的版权与许可声明；软件开源不表示外部模型和服务免费。
- OpenWork [根许可证](https://github.com/different-ai/openwork/blob/dev/LICENSE)明确区分 `ee/` 与其余代码。不能把组织控制台代码一概当MIT吸收。远程MCP方案的文档需要登录并选择OpenWork组织，与本轮“不增加新账号”体验存在成本。
- 本轮主要吸收设计思想，代码由本项目独立实现，没有拷入第三方源码。GPT Researcher只作架构／依赖参考，本轮没有完成它的许可证与部署条件复核。
- `examples/capabilities.json`保留四个候选的核查项与缺口，缺少完整依赖／权限等审查的候选全部维持 `needs_review`。没有将“支持Codex”的文档声明升级成实测通过。

## 已吸收进原型的具体变化

1. **统一能力候选格式。** Skill、MCP、插件、应用和框架分开；记录用途、兼容性、账号、费用、许可、权限、数据流及证据。来源完整性是可执行的检查，不只写在说明里。
2. **复用优先。** 当前已启用能力 → 官方能力 → 社区 → GitHub。来源层级只是偏好，不能让不兼容的官方候选排在已可审阅的社区方案前面；也不等于安全评分。
3. **跨目录重复防线。** 同一候选换ID、不同URL片段或尾斜线，不能冒充多个选项。规范URL比较会拒绝明显重复；不同目录镜像指向同一上游仍需宿主确认，未解决全部语义去重。
4. **未知阻止过度承诺。** 账号、成本、兼容性或六项关键证据未齐，保留需要核查。校验器只检查结构，不假装读取了网页或评估安全。
5. **事实与关系拆分。** 公司业务事实和合作可能性分开；全大会赞助、技术伙伴、大阪到场、大阪奖项独立存证。公司宣传不会被写进用户个人画像。

## 这轮最合适的使用方式

优先使用现有Codex里的搜索与这套项目Skill，不新增GitHub、registry或OpenWork账号。公开仓库的资料可由宿主读取；只有某个具体插件确实提供任务所缺的能力时，才向用户解释并进入部署。

实际演示可以是：描述“我需要理解这次比赛和会社” → 得到有来源的重点结论 → 展开为什么选这些会社 → 查看类似工具及限制 → 选择要继续核查的能力。演示应将“已调查”“文档支持”“已实际运行”分别说明。我们已经实跑公开调查与本地校验，尚未实测第三方集成、定时更新和跨宿主部署。
