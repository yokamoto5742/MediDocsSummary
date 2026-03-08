"""CSRF認証の統合テスト"""

from fastapi.testclient import TestClient


class TestCsrfAuthentication:
    """APIエンドポイントのCSRF認証テスト"""

    def test_protected_endpoint_requires_csrf_token(self, client: TestClient):
        """保護されたエンドポイントはCSRFトークンなしで401エラー"""
        response = client.post(
            "/api/summary/generate",
            json={
                "medical_text": "test",
                "department": "内科",
                "document_type": "診療情報提供書",
            },
        )
        assert response.status_code == 401
        assert "CSRFトークンが必要です" in response.json()["detail"]

    def test_protected_endpoint_with_invalid_token(self, client: TestClient):
        """無効なCSRFトークンで403エラー"""
        response = client.post(
            "/api/summary/generate",
            json={
                "medical_text": "test",
                "department": "内科",
                "document_type": "診療情報提供書",
            },
            headers={"X-CSRF-Token": "invalid.token"},
        )
        assert response.status_code == 403
        assert "無効または期限切れのCSRFトークンです" in response.json()["detail"]

    def test_evaluation_endpoint_requires_csrf_token(self, client: TestClient):
        """評価エンドポイントもCSRFトークン必須"""
        response = client.post(
            "/api/evaluation/evaluate",
            json={
                "document_type": "診療情報提供書",
                "input_text": "test",
                "output_summary": "test",
            },
        )
        assert response.status_code == 401
        assert "CSRFトークンが必要です" in response.json()["detail"]

    def test_web_pages_do_not_require_csrf(self, client: TestClient):
        """WebページUIはCSRF認証不要"""
        response = client.get("/")
        assert response.status_code == 200

    def test_public_endpoints_no_csrf(self, client: TestClient):
        """公開エンドポイント(GET)はCSRF認証不要"""
        # 設定エンドポイント
        response = client.get("/api/settings/departments")
        assert response.status_code == 200
        assert "departments" in response.json()

        # モデル一覧エンドポイント
        response = client.get("/api/summary/models")
        assert response.status_code == 200

    def test_admin_endpoints_require_csrf(self, client: TestClient, csrf_headers):
        """管理用エンドポイント(POST/DELETE)はCSRF認証必須"""
        # プロンプト作成はCSRF トークン必須
        response = client.post(
            "/api/prompts/",
            json={
                "department": "内科",
                "doctor": "default",
                "document_type": "他院への紹介",
                "content": "test",
            },
        )
        assert response.status_code == 401

        # CSRF トークンありでは成功
        response = client.post(
            "/api/prompts/",
            json={
                "department": "内科",
                "doctor": "default",
                "document_type": "他院への紹介",
                "content": "test",
            },
            headers=csrf_headers,
        )
        assert response.status_code == 200
