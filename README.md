# funasr_input

基于 FunASR 的 Windows 语音输入法。

## 功能

- 热键触发录音（默认 Ctrl+Alt+Space）
- 自动静音检测停止
- FunASR 本地识别，支持 50+ 语言
- SendInput 逐字注入当前焦点窗口
- 兼容 Claude Code CLI / Codex CLI / 终端 / GUI 程序

## 安装

```bash
pip install -e ".[dev]"
```

## 使用

```bash
python -m funasr_input
```

按 `Ctrl+Alt+Space` 开始录音，静音 1 秒自动识别并输入。

## 开发

```bash
# 安装依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 打包
python -m build
```

## 许可证

MIT
