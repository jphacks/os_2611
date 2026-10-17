# NORALAB / os_2611

仕事・学習・制作の実際の資料を理解し、外部の情報や利用可能な能力を組み合わせて、いつものAIツールで作業を進めるオープンソースのアシスタントです。製品名は未定、内部プロジェクト名は work-intake です。

学生・会社員・フリーランス・開発者に共通の仕組みを使います。独立したモデル契約、常駐サーバー、追加Python依存は不要です。既存のCodex／Claude CodeとPython 3.9+を利用します。

## 試す / 开始

[最新运行包 0.2.0](releases/work-intake-0.2.0.zip) を解凍し、Macで START.command を開きます。Codexの新規会話では送信を一度押してください。既に会話中なら、[AGENTS.md](work-intake/AGENTS.md) を読んで開始するよう依頼できます。

- [使用说明](work-intake/README.md)
- [可浏览源码](work-intake/work.py)
- [源码包](releases/work-intake-0.2.0-source.zip)
- [实际验证与未验证部分](work-intake/docs/validation.md)
- [工程结构与参考来源](work-intake/docs/architecture.md)

0.2增加真实文件与进程操作、任务状态、来源指纹、执行记录、检查点恢复与产出验证。宿主模型根据实际证据选择下一步，不按身份硬编码，也不固定先对内后对外。

研究备忘录、工时表与周报、客户交付清单已在当前宿主中实际生成和核对。输入明确为合成验收材料。新用户双击后完整模型交互、Claude真实会话和自动调度尚未验证；不宣称普适完成或已有量化生产力收益。

原始比赛说明模板保留于 [docs/original-jphacks-template.md](docs/original-jphacks-template.md)。旧 work-intake-share.zip 是历史快照，最新版本以上方 releases 为准。

Team: NORALAB（ノララボ） / JPHACKS Osaka os_2611
