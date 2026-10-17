# 从需求到游戏包

以下命令均在解压后的项目根目录执行。示例游戏目录为 `.work/my-game`，构建目录为 `.work/my-game-v1`；更换名称时保持所有命令中的路径一致。

## 1. 准备环境

需要 Python 3.11.8+ 和 Node.js 20+。先检查：

```sh
python3 --version
node --version
```

支持 macOS 11+、Linux（x86_64 或 ARM64）；Windows 使用 WSL2。缺少 Python 或 Node.js 时先安装，然后执行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/game.py setup
.venv/bin/python tools/game.py new .work/my-game --name "My Game"
```

首次安装依赖需要联网。`setup` 校验 SDK 文件并安装对应平台的运行工具，完成后位于 `.work/sdk`。同一目录继续开发时跳过已完成的环境初始化和 `new`，不要重复创建或覆盖。

## 2. 写规则并冻结

按需求填写 `.work/my-game/spec.json` 的 `name`、`description`、`rules`、`tests` 和 `ui.controller`。操作、测试字段及 Lua 接口见 [作者参考](GAME_API.md)。

每条规则至少被一个测试引用，断言使用 `snapshot()` 可观察的状态。覆盖实际移动、计分、碰撞或胜负，不能只检查游戏启动。确定测试后执行：

```sh
.venv/bin/python tools/game.py freeze .work/my-game
```

这会创建 `frozen-tests.json`，已有文件不会覆盖。实现失败时修复代码；用户修改规则时建立新的游戏版本，记录 `test_changes`，重新冻结。

## 3. 实现玩法与素材

编辑 `.work/my-game/game.lua`，实现模板中的玩法和成绩回调，完成后移除 `@manba-template` 标记。构建以这个 Lua 文件为准，自动写入最终 GameSpec；无需手动同步 `spec.json` 中的 `code`。

`new` 已分配独立的 `records_id` 和 `@records-key`。同一游戏修复问题或更新美术时保留它们，计分规则改变时再更新。游戏 API 详见初始化后的 `.work/sdk/docs/SDK.md`，音频见 `.work/sdk/docs/AUDIO.md`。

将素材放在 `.work/my-game/art/`：

- `pack.json` 及其引用的 PNG：游戏图集，按 [素材说明](ASSETS.md) 编写清单。
- `icon.png`：4:3、不透明图标，构建时生成包内的 128×96 和 32×24 图标。
- `title.png`：可选的 4:3 启动插画；游戏自行绘制标题时可省略。

编译图集：

```sh
.venv/bin/python .work/sdk/scripts/build_bitmap_pack.py \
  .work/my-game/art/pack.json --output-dir .work/my-game/art/compiled
```

GameSpec 显式设置 `bitmap_compression: "zlib"`。图集、标题和运行内存共同受 [游戏规格](GAME_LIMITS.md) 限制。只有几何绘图、没有 PNG 图集时，跳过这条命令，并在下一步省略 `--bindings`。

## 4. 构建

```sh
.venv/bin/python tools/game.py build .work/my-game \
  --bindings .work/my-game/art/compiled/bindings.json \
  --icon .work/my-game/art/icon.png \
  --output .work/my-game-v1
```

游戏图标由 `--icon` 编译；已有 `launcher_card` 时可省略。需要使用启动插画时，加 `--title-art .work/my-game/art/title.png`，游戏名需为大写后可显示的 ASCII 标题，description 至少 20 字符。素材清单与 GameSpec 的 `runtime_profile` 必须一致。

构建读取最新 `game.lua`、合入素材、检查包与冻结测试，再比较本机 Lua 和 Wasm 的绘制指令及状态。成功输出：

| 文件 | 用途 |
| --- | --- |
| `game.edgegame` | 在 Play 中打开的游戏包 |
| `spec.json` | 本次构建实际使用的代码、规则和素材 |
| `validation.json` | 包格式、素材无损校验与规则测试结果 |
| `native-wasm.json` | 本机 Lua 与 Wasm 的对照结果 |

构建失败时先读终端中的回调、用例和断言错误，再修复源码。重试使用新的输出目录，例如 `.work/my-game-v2`；失败目录中的 `candidate-*.edgegame` 留作诊断。

## 5. 检查玩法

编写 `.work/my-game/stress.json`，覆盖对象最多、速度最快、长局及多次重开的操作轨迹。文件是数组，每项含 `name`、`actions`、`restart_on_over`；动作与 GameSpec 测试相同。完整示例见 `.work/sdk/docs/GAME_PERFORMANCE_GUIDE.md`。

```sh
.venv/bin/python .work/sdk/scripts/profile_game_performance.py \
  .work/my-game-v1/game.edgegame --scenarios .work/my-game/stress.json \
  --output .work/my-game-v1/performance.json
```

用 `phase_samples` 和 `running_step_results` 确认轨迹进入了实际玩法。不要把停在标题页的空运行当作压力测试。

## 6. 用 Play 试玩

双击项目根目录 `play.html`，选择 `.work/my-game-v1/game.edgegame`，点击“开始 / 继续”。检查操作、暂停、重开、胜负、画面和声音，具体按键见 [Play 使用说明](PLAY.md)。

分享试玩时发送 `play.html` 和这个游戏包。向用户说明包的位置、操作和测试结果；源码、素材、冻结测试与报告保留在 `.work/` 中。

## 开发问题

| 现象 | 处理 |
| --- | --- |
| 找不到 Python 模块 | 用 `.venv/bin/python` 执行命令，并检查依赖安装是否成功。 |
| SDK 已存在 | 初始化已完成就继续开发；更新 SDK 时选新目录：`tools/game.py --sdk .work/sdk-v2 setup`，后续 freeze/build 使用同一个 `--sdk`。 |
| 模板无法冻结 | 填写完整 rules/tests；字段格式见作者参考。 |
| 提示模板未实现 | 完成 `game.lua` 的回调并移除 `@manba-template` 标记。 |
| 冻结测试不一致 | 恢复原测试并修复实现；规则变化应另存版本。 |
| 包或图集超预算 | 检查字节数、图块、源像素、Lua 和每帧工作量；先压缩与复用资源，保留已确认画质。 |
