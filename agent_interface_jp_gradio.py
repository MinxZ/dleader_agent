# -*- coding: utf-8 -*-

"""
日本語エージェントインターフェース（ライブ思考表示付き）
このインターフェースは以下の機能を持つクリーンなレイアウトを提供します：
- 左側：ユーザー入力と最終レポート表示
- 右側：プランニングと思考プロセスを表示するライブ実行エンジン
- レポートと思考プロセスのダウンロード機能
"""

import argparse
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

import gradio as gr
import pandas as pd
from PIL import Image

# インポート用に現在のディレクトリをパスに追加
sys.path.insert(0, os.getcwd())

from dleader_agent.agent.a1 import A1

# JST (Japan Standard Time) タイムゾーンを定義
JST = timezone(timedelta(hours=9))

def now_jst():
    """JST (UTC+9) での現在時刻を取得"""
    return datetime.now(JST)


class SessionManager:
    """セッションフォルダーとファイル保存を管理"""
    def __init__(self):
        self.sessions_dir = os.path.join(os.getcwd(), "chat_sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)
    
    def create_session_folder(self):
        """ユニークなセッションフォルダーを作成"""
        session_id = str(uuid.uuid4())[:8]
        timestamp = now_jst().strftime("%Y%m%d_%H%M%S")
        session_name = f"session_{timestamp}_{session_id}"
        session_path = os.path.join(self.sessions_dir, session_name)
        os.makedirs(session_path, exist_ok=True)
        return session_path, session_name
    
    def get_all_sessions(self):
        """既存のチャットセッション一覧を取得"""
        if not os.path.exists(self.sessions_dir):
            return []
        
        sessions = []
        for item in os.listdir(self.sessions_dir):
            session_path = os.path.join(self.sessions_dir, item)
            if os.path.isdir(session_path) and item.startswith("session_"):
                # セッション名からタイムスタンプを抽出
                try:
                    parts = item.split("_")
                    if len(parts) >= 3:
                        date_part = parts[1]
                        time_part = parts[2]
                        # フォーマット: YYYYMMDD_HHMMSS
                        display_name = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
                        sessions.append((item, display_name, session_path))
                except:
                    sessions.append((item, item, session_path))
        
        # セッション名でソート（最新順）
        sessions.sort(key=lambda x: x[0], reverse=True)
        return sessions
    
    def load_session_data(self, session_path):
        """既存セッションからデータを読み込み"""
        if not os.path.exists(session_path):
            return None, None, None
        
        # レポート、思考、クエリファイルを探す
        report_content = None
        thinking_content = None
        session_files = []
        
        try:
            for file in os.listdir(session_path):
                file_path = os.path.join(session_path, file)
                if file.startswith("report_") and file.endswith(".md"):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        report_content = f.read()
                elif file.startswith("thinking_process_") and file.endswith(".txt"):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        thinking_content = f.read()
                elif not file.startswith("report_") and not file.startswith("thinking_process_") and not file.startswith("query_"):
                    # ユーザーがアップロードしたファイル
                    session_files.append(file_path)
        except Exception as e:
            print(f"セッションデータ読み込みエラー: {e}")
        
        return report_content, thinking_content, session_files
    
    def save_uploaded_files(self, uploaded_files, session_path):
        """アップロードファイルをセッションフォルダーに保存し新しいパスを返却"""
        if not uploaded_files:
            return []
        
        saved_files = []
        for file in uploaded_files:
            if file is None:
                continue
            original_name = os.path.basename(file.name)
            new_path = os.path.join(session_path, original_name)
            shutil.copy2(file.name, new_path)
            saved_files.append(new_path)
        
        return saved_files


class StreamingCapture:
    """標準出力をキャプチャしリアルタイム更新を提供"""
    def __init__(self):
        self.content = ""
        self.original_stdout = sys.stdout
        
    def write(self, text):
        self.content += text
        self.original_stdout.write(text)
        self.original_stdout.flush()
        
    def flush(self):
        self.original_stdout.flush()
        
    def get_content(self):
        return self.content


def create_agent():
    """画像解析タスク専用に設定されたエージェントを作成"""
    
    # デフォルトのデータレイクをダウンロードせずにエージェントを初期化
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False, 
        llm='claude-sonnet-4-5-20250929'
    )
    
    return agent


