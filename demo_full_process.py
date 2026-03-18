#!/usr/bin/env python3
"""
完整的 PROCESS 七階段審核流程演示

執行方式：
    python demo_full_process.py
    
或在 venv 中：
    source .venv/bin/activate
    python demo_full_process.py
"""

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

def main():
    print("=" * 70)
    print("🚀 PROCESS 七階段審核框架 - 完整演示")
    print("=" * 70)

    # ==========================================
    # 初始化框架
    # ==========================================
    framework = ProcessFramework(audit_type=AuditType.NEW_PRODUCT)
    print("\n✓ 框架初始化完成")

    # ==========================================
    # P - Purpose（目標與需求評估）
    # ==========================================
    print("\n" + "=" * 70)
    print("📋 [P] Purpose - 定義審核目標與範圍")
    print("=" * 70)
    
    plan = framework.setup_purpose(
        description="上線電商智能客服 v2.0",
        must_pass_set=["問候語", "訂單查詢", "退換貨政策"],
        high_frequency_issues=["配送時間", "退款流程"],
        hallucination_mitigation_kpi=0.99,
        total_sample_size=600,
        must_pass_sample_size=50,
        high_frequency_sample_size=30,
    )
    print(f"✓ 審核範圍：{plan.audit_description}")
    print(f"  - 總樣本數：{plan.total_sample_size}")
    print(f"  - 必須通過集合：{plan.must_pass_set}")
    print(f"  - 高頻問題：{plan.high_frequency_issues}")

    # ==========================================
    # R - Resources（資源與評估材料準備）
    # ==========================================
    print("\n" + "=" * 70)
    print("📦 [R] Resources - 收集評估材料")
    print("=" * 70)

    cases = [
        EvaluationCase(
            scenario_type=ScenarioType.QA,
            user_input="夏季顯瘦洋裝有哪些推薦？",
            expected_output="推薦以下幾款夏季顯瘦洋裝：...",
            actual_output="我們有許多洋裝款式可供選擇：...",
        ),
        EvaluationCase(
            scenario_type=ScenarioType.QA,
            user_input="如何查詢我的訂單？",
            expected_output="您可以在個人帳戶中查看訂單狀態。",
            actual_output="訂單查詢可通過首頁「我的訂單」功能進行。",
        ),
        EvaluationCase(
            scenario_type=ScenarioType.QA,
            user_input="退換貨的時間限制是什麼？",
            expected_output="商品簽收後 7 天內可申請退換。",
            actual_output="我們提供 30 天的退貨保證。",
        ),
    ]
    
    framework.add_evaluation_cases(cases)
    print(f"✓ 已添加 {len(cases)} 個評估案例")

    dataset_report = framework.build_dataset_report(
        representativeness_notes="涵蓋電商高頻場景（商品推薦、訂單查詢、售後服務）"
    )
    print(f"✓ 數據集報告已生成")
    print(f"  - 覆蓋場景數：{len(dataset_report.scenarios)}")

    # ==========================================
    # O - Optimization Loop（優化閉環）
    # ==========================================
    print("\n" + "=" * 70)
    print("🔄 [O] Optimization - 識別壞案例並歸因")
    print("=" * 70)

    bad_case1 = EvaluationCase(
        scenario_type=ScenarioType.QA,
        user_input="夏季顯瘦洋裝有哪些推薦？",
        expected_output="推薦以下幾款夏季顯瘦洋裝：...",
        actual_output="我們有許多洋裝款式可供選擇：...",
    )
    
    framework.record_bad_case(
        evaluation_case=bad_case1,
        category=BadCaseCategory.INTENT_UNDERSTANDING,
        description="模型忽略了「夏季」和「顯瘦」等關鍵限制詞",
        ignored_keywords=["夏季", "顯瘦"],
        improvement_suggestion="加入限制詞對抗性訓練數據",
    )
    print("✓ 壞案例已記錄：")
    print(f"  - 分類：意圖理解不足")
    print(f"  - 描述：忽略關鍵限制詞")
    print(f"  - 改進建議：加強限制詞訓練")

    bad_case_report = framework.build_bad_case_report(
        total_evaluated=100,
        model_iteration_suggestions=["優先處理意圖理解型壞案例", "增加領域特定詞彙訓練"],
    )
    print(f"✓ 壞案例分析報告已生成")
    print(f"  - 壞案例總數：{len(bad_case_report.bad_cases)}")

    # ==========================================
    # C - Count（評估數量定義）
    # ==========================================
    print("\n" + "=" * 70)
    print("📊 [C] Count - 定義統計顯著的樣本量")
    print("=" * 70)

    count_plan = framework.plan_evaluation_count(cases_per_scenario=150)
    print(f"✓ 評估數量計劃已制定")
    print(f"  - 每個場景的評估數：{count_plan.cases_per_scenario}")
    print(f"  - 必須通過集：{count_plan.must_pass_sample_size} 個案例")

    # ==========================================
    # E - Effectiveness（有效性與評估指標）
    # ==========================================
    print("\n" + "=" * 70)
    print("⭐ [E] Effectiveness - 多維度指標評估")
    print("=" * 70)

    scores = [
        EvaluationScore(
            case_id=cases[0].case_id,
            dimension=EvaluationDimension.USER_INTENT_RECOGNITION,
            score=ScoreLevel.SCORE_2,
            reviewer_id="reviewer-001",
            notes="忽略了關鍵限制詞",
        ),
        EvaluationScore(
            case_id=cases[1].case_id,
            dimension=EvaluationDimension.ANSWER_ACCURACY,
            score=ScoreLevel.SCORE_4,
            reviewer_id="reviewer-001",
            notes="準確回答訂單查詢",
        ),
        EvaluationScore(
            case_id=cases[2].case_id,
            dimension=EvaluationDimension.ANSWER_ACCURACY,
            score=ScoreLevel.SCORE_1,
            reviewer_id="reviewer-001",
            notes="時限信息與實際政策不符（幻覺）",
        ),
    ]
    
    framework.add_evaluation_scores(scores)
    print(f"✓ 已添加 {len(scores)} 條評估分數")

    effectiveness_report = framework.build_effectiveness_report()
    print(f"✓ 有效性報告已生成")
    print(f"  - 通過率：{effectiveness_report.pass_rate:.1%}")
    print(f"  - 平均得分：{effectiveness_report.average_score:.2f}")

    # ==========================================
    # S - Standards（評分標準）
    # ==========================================
    print("\n" + "=" * 70)
    print("📖 [S] Standards - 查看評分標準手冊")
    print("=" * 70)

    handbook = framework.get_scoring_handbook()
    print(f"✓ 評分標準手冊已生成")
    print(f"  - 評分維度數：{len(handbook.dimensions)}")
    for dim in list(handbook.dimensions.keys())[:3]:
        print(f"    • {dim}")

    # ==========================================
    # S - Scrutiny（審核方法）
    # ==========================================
    print("\n" + "=" * 70)
    print("🔍 [S] Scrutiny - 人工審核與驗證")
    print("=" * 70)

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
    print(f"✓ 人工審核記錄已生成")
    print(f"  - 審核員：{record.reviewer_id}")
    print(f"  - 備註：{record.annotation}")

    # ==========================================
    # 生成完整報告
    # ==========================================
    print("\n" + "=" * 70)
    print("📄 生成完整審核報告")
    print("=" * 70)

    full_report = framework.generate_full_report()
    
    print(f"\n✅ 審核完成！")
    print(f"  • 整體風險等級：{full_report.get('overall_risk_level', 'N/A')}")
    print(f"  • 通過率：{effectiveness_report.pass_rate:.1%}")
    print(f"  • 評估案例數：{len(cases)}")
    print(f"  • 識別的壞案例數：{len(bad_case_report.bad_cases)}")
    print(f"\n完整報告：")
    print("-" * 70)
    import json
    print(json.dumps(full_report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
