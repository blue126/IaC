# Speech Central Base profile 路由

## 固定 profile

Speech Central 仍可发送其 13 个固定 OpenAI `voice` alias，但它们只是客户端兼容槽位，不映射为 Qwen preset，也不表示不同性别或不同 speaker。local shim 对每一个 alias、空值和未知值都发送相同的 Qwen3-TTS Base 请求：

```json
{
  "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
  "task_type": "Base",
  "voice": "audiobook_narrator_zh",
  "language": "Chinese"
}
```

客户端 `instructions` 会被移除，因为当前 Base clone 运行链路不使用 CustomVoice 的 instruction 控制。其余 OpenAI audio 兼容字段仍照常处理；AAC 会转换为 MP3，未指定格式的流式请求使用 PCM。

## Profile 资产与就绪条件

`audiobook_narrator_zh` 是通过一次性 VoiceDesign 合成的非真人参考 WAV 和准确转写注册的 ICL profile。参考 WAV 和服务端 profile 只保存在持久模型目录，绝不提交、公开或记录内容。

shim 每次 speech 请求及 `/health` 都确认私有 Base `/v1/audio/voices` 列出了 profile。缺失或不可读时响应 `503 profile_unavailable`，从不退回 CustomVoice 或预设 speaker。

## Alias 兼容集

接受的 Speech Central 名称为：`alloy`、`echo`、`fable`、`onyx`、`ash`、`ballad`、`cedar`、`verse`、`coral`、`marin`、`nova`、`sage`、`shimmer`。这些名称不参与 Base 身份选择；连续试听任意三个 alias 应听到同一目标身份。最终听感仍由用户在 Speech Central 中判断。
