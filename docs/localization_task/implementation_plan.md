# 多言語化 実装計画

## 目標
ユーザーはメニューの日本語化を希望しています。調査の結果、`base.html` のヘッダーとフッターにある "EDI SYSTEM" という表記が英語でハードコードされていることが判明しました。これを修正し、完全な日本語化を行います。

## ユーザーレビュー事項
> [!NOTE]
> 「Antigravity メニュー」というご指摘は、私（Antigravity）に対してアプリケーションのメニュー/ヘッダーの日本語化を依頼されたものと解釈しました。

## 変更内容

### Core テンプレート

#### [変更] [base.html](file:///c:/workspace/Macplanning/EDI_MP/core/templates/base.html)
- ヘッダーの `<a href="/" class="brand">EDI SYSTEM</a>` を `{% trans "EDIシステム" %}` に変更します。
- フッターのコピーライト表記 `EDI System` を `EDIシステム` に変更します。

### 翻訳ファイル

#### [確認] [django.po](file:///c:/workspace/Macplanning/EDI_MP/locale/ja/LC_MESSAGES/django.po)
- 既に `msgid "EDIシステム"` が存在することを確認済みです。

## 検証計画

### 手動検証
1.  **目視確認**: アプリケーションを開き、ヘッダーの "EDI SYSTEM" が "EDIシステム" になっていることを確認します。
2.  **コード確認**: `base.html` に日本語（または翻訳タグ）が含まれていることを確認します。
