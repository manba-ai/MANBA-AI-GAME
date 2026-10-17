# 项目检查与打包

此处用于检查项目文件和制作分发包。制作游戏按 [开发流程](AUTHORING.md) 执行。

## 文件位置

- `sdk/sdk.zip`：游戏包编译工具、平台运行文件、Wasm 及 API 文档。初始化后位于 `.work/sdk`。
- `play.html`：可直接打开的试玩页面。
- `SOURCE.json`、SDK 内的 `SDK-MANIFEST.json`、`play.build.json`：文件与契约摘要。

更新运行器时使用配套的 SDK 和 Play，保留第三方许可。

## 检查与归档

在已完成环境初始化的项目根目录执行：

```sh
python3 tools/check_project.py
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
node --test tests/*.test.mjs
python3 tools/package_project.py
python3 tools/check_project.py --archive dist/manba-ai-game.zip
```

产物为 `dist/manba-ai-game.zip` 及 SHA-256 文件，压缩包内的 MANIFEST.json 记录逐文件摘要。文件范围见 `tools/check_project.py`；归档检查覆盖外层压缩包和 sdk.zip。

## 完整流程检查

用新 Python 环境验证归档内容：

```sh
python3 -m venv /tmp/manba-clean-venv
/tmp/manba-clean-venv/bin/python -m pip install -r requirements.txt
/tmp/manba-clean-venv/bin/python tools/verify_portable.py \
  --archive dist/manba-ai-game.zip --output /tmp/manba-check.json
```

脚本在含中文和空格的新目录中解压项目，逐条执行开发流程中的命令；使用临时测试数据完成环境安装、SDK 初始化、游戏构建、规则验收、压力回放和 Play 导入检查。结果与中间文件保存在临时目录。

Play 自动检查使用 Node Worker 和 DOM 替身，不代表浏览器操作与听测已经通过；手动检查项见 [Play](PLAY.md)。
