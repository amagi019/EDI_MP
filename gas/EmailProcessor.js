/**
 * メール検索・処理モジュール
 * Gmailから報告書メールとパスワードメールを検索し、マッチングする
 */

/**
 * 受信メールを処理するメイン関数
 * 1. 各パートナーの報告書メールを検索
 * 2. 対応するパスワードメールを検索
 * 3. 添付ファイルをDriveに保存
 * 4. パスワードを抽出
 * 5. 管理シートに記録
 */
function processIncomingEmails() {
  if (!isSetupDone()) {
    Logger.log('セットアップが完了していません。initialSetup() を先に実行してください。');
    return;
  }

  const props = PropertiesService.getScriptProperties();
  const sheet = SpreadsheetApp.openById(props.getProperty('SHEET_ID'))
    .getSheetByName(CONFIG.sheet.sheetTab);
  const incomingFolderId = props.getProperty('INCOMING_FOLDER_ID');
  const incomingFolder = DriveApp.getFolderById(incomingFolderId);
  const processedLabel = GmailApp.getUserLabelByName(CONFIG.processedLabel)
    || GmailApp.createLabel(CONFIG.processedLabel);

  // 処理済みメッセージIDを取得
  const processedIds = getProcessedMessageIds_(sheet);

  CONFIG.partners.forEach(function(partner) {
    Logger.log('パートナー処理中: ' + partner.name);

    // 報告書メールを検索
    const reportThreads = searchReportEmails_(partner);
    Logger.log('報告書メール: ' + reportThreads.length + '件');

    reportThreads.forEach(function(thread) {
      const messages = thread.getMessages();
      messages.forEach(function(message) {
        const messageId = message.getId();

        // 処理済みチェック
        if (processedIds.has(messageId)) {
          Logger.log('スキップ（処理済み）: ' + message.getSubject());
          return;
        }

        // 報告書メールか確認（件名＋本文の二重チェック）
        if (!isReportEmail_(message, partner)) {
          return;
        }

        Logger.log('報告書メール検出: ' + message.getSubject());

        // 月を特定
        const month = extractMonth_(message.getSubject());
        if (!month) {
          Logger.log('月の特定ができませんでした: ' + message.getSubject());
          return;
        }
        Logger.log('対象月: ' + month + '月');

        // 対応するパスワードメールを検索
        const passwordInfo = findPasswordEmail_(partner, month);
        if (!passwordInfo) {
          Logger.log('パスワードメールが見つかりません（' + month + '月分）');
          return;
        }
        Logger.log('パスワード取得成功');

        // 添付ファイルを保存
        const attachments = message.getAttachments();
        Logger.log('添付ファイル数: ' + attachments.length);
        attachments.forEach(function(att) {
          Logger.log('  添付: ' + att.getName() + ' (' + att.getContentType() + ')');
        });

        const excelAttachments = attachments.filter(function(att) {
          return att.getName().match(/\.(xlsx?|xls|xlsm)$/i)
              || att.getContentType().indexOf('spreadsheet') !== -1
              || att.getContentType().indexOf('excel') !== -1;
        });

        if (excelAttachments.length === 0) {
          Logger.log('Excelファイルの添付がありません');
          return;
        }

        const attachment = excelAttachments[0];
        const savedFile = incomingFolder.createFile(attachment);
        Logger.log('ファイル保存: ' + savedFile.getName());

        // ファイルから情報を抽出試行（パスワードなしの場合）
        var workerName = extractWorkerNameFromFilename(attachment.getName(), partner.supervisor);
        var totalHours = '';
        var projectName = '';
        var workPeriod = '';
        var excelParsed = false;
        
        try {
          var excelData = parseExcelFile(savedFile.getId(), partner.excelConfig);
          if (excelData.projectName || excelData.totalHours) {
            // 解析成功（パスワードなし）
            excelParsed = true;
            projectName = excelData.projectName || '';
            if (excelData.startDate && excelData.endDate) {
              workPeriod = excelData.startDate + ' ～ ' + excelData.endDate;
            }
            totalHours = excelData.totalHours || '';
            Logger.log('Excel解析成功: 作業者=' + workerName + ', 時間=' + totalHours);
          }
        } catch (e) {
          Logger.log('Excel解析スキップ（パスワード保護の可能性）: ' + e.toString());
        }

        // ステータス判定
        var status = excelParsed ? '解析完了' : 'パスワード解除待ち';

        // 管理シートに記録
        const now = new Date();
        const targetMonth = buildTargetMonthLabel_(month, message.getDate());

        sheet.appendRow([
          targetMonth,                                        // 1:対象月
          partner.name,                                       // 2:パートナー名
          workerName || '（未取得）',                           // 3:作業者名
          Utilities.formatDate(message.getDate(), 'Asia/Tokyo', 'yyyy/MM/dd HH:mm'), // 4:受信日
          passwordInfo.password,                              // 5:パスワード
          savedFile.getName(),                                // 6:元ファイル名
          savedFile.getUrl(),                                 // 7:元ファイルリンク
          '',                                                 // 8:送信用ファイルリンク
          status,                                             // 9:ステータス
          '',                                                 // 10:送信日
          messageId,                                          // 11:報告書メッセージID
          passwordInfo.messageId,                             // 12:パスワードメッセージID
          projectName,                                        // 13:プロジェクト名
          workPeriod,                                         // 14:作業期間
          totalHours,                                         // 15:稼働時間
        ]);

        // 処理済みラベルを付与
        thread.addLabel(processedLabel);

        Logger.log('管理シートに記録完了: ' + partner.name + ' ' + targetMonth);
      });
    });
  });

  Logger.log('受信メール処理完了');
}

