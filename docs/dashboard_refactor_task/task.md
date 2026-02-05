# ダッシュボード改修タスク (Dashboard Refactor)

- [x] 現状調査 (Investigation) <!-- id: 0 -->
    - [x] `core/views.py` の確認 (データ取得ロジックの特定 - 既にView存在) <!-- id: 1 -->
    - [x] `core/urls.py` の確認 (既にURL存在) <!-- id: 2 -->
- [x] 画面の分離 (Separate Screen) <!-- id: 3 -->
    - [x] 新規ビュー `ContractProgressView` の作成 (既存利用) <!-- id: 4 -->
    - [x] `contract_progress_list.html` の修正 (再実装・CSS変数整合) <!-- id: 5 -->
    - [x] `urls.py` へのルーティング追加 (既存利用) <!-- id: 6 -->
- [x] ダッシュボードの修正 (Dashboard Update) <!-- id: 7 -->
    - [x] 「取引先オンボーディング・基本契約進捗」セクションの削除 <!-- id: 8 -->
    - [x] 「基本契約進捗」画面への遷移ボタン追加 <!-- id: 9 -->
    - [x] 「新規取引先登録」ボタンのスタイル変更 (`btn-secondary`化) <!-- id: 10 -->
- [x] 検証 (Verification) <!-- id: 11 --> (ユーザー作業待ち: 詳細はwalkthrough.md参照)
