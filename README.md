# PROCESS AI 審核框架 (PROCESS AI Review Framework)

A seven-stage AI system evaluation and audit framework designed to ensure
transparency, practicality, universality, and closed-loop improvement for AI
products.

---

## 核心原則 (Core Principles)

| 原則 | 說明 |
|------|------|
| **透明性** | 審核過程與結果完全可追溯、可解釋 |
| **實用性** | 直接針對幻覺、用戶體驗、業務價值等關鍵問題 |
| **通用性** | 適用於新產品上線或既有系統優化 |
| **閉環改善** | 透過錯誤歸因分析，將審核發現反饋至模型迭代流程 |

---

## 七階段流程 (Seven-Stage Process)

```
P → R → O → C → E → S → S
```

| 階段 | 名稱 | 說明 | 主要輸出 |
|------|------|------|----------|
| **P** | Purpose（目標與需求評估） | 明確審核目標與範圍 | 《審核範圍與目標文件》 |
| **R** | Resources（資源與評估材料準備） | 收集歷史對話與建立場景數據集 | 《評估數據集報告》 |
| **O** | Optimization Loop（優化閉環） | 識別壞案例並進行錯誤歸因分析 | 《壞案例歸因分析報告》 |
| **C** | Count（評估數量定義） | 定義統計顯著的樣本量 | 《評估數量規劃表》 |
| **E** | Effectiveness（有效性與評估指標） | 多維度指標體系評估 | 《多維度評估指標得分表》 |
| **S** | Standards（評分標準） | 定義1-5分評分標準確保一致性 | 《評分標準手冊》 |
| **S** | Scrutiny（審核方法） | 三層審核流程（自動→LLM→人工） | 《人工評估記錄》 |

---

## 安裝 (Installation)

### Framework only (核心框架)

```bash
pip install -e ".[dev]"
```

### With Chat Auditing API

```bash
pip install -e ".[api,dev]"
```

---

## Chat Auditing API

