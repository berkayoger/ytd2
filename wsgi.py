from loguru import logger

from backend import create_app, socketio
from backend.core.services import YTDCryptoSystem

app = create_app()
app.ytd_system_instance = YTDCryptoSystem()


if __name__ == '__main__':
    logger.info("Flask uygulaması başlatılıyor.")
    socketio.run(app, debug=app.config.get("DEBUG", False), port=5000, allow_unsafe_werkzeug=True)
