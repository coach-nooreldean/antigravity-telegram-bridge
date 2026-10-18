#!/usr/bin/env bash
set -e

# ==========================================================
# Antigravity Telegram Bridge - Interactive Setup Script
# Works on Linux (Debian, Ubuntu, Arch, Fedora) and macOS
# ==========================================================

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${GREEN}    🚀 Antigravity Telegram Bridge Installer        ${NC}"
echo -e "${BLUE}====================================================${NC}"

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[!] Python 3 is not installed. Please install Python 3.9+ first.${NC}"
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}[+] Detected Python ${PY_VER}${NC}"

# Select Language
echo ""
echo -e "${YELLOW}Select your preferred language / اختر لغتك المفضلة:${NC}"
echo "1) English (Default)"
echo "2) العربية (Arabic)"
read -rp "Enter choice [1-2] (default: 1): " LANG_CHOICE

BOT_LANG="en"
if [ "$LANG_CHOICE" == "2" ]; then
    BOT_LANG="ar"
fi

# Locate or check agy CLI
AGY_PATH=$(command -v agy || true)
if [ -z "$AGY_PATH" ] && [ -f "$HOME/.local/bin/agy" ]; then
    AGY_PATH="$HOME/.local/bin/agy"
fi

if [ -z "$AGY_PATH" ]; then
    if [ "$BOT_LANG" == "ar" ]; then
        echo -e "${YELLOW}[!] لم نتمكن من العثور على أداة 'agy' تلقائياً.${NC}"
        read -rp "أدخل المسار الكامل لـ agy (أو اضغط Enter للاعتماد على 'agy' في PATH): " INPUT_AGY
    else
        echo -e "${YELLOW}[!] 'agy' CLI binary not found in standard PATH.${NC}"
        read -rp "Enter full path to agy (or press Enter to use 'agy'): " INPUT_AGY
    fi
    AGY_PATH="${INPUT_AGY:-agy}"
else
    echo -e "${GREEN}[+] Found Antigravity CLI at: ${AGY_PATH}${NC}"
fi

# Get Telegram Bot Token
echo ""
if [ "$BOT_LANG" == "ar" ]; then
    echo -e "${YELLOW}احصل على توكن البوت من @BotFather في تيليجرام:${NC}"
    read -rp "أدخل توكن البوت (Telegram Bot Token): " BOT_TOKEN
else
    echo -e "${YELLOW}Get your Telegram Bot Token from @BotFather:${NC}"
    read -rp "Enter your Telegram Bot Token: " BOT_TOKEN
fi

if [ -z "$BOT_TOKEN" ]; then
    echo -e "${RED}[!] Bot token cannot be empty.${NC}"
    exit 1
fi

# Default project workspace
DEFAULT_WS="$PWD"
if [ "$BOT_LANG" == "ar" ]; then
    read -rp "أدخل مسار مجلد مشاريعك الافتراضي (افتراضي: $DEFAULT_WS): " USER_WS
else
    read -rp "Enter your default project workspace path (default: $DEFAULT_WS): " USER_WS
fi
CURRENT_WS="${USER_WS:-$DEFAULT_WS}"

# Install requirements
echo -e "\n${BLUE}[*] Installing dependencies (requests)...${NC}"
pip3 install --user -r requirements.txt || pip install -r requirements.txt

# Generate config.json
cat << CONF > config.json
{
  "bot_token": "${BOT_TOKEN}",
  "allowed_user_id": null,
  "language": "${BOT_LANG}",
  "workspace_mode": "auto",
  "current_workspace": "${CURRENT_WS}",
  "current_model": "default",
  "current_effort": "default",
  "agy_bin": "${AGY_PATH}"
}
CONF

echo -e "${GREEN}[+] Generated config.json successfully!${NC}"

# Setup Systemd Service on Linux
if [[ "$OSTYPE" == "linux-gnu"* ]] && command -v systemctl &> /dev/null; then
    echo ""
    if [ "$BOT_LANG" == "ar" ]; then
        read -rp "هل تود تشغيل البوت كخدمة خلفية دائمة 24/7 عبر systemd؟ (y/N): " SETUP_SVC
    else
        read -rp "Do you want to run the bot 24/7 in background via systemd user service? (y/N): " SETUP_SVC
    fi

    if [[ "$SETUP_SVC" =~ ^[Yy]$ ]]; then
        SVC_DIR="$HOME/.config/systemd/user"
        mkdir -p "$SVC_DIR"
        SVC_FILE="$SVC_DIR/antigravity-bridge.service"
        
        PYTHON_BIN=$(command -v python3)
        CURR_DIR=$(pwd)
        
        cat << SERVICE > "$SVC_FILE"
[Unit]
Description=Antigravity Telegram Bot Remote Controller
After=network.target

[Service]
Type=simple
WorkingDirectory=${CURR_DIR}
ExecStart=${PYTHON_BIN} ${CURR_DIR}/bot.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
SERVICE

        systemctl --user daemon-reload
        systemctl --user enable antigravity-bridge.service
        systemctl --user restart antigravity-bridge.service

        if [ "$BOT_LANG" == "ar" ]; then
            echo -e "${GREEN}[+] تم تثبيت وتشغيل خدمة البوت بنجاح!${NC}"
            echo -e "${GREEN}فحص الحالة: systemctl --user status antigravity-bridge.service${NC}"
        else
            echo -e "${GREEN}[+] Service installed and started successfully!${NC}"
            echo -e "${GREEN}Check status with: systemctl --user status antigravity-bridge.service${NC}"
        fi
    fi
fi

echo -e "\n${BLUE}====================================================${NC}"
if [ "$BOT_LANG" == "ar" ]; then
    echo -e "${GREEN}🎉 تم التثبيت بنجاح!${NC}"
    echo -e "افتح البوت في تيليجرام واضغط /start أو أرسل أي رسالة لربطه بحسابك فوراً."
    echo -e "للتشغيل اليدوي: python3 bot.py"
else
    echo -e "${GREEN}🎉 Setup Complete!${NC}"
    echo -e "Open your bot on Telegram and type /start or send any message to pair."
    echo -e "To run manually: python3 bot.py"
fi
echo -e "${BLUE}====================================================${NC}"