A FastAPI service that wraps Ollama for local-LLM chat, persists every
conversation turn to Supabase, and surfaces PROCESS-framework auditing
(including hallucination marking).

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python ≥ 3.9 | — |
| [Ollama](https://ollama.ai) running locally | `ollama run llama3.1:8b` |
| Supabase project | Free tier works fine |

### Environment Variables

Copy `.env.example` → `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SUPABASE_URL` | ✅ | — | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | — | Service-role key (keep secret!) |
| `OLLAMA_BASE_URL` | — | `http://localhost:11434` | Ollama server base URL |
| `OLLAMA_MODEL` | — | `llama3.1:8b` | Ollama model name |
| `CORS_ORIGINS` | — | `["*"]` | Allowed CORS origins (JSON array) |

> ⚠️ **Never expose `SUPABASE_SERVICE_ROLE_KEY` to the browser.**
> The API server is the only process that should hold this key.

### Supabase SQL Migration

Run `supabase/migrations/001_chat_auditing.sql` in your Supabase project's
**SQL Editor** (or via the Supabase CLI):

```bash
# Via Supabase CLI
supabase db push

# Or paste supabase/migrations/001_chat_auditing.sql into the SQL Editor
```

The migration creates five tables with indexes:
`chat_sessions`, `chat_messages`, `ai_audits`, `bad_cases`, `process_reports`.

### Start the API Server

```bash
uvicorn process_framework.api.main:app --reload
```

The server starts on `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### cURL Examples

#### POST /chat

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What is the capital of France?"}],
    "temperature": 0.7
  }' | jq .
```

Response:

```json
{
  "session_id": "550e8400-...",
  "assistant_message": "The capital of France is Paris.",
  "assistant_message_id": "6ba7b810-..."
}
```

#### POST /audit/{message_id}/mark-bad

```bash
curl -s -X POST http://localhost:8000/audit/6ba7b810-.../mark-bad \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Model fabricated a historical date.",
    "category": "hallucination",
    "reviewer": "alice",
    "ignored_keywords": ["date", "historical"]
  }' | jq .
```

Response:

```json
{
  "bad_case_id": "...",
  "audit_id": "...",
  "message_id": "6ba7b810-...",
  "status": "bad_case"
}
```

#### POST /process/run/{session_id}

```bash
curl -s -X POST http://localhost:8000/process/run/550e8400-... | jq .
```

Response:

```json
{
  "session_id": "550e8400-...",
  "report_id": "...",
  "overall_risk_level": "medium",
  "total_cases": 3
}
```

### Minimal Chat UI

Open `chat_ui.html` directly in your browser (no build step required):

```bash
open chat_ui.html          # macOS
xdg-open chat_ui.html      # Linux
start chat_ui.html         # Windows
```

The UI provides:
- Chat input with real-time responses from Ollama via the API
- A **⚑ Flag** button on every assistant message to mark hallucinations
- A modal form for capturing category, keywords, and reviewer

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `503 Cannot reach Ollama` | Make sure `ollama serve` is running and `OLLAMA_BASE_URL` is correct |
| `502 Supabase upsert session failed` | Check `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`; verify tables exist |
| `404 Message not found` | The `message_id` doesn't exist in `chat_messages`; call `/chat` first |
| CORS errors in browser | Set `CORS_ORIGINS` to your frontend origin, e.g. `["http://localhost:3000"]` |
| `pydantic_settings` import error | Run `pip install -e ".[api]"` |

---

## 快速開始 (Quick Start)

### 完整框架使用範例

```python
from process_framework import (
    ProcessFramework,
    AuditType,
    BadCaseCategory,
    EvaluationDimension,
    EvaluationCase,
    EvaluationScore,
    ScoreLevel,
    ScenarioType,
)

# 初始化框架
framework = ProcessFramework(audit_type=AuditType.NEW_PRODUCT)

# P - 定義審核目標
plan = framework.setup_purpose(
    description="上線電商智能客服 v2.0",
    must_pass_set=["問候語", "訂單查詢", "退換貨政策"],
    high_frequency_issues=["配送時間", "退款流程"],
    hallucination_mitigation_kpi=0.99,
    total_sample_size=600,
    must_pass_sample_size=50,
    high_frequency_sample_size=30,
)

# R - 添加評估案例
cases = [
    EvaluationCase(
        scenario_type=ScenarioType.QA,
        user_input="夏季顯瘦洋裝有哪些推薦？",
        expected_output="推薦以下幾款夏季顯瘦洋裝：...",
        actual_output="我們有許多洋裝款式可供選擇：...",
    )
]
framework.add_evaluation_cases(cases)
dataset_report = framework.build_dataset_report(
    representativeness_notes="涵蓋電商高頻場景"
)

# O - 記錄壞案例並歸因
framework.record_bad_case(
    evaluation_case=cases[0],
    category=BadCaseCategory.INTENT_UNDERSTANDING,
    description="模型忽略了「夏季」和「顯瘦」等關鍵限制詞",
    ignored_keywords=["夏季", "顯瘦"],
    improvement_suggestion="加入限制詞對抗性訓練數據",
)
bad_case_report = framework.build_bad_case_report(
    total_evaluated=100,
    model_iteration_suggestions=["優先處理意圖理解型壞案例"],
)

# C - 規劃評估數量
count_plan = framework.plan_evaluation_count(cases_per_scenario=150)

# E - 添加評估分數
scores = [
    EvaluationScore(
        case_id=cases[0].case_id,
        dimension=EvaluationDimension.USER_INTENT_RECOGNITION,
        score=ScoreLevel.SCORE_2,
        reviewer_id="reviewer-001",
        notes="忽略了關鍵限制詞",
    )
]
framework.add_evaluation_scores(scores)
effectiveness_report = framework.build_effectiveness_report()

# S (Standards) - 查看評分標準手冊
handbook = framework.get_scoring_handbook()

# S (Scrutiny) - 人工審核
record = framework.review_case(
    case=cases[0],
    reviewer_id="reviewer-001",
    human_scores={
        EvaluationDimension.USER_INTENT_RECOGNITION: ScoreLevel.SCORE_2,
        EvaluationDimension.ANSWER_ACCURACY: ScoreLevel.SCORE_3,
    },
    annotation="意圖識別不足，建議加強訓練",
    force_human_review=True,
)

# 生成完整報告
full_report = framework.generate_full_report()
print(f"整體風險等級: {full_report['overall_risk_level']}")
print(f"通過率: {effectiveness_report.pass_rate:.1%}")
```

### 使用三層審核流程 (Three-tier Scrutiny)

```python
from process_framework import ScrutinyStage, EvaluationDimension, ScoreLevel

def my_automated_filter(case):
    """快速分類：明確好/壞，不確定返回 None"""
    if len(case.actual_output) < 10:
        return False   # 明顯過短
    return None        # 不確定，交給下一層

def my_llm_judge(case):
    """LLM-as-a-Judge 中等粒度評分"""
    # 實際應用中呼叫 GPT-4o 等模型
    return {
        EvaluationDimension.ANSWER_ACCURACY.value: 4,
        EvaluationDimension.RELEVANCE.value: 3,
    }

scrutiny = ScrutinyStage(
    automated_filter=my_automated_filter,
    llm_judge=my_llm_judge,
)
```

---

## 壞案例類型 (Bad Case Categories)

| 類型 | 說明 | 典型案例 |
|------|------|----------|
| `HALLUCINATION` | 輸出不正確或捏造資訊 | 虛構產品規格、不存在的政策 |
| `INTENT_UNDERSTANDING` | 忽略用戶查詢中的關鍵限制詞 | 忽略「夏季」、「顯瘦」等條件 |
| `USER_EXPERIENCE` | 理解正確但表達冗長、體驗差 | 回答過長、格式混亂 |

---

## 評估維度 (Evaluation Dimensions)

### 系統能力 (System Capability)
- `USER_INTENT_RECOGNITION` — 用戶意圖識別
- `CONSTRAINT_COMPLIANCE` — 限制條件遵守
- `PRONOUN_UNDERSTANDING` — 代詞理解
- `ANSWER_ACCURACY` — 答案準確性
- `TIMELINESS` — 時效性

### 內容品質 (Content Quality)
- `RELEVANCE` — 相關性
- `HALLUCINATION_LEVEL` — 幻覺等級
- `LOGICAL_COHERENCE` — 邏輯性
- `COMPLETENESS` — 完整性

### 性能指標 (Performance)
- `RESPONSE_TIME` — 回應時間

### 用戶體驗 (User Experience)
- `SATISFACTION` — 滿意度
- `MULTI_TURN_RATE` — 多輪對話率
- `PROMPT_LENGTH_RATIO` — 提示長度比例

### 業務價值 (Business Value)
- `USAGE_RATE` — 使用率
- `RETENTION_RATE` — 留存率

### 風險控制 (Risk Control)
- `SENSITIVE_TOPIC_INTERCEPTION` — 隱私/敏感話題攔截率

---

## 評分標準 (Scoring Standards)

| 分數 | 說明 |
|------|------|
| **5** | 回答完全正確、邏輯清晰、表達簡潔，完全滿足用戶需求 |
| **4** | 回答基本正確，存在輕微缺陷，不影響整體使用體驗 |
| **3** | 回答基本達標，但存在明顯改善空間（如冗長、部分不準確）|
| **2** | 存在重大缺陷（如關鍵信息遺漏、輕微幻覺），影響使用 |
| **1** | 出現嚴重幻覺、完全誤解意圖、或用戶體驗極差，無法接受 |

---

## 上線標準 (Launch Criteria)

- **必須通過集 (Must-Pass Set)**：需達 **99%** 正確率方可上線
- **壞案例率 (Bad Case Rate)**：預期佔總評估量的 **15–30%**
- **每類場景建議樣本量**：**100–200** 條帶標準答案的數據

---

## 專案結構 (Project Structure)

```
process_framework/
├── __init__.py              # 套件主入口
├── framework.py             # ProcessFramework 完整流程協調器
├── core/
│   ├── enums.py             # 枚舉類型（AuditType、BadCaseCategory 等）
│   └── models.py            # 數據模型（AuditScope、BadCase 等）
├── stages/
│   ├── purpose.py           # P - Purpose 階段
│   ├── resources.py         # R - Resources 階段
│   ├── optimization.py      # O - Optimization Loop 階段
│   ├── count.py             # C - Count 階段
│   ├── effectiveness.py     # E - Effectiveness 階段
│   ├── standards.py         # S - Standards 階段
│   └── scrutiny.py          # S - Scrutiny 階段
├── evaluation/
│   ├── metrics.py           # 指標計算工具
│   ├── scoring.py           # 評分引擎
│   └── bad_cases.py         # 壞案例分析工具
└── reporting/
    └── reports.py           # 標準化報告生成器

tests/
├── test_purpose.py
├── test_resources.py
├── test_optimization.py
├── test_count.py
├── test_effectiveness.py
├── test_standards.py
├── test_scrutiny.py
├── test_evaluation.py
└── test_framework.py
```

---

## 執行測試 (Running Tests)

```bash
pytest tests/ -v
```

---

## 與 ISO/IEC 42001 整合

| PROCESS 階段 | 對應 ISO 42001 要求 |
|-------------|---------------------|
| **P** | 「組織脈絡」、「規劃」，將幻覺緩解設為正式風險目標 |
| **R** | 「AI 系統數據」控制項，確保數據品質與代表性 |
| **O** | 「績效評估」與「改善」，實現閉環管理 |
| **E/S** | 「相關方資訊」與「人類監督」，提供透明評分與解釋 |