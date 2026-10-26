# Qwen3-TTS 官方控制面与预置音色（R2.1）

## Source

- **Publisher:** QwenLM
- **Title:** Qwen3-TTS README at commit `022e286b98fbec7e1e916cb940cdf532cd9f488e`
- **Commit date:** 2026-03-17
- **Accessed:** 2026-09-02
- **URL:** https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md
- **Confidence:** high for the documented model surface and voice descriptions; not evidence of audiobook drift elimination.

## Extracted evidence

1. The model table says `Qwen3-TTS-12Hz-1.7B-CustomVoice` supports instruction control, while `Qwen3-TTS-12Hz-0.6B-CustomVoice` does not. The 1.7B description explicitly says it provides style control over target timbres via user instructions (README lines 73–79).
2. The official API accepts optional `instruct` for CustomVoice. The example deliberately requests an angry delivery, demonstrating that the same control surface can materially change emotion/prosody; omission is allowed (lines 146–182).
3. Official preset descriptions are not stylistically neutral equivalents (lines 187–199):
   - `Vivian`: “Bright, slightly edgy young female voice.”
   - `Serena`: “Warm, gentle young female voice.”
   - `Uncle_Fu`: “Seasoned male voice with a low, mellow timbre.”
   - `Dylan`: “Youthful Beijing male voice with a clear, natural timbre.”
   - `Eric`: “Lively Chengdu male voice with a slightly husky brightness.”
4. Qwen describes a VoiceDesign → reusable voice-clone-prompt workflow as useful when a consistent character voice is wanted across many lines (lines 288–315). This is a different multi-model workflow, not a drop-in CustomVoice parameter.
5. The README claims natural-language control over timbre, emotion and prosody and semantic adaptation of tone/rhythm/emotion (lines 50–55). That capability makes a restrained narration instruction plausible, but the source contains no controlled audiobook evaluation proving a specific instruction suppresses drift.

## Applicability to the current decision

- Testing `Serena`, `Uncle_Fu`, or `Dylan` before further stochastic tuning is directly supported by the official voice descriptions and has near-zero runtime cost.
- Injecting a restrained `instruct` is supported by 1.7B CustomVoice at the official model API, subject to confirming that the deployed vLLM-Omni speech adapter maps the OpenAI `instructions` field to Qwen's `instruct` input.
- Returning to 0.6B would also remove instruction control. Its apparently calmer output cannot be attributed to a documented “audiobook mode.”
- VoiceDesign → clone may offer stronger reusable identity conditioning, but requires another model/workflow and is not evidence that the current stateless CustomVoice endpoint can preserve cross-request state.

## Claim ledger

- **verified · version-compatibility:** Official Qwen docs expose instruction control for 1.7B CustomVoice but not 0.6B CustomVoice. [Source]
- **verified · version-compatibility:** Preset voices have explicitly different style descriptors; Vivian/Eric are described with brighter or livelier traits, while Serena/Uncle_Fu/Dylan are described as gentler, mellower, or more natural. [Source]
- **verified · architecture-pattern:** Qwen documents a VoiceDesign-to-reusable-clone-prompt workflow for consistent character reuse across many lines, but it is distinct from direct CustomVoice serving. [Source]
- **unverified · implementation-experience:** A calm/neutral instruction may reduce dramatic prosody in audiobook narration; the official source demonstrates controllability but not this outcome or its effect on timbre drift. [Source]
