/**
 * メール送信モジュール
 * 管理シートのステータスが「送信準備完了」の行を処理し、
 * メールの下書き作成または自動送信を行う
 */

/**
 * 送信待ちの報告書を処理
 * ステータスが「送信準備完了」の行を検出し、メールを作成する
 */
function sendPendingReports() {
  if (!isSetupDone()) {
    Logger.log('セットアップが完了していません。');
    return;
  }

  const props = PropertiesService.getScriptProperties();
  const ss = SpreadsheetApp.openById(props.getProperty('SHEET_ID'));
  const sheet = ss.getSheetByName(CONFIG.sheet.sheetTab);
  const archivedFolderId = props.getProperty('ARCHIVED_FOLDER_ID');
  const archivedFolder = DriveApp.getFolderById(archivedFolderId);

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    Logger.log('処理対象のデータがありません。');
    return;
  }

  // 全データ取得
  const data = sheet.getRange(2, 1, lastRow - 1, 12).getValues();

  data.forEach(function(row, index) {
    const rowNum = index + 2;
    const status = row[8]; // ステータス（I列）

    if (status !== '送信準備完了') {
      return;
    }

    Logger.log('送信処理開始: 行 ' + rowNum);

    try {
      const targetMonth = row[0];      // 対象月
      const partnerName = row[1];      // パートナー名
      const workerName = row[2];       // 作業者名
      const outgoingFileUrl = row[7];  // 送信用ファイルリンク

      // パートナー設定を取得
      const partner = findPartnerByName_(partnerName);
      if (!partner) {
        Logger.log('パートナー設定が見つかりません: ' + partnerName);
        sheet.getRange(rowNum, 9).setValue('エラー');
        return;
      }

      // 送信用ファイルを取得
      if (!outgoingFileUrl) {
        Logger.log('送信用ファイルリンクが空です: 行 ' + rowNum);
        sheet.getRange(rowNum, 9).setValue('エラー');
        return;
      }

      const fileId = extractFileIdFromUrl_(outgoingFileUrl);
      if (!fileId) {
        Logger.log('ファイルIDを取得できません: ' + outgoingFileUrl);
        sheet.getRange(rowNum, 9).setValue('エラー');
        return;
      }

      const file = DriveApp.getFileById(fileId);
      const fileBlob = file.getBlob();

      // 月の数字を抽出
      var monthMatch = targetMonth.match(/(\d{1,2})月/);
      var monthNum = monthMatch ? monthMatch[1] : '';

      // Excelファイルからプロジェクト名・作業期間を自動抽出
      var excelData = parseExcelFile(fileId);
      Logger.log('Excel解析結果: ' + JSON.stringify(excelData));

      // 作業期間（Excel抽出 → フォールバック: 月から計算）
      var periodStart, periodEnd;
      if (excelData.startDate && excelData.endDate) {
        periodStart = excelData.startDate;
        periodEnd = excelData.endDate;
      } else {
        var period = calculateWorkPeriod_(targetMonth);
        periodStart = period.start;
        periodEnd = period.end;
      }

      // プロジェクト名（Excel抽出 → フォールバック: '要確認'）
      var projectName = excelData.projectName || '（要確認）';

      // 管理シートにプロジェクト名・作業期間を記録
      sheet.getRange(rowNum, 13).setValue(projectName);
      sheet.getRange(rowNum, 14).setValue(periodStart + ' ～ ' + periodEnd);

      // テンプレート生成
      var emailContent = buildEmailTemplate({
        month: monthNum,
        workerName: workerName,
        projectName: projectName,
        periodStart: periodStart,
        periodEnd: periodEnd,
        supervisor: partner.supervisor,
      });

      if (CONFIG.sendMode === 'draft') {
        // 下書き作成
        createDraft_(emailContent, fileBlob);
        Logger.log('下書き作成完了: ' + emailContent.subject);
      } else {
        // 自動送信
        sendEmail_(emailContent, fileBlob);
        Logger.log('メール送信完了: ' + emailContent.subject);
      }

      // ステータス更新
      sheet.getRange(rowNum, 9).setValue('送信済み');
      sheet.getRange(rowNum, 10).setValue(
        Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy/MM/dd HH:mm')
      );

      // ファイルを送信済みフォルダに移動
      archivedFolder.addFile(file);
      var parents = file.getParents();
      while (parents.hasNext()) {
        var parent = parents.next();
        if (parent.getId() !== archivedFolder.getId()) {
          parent.removeFile(file);
        }
      }

      Logger.log('処理完了: 行 ' + rowNum);

    } catch (e) {
      Logger.log('エラー（行 ' + rowNum + '）: ' + e.toString());
      sheet.getRange(rowNum, 9).setValue('エラー');
    }
  });

  Logger.log('送信処理完了');
}

/**
 * メールの下書きを作成
 * @param {Object} emailContent - { subject, body }
 * @param {Blob} fileBlob - 添付ファイル
 */
function createDraft_(emailContent, fileBlob) {
  GmailApp.createDraft(
    CONFIG.recipient.email,
    emailContent.subject,
    emailContent.body,
    {
      attachments: [fileBlob],
      name: CONFIG.sender.name.replace('　', ' '),
    }
  );
}

/**
 * メールを送信
 * @param {Object} emailContent - { subject, body }
 * @param {Blob} fileBlob - 添付ファイル
 */
function sendEmail_(emailContent, fileBlob) {
  GmailApp.sendEmail(
    CONFIG.recipient.email,
    emailContent.subject,
    emailContent.body,
    {
      attachments: [fileBlob],
      name: CONFIG.sender.name.replace('　', ' '),
    }
  );
}

/**
 * パートナー名から設定を検索
 * @param {string} name
 * @returns {Object|null}
 */
function findPartnerByName_(name) {
  for (var i = 0; i < CONFIG.partners.length; i++) {
    if (CONFIG.partners[i].name === name) {
      return CONFIG.partners[i];
    }
  }
  return null;
}

/**
 * Google DriveのURLからファイルIDを抽出
 * @param {string} url
 * @returns {string|null}
 */
function extractFileIdFromUrl_(url) {
  // パターン1: https://drive.google.com/file/d/FILE_ID/...
  var match1 = url.match(/\/d\/([a-zA-Z0-9_-]+)/);
  if (match1) return match1[1];

  // パターン2: https://drive.google.com/open?id=FILE_ID
  var match2 = url.match(/[?&]id=([a-zA-Z0-9_-]+)/);
  if (match2) return match2[1];

  // パターン3: ファイルIDそのもの
  if (url.match(/^[a-zA-Z0-9_-]+$/)) return url;

  return null;
}

/**
 * 対象月から作業期間を計算
 * @param {string} targetMonth - 例: '2026年3月'
 * @returns {Object} { start, end }
 */
function calculateWorkPeriod_(targetMonth) {
  var match = targetMonth.match(/(\d{4})年(\d{1,2})月/);
  if (!match) {
    return { start: '不明', end: '不明' };
  }

  var year = parseInt(match[1], 10);
  var month = parseInt(match[2], 10);

  // 月末日を計算
  var lastDay = new Date(year, month, 0).getDate();

  return {
    start: month + '月1日',
    end: month + '月' + lastDay + '日',
  };
}
