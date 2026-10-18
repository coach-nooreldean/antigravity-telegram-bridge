# 🚀 Antigravity Telegram Bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9+-yellow.svg)](https://python.org)
[![Telegram Bot API](https://img.shields.io/badge/Telegram-Bot%20API-blue?logo=telegram)](https://core.telegram.org/bots/api)
[![Platform: Linux | macOS | Windows](https://img.shields.io/badge/Platform-Linux%20|%20macOS%20|%20Windows-lightgrey.svg)]()

> **تحكم بوكيلك الذكي Google Antigravity وطوّر مشاريعك البرمجية عن بُعد من شاشة موبايلك في تيليجرام.**

**العربية** | [English (README)](README.md)

---

## ✨ المميزات الرئيسية

- **🤖 تحكم كامل في الوكيل الذكي:** جسر متصل ومباشر مع أداة `agy` CLI يدعم استمرار الجلسات (`-c`) وبدء جلسات جديدة نظيفة (`-n`).
- **🧠 اختيار النماذج ومستويات التفكير:** التبديل الفوري بين نماذج Claude (Sonnet / Opus Thinking)، و Gemini، و GPT عبر الأمر `/model` وتحديد عمق التفكير عبر `/effort`.
- **📱 لوحة أزرار سريعة ومثبتة للموبايل:** كيبورد تفاعلي (3×3) مثبت أسفل الشاشة للوصول السريع لـ Git، و Diff، ومراقبة المهام، والتقاط الشاشة بنقرة واحدة.
- **📸 لقطات شاشة حية لكل أنظمة التشغيل:** يدعم التقاط شاشة الكمبيوتر لايف على أنظمة Linux (Wayland عبر `grim` أو X11 عبر `scrot`)، و macOS (`screencapture`)، و Windows (PowerShell).
- **🎙️ دعم الرسائل الصوتية (Voice Notes):** تحدث باللغة العربية أو الإنجليزية وسيقوم الأيجنت بالاستماع للرسالة الصوتية وتنفيذ التعديل البرمجي المطلوب فوراً.
- **📥 تبادل الملفات والمستندات في الاتجاهين:** أرسل أي ملف كود (`.py`, `.dart`, `.ts`, `.json`) وسيقوم الأيجنت بفحصه، تلخيصه، أو كتابة تعديلات عليه في مشروعك.
- **🎨 تسليم المخرجات المرئية تلقائياً:** أي صور، تصاميم، أو لقطات واجهات ينشئها الأيجنت تصلك فوراً على تيليجرام كصور عالية الجودة.
- **🌿 إنشاء ومتابعة الـ Pull Requests بنقرة واحدة:** تكامل مباشر مع `gh CLI` عبر أمر `/pr` لرفع الكود وإنشاء Pull Request على GitHub وإرسال الرابط المباشر.
- **🌐 دعم كامل للغتين (العربية والإنجليزية):** التبديل الفوري بين العربية والإنجليزية في أي وقت عبر أمر `/lang`.
- **🔒 اقتران أمني سريع:** يقفل البوت تلقائياً على أول حساب يتواصل معه في تيليجرام لمنع أي وصول خارجي.
- **🧹 تنظيف دوري للوسائط:** خدمة في الخلفية تحذف الملفات المؤقتة القديمة التي مر عليها أكثر من 24 ساعة للحفاظ على مساحة جهازك.

---

## ⚡ التثبيت السريع في دقيقتين

### 1. استنساخ المستودع (Clone)
```bash
git clone https://github.com/coach-nooreldean/antigravity-telegram-bridge.git
cd antigravity-telegram-bridge
```

### 2. تشغيل معالج التثبيت التفاعلي
```bash
chmod +x install.sh
./install.sh
```
*سيطلب منك المعالج إدخال توكن البوت من [@BotFather](https://t.me/BotFather)، واكتشاف مسار أداة `agy`، مع خيار إعداد خدمة خلفية 24/7 عبر systemd.*

### 3. ابدأ الاستخدام!
افتح البوت في تيليجرام واكتب `/start` أو أرسل أي طلب برمجي بلغتك الطبيعية!

---

## 📖 جدول الأوامر المتاحة

| الأمر | الوصف |
| :--- | :--- |
| `/menu` | إظهار شريط الأزرار السريعة المثبت أسفل الشاشة 📱 |
| `/lang` | التبديل بين اللغتين العربية والإنجليزية 🌐 |
| `/model` | اختيار نموذج الذكاء الاصطناعي (Claude / Gemini / GPT) 🧠 |
| `/effort` | تحديد مستوى وعمق التفكير (Max / High / Medium / Low) ⚡ |
| `/goal [الهدف]` | وضع الهدف المستقل (ينفذ المهمة بدون توقف حتى تكتمل) 🎯 |
| `/diff` | استعراض التغييرات غير المحفوظة في الكود وتحميل الملفات 📝 |
| `/git` | فحص حالة Git والفرع النشط والكوميتات الأخيرة 📊 |
| `/commit [رسالة]` | حفظ وتثبيت التعديلات الحالية في Git محلياً 💾 |
| `/push` | رفع التعديلات على فرع GitHub الحالي 🚀 |
| `/pr [عنوان]` | إنشاء أو فحص Pull Request على GitHub عبر `gh CLI` 🌿 |
| `/screenshot` | لقطة شاشة حية لشاشات الكمبيوتر في أي وقت 📸 |
| `/sh [أمر]` | تنفيذ أي أمر شل/ترمينال مباشر على الجهاز ⚡ |
| `/stop` | إيقاف المهمة الجارية حالياً وتنظيف العمليات 🛑 |

---

## ⚙️ ملف الإعدادات (`config.json`)

```json
{
  "bot_token": "YOUR_BOT_TOKEN_HERE",
  "allowed_user_id": null,
  "language": "ar",
  "workspace_mode": "auto",
  "current_workspace": "~/projects/my-app",
  "current_model": "default",
  "current_effort": "default",
  "agy_bin": "agy"
}
```

---

## 🛠️ التشغيل الدائم 24/7 عبر Systemd (Linux)

```bash
systemctl --user enable antigravity-bridge.service
systemctl --user start antigravity-bridge.service
systemctl --user status antigravity-bridge.service
```

---

## 📄 الرخصة (License)

المشروع مرخص تحت رخصة **MIT**. راجع ملف [LICENSE](LICENSE) لمزيد من التفاصيل.