/**
 * 報告書メールを検索
 * @param {Object} partner - パートナー設定
 * @returns {GmailThread[]}
 */
function searchReportEmails_(partner) {
  // 検索クエリ: 送信元 + 件名パターン + 添付あり + ラベルなし（未処理）
  const query = 'from:' + partner.senderEmail
    + ' subject:(' + partner.reportSubjectPattern + ')'
    + ' has:attachment'
    + ' -label:' + CONFIG.processedLabel.replace(/\s/g, '-')
    + ' newer_than:' + CONFIG.searchDaysFromMonthStart + 'd';

  Logger.log('検索クエリ: ' + query);
  return GmailApp.search(query);
}

/**
 * メッセージが報告書メールかどうかを判定
 * @param {GmailMessage} message - メッセージ
 * @param {Object} partner - パートナー設定
 * @returns {boolean}
 */
function isReportEmail_(message, partner) {
  const subject = message.getSubject();
  const body = message.getPlainBody();

  // 件名チェック
  if (subject.indexOf(partner.reportSubjectPattern) === -1) {
    return false;
  }

  // 本文キーワードチェック
  if (body.indexOf(partner.reportBodyKeyword) === -1) {
    return false;
  }

  return true;
}

/**
 * パスワードメールを検索し、パスワードを抽出
 * @param {Object} partner - パートナー設定
 * @param {string} month - 対象月（例: '3'）
 * @returns {Object|null} { password, messageId } or null
 */
function findPasswordEmail_(partner, month) {
  const query = 'from:' + partner.senderEmail
    + ' subject:(' + partner.passwordSubjectPattern + month + '月)';

  Logger.log('パスワード検索クエリ: ' + query);
  const threads = GmailApp.search(query);

  if (threads.length === 0) {
    // 月の表記揺れに対応（例: 03月 vs 3月）
    const altQuery = 'from:' + partner.senderEmail
      + ' subject:(' + partner.passwordSubjectPattern + ')';
    const altThreads = GmailApp.search(altQuery);

    for (var i = 0; i < altThreads.length; i++) {
      var messages = altThreads[i].getMessages();
      for (var j = 0; j < messages.length; j++) {
        if (messages[j].getSubject().indexOf(month + '月') !== -1) {
          var password = extractPassword_(messages[j]);
          if (password) {
            return { password: password, messageId: messages[j].getId() };
          }
        }
      }
    }
    return null;
  }

  // 最新のスレッドからパスワードを抽出
  const msgs = threads[0].getMessages();
  const latestMessage = msgs[msgs.length - 1];
  const foundPassword = extractPassword_(latestMessage);

  if (foundPassword) {
    return { password: foundPassword, messageId: latestMessage.getId() };
  }

  return null;
}

