from backend import create_app as backend_create_app


def create_app():
    """Gunicorn entry point to create the Flask application."""
    return backend_create_app()
