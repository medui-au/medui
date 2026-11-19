"""Local development entry point; production uses wsgi:app."""
import os
from app import create_app

app = create_app(os.environ.get('FLASK_ENV', 'dev'))

if __name__ == '__main__':
    cert, key = os.environ.get('SSL_CERT_PATH'), os.environ.get('SSL_KEY_PATH')
    app.run(host=os.environ.get('BIND_HOST', '127.0.0.1'),
            port=int(os.environ.get('PORT', '5005')),
            ssl_context=(cert, key) if cert and key else None,
            debug=app.config['DEBUG'])
