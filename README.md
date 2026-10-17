# MANBA 手柄游戏开发

用 AI 编写 MANBA 手柄游戏，生成 `.edgegame` 文件，再用 Play 试玩。

## 开始

1. 完整解压压缩包，在能读写文件、执行终端命令的 AI 编程工具中打开 `manba-ai-game` 文件夹。
2. 填写下面的需求并发给 AI。AI 按 [开发流程](docs/AUTHORING.md) 检查环境、编写游戏和构建。
3. 完成后双击根目录 [play.html](play.html)，选择 AI 交付的 `game.edgegame`，点击“开始 / 继续”。

```text
请按 AGENTS.md 和 docs/AUTHORING.md 开发一款 MANBA 手柄游戏。

游戏名：
玩法和胜负条件：
操作方式：
关卡或难度：
美术风格、已有素材：

先检查开发环境，明确规则和测试，再实现玩法。
完成后提供 game.edgegame 的位置、操作说明和测试结果，保留源码。
```

开发需要 Python 3.11.8+、Node.js 20+。支持 macOS 11+ 和 Linux 的 Intel/AMD 64 位、ARM64 平台；Windows 在 WSL2 中开发。首次安装 Python 依赖需要网络，具体命令由 AI 按开发流程执行。

试玩只需 `play.html` 和游戏包，可将这两个文件一起发给别人。按键、声音及常见问题见 [Play 使用说明](docs/PLAY.md)。

[开发流程](docs/AUTHORING.md) · [游戏规格](docs/GAME_LIMITS.md) · [项目检查与打包](docs/VALIDATION.md) · [第三方许可](THIRD_PARTY.md)
