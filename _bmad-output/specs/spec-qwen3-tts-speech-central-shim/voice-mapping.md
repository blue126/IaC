# Speech Central 音色映射

## 初始映射

Speech Central 使用固定 OpenAI voice alias。本地 shim 必须覆盖 `groxaxo` 的默认 alias 行为，将这些槽位映射到 Qwen3-TTS 1.7B CustomVoice 的中文候选音色。

| Speech Central alias | Qwen3 speaker | 槽位用途 |
|---|---|---|
| `alloy` | `Uncle_Fu` | 男声 |
| `echo` | `Dylan` | 男声 |
| `fable` | `Eric` | 男声 |
| `onyx` | `Uncle_Fu` | 男声 |
| `ash` | `Dylan` | 男声 |
| `ballad` | `Eric` | 男声 |
| `cedar` | `Uncle_Fu` | 男声 |
| `verse` | `Dylan` | 男声 |
| `coral` | `Vivian` | 女声 |
| `marin` | `Serena` | 女声 |
| `nova` | `Vivian` | 女声 |
| `sage` | `Serena` | 女声 |
| `shimmer` | `Vivian` | 女声 |

重复映射是有意的：Speech Central 的槽位数量多于首轮中文候选音色数量。PoC 只要求暴露每个候选音色，最终映射由用户试听结果决定。

## 解析规则

1. 将请求中的 `voice` 转为字符串并进行不区分大小写的匹配。
2. 命中上表时，用对应的规范 Qwen speaker 名替换 `voice`。
3. 请求值若已经是启用的 Qwen speaker 名，则规范化大小写后直接透传。
4. 空值或未知值回退到 `alloy` 的目标 `Uncle_Fu`。
5. 只改写 `voice`；`model`、`input`、`response_format`、`speed`、`stream` 及上游支持的其他字段保持不变。

## 后端音色配置

Qwen3-TTS 后端至少必须启用：

```yaml
voices:
  - name: Vivian
    language: Chinese
  - name: Serena
    language: Chinese
  - name: Uncle_Fu
    language: Chinese
  - name: Dylan
    language: Chinese
  - name: Eric
    language: Chinese
```

验证必须覆盖全部 13 个 alias，并确认每个结果都属于上述 speaker 集合。音频生成冒烟测试只需选择一个男声 alias 和一个女声 alias；最终听感由 Speech Central 实际试听确认。
