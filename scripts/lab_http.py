"""HTTP transports must not forward private headers or prompts across redirects."""
from urllib.request import HTTPRedirectHandler, build_opener

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_request(request, **kwargs):
    return build_opener(NoRedirect()).open(request, **kwargs)
