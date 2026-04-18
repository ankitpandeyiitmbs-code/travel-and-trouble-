import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    _base_dir = os.path.dirname(os.path.abspath(__file__))
    DATABASE = os.environ.get('DATABASE') or os.path.join(_base_dir, 'wanderbuddy.db')
    UPLOAD_FOLDER = os.path.join(_base_dir, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'mp4', 'webp'}
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL') or 'admin@travelandtrouble.com'
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID') or 'rzp_test_replace_me'
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET') or 'replace_this_secret'
    ITEMS_PER_PAGE = 12

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
