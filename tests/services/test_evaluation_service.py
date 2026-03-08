from app.services.evaluation_service import (
    build_evaluation_prompt,
)


class TestBuildEvaluationPrompt:
    """build_evaluation_prompt 関数のテスト"""

    def test_build_evaluation_prompt(self):
        """評価プロンプト構築 - 正常系"""
        prompt_template = "以下の出力を評価してください。"
        input_text = "患者は60歳男性。"
        current_prescription = "メトホルミン500mg"
        additional_info = "HbA1c 7.5%"
        output_summary = "主病名: 糖尿病"

        result = build_evaluation_prompt(
            prompt_template,
            input_text,
            current_prescription,
            additional_info,
            output_summary
        )

        assert prompt_template in result
        assert "【カルテ記載】" in result
        assert input_text in result
        assert "【退院時処方(現在の処方)】" in result
        assert current_prescription in result
        assert "【追加情報】" in result
        assert additional_info in result
        assert "【生成された出力】" in result
        assert output_summary in result

    def test_build_evaluation_prompt_empty_fields(self):
        """評価プロンプト構築 - 空のフィールド"""
        prompt_template = "評価してください"
        result = build_evaluation_prompt(
            prompt_template, "", "", "", "出力内容"
        )

        assert prompt_template in result
        assert "【カルテ記載】" in result
        assert "【生成された出力】" in result
        assert "出力内容" in result
