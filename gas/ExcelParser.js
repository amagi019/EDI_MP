/**
 * Excelファイル解析モジュール
 * パスワード解除済みのExcelファイルから情報を抽出する
 *
 * 抽出項目:
 * - プロジェクト名（B6セルから）
 * - 作業期間 開始日・終了日（B6セルの括弧内から）
 * - 作業者名（ファイル名の括弧内から）
 *
 * ★ Advanced Drive Service (Drive API v2) の有効化が必要
 *   GASエディタ → サービス → Drive API を追加
 */

/**
 * Excelファイルから必要な情報を抽出
 * @param {string} fileId - Google Drive上のExcelファイルID
 * @returns {Object} { projectName, startDate, endDate, workerName }
 */
function parseExcelFile(fileId, excelConfig) {
  var config = excelConfig || (CONFIG.partners[0] ? CONFIG.partners[0].excelConfig : {});
  var result = {
    projectName: null,
    startDate: null,
    endDate: null,
    totalHours: null,
  };

  var tempSheetId = null;

  try {
    // ExcelファイルをGoogle Sheetsに変換（一時的）
    var excelFile = DriveApp.getFileById(fileId);
    var blob = excelFile.getBlob();

    var resource = {
      title: '_temp_parse_' + Date.now(),
      mimeType: 'application/vnd.google-apps.spreadsheet',
    };

    var tempFile = Drive.Files.insert(resource, blob, { convert: true });
    tempSheetId = tempFile.id;

    // Google Sheetsとして開く
    var ss = SpreadsheetApp.openById(tempSheetId);
    var sheet = ss.getSheets()[0]; // 最初のシート

    // B6セルを読み取り
    var b6Value = sheet.getRange(config.projectCell || 'B6').getValue();
    Logger.log('B6セルの値: ' + b6Value);

    if (b6Value) {
      var parsed = parseProjectCell(String(b6Value));
      result.projectName = parsed.projectName;
      result.startDate = parsed.startDate;
      result.endDate = parsed.endDate;
    }

    // 合計時間を読み取り
    var hCell = config.totalHoursCell || 'H39';
    var hValue = sheet.getRange(hCell).getValue();
    if (hValue) {
      // 数値または '152:00' のような形式を想定
      result.totalHours = hValue;
    }

  } catch (e) {
    Logger.log('Excel解析エラー: ' + e.toString());
  } finally {
    // 一時ファイルを削除
    if (tempSheetId) {
      try {
        DriveApp.getFileById(tempSheetId).setTrashed(true);
        Logger.log('一時ファイル削除完了');
      } catch (e2) {
        Logger.log('一時ファイル削除エラー: ' + e2.toString());
      }
    }
  }

  return result;
}

/**
 * B6セルの内容を解析してプロジェクト名と期間を抽出
 *
 * 対応形式:
 *   "AMS水道マッピング（2026年2月1日～2026年2月28日）"
 *   "案件名：AMS水道マッピング（2026年2月1日～2026年2月28日）"
 *
 * @param {string} cellValue - B6セルの文字列
 * @returns {Object} { projectName, startDate, endDate }
 */
function parseProjectCell(cellValue) {
  var result = {
    projectName: null,
    startDate: null,
    endDate: null,
  };

  if (!cellValue) return result;

  // 「案件名：」プレフィックスを除去
  var value = cellValue.replace(/^案件名[：:]\s*/, '');

  // プロジェクト名を抽出（括弧の前の部分）
  // 全角括弧（）と半角括弧()の両方に対応
  var projectMatch = value.match(/^(.+?)\s*[（(]/);
  if (projectMatch) {
    result.projectName = projectMatch[1].trim();
  } else {
    // 括弧がない場合は全体をプロジェクト名とする
    result.projectName = value.trim();
  }

  // 日付を抽出（括弧内の「～」「~」「〜」で区切られた日付）
  var dateMatch = value.match(/[（(](\d{4}年\d{1,2}月\d{1,2}日)\s*[～~〜]\s*(\d{4}年\d{1,2}月\d{1,2}日)[）)]/);
  if (dateMatch) {
    // 年を除いた「月日」形式に変換（テンプレートに合わせる）
    result.startDate = removeYear_(dateMatch[1]);
    result.endDate = removeYear_(dateMatch[2]);
  }

  Logger.log('解析結果: プロジェクト=' + result.projectName
    + ', 開始=' + result.startDate
    + ', 終了=' + result.endDate);

  return result;
}

/**
 * ファイル名から作業者名を抽出
 * 例: "作業報告書（山田太郎）.xlsx" → "山田太郎"
 *
 * @param {string} filename - ファイル名
 * @returns {string|null}
 */
/**
 * ファイル名から作業者名を抽出
 * 例: "作業報告書（山田太郎）.xlsx" → "山田太郎"
 *     "前野_26.04.xlsm" → "前野"
 *
 * @param {string} filename - ファイル名
 * @param {string} supervisor - パートナーの責任者名（フォールバック用）
 * @returns {string|null}
 */
function extractWorkerNameFromFilename(filename, supervisor) {
  if (!filename) return null;

  // 1. 全角括弧（）と半角括弧()の両方に対応
  var match = filename.match(/[（(]([^）)]+)[）)]/);
  if (match) return match[1].trim();

  // 2. アンダースコアまたはドットで区切られた先頭部分を試行 (例: 前野_26.04.xlsm)
  var prefixMatch = filename.match(/^([^_.]+)[_.]/);
  if (prefixMatch) {
    var prefix = prefixMatch[1].trim();
    // 漢字が含まれているか、または責任者名の一部であれば採用
    if (prefix.match(/[\u4E00-\u9FFF]/) || (supervisor && supervisor.indexOf(prefix) !== -1)) {
      return prefix;
    }
  }

  // 3. 責任者名がファイル名に含まれているかチェック
  if (supervisor && filename.indexOf(supervisor) !== -1) {
    return supervisor;
  }

  return null;
}

/**
 * 日付文字列から年を除去
 * 例: "2026年2月1日" → "2月1日"
 * @param {string} dateStr
 * @returns {string}
 */
function removeYear_(dateStr) {
  return dateStr.replace(/\d{4}年/, '');
}
