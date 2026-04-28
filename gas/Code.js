/**
 * メインエントリーポイント
 * トリガーから呼ばれる関数群と、手動実行用のユーティリティ
 */

/**
 * 日次トリガーから呼ばれるメイン関数
 * 1. 受信メールの処理（報告書＋パスワードの検出）
 * 2. 送信待ちレポートの処理（下書き作成 or 送信）
 */
function dailyProcess() {
  Logger.log('=== 日次処理開始: ' + new Date().toLocaleString('ja-JP') + ' ===');

  try {
    // 処理前の行数を記録
    var props = PropertiesService.getScriptProperties();
    var sheetId = props.getProperty('SHEET_ID');
    var sheet = SpreadsheetApp.openById(sheetId).getSheetByName(CONFIG.sheet.sheetTab);
    var beforeCount = sheet.getLastRow() - 1; // ヘッダー除く

    // Step 1: 受信メール処理
    processIncomingEmails();

    // Step 2: 送信待ち処理
    sendPendingReports();

    // Step 3: 新規レコードがあれば通知メール送信
    var afterCount = sheet.getLastRow() - 1;
    if (afterCount > beforeCount) {
      sendNotification_(sheet, beforeCount + 2, afterCount + 1, sheetId);
    }

  } catch (e) {
    Logger.log('エラー: ' + e.toString());
    MailApp.sendEmail(
      Session.getActiveUser().getEmail(),
      '【エラー】稼働報告メール自動処理',
      '日次処理でエラーが発生しました。\n\n'
      + 'エラー内容: ' + e.toString() + '\n'
      + '日時: ' + new Date().toLocaleString('ja-JP')
    );
  }

  Logger.log('=== 日次処理完了 ===');
}

/**
 * 新しい報告書検出時にユーザーに通知メールを送信
 */
/**
 * 新しい報告書検出時にユーザーに通知メールを送信
 */
function sendNotification_(sheet, startRow, endRow, sheetId) {
  var sheetUrl = SpreadsheetApp.openById(sheetId).getUrl();
  var subject = '【自動通知】新しい作業報告書を受信しました';
  var body = '';
  var hasPasswordProtected = false;

  for (var row = startRow; row <= endRow; row++) {
    var data = sheet.getRange(row, 1, 1, 15).getValues()[0];
    var workerName = data[2];
    var status = data[8];
    var totalHours = data[14];

    var isSuccess = (status === '解析完了');
    if (!isSuccess) hasPasswordProtected = true;

    body += '━━━━━━━━━━━━━━━━━━━━\n';
    body += '対象月: ' + data[0] + '\n';
    body += 'パートナー: ' + data[1] + '\n';
    body += '作業者: ' + workerName + '\n';

    if (isSuccess) {
      body += '✅ ステータス: 解析完了\n';
      body += '稼働時間: ' + (totalHours || '（取得できませんでした）') + '\n';
      body += 'ファイル: ' + data[5] + '\n';
    } else {
      body += '⚠️ ステータス: パスワード解除待ち\n';
      body += 'パスワード: ' + data[4] + '\n';
      body += 'ファイル: ' + data[5] + '\n';
    }
    body += '\n';
  }

  body += '━━━━━━━━━━━━━━━━━━━━\n\n';

  body += '【次のステップ】\n';
  if (hasPasswordProtected) {
    body += '1. パスワード保護されたファイルを上記パスワードで開く\n';
    body += '2. パスワードなしで保存し、送信用フォルダにアップロード\n';
    body += '3. 管理シートの「送信用ファイルリンク」にURLを記入\n';
    body += '4. ステータスを「送信準備完了」に変更\n';
  } else {
    body += '1. 管理シートを確認し、内容に問題がなければ送信準備へ\n';
    body += '2. ファイルを送信用フォルダにコピー\n';
    body += '3. 管理シートの「送信用ファイルリンク」にURLを記入\n';
    body += '4. ステータスを「送信準備完了」に変更\n';
  }
  body += '\n管理シート: ' + sheetUrl + '\n';

  MailApp.sendEmail(
    Session.getActiveUser().getEmail(),
    subject,
    body
  );

  Logger.log('通知メール送信完了');
}