def scan_for_new_files(current_path, start_time, exclude_folders=None):
    """開始時刻以降に作成されたファイルをスキャン、指定フォルダーを除外"""
    if exclude_folders is None:
        exclude_folders = {'chat_sessions', '__pycache__', '.git', '.vscode', 'node_modules'}
    
    new_files = []
    try:
        for root, dirs, files in os.walk(current_path):
            # 除外ディレクトリをスキップするため、dirsをその場で変更（os.walkが巡回を制御）
            dirs[:] = [d for d in dirs if d not in exclude_folders]
            
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime > start_time:
                        new_files.append(file_path)
                except OSError:
                    # アクセスできないファイルはスキップ
                    continue
    except Exception as e:
        print(f"新しいファイルのスキャンエラー: {e}")
    
    return new_files


def move_files_to_session(file_paths, session_path):
    """ファイルをセッションフォルダーに移動、重複は名前変更で処理"""
    moved_files = []
    
    for file_path in file_paths:
        try:
            filename = os.path.basename(file_path)
            destination = os.path.join(session_path, filename)
            
            # 重複をカウンターで処理
            counter = 1
            while os.path.exists(destination):
                name, ext = os.path.splitext(filename)
                destination = os.path.join(session_path, f"{name}_{counter}{ext}")
                counter += 1
            
            # ファイルを移動
            shutil.move(file_path, destination)
            moved_files.append(destination)
            print(f"ファイルを移動しました: {file_path} → {destination}")
            
        except Exception as e:
            print(f"ファイル移動エラー {file_path}: {e}")
    
    return moved_files


