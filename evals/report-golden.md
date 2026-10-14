# Paperly eval — golden

Run: 2026-10-14 11:50 · LLM: no (retrieval + abstain only)

| Metric | Value |
|---|---|
| items | 45 |
| recall_at_8 | 0.895 |
| mrr | 0.715 |
| false_abstain_rate | 0.0 |
| abstain_accuracy | 1.0 |
| retrieval_p95_ms | 19994 |
| llm | False |

## Misses

- `1706.03762` How many attention heads does the base model use? — rank None, abstained False, rerank 0.934, vsim 0.799
- `1512.03385` What top-5 error does the ensemble achieve on the ImageNet test set? — rank None, abstained False, rerank 0.969, vsim 0.848
- `2106.09685` By how much does LoRA reduce the number of trainable parameters compared to GPT-3 fine-tuning? — rank None, abstained False, rerank 0.933, vsim 0.834
- `2106.09685` How much does LoRA reduce GPU memory requirements? — rank None, abstained False, rerank 0.776, vsim 0.789
