import logging
import os
import sys
import asyncio
import signal
import psutil
import requests
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from flask import Flask
from database.models import db, User, Transaction

# === ƯU TIÊN ĐỌC TỪ BIẾN MÔI TRƯỜNG (RAILWAY) ===
print("📁 Đang đọc biến môi trường từ Railway...")

BOT_TOKEN = os.environ.get('BOT_TOKEN')
API_KEY = os.environ.get('API_KEY')
BASE_URL = os.environ.get('BASE_URL')
ADMIN_ID = os.environ.get('ADMIN_ID')
MB_ACCOUNT = os.environ.get('MB_ACCOUNT')
MB_NAME = os.environ.get('MB_NAME')
MB_BIN = os.environ.get('MB_BIN')
SEPAY_TOKEN = os.environ.get('SEPAY_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///database/bot.db')

# Kiểm tra các biến quan trọng
if not BOT_TOKEN:
    print("❌ KHÔNG TÌM THẤY BOT_TOKEN trong biến môi trường!")
    print("📋 Các biến hiện có:", [k for k in os.environ.keys() if not k.startswith('_')])
    sys.exit(1)
if not API_KEY:
    print("❌ KHÔNG TÌM THẤY API_KEY")
    sys.exit(1)
if not BASE_URL:
    print("❌ KHÔNG TÌM THẤY BASE_URL")
    sys.exit(1)

print(f"✅ BOT_TOKEN: {BOT_TOKEN[:10]}...")
print(f"✅ API_KEY: {API_KEY[:10]}...")
print(f"✅ BASE_URL: {BASE_URL}")
print("✅ Đã đọc tất cả biến môi trường thành công!")

# Cấu hình logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# === DATABASE ===
app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, 'database', 'bot.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
logger.info(f"✅ Database path: {db_path}")

# Import handlers
try:
    from handlers.start import start_command, menu_command, cancel, help_command, check_command, history_command, cancel_command
    from handlers.balance import balance_command
    from handlers.deposit import deposit_command, deposit_amount_callback, deposit_check_callback
    from handlers.rent import (
        rent_command, rent_service_callback, rent_network_callback,
        rent_confirm_callback, rent_check_callback, rent_cancel_callback,
        rent_view_callback, rent_list_callback, rent_reuse_callback
    )
    from handlers.callback import menu_callback
    logger.info("✅ Import handlers thành công")
except Exception as e:
    logger.error(f"❌ LỖI IMPORT HANDLERS: {e}")
    sys.exit(1)

def kill_other_instances():
    current_pid = os.getpid()
    killed = 0
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                if (proc.info['pid'] != current_pid and 
                    'python' in proc.info['name'] and 
                    'bot.py' in cmdline):
                    os.kill(proc.info['pid'], signal.SIGTERM)
                    killed += 1
                    logger.info(f"✅ Đã kill instance cũ PID: {proc.info['pid']}")
            except:
                pass
    except Exception as e:
        logger.error(f"Lỗi kill: {e}")
    return killed

def cleanup_telegram():
    try:
        close_url = f"https://api.telegram.org/bot{BOT_TOKEN}/close"
        close_res = requests.post(close_url)
        logger.info(f"Close connection: {close_res.status_code}")
        
        webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
        webhook_res = requests.post(webhook_url)
        logger.info(f"Delete webhook: {webhook_res.status_code}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

async def set_bot_commands(application):
    """Thiết lập menu commands cho bot"""
    commands = [
        ("start", "🚀 Khởi động bot"),
        ("rent", "📱 Thuê số nhận OTP"),
        ("balance", "💰 Xem số dư"),
        ("deposit", "💳 Nạp tiền"),
        ("history", "📜 Lịch sử giao dịch"),
        ("help", "❓ Hướng dẫn sử dụng"),
        ("cancel", "❌ Hủy thao tác hiện tại"),
        ("check", "🔍 Kiểm tra giao dịch (kèm mã GD)")
    ]
    
    await application.bot.set_my_commands(commands)
    logger.info("✅ Đã thiết lập menu commands")

async def main():
    killed = kill_other_instances()
    if killed > 0:
        logger.info(f"Đã kill {killed} instance cũ")
    cleanup_telegram()
    
    try:
        logger.info("🚀 BOT ĐANG KHỞI ĐỘNG...")
        
        with app.app_context():
            try:
                # Tạo database nếu chưa có
                db.create_all()
                user_count = User.query.count()
                logger.info(f"✅ Kết nối database thành công! Số user: {user_count}")
            except Exception as e:
                logger.error(f"❌ Lỗi kết nối database: {e}")
        
        # Tạo application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Thiết lập menu commands
        await set_bot_commands(application)
        
        # COMMAND HANDLERS
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("balance", balance_command))
        application.add_handler(CommandHandler("deposit", deposit_command))
        application.add_handler(CommandHandler("rent", rent_command))
        application.add_handler(CommandHandler('check', check_command))
        application.add_handler(CommandHandler('cancel', cancel_command))
        application.add_handler(CommandHandler('help', help_command))
        application.add_handler(CommandHandler('history', history_command))
        
        # CALLBACK HANDLERS
        application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
        application.add_handler(CallbackQueryHandler(deposit_amount_callback, pattern="^deposit_amount_"))
        application.add_handler(CallbackQueryHandler(deposit_check_callback, pattern="^deposit_check_"))
        application.add_handler(CallbackQueryHandler(rent_service_callback, pattern="^rent_service_"))
        application.add_handler(CallbackQueryHandler(rent_network_callback, pattern="^rent_network_"))
        application.add_handler(CallbackQueryHandler(rent_confirm_callback, pattern="^rent_confirm_"))
        application.add_handler(CallbackQueryHandler(rent_check_callback, pattern="^rent_check_"))
        application.add_handler(CallbackQueryHandler(rent_cancel_callback, pattern="^rent_cancel_"))
        application.add_handler(CallbackQueryHandler(rent_view_callback, pattern="^rent_view_"))
        application.add_handler(CallbackQueryHandler(rent_reuse_callback, pattern="^rent_reuse_"))
        application.add_handler(CallbackQueryHandler(rent_list_callback, pattern="^menu_rent_list"))
        
        logger.info("✅ BOT KHỞI ĐỘNG THÀNH CÔNG!")
        
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"❌ LỖI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot đã dừng")
    except Exception as e:
        logger.error(f"❌ LỖI: {e}")