def process_with_agent_streaming(message, uploaded_files):
    """エージェントの思考をライブストリーミングでユーザーリクエストを処理"""
    if not message.strip():
        yield "😴 メッセージを入力してください...", "", "", "", ""
        return
    
    try:
        # このチャット用のセッションフォルダーを作成
        session_manager = SessionManager()
        session_path, session_name = session_manager.create_session_folder()
        
        # エージェントを初期化
        yield f"🔄 **エージェントを初期化中...** (セッション: {session_name})", "", "", "", ""
        agent = create_agent()
        
        # アップロードファイルを処理
        session_file_paths = []
        if uploaded_files:
            yield f"📁 **アップロードファイルをセッションフォルダーに保存中...**", "", "", "", ""
            session_file_paths = session_manager.save_uploaded_files(uploaded_files, session_path)
            
            # セッションパスでエージェントのデータレイクにファイルを追加
            agent.data_lake_dict = {}
            for file_path in session_file_paths:
                filename = os.path.basename(file_path)
                try:
                    if filename.endswith('.csv'):
                        data = pd.read_csv(file_path)
                        agent.data_lake_dict[filename] = f"{data.shape[0]}行 {data.shape[1]}列のデータセット (パス: {file_path})"
                    elif filename.endswith(('.xlsx', '.xls')):
                        data = pd.read_excel(file_path)
                        agent.data_lake_dict[filename] = f"{data.shape[0]}行 {data.shape[1]}列のExcelファイル (パス: {file_path})"
                    else:
                        agent.data_lake_dict[filename] = f"アップロードされたファイル (フォーマット自動検出) (パス: {file_path})"
                except:
                    agent.data_lake_dict[filename] = f"アップロードされたファイル (フォーマット自動検出) (パス: {file_path})"
            agent.configure()
            
        yield f"🚀 **処理を開始中...** (ファイル保存先: {session_path})", "", "", "", ""
        
        # ストリーミングキャプチャを設定
        stream_capture = StreamingCapture()
        
        # 結果用のコンテナ
        result_container = {"result": None, "error": None, "completed": False}
        accumulated_thinking = ""
        
        def run_agent():
            try:
                with redirect_stdout(stream_capture):
                    # セッションフォルダーパスをメッセージに追加
                    enhanced_message = f"{message}\n\n注意: アップロードされたファイルは次の作業フォルダに保存されています: {session_path} ファイルを生成あるいは保存する場合は、作業フォルダに保存してください。コメントはできるだけ日本語で記述し、最終レポートも日本語で作成すること。 use plt.rcParams['font.family'] = ['Noto Sans CJK JP', 'DejaVu Sans' ] when plot"
                    _, result = agent.go(enhanced_message)
                result_container["result"] = result
            except Exception as e:
                result_container["error"] = str(e)
            finally:
                result_container["completed"] = True
        
        # エージェントをバックグラウンドで開始
        agent_thread = threading.Thread(target=run_agent)
        agent_thread.start()
        
        # ファイル追跡のため開始時刻を記録
        start_time = time.time()
        current_path = os.getcwd()
        chat_sessions_path = os.path.join(os.getcwd(), "chat_sessions")
        print(f"現在のパス: {current_path}")
        print(f"チャットセッションパス: {chat_sessions_path}")
        
        # 更新を監視してストリーミング
        last_content_length = 0
        while not result_container["completed"]:
            current_content = stream_capture.get_content()
            if len(current_content) > last_content_length:
                # 新しいコンテンツが利用可能 - 増分更新を表示
                new_content = current_content[last_content_length:]
                accumulated_thinking += new_content
                
                # ライブ思考表示をフォーマット
                thinking_display = f"""## 🤖 エージェント実行エンジン (ライブ)
                
```
{accumulated_thinking}
```

**ステータス:** 🔄 処理中...
**最終更新:** {now_jst().strftime('%H:%M:%S')}
"""
                
                yield thinking_display, "", "", "", ""
                last_content_length = len(current_content)
            time.sleep(0.5)  # 500msごとに更新
        
        # スレッド完了を待機
        agent_thread.join()
        
        # 最終コンテンツを取得
        final_content = stream_capture.get_content()
        if len(final_content) > last_content_length:
            new_content = final_content[last_content_length:]
            accumulated_thinking += new_content
        
        # 最終結果をフォーマット
        if result_container["error"]:
            final_report = f"""## ❌ 最終レポート

```
{result_container['error']}
```
"""
            thinking_final = f"""## ❌ エージェント実行エンジン (完了)

```
{accumulated_thinking}
```

**ステータス:** ❌ エラーが発生しました
**完了時刻:** {now_jst().strftime('%H:%M:%S')}
"""
        else:
            # <solution>と</solution>タグ間のコンテンツを抽出
            raw_result = result_container['result'] or '処理が正常に完了しました。'
            
            # solutionタグを探す
            if '<solution>' in raw_result and '</solution>' in raw_result:
                start_idx = raw_result.find('<solution>') + len('<solution>')
                end_idx = raw_result.find('</solution>')
                solution_content = raw_result[start_idx:end_idx].strip()
            else:
                # solutionタグが見つからない場合、結果全体を使用
                solution_content = raw_result
            
            final_report = f"""## ✅ 最終レポート

{solution_content}
"""
            
            thinking_final = f"""## ✅ エージェント実行エンジン (完了)

```
{accumulated_thinking}
```

**ステータス:** ✅ 正常に完了
**終了時刻:** {now_jst().strftime('%H:%M:%S')}
"""
        
        # 処理中に作成された新しいファイルをスキャンして移動
        try:
            exclude_paths = {'chat_sessions', '__pycache__', '.git', '.vscode', 'node_modules', chat_sessions_path}
            new_files = scan_for_new_files(current_path, start_time, exclude_paths)
            
            # chat_sessionsフォルダーに既にあるファイルを除外
            filtered_files = [f for f in new_files if not f.startswith(chat_sessions_path)]
            
            if filtered_files:
                print(f"処理中に作成された新しいファイルを{len(filtered_files)}個発見:")
                for file in filtered_files:
                    print(f"  - {file}")
                moved_files = move_files_to_session(filtered_files, session_path)
                print(f"{len(moved_files)}個のファイルをセッションフォルダーに移動しました")
        except Exception as e:
            print(f"新しいファイルの処理エラー: {e}")
        
        # セッションファイルをchat_sessionsフォルダーに保存
        try:
            # レポートファイルを保存
            report_filename = f"report_{now_jst().strftime('%Y%m%d_%H%M%S')}.md"
            report_path = os.path.join(session_path, report_filename)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(final_report)
            
            # 思考プロセスファイルを保存
            thinking_filename = f"thinking_process_{now_jst().strftime('%Y%m%d_%H%M%S')}.txt"
            thinking_path = os.path.join(session_path, thinking_filename)
            with open(thinking_path, 'w', encoding='utf-8') as f:
                f.write(accumulated_thinking)
            
            # 参考用にクエリ/メッセージを保存
            query_filename = f"query_{now_jst().strftime('%Y%m%d_%H%M%S')}.txt"
            query_path = os.path.join(session_path, query_filename)
            with open(query_path, 'w', encoding='utf-8') as f:
                f.write(f"クエリ: {message}\nタイムスタンプ: {now_jst().strftime('%Y-%m-%d %H:%M:%S')}")
                
        except Exception as e:
            print(f"セッションファイル保存エラー: {e}")
        
        # ダウンロード用ファイルを作成
        report_file = create_download_file(final_report, "report", "md")
        thinking_file = create_download_file(accumulated_thinking, "thinking_process", "txt")
        session_zip = create_session_zip(session_path)
        
        # エージェント実行エンジン表示用に思考と最終レポートを結合
        combined_executor_display = f"{thinking_final}\n\n---\n\n{final_report}"
        
        yield combined_executor_display, "## ✅ 処理完了\n\n結果はエージェント実行エンジンパネルに表示されています →", report_file, thinking_file, session_zip
        
    except Exception as e:
        error_display = f"""## ❌ エージェント実行エンジン (システムエラー)

```
システムエラー: {str(e)}
```

**ステータス:** ❌ システムエラー
**タイムスタンプ:** {now_jst().strftime('%H:%M:%S')}
"""
        yield error_display, "## ❌ システムエラー\n\nエラー詳細はエージェント実行エンジンパネルに表示されています →", "", "", "", ""


