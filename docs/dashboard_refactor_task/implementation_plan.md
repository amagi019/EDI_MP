# ダッシュボード改修 実装計画

## 目標
ユーザーの要望に基づき、ダッシュボードの表示を整理し、ボタンのスタイルを修正します。
具体的には、「取引先オンボーディング・基本契約進捗」をダッシュボードから削除し（既存の別画面へのリンクは維持）、新規取引先登録ボタンのスタイルを他のボタンと統一します。

## 変更内容

### Core テンプレート

#### [変更] [dashboard.html](file:///c:/workspace/Macplanning/EDI_MP/core/templates/core/dashboard.html)
1.  **進捗リストの削除**: 画面下部の `{% if user.is_staff and contract_progress_list %}` ブロック（テーブル表示部分）を完全に削除します。
    *   *注記*: 既に「基本契約進捗」ボタンが存在し、別画面 (`contract_progress_list`) への遷移が機能しているため、ダッシュボード上のテーブルは不要となります。
2.  **ボタン・スタイルの変更**: 「取引先新規登録」ボタンのクラスを `btn` (独自スタイル) から `btn btn-secondary` に変更し、インラインスタイルを削除します。
    *   *After*: `<a href="..." class="btn btn-secondary">`

#### [修正] [contract_progress_list.html](file:///c:/workspace/Macplanning/EDI_MP/core/templates/core/contract_progress_list.html)
1.  **CSS変数の修正**: `base.html` で定義されていない変数（`--border-color`, `--bg-surface`, `--secondary-color` 等）を、正しい変数（`--border`, `--surface`, `--secondary`）に置き換えます。
2.  **テーブル構造の整理**: 表示崩れの原因となるスタイルを修正し、`dashboard.html` で使用されていた安定したデザインパターンを適用します。

## 検証計画

### 手動検証
1.  **サーバー起動**: `python manage.py runserver`
2.  **ダッシュボード確認**:
    *   「取引先オンボーディング・基本契約進捗」のテーブルが表示されていないことを確認。
    *   「取引先新規登録」ボタンが、「注文書一覧」ボタンと同じグレー（セカンダリ）スタイルになっていることを確認。
3.  **画面遷移確認**:
    *   「基本契約進捗」ボタンをクリックし、進捗一覧画面が正しく表示されることを確認。