/**
 * メール本文からパスワードを抽出
 * よくあるパターンに対応:
 *   パスワード: xxxx
 *   パスワード：xxxx
 *   PW: xxxx
 *   Password: xxxx
 * @param {GmailMessage} message - メッセージ
 * @returns {string|null}
 */
function extractPassword_(message) {
  const body = message.getPlainBody();

  // パターン1: 「パスワード：xxxx」「パスワード: xxxx」（同一行）
  var match = body.match(/パスワード[：:\s]+([^\s\r\n]+)/);
  if (match) {
    Logger.log('パスワード抽出成功（パターン1）: ' + match[1]);
    return match[1].trim();
  }

  // パターン2: 「パスワードは下記...」の次の行に値がある
  // 行ごとに分割して、「パスワード」を含む行の次の非空行を取得
  var lines = body.split(/\r?\n/);
  for (var i = 0; i < lines.length - 1; i++) {
    if (lines[i].indexOf('パスワード') !== -1 || lines[i].indexOf('下記') !== -1) {
      // 次の非空行を探す
      for (var j = i + 1; j < lines.length; j++) {
        var nextLine = lines[j].trim();
        if (nextLine.length > 0 && nextLine.length <= 30) {
          Logger.log('パスワード抽出成功（パターン2）: ' + nextLine);
          return nextLine;
        }
      }
    }
  }

  // パターン3: 半角カナ
  match = body.match(/ﾊﾟｽﾜｰﾄﾞ[：:\s]+([^\s\r\n]+)/);
  if (match) return match[1].trim();

  // パターン4: PW / Password
  match = body.match(/PW[：:\s]+([^\s\r\n]+)/i);
  if (match) return match[1].trim();

  match = body.match(/Password[：:\s]+([^\s\r\n]+)/i);
  if (match) return match[1].trim();

  Logger.log('パスワードを抽出できませんでした。メール本文:\n' + body.substring(0, 500));
  return null;
}

/**
 * メール件名から月を抽出
 * 例: "請求書送付_3月分" → "3"
 *     "請求書送付_03月分" → "3"
 *     "請求書送付_2026年3月分" → "3"
 * @param {string} subject - メール件名
 * @returns {string|null}
 */
function extractMonth_(subject) {
  // パターン: 数字 + 月
  var match = subject.match(/(\d{1,2})月/);
  if (match) {
    return String(parseInt(match[1], 10)); // 先頭ゼロを除去
  }
  return null;
}

/**
 * 対象月のラベルを生成
 * @param {string} month - 月（例: '3'）
 * @param {Date} emailDate - メールの日付
 * @returns {string} 例: '2026年3月'
 */
function buildTargetMonthLabel_(month, emailDate) {
  var year = emailDate.getFullYear();
  var emailMonth = emailDate.getMonth() + 1;

  // メールの月と対象月が異なる場合（例: 4月に届いた3月分の報告書）
  // 対象月がメールの月より大きい場合は前年の可能性
  var targetMonth = parseInt(month, 10);
  if (targetMonth > emailMonth) {
    year = year - 1;
  }

  return year + '年' + targetMonth + '月';
}

/**
 * 管理シートから処理済みメッセージIDを取得
 * @param {SpreadsheetApp.Sheet} sheet
 * @returns {Set}
 */
function getProcessedMessageIds_(sheet) {
  var ids = new Set();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return ids;

  // 報告書メッセージID（K列 = 11列目）
  var range = sheet.getRange(2, 11, lastRow - 1, 1).getValues();
  range.forEach(function(row) {
    if (row[0]) ids.add(row[0]);
  });

  return ids;
}
