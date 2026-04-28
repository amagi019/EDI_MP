/**
 * 初回セットアップ
 * Google Drive フォルダとスプレッドシートを自動作成する
 * 
 * 使い方: GASエディタで initialSetup() を手動実行
 */

/**
 * 初回セットアップのメイン関数
 */
function initialSetup() {
  Logger.log('=== 初回セットアップ開始 ===');

  // 1. フォルダ作成
  const folders = createFolders_();
  Logger.log('フォルダ作成完了');

  // 2. スプレッドシート作成
  const spreadsheet = createManagementSheet_(folders);
  Logger.log('管理シート作成完了: ' + spreadsheet.getUrl());

  // 3. フォルダID・シートIDをプロパティに保存
  saveProperties_(folders, spreadsheet);
  Logger.log('プロパティ保存完了');

  // 4. 処理済みラベル作成
  createProcessedLabel_();
  Logger.log('Gmailラベル作成完了');

  // 5. トリガー設定
  setupTriggers_();
  Logger.log('トリガー設定完了');

  Logger.log('=== 初回セットアップ完了 ===');
  Logger.log('管理シート URL: ' + spreadsheet.getUrl());
  Logger.log('ルートフォルダ URL: https://drive.google.com/drive/folders/' + folders.root.getId());

  Logger.log('★ セットアップ完了 ★');
  Logger.log('管理シート: ' + spreadsheet.getUrl());
  Logger.log('Driveフォルダ: https://drive.google.com/drive/folders/' + folders.root.getId());
}

/**
 * Google Drive にフォルダ構成を作成
 * @returns {Object} { root, incoming, outgoing, archived }
 */
function createFolders_() {
  const rootFolder = getOrCreateFolder_(DriveApp.getRootFolder(), CONFIG.folders.root);
  const incomingFolder = getOrCreateFolder_(rootFolder, CONFIG.folders.incoming);
  const outgoingFolder = getOrCreateFolder_(rootFolder, CONFIG.folders.outgoing);
  const archivedFolder = getOrCreateFolder_(rootFolder, CONFIG.folders.archived);

  return {
    root: rootFolder,
    incoming: incomingFolder,
    outgoing: outgoingFolder,
    archived: archivedFolder,
  };
}

/**
 * フォルダが存在しなければ作成
 * @param {DriveApp.Folder} parentFolder - 親フォルダ
 * @param {string} folderName - フォルダ名
 * @returns {DriveApp.Folder}
 */
function getOrCreateFolder_(parentFolder, folderName) {
  const folders = parentFolder.getFoldersByName(folderName);
  if (folders.hasNext()) {
    return folders.next();
  }
  return parentFolder.createFolder(folderName);
}

/**
 * 管理用スプレッドシートを作成
 * @param {Object} folders - フォルダオブジェクト
 * @returns {SpreadsheetApp.Spreadsheet}
 */
function createManagementSheet_(folders) {
  // 既存チェック
  const existingId = PropertiesService.getScriptProperties().getProperty('SHEET_ID');
  if (existingId) {
    try {
      return SpreadsheetApp.openById(existingId);
    } catch (e) {
      Logger.log('既存シートが見つかりません。新規作成します。');
    }
  }

  const ss = SpreadsheetApp.create(CONFIG.sheet.name);

  // ルートフォルダに移動
  const file = DriveApp.getFileById(ss.getId());
  folders.root.addFile(file);
  DriveApp.getRootFolder().removeFile(file);

  // シートのヘッダー設定
  const sheet = ss.getActiveSheet();
  sheet.setName(CONFIG.sheet.sheetTab);

  const headers = [
    '対象月',
    'パートナー名',
    '作業者名',
    'メール受信日',
    'パスワード',
    '元ファイル名',
    '元ファイルリンク',
    '送信用ファイルリンク',
    'ステータス',
    '送信日',
    '報告書メッセージID',
    'パスワードメッセージID',
    'プロジェクト名',
    '作業期間',
    '稼働時間',
  ];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);

  // ヘッダー書式設定
  const headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setFontWeight('bold');
  headerRange.setBackground('#4a86e8');
  headerRange.setFontColor('#ffffff');

  // カラム幅設定
  sheet.setColumnWidth(1, 100);  // 対象月
  sheet.setColumnWidth(2, 140);  // パートナー名
  sheet.setColumnWidth(3, 100);  // 作業者名
  sheet.setColumnWidth(4, 120);  // メール受信日
  sheet.setColumnWidth(5, 120);  // パスワード
  sheet.setColumnWidth(6, 200);  // 元ファイル名
  sheet.setColumnWidth(7, 200);  // 元ファイルリンク
  sheet.setColumnWidth(8, 200);  // 送信用ファイルリンク
  sheet.setColumnWidth(9, 140);  // ステータス
  sheet.setColumnWidth(10, 120); // 送信日
  sheet.setColumnWidth(11, 200); // 報告書メッセージID
  sheet.setColumnWidth(12, 200); // パスワードメッセージID
  sheet.setColumnWidth(13, 200); // プロジェクト名
  sheet.setColumnWidth(14, 200); // 作業期間
  sheet.setColumnWidth(15, 100); // 稼働時間

  // ステータスのデータ入力規則を設定
  const statusRule = SpreadsheetApp.newDataValidation()
    .requireValueInList(['パスワード解除待ち', '送信準備完了', '送信済み', 'エラー'], true)
    .setAllowInvalid(false)
    .build();
  sheet.getRange(2, 9, 100, 1).setDataValidation(statusRule);

  // 行の固定
  sheet.setFrozenRows(1);

  return ss;
}

/**
 * フォルダIDとシートIDをスクリプトプロパティに保存
 */
function saveProperties_(folders, spreadsheet) {
  const props = PropertiesService.getScriptProperties();
  props.setProperties({
    'ROOT_FOLDER_ID': folders.root.getId(),
    'INCOMING_FOLDER_ID': folders.incoming.getId(),
    'OUTGOING_FOLDER_ID': folders.outgoing.getId(),
    'ARCHIVED_FOLDER_ID': folders.archived.getId(),
    'SHEET_ID': spreadsheet.getId(),
  });
}

/**
 * Gmail処理済みラベルを作成
 */
function createProcessedLabel_() {
  const label = GmailApp.getUserLabelByName(CONFIG.processedLabel);
  if (!label) {
    GmailApp.createLabel(CONFIG.processedLabel);
  }
}

/**
 * 時間ベースのトリガーを設定
 * 毎日午前9時に実行
 */
function setupTriggers_() {
  // 既存トリガーを削除
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(function(trigger) {
    if (trigger.getHandlerFunction() === 'dailyProcess') {
      ScriptApp.deleteTrigger(trigger);
    }
  });

  // 新規トリガー作成（毎日午前9時〜10時）
  ScriptApp.newTrigger('dailyProcess')
    .timeBased()
    .everyDays(1)
    .atHour(9)
    .create();

  Logger.log('トリガー設定: dailyProcess を毎日9時に実行');
}

/**
 * セットアップ状態を確認
 * @returns {boolean} セットアップ済みかどうか
 */
function isSetupDone() {
  const props = PropertiesService.getScriptProperties();
  return props.getProperty('SHEET_ID') !== null
      && props.getProperty('INCOMING_FOLDER_ID') !== null;
}
