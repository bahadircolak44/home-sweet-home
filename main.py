"""Google Cloud Run function entry point for the Django application."""

import functions_framework
from werkzeug.wrappers import Response

from home_sweet_home.wsgi import application


@functions_framework.http
def home_sweet_home(request):
    """Forward a Functions Framework HTTP request to Django's WSGI app."""
    return Response.from_app(application, request.environ)
