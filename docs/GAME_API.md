# GameSpec、Lua 与验收

使用 custom GameSpec 构建游戏。Lua 源文件按下述标记实现 records ABI。

`templates/spec.json` 定义游戏配置，`templates/game.lua` 提供 Lua 回调结构。JSON 元数据可以中文，MANBA 手柄绘制文本使用 ASCII。

## 实际字段限制

| 字段 | 约束 |
|---|---|
| name | 1–24 字符；建议可显示的英文名称 |
| description | 1–1,200 字符 |
| rules | 1–12 条，每条最多 300 字符 |
| tests | 1–6 个规范用例，每例最多 20 个 action / 8 个 expect |
| rule_ids | 从 1 开始，引用 rules；全套最多 1,200 次动作计数 |
| step | value=0–50 毫秒，count=1–200 |
| data | 不含 null 的 JSON 标量/对象/数组，最多 16 层、48 KiB |
| code | Lua 文本；编译后连 SDK adapter 默认至多 128 KiB，resources-v2 为 256 KiB |
| requires | 作者可显式选 `bitmap-scale-v1`、`bitmap-column-v1`、`rumble-v1`、`graphics-v2` |
| runtime_profile | 默认 `legacy`；使用扩展资源预算时显式选择 `resources-v2` |
| launcher_icon | 80×80、不透明的 `indexed8-zlib` 图标，由 `--icon` 编译；构建必需，不生成 `launcher_card` |

音频、位图、压缩、ABXY、records 的能力由编译器推导，不要手工塞进 `requires`。使用 `screen.sprite` 的 width/height 参数时声明缩放能力。

JSON 不接受未知字段。`cover` 是包内启动美术，可选 version=4 六图块；它也占游戏图集。完整 schema 见 SDK 的 `compiler/authoring/schema.py`。

## Lua 约定

```lua
-- @library-controller-v2
-- @game-hud-v1
-- @records-key <64位小写十六进制SHA256>
function init() end
function input(key) end
function buttons(mask) end -- 仅 held 模式需要
function update(dt_ms) return false end
function draw() end
function snapshot() return {status='paused', ticks=0, score=0} end
```

`@library-controller-v2` 必须在首行以启用词法压缩；注释不会进入最终 Lua。records-key 是游戏规则/计分身份的稳定 SHA-256，可用 `sha256(b'<slug>:rules-v1')`；不要用图像或包摘要，单改美术/标题不改变记录身份。

SDK 将 `data` 注入 `local game_data`。`snapshot` 返回 `status=paused/running/won/over`、数字 ticks/score、必要的测试字段；draw 后自动加入 scene。标题/帮助/选关返回 `menu_navigation=true`。过大的世界数组不要每帧放进 snapshot；遵守深度、字段、数组长度与总字节限制。

`init` 暂停且 ticks=0；`action`/A 能开始，运行 update 增加 ticks；`pause` 冻结，`restart` 回标题清 ticks，`stop` 清输入并暂停。启用 `game-hud-v1` 时系统页 B 请求退出，不开始模拟。已确认的游戏专属按键可不同，但 UI 的 key、hold、repeat_ms 必须与实现一致。held 的位为 1/2/4/8/16，不含 ABXY；ABXY 是命名事件。

只可用受限的 base/math/table/string 与 screen/audio/haptics/records 钩子，不能访问文件、网络、模块、动态加载。用确定性 PRNG；视觉随机不消费玩法 RNG。draw/snapshot 纯读，不更新碰撞、计时和随机。

## 最佳记录

自定义记录实现四个回调：`records_export()` 返回 R1 ASCII 记录或 nil；`records_restore(raw)` 校验并恢复；`records_storage(ok)` 标记保存状态；`records_finish()` 在退出前生成检查点。

常用单分数形式 `R1|0,SCORE,0,-1;`，空记录 `R1|`；不要假设所有游戏都用最高分，过关数、最低用时需要匹配游戏语义。读取失败保留错误状态，不把损坏记录覆盖成零。保存检查点放在暂停、结算、重试和退出，不每帧保存。接口实现根据游戏的计分或通关规则编写；不要直接复用其他游戏的成绩标识。

## 规则验收与压力

每条规则对应可观察状态。覆盖移动/动作/计分/碰撞/胜负等语义，不只有“运行不报错”。例如：

```json
{"name":"Pause freezes simulation", "rule_ids":[4],
 "actions":[{"kind":"input","value":"a"},{"kind":"step","value":50,"count":10},
            {"kind":"input","value":"pause"},{"kind":"step","value":50,"count":100}],
 "expect":[{"path":"ticks","op":"eq","value":10},{"path":"status","op":"eq","value":"paused"}]}
```

每例从新的 init 开始。`op` 是 eq/gt/gte/lt/lte；path 至多四段对象字段，没有数组下标语法。超过 6 个核心用例的原作轨迹/边界检查放在外部 Python/Node 测试中，不削弱规则覆盖。

首次有效测试冻结后修实现；因用户修改规则而变更验收，在新版本记录 `test_changes` 的 case/rule_id/reason，保留旧版本。若静态 schema 认为原测试语法无效可纠正语法，不能借此更换断言。

压力至少考虑密集对象、透明图层、多状态动画、最高速度、长局和多次重开。报告 Lua 峰值、最大绘制、位图工作量、包/代码字节。448 KiB Lua 是当前性能指南的审查建议线，512 KiB 是硬限。
