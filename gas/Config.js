/**
 * 設定ファイル
 * パートナー情報、テンプレート、フォルダ設定を管理
 */

/**
 * メインの設定オブジェクト
 * ★ 初回セットアップ後、作業者名・プロジェクト名を記入してください
 */
const CONFIG = {
  // ========================================
  // 送信モード設定
  // ========================================
  // 'draft' = 下書き保存（確認後に手動送信）
  // 'auto'  = 自動送信
  sendMode: 'draft',

  // ========================================
  // パートナー設定
  // ========================================
  partners: [
    {
      id: 'granthope',
      name: 'グラントホープ',
      senderEmail: 'jimu@granthope.jp',
      // メール件名のパターン（部分一致）
      reportSubjectPattern: '請求書送付_',
      reportBodyKeyword: '勤務表を送付させて頂きます',
      passwordSubjectPattern: 'パスワード送付_',
      supervisor: '前野謙',
      // Excel解析設定（イービジネスの作業報告書フォーマット）
      // ※ クライアント企業によってフォーマットが異なる場合はここを変更
      excelConfig: {
        projectCell: 'B6',  // プロジェクト名＋期間が記載されたセル
        totalHoursCell: 'H39', // 合計稼働時間が記載されたセル
      },
    },
    // 4月以降、2社目を追加する場合はここに追記
    // {
    //   id: 'partner2',
    //   name: '会社名',
    //   senderEmail: 'xxx@example.com',
    //   reportSubjectPattern: '請求書送付_',
    //   reportBodyKeyword: '勤務表を送付させて頂きます',
    //   passwordSubjectPattern: 'パスワード送付_',
    //   supervisor: '前野謙',
    //   excelConfig: {
    //     projectCell: 'B6',  // ← フォーマットに応じて変更
    //   },
    // },
  ],

  // ========================================
  // 転送先設定
  // ========================================
  recipient: {
    name: '前野様',
    fullName: '前野俊介',
    company: '株式会社イービジネス',
    email: 'maeno.shunsuke@e-business.co.jp',
  },

  // ========================================
  // 送信者情報（署名用）
  // ========================================
  sender: {
    company: '有限会社　MacPlanning',
    name: '吉川　裕',
    email: 'y.yoshikawa@macplanning.com',
    tel: '090-3043-0477',
  },

  // ========================================
  // Google Drive フォルダ名
  // ========================================
  folders: {
    root: '作業報告書',
    incoming: '受信',
    outgoing: '送信用',
    archived: '送信済み',
  },

  // ========================================
  // Google Sheets 管理シート名
  // ========================================
  sheet: {
    name: '稼働報告書管理',
    sheetTab: '管理台帳',
  },

  // ========================================
  // メール検索の対象期間（月初から何日間）
  // ========================================
  searchDaysFromMonthStart: 15,

  // ========================================
  // 処理済みラベル名
  // ========================================
  processedLabel: '稼働報告_処理済み',
};

/**
 * メールテンプレートを生成
 * @param {Object} params - テンプレートパラメータ
 * @param {string} params.month - 対象月（例: '3'）
 * @param {string} params.workerName - 作業者名
 * @param {string} params.projectName - プロジェクト名
 * @param {string} params.periodStart - 作業期間開始日（例: '3月1日'）
 * @param {string} params.periodEnd - 作業期間終了日（例: '3月31日'）
 * @param {string} params.supervisor - 作業責任者名
 * @returns {Object} { subject, body }
 */
function buildEmailTemplate(params) {
  const subject = `${params.month}月分 作業報告書（${params.workerName}）`;

  const body = `${CONFIG.recipient.company} ${CONFIG.recipient.name}

いつもお世話になっております。
${CONFIG.sender.company.replace('　', '')}の${CONFIG.sender.name.replace('　', '')}です。

${params.month}月分の${params.workerName}の作業報告書を送付いたします。
ご確認をお願いいたします。


業務名：${params.projectName}
作業期間：${params.periodStart} ～ ${params.periodEnd}
作業責任者：${params.supervisor}

引き続きよろしくお願いいたします。

*******************************************
${CONFIG.sender.company}
${CONFIG.sender.name}
Mail：${CONFIG.sender.email}
TEL：${CONFIG.sender.tel}
*******************************************`;

  return { subject, body };
}
