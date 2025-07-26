from flask import render_template
from . import frontend_bp


@frontend_bp.route('/')
def index():
    return render_template('index.html')


@frontend_bp.route('/predictions')
def prediction_display():
    """Render the public predictions page."""
    return render_template('prediction_display.html')