def create_download_file(content, prefix, extension):
    """ダウンロード用の一時ファイルを作成"""
    try:
        timestamp = now_jst().strftime('%Y%m%d_%H%M%S')
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', 
            suffix=f'.{extension}',
            prefix=f'{prefix}_{timestamp}_',
            delete=False,
            encoding='utf-8'
        )
        temp_file.write(content)
        temp_file.close()
        return temp_file.name
    except Exception:
        return None


def create_session_zip(session_path):
    """全セッションコンテンツを含むzipファイルを作成"""
    if not os.path.exists(session_path):
        return None
    
    try:
        session_name = os.path.basename(session_path)
        timestamp = now_jst().strftime('%Y%m%d_%H%M%S')
        
        # 一時zipファイルを作成
        zip_file = tempfile.NamedTemporaryFile(
            suffix='.zip',
            prefix=f"{'_'.join(session_name.split('_')[:-1])}_",
            delete=False
        )
        zip_file.close()
        
        # zipアーカイブを作成
        with zipfile.ZipFile(zip_file.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # セッションディレクトリ内の全ファイルを巡回
            for root, dirs, files in os.walk(session_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # 相対パスでファイルをzipに追加
                    arcname = os.path.relpath(file_path, session_path)
                    zipf.write(file_path, arcname)
        
        return zip_file.name
    except Exception as e:
        print(f"セッションzip作成エラー: {e}")
        return None


def format_files_info(files):
    """アップロードファイル情報をフォーマット"""
    if not files:
        return "ファイルがアップロードされていません"
    
    file_info = []
    for file in files:
        filename = os.path.basename(file.name)
        file_size = os.path.getsize(file.name) / (1024 * 1024)  # MBサイズ
        file_info.append(f"📁 **{filename}** ({file_size:.2f} MB)")
    
    return "**アップロードファイル:**\n\n" + "\n".join(file_info)


def load_logo():
    """ロゴ画像を読み込み"""
    try:
        img = Image.open("dleader_logo.png")
        return img
    except:
        return None

def create_interface():
    """メインGradioインターフェースを作成"""
    
    with gr.Blocks(title="AIエージェントインターフェース", theme=gr.themes.Soft()) as demo:
        # ロゴとタイトルのブロックによるヘッダーセクション
        with gr.Row():
            with gr.Column(scale=1, min_width=120):
                gr.Image(
                    value=load_logo(),
                    show_label=False,
                    show_download_button=False,
                    container=False,
                    height=100,
                    width=120,
                    interactive=False
                )
            with gr.Column(scale=5):
                gr.HTML("""
                <div style="display: flex; align-items: center; justify-content: center; height: 120px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 20px; margin: 10px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
                    <div style="text-align: center;">
                        <h1 style="margin: 0; font-size: 2.5em; color: white; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">KumiChem AI Agent</h1>
                    </div>
                </div>
                """)
        
        with gr.Row(equal_height=True):
            # 左カラム - ユーザー入力と最終レポート
            with gr.Column(scale=1):
                gr.Markdown("## 📝 入力と結果")
                
                # ファイルアップロードセクション
                with gr.Group():
                    gr.Markdown("### 📁 ファイルアップロード")
                    file_input = gr.File(
                        label="ファイルをアップロード",
                        file_count="multiple",
                        file_types=None,
                        height=100
                    )
                    file_status = gr.Markdown("ファイルがアップロードされていません")
                
                # ユーザー入力セクション
                with gr.Group():
                    gr.Markdown("### 💬 あなたのリクエスト")
                    user_input = gr.Textbox(
                        label="エージェントに実行してほしいタスクを記述してください",
                        placeholder="ここにリクエストを入力してください...\n\n例:\n• アップロードされたデータを分析\n• 文書から重要な情報を抽出\n• 計算や分析を実行\n• レポートやサマリーを生成",
                        lines=5,
                        max_lines=10
                    )
                    
                    with gr.Row():
                        submit_btn = gr.Button("🚀 処理開始", variant="primary", scale=2)
                        clear_btn = gr.Button("🗑️ クリア", variant="secondary", scale=1)
                
                # ステータスセクション（最終レポートの代替）
                with gr.Group():
                    gr.Markdown("### 📊 ステータスと結果")
                    final_report = gr.Markdown(
                        """## 📊 セッションステータス

結果表示の準備ができています...

**ステータス:** 🟢 処理待機中
**結果表示準備完了...**
""",
                        height=200
                    )
                    
                    with gr.Row():
                        download_report = gr.File(
                            label="📥 レポートダウンロード",
                            visible=False
                        )
                        download_thinking = gr.File(
                            label="📥 思考プロセスダウンロード",
                            visible=False
                        )
                        download_session_zip = gr.File(
                            label="📦 完全セッションダウンロード",
                            visible=False
                        )
            
            # 右カラム - ライブ実行エンジン表示
            with gr.Column(scale=1):
                gr.Markdown("## 🧠 エージェント実行エンジン (詳細を見るには下にスクロール)")
                
                executor_display = gr.Markdown(
                    """## 🤖 エージェント実行エンジン
                    
リクエストの処理準備ができています...

**ステータス:** 🟢 待機中
**入力待機中...**
""",
                    height=600
                )
                
                # ステータスインジケーター
                with gr.Row():
                    gr.HTML("""
                    <div style="display: flex; align-items: center; justify-content: center; padding: 10px; background: #f0f0f0; border-radius: 5px;">
                        <span style="color: #28a745; font-weight: bold;">●</span>
                        <span style="margin-left: 10px;">システム準備完了</span>
                    </div>
                    """)
        
        # イベントハンドラー
        def update_file_status(files):
            return format_files_info(files)
        
        
        def process_request(message, files):
            if not message.strip():
                return (
                    "## ❌ エージェント実行エンジン\n\n❌ リクエストを入力してください", 
                    "## ❌ 入力なし\n\n処理するリクエストを入力してください。",
                    gr.update(visible=False), 
                    gr.update(visible=False),
                    gr.update(visible=False)
                )
            
            # 処理をストリーミング
            for executor, report, report_file, thinking_file, session_zip in process_with_agent_streaming(message, files):
                if report_file and thinking_file and session_zip:
                    yield (
                        executor, 
                        report,
                        gr.update(visible=True, value=report_file),
                        gr.update(visible=True, value=thinking_file),
                        gr.update(visible=True, value=session_zip)
                    )
                else:
                    yield (executor, report, gr.update(visible=False), gr.update(visible=False), gr.update(visible=False))
        
        def clear_interface():
            return (
                "",  # ユーザー入力をクリア
                """## 🤖 エージェント実行エンジン
                    
リクエストの処理準備ができています...

**ステータス:** 🟢 待機中
**入力待機中...**
""",  # 実行エンジンをリセット
                """## 📊 セッションステータス

結果表示の準備ができています...

**ステータス:** 🟢 処理待機中
**結果表示準備完了...**
""",  # ステータスをリセット
                gr.update(visible=False),  # ダウンロードボタンを隠す
                gr.update(visible=False),
                gr.update(visible=False)  # セッションzipを隠す
            )
        
        # イベントを配線
        file_input.change(
            fn=update_file_status,
            inputs=[file_input],
            outputs=[file_status]
        )
        
        
        submit_btn.click(
            fn=process_request,
            inputs=[user_input, file_input],
            outputs=[executor_display, final_report, download_report, download_thinking, download_session_zip]
        )
        
        clear_btn.click(
            fn=clear_interface,
            outputs=[user_input, executor_display, final_report, download_report, download_thinking, download_session_zip]
        )
        
        # Enterキーでの送信を許可
        user_input.submit(
            fn=process_request,
            inputs=[user_input, file_input],
            outputs=[executor_display, final_report, download_report, download_thinking, download_session_zip]
        )
    
    return demo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="日本語エージェントインターフェース（ライブ思考表示付き）")
    parser.add_argument("--server_port", type=int, default=8000, help="サーバーのポート番号 (デフォルト: 8000)")
    args = parser.parse_args()
    
    demo = create_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=args.server_port,
        share=True,
        debug=True
    )