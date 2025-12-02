# --- Vertex AIのセットアップ ---
def setup_vertex_ai():
    try:
        # SecretsからJSONキー情報を取得
        key_info = dict(st.secrets["gcp_service_account"])

        # 【★ここが修正ポイント】 
        # 秘密鍵の "\n" という文字を、本当の改行コードに置き換えます
        key_info["private_key"] = key_info["private_key"].replace("\\n", "\n")
        
        # 一時ファイルを作成して認証情報を書き込む
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(key_info, f)
            key_path = f.name
        
        # 環境変数にセット
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path
        
        # Vertex AI初期化
        project_id = key_info["project_id"]
        vertexai.init(project=project_id, location="us-central1")
        return ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")

    except Exception as e:
        st.error(f"接続設定エラー: {e}")
        return None
