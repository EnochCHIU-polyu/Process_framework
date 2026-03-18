"""Enumerations used across the PROCESS AI Review Framework."""

from enum import Enum


class AuditType(Enum):
    """Type of audit: new product launch or system optimization."""

    NEW_PRODUCT = "new_product"        # 新產品上線
    OPTIMIZATION = "optimization"      # 系統優化


class BadCaseCategory(Enum):
    """Categories for bad case root cause analysis (錯誤歸因分類)."""

    HALLUCINATION = "hallucination"            # 幻覺型：輸出不正確或捏造資訊
    INTENT_UNDERSTANDING = "intent_understanding"  # 意圖理解型：忽略關鍵限制詞
    USER_EXPERIENCE = "user_experience"        # 用戶體驗型：理解正確但表達差


class EvaluationDimension(Enum):
    """Multi-dimensional evaluation dimensions (多維度指標)."""

    # System capability (系統能力)
    USER_INTENT_RECOGNITION = "user_intent_recognition"      # 用戶意圖識別
    CONSTRAINT_COMPLIANCE = "constraint_compliance"          # 限制條件遵守
    PRONOUN_UNDERSTANDING = "pronoun_understanding"          # 代詞理解
    ANSWER_ACCURACY = "answer_accuracy"                      # 答案準確性
    TIMELINESS = "timeliness"                                # 時效性

    # Content quality (內容品質)
    RELEVANCE = "relevance"                  # 相關性
    HALLUCINATION_LEVEL = "hallucination_level"  # 幻覺等級
    LOGICAL_COHERENCE = "logical_coherence"  # 邏輯性
    COMPLETENESS = "completeness"            # 完整性

    # Performance (性能指標)
    RESPONSE_TIME = "response_time"          # 回應時間

    # User experience (用戶體驗)
    SATISFACTION = "satisfaction"            # 滿意度
    MULTI_TURN_RATE = "multi_turn_rate"      # 多輪對話率
    PROMPT_LENGTH_RATIO = "prompt_length_ratio"  # 提示長度比例

    # Business value (業務價值)
    USAGE_RATE = "usage_rate"                # 使用率
    RETENTION_RATE = "retention_rate"        # 留存率

    # Risk control (風險控制)
    SENSITIVE_TOPIC_INTERCEPTION = "sensitive_topic_interception"  # 隱私/敏感話題攔截率


class ScoreLevel(Enum):
    """Five-level scoring scale (1–5分評分標準)."""

    SCORE_1 = 1   # 嚴重幻覺、完全誤解意圖、用戶體驗極差
    SCORE_2 = 2   # 重大缺陷，影響使用
    SCORE_3 = 3   # 基本達標，存在改善空間
    SCORE_4 = 4   # 良好表現，輕微問題
    SCORE_5 = 5   # 完全正確、邏輯清晰、表達簡潔


class ReviewMethod(Enum):
    """Methods used in the Scrutiny stage (審核方法)."""

    AUTOMATED_FILTERING = "automated_filtering"     # 自動化初步篩選
    LLM_AS_JUDGE = "llm_as_judge"                   # LLM-as-a-Judge 中間篩選
    HUMAN_REVIEW = "human_review"                   # 人工精細篩選


class ScenarioType(Enum):
    """Types of evaluation scenarios (場景類型)."""

    CASUAL_CHAT = "casual_chat"          # 閒聊
    QA = "qa"                            # QA
    LOGICAL_REASONING = "logical_reasoning"  # 邏輯推理
    GENERATION = "generation"            # 生成
