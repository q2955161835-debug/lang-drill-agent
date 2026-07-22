// English (US) UI message catalog.
// Must satisfy the same MessageCatalog type as the Chinese source catalog.

import type { MessageCatalog } from "../types";

export const enUS: MessageCatalog = {
  // App shell and navigation
  "app.title": "Lang Drill Agent",
  "app.settings": "Settings",
  "app.settings.open": "Open settings",
  "app.newChat": "New chat",
  "app.send": "Send",
  "app.cancel": "Cancel",
  "app.save": "Save",
  "app.confirm": "Confirm",
  "app.close": "Close",
  "app.retry": "Retry",
  "app.restoreDefaults": "Restore defaults",
  "app.todayLearning": "Today's learning",
  "app.longTermPanel": "Long-term learning record",
  "app.longTermPanelTitle": "Long-term learning record overview",

  // Settings tabs
  "settings.title": "Settings",
  "settings.tab.model": "Model",
  "settings.tab.exam": "Exam",
  "settings.tab.syllabus": "Syllabus",
  "settings.tab.tokens": "Tokens",
  "settings.tab.data": "Data",
  "settings.tab.knowledge": "Knowledge base",
  "settings.tab.memory": "Memory",
  "settings.tab.creative": "Creative mode",
  "settings.tab.pastPapers": "Past papers",
  "settings.tab.permissions": "Permissions",
  "settings.tab.skills": "Extended skills",
  "settings.tab.study": "Study",
  "settings.tab.appearance": "Appearance",
  "settings.tab.language": "Language",

  // Chat area
  "chat.placeholder": "Enter today's learning content, answers or any study request",
  "chat.sending": "Sending...",
  "chat.thinking": "Model is thinking",
  "chat.judging": "Model is judging",
  "chat.recognizingImage": "Model is recognizing image",
  "chat.confirmingIntent": "Confirming practice intent",
  "chat.noSession": "No session yet",
  "chat.emptyToday": "Waiting for today's input",
  "chat.imageVision": "Model vision",
  "chat.imageMineru": "MinerU parsing",
  "chat.imageHintVision": "Dropped images are sent to the current model",
  "chat.imageHintMineru": "Dropped images are first parsed by MinerU/local OCR to extract text",

  // Long-term panel stats
  "stats.examCountdown": "Exam countdown",
  "stats.examCountdownDetail": "Calculated from the exam time",
  "stats.examCountdownEmpty": "Add an exam time in settings",
  "stats.currentExam": "Current exam",
  "stats.totalTokens": "Total tokens",
  "stats.questionsCompleted": "Questions completed",
  "stats.wordsMastered": "Words mastered",
  "stats.overallAccuracy": "Overall accuracy",

  // Learning memory
  "learningMemory.kicker": "Learning Memory",

  // Exam status
  "exam.deadlineNotSet": "Not set",
  "exam.deadlineReached": "Exam time reached",

  // Model related
  "model.unidentified": "Unidentified model name",
  "model.sameAsModelName": "Same as model name",
  "model.visionSupported": "Supported",
  "model.visionTextOnly": "Text model",
  "model.provider": "Model provider",
  "model.name": "Model",
  "model.confirmFillSettings": "Confirm and fill settings",

  // Branch
  "branch.defaultPrompt": "Based on all content in the current main session, organize study branches that can be followed up.",
  "branch.referenceMessage": "Reference this message",
  "branch.needMainMessage": "Send a main session message first",

  // Permission profiles (creative mode)
  "creative.title": "Creative mode",
  "creative.enable": "Enable creative mode",
  "creative.runtimeReady": "Runtime ready",
  "creative.runtimeNotReady": "Runtime not ready",
  "creative.repair": "One-click repair",
  "creative.repairing": "Repairing...",
  "creative.openLog": "Open log directory",
  "creative.failureCode": "Failure code",
  "creative.version": "Version",
  "creative.attemptedSteps": "Attempted steps",
  "creative.logPath": "Log path",
  "creative.manualInstall": "Manual install command",
  "creative.profile.requestApproval": "Request approval",
  "creative.profile.smartApproval": "Smart approval",
  "creative.profile.fullAccess": "Full access",
  "creative.profile.custom": "Custom",
  "creative.hardBlocks.title": "Catastrophic hard blocks (cannot be overridden in any profile)",

  // Errors and status
  "error.dataPathRefresh": "Failed to refresh database statistics",
  "error.generic": "Operation failed, please retry",
  "error.loading": "Loading...",
  "error.saveFailed": "Save failed",

  // Language settings
  "language.label": "Interface language",
  "language.description": "Only affects UI copy, not the language of model replies, questions or custom instructions.",
  "language.followSystem": "Follow system",
};