/**
 * 手動実行: 受信メール処理のみ
 * GASエディタから手動で実行する場合に使用
 */
function manualProcessEmails() {
  Logger.log('=== 手動: 受信メール処理 ===');
  processIncomingEmails();
  Logger.log('=== 完了 ===');
}

/**
 * 手動実行: 送信処理のみ
 * GASエディタから手動で実行する場合に使用
 */
function manualSendReports() {
  Logger.log('=== 手動: 送信処理 ===');
  sendPendingReports();
  Logger.log('=== 完了 ===');
}

/**
 * 管理シートのURLを取得（ログ出力用）
 */
function getSheetUrl() {
  var sheetId = PropertiesService.getScriptProperties().getProperty('SHEET_ID');
  if (sheetId) {
    var url = SpreadsheetApp.openById(sheetId).getUrl();
    Logger.log('管理シート: ' + url);
    return url;
  }
  Logger.log('管理シートが設定されていません。initialSetup() を実行してください。');
  return null;
}

/**
 * 送信モードを切り替え
 * @param {string} mode - 'draft' or 'auto'
 */
function setSendMode(mode) {
  if (mode !== 'draft' && mode !== 'auto') {
    Logger.log('無効なモードです。"draft" または "auto" を指定してください。');
    return;
  }

  // 注意: CONFIG は const なので実行時の変更はセッション中のみ有効
  // 恒久的に変更する場合は Config.gs の sendMode を直接編集してください
  PropertiesService.getScriptProperties().setProperty('SEND_MODE', mode);
  Logger.log('送信モードを "' + mode + '" に設定しました。');
  Logger.log('注意: 恒久的な変更は Config.gs の sendMode を直接編集してください。');
}

/**
 * 現在の設定状態を確認
 */
function checkStatus() {
  var props = PropertiesService.getScriptProperties().getProperties();
  Logger.log('=== 現在の設定 ===');
  Logger.log('送信モード: ' + CONFIG.sendMode);
  Logger.log('パートナー数: ' + CONFIG.partners.length);

  CONFIG.partners.forEach(function(p) {
    Logger.log('  - ' + p.name + ' (' + p.senderEmail + ')');
    Logger.log('    作業者名: ' + p.workerName);
    Logger.log('    プロジェクト名: ' + p.projectName);
  });

  Logger.log('転送先: ' + CONFIG.recipient.email);
  Logger.log('セットアップ済み: ' + isSetupDone());

  if (props['SHEET_ID']) {
    Logger.log('管理シート: ' + SpreadsheetApp.openById(props['SHEET_ID']).getUrl());
  }
  if (props['ROOT_FOLDER_ID']) {
    Logger.log('Driveフォルダ: https://drive.google.com/drive/folders/' + props['ROOT_FOLDER_ID']);
  }
}

/**
 * トリガーを再設定
 */
function resetTriggers() {
  // 既存の全トリガーを削除
  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    ScriptApp.deleteTrigger(trigger);
  });

  // dailyProcessトリガーを再作成
  ScriptApp.newTrigger('dailyProcess')
    .timeBased()
    .everyDays(1)
    .atHour(9)
    .create();

  Logger.log('トリガーを再設定しました。dailyProcess: 毎日9時');
}

/**
 * 全データをリセット（テスト用）
 * 注意: 管理シートのデータを全削除します
 */
function resetSheetData() {
  var sheetId = PropertiesService.getScriptProperties().getProperty('SHEET_ID');
  if (!sheetId) {
    Logger.log('管理シートが見つかりません。');
    return;
  }

  var sheet = SpreadsheetApp.openById(sheetId).getSheetByName(CONFIG.sheet.sheetTab);
  var lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    sheet.deleteRows(2, lastRow - 1);
    Logger.log('管理シートのデータを削除しました。');
  }
}
