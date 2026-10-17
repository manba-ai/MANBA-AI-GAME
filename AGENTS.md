# MANBA 手柄开发规则

开发命令统一见 [开发流程](docs/AUTHORING.md)，GameSpec、Lua 和测试格式见 [作者参考](docs/GAME_API.md)。

1. 先确认玩法、胜负、操作和素材来源，在 `.work/` 中保存游戏源码及构建结果；保留已有文件和改动。
2. 按 [游戏规格](docs/GAME_LIMITS.md) 和 `contracts/km013-st7789-i8080-v1.json` 规划资源。默认 legacy；需要扩展预算时显式选择 resources-v2。
3. 先写规则和验收测试并冻结，再实现玩法。修复代码不得改变冻结断言；规则变更另存版本并记录原因。
4. 高清素材使用 indexed8-alpha4，GameSpec 设置 `bitmap_compression: "zlib"`。保留已确认的尺寸、颜色、透明度、锚点和动画。
5. 完成标题、帮助、开始、暂停、结算、重开和退出。`draw/snapshot` 不推进逻辑；`stop` 清输入；持续输入超过 400ms 未刷新即释放。
6. 绘图文字使用 5×7 ASCII，页面说明可用中文；音频只在输入或更新中触发。
7. 运行包校验、规则测试、原生/Wasm 对照及玩法压力测试，分别记录自动检查和实际试玩结果。不能用 Wasm 的额外内存放宽游戏预算。
8. 项目工具检查及归档见 [项目检查](docs/VALIDATION.md)。SDK 运行文件与 Play 按同一版本配套使用。
