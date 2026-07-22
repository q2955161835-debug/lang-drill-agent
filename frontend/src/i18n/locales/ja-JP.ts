// 日本語 UI メッセージカタログ。
// 中国語ソースカタログと同じ MessageCatalog 型を満たす必要があります。

import type { MessageCatalog } from "../types";

export const jaJP: MessageCatalog = {
  // アプリシェルとナビゲーション
  "app.title": "Lang Drill Agent",
  "app.settings": "設定",
  "app.settings.open": "設定を開く",
  "app.newChat": "新しいチャット",
  "app.send": "送信",
  "app.cancel": "キャンセル",
  "app.save": "保存",
  "app.confirm": "確認",
  "app.close": "閉じる",
  "app.retry": "再試行",
  "app.restoreDefaults": "デフォルトに戻す",
  "app.todayLearning": "今日の学習",
  "app.longTermPanel": "長期学習記録",
  "app.longTermPanelTitle": "長期学習記録総合パネル",

  // 設定タブ
  "settings.title": "設定",
  "settings.tab.model": "モデル",
  "settings.tab.exam": "試験",
  "settings.tab.syllabus": "シラバス",
  "settings.tab.tokens": "トークン",
  "settings.tab.data": "データ",
  "settings.tab.knowledge": "ナレッジベース",
  "settings.tab.memory": "メモリ",
  "settings.tab.creative": "クリエイティブモード",
  "settings.tab.pastPapers": "過去問",
  "settings.tab.permissions": "権限",
  "settings.tab.skills": "拡張スキル",
  "settings.tab.study": "学習",
  "settings.tab.appearance": "外観",
  "settings.tab.language": "言語",

  // チャットエリア
  "chat.placeholder": "今日の学習内容、解答、または学習リクエストを入力",
  "chat.sending": "送信中...",
  "chat.thinking": "モデルが思考中",
  "chat.judging": "モデルが採点中",
  "chat.recognizingImage": "モデルが画像を認識中",
  "chat.confirmingIntent": "練習意図を確認中",
  "chat.noSession": "セッションなし",
  "chat.emptyToday": "今日の入力待ち",
  "chat.imageVision": "モデル視覚",
  "chat.imageMineru": "MinerU解析",
  "chat.imageHintVision": "ドロップした画像は現在のモデルに送信されます",
  "chat.imageHintMineru": "ドロップした画像はMinerU/ローカルOCRでテキスト抽出されます",

  // 長期パネル統計
  "stats.examCountdown": "試験カウントダウン",
  "stats.examCountdownDetail": "試験時間からリアルタイム計算",
  "stats.examCountdownEmpty": "設定で試験時間を追加",
  "stats.currentExam": "現在の試験",
  "stats.totalTokens": "累計トークン",
  "stats.questionsCompleted": "問題完了",
  "stats.wordsMastered": "単語習得",
  "stats.overallAccuracy": "全体正答率",

  // 学習メモリ
  "learningMemory.kicker": "Learning Memory（学習メモリ）",

  // 試験ステータス
  "exam.deadlineNotSet": "未設定",
  "exam.deadlineReached": "試験時間に到達",

  // モデル関連
  "model.unidentified": "未識別モデル名",
  "model.sameAsModelName": "モデル名と同じ",
  "model.visionSupported": "対応",
  "model.visionTextOnly": "テキストモデル",
  "model.provider": "モデルプロバイダー",
  "model.name": "モデル",
  "model.confirmFillSettings": "設定に反映",

  // ブランチ
  "branch.defaultPrompt": "現在のメインセッションの全内容に基づき、フォローアップ可能な学習ブランチを整理してください。",
  "branch.referenceMessage": "このメッセージを引用",
  "branch.needMainMessage": "先にメインセッションのメッセージを送信してください",

  // 権限プロファイル（クリエイティブモード）
  "creative.title": "クリエイティブモード",
  "creative.enable": "クリエイティブモードを有効化",
  "creative.runtimeReady": "ランタイム準備完了",
  "creative.runtimeNotReady": "ランタイム未準備",
  "creative.repair": "ワンクリック修復",
  "creative.repairing": "修復中...",
  "creative.openLog": "ログディレクトリを開く",
  "creative.failureCode": "失敗コード",
  "creative.version": "バージョン",
  "creative.attemptedSteps": "試行ステップ",
  "creative.logPath": "ログパス",
  "creative.manualInstall": "手動インストールコマンド",
  "creative.profile.requestApproval": "都度承認",
  "creative.profile.smartApproval": "スマート承認",
  "creative.profile.fullAccess": "フルアクセス",
  "creative.profile.custom": "カスタム",
  "creative.hardBlocks.title": "致命的ハードブロック（全プロファイルで上書き不可）",

  // エラーとステータス
  "error.dataPathRefresh": "データベース統計の更新に失敗",
  "error.generic": "操作に失敗しました。再試行してください",
  "error.loading": "読み込み中...",
  "error.saveFailed": "保存に失敗",

  // 言語設定
  "language.label": "インターフェース言語",
  "language.description": "UI文案のみに影響し、モデル返信、問題、カスタム指示の言語には影響しません。",
  "language.followSystem": "システムに従う",
};
