"""Keep the read and stream boundary present even when application code is rolled back."""
import argparse
import importlib.util
import os
from pathlib import Path
import sys
from house_auth import install, require_secret


def build(server):
    secret = require_secret()
    server = Path(server).resolve()
    sys.path.insert(0, str(server.parent))
    sys.path.insert(0, str(Path.home()/'.vintos/workspace/scripts'))
    spec = importlib.util.spec_from_file_location('vintos_guarded_server', server)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    legacy_client = not getattr(module.app.state, 'house_read_guard', False)
    install(module.app, secret)
    # Preserve the reviewed enrollment UI across application-code rollback.
    from fastapi.responses import FileResponse
    guard = Path(__file__).resolve().parent
    for path, name in [('/', 'index.html'), ('/app/', 'index.html'),
                       ('/house_auth_client.js', 'house_auth_client.js'),
                       ('/app/house_auth_client.js', 'house_auth_client.js')]:
        if not legacy_client or not (guard/name).is_file(): continue
        module.app.router.routes[:] = [r for r in module.app.router.routes if getattr(r,'path',None)!=path]
        def asset_handler(file):
            def asset():
                return FileResponse(file, media_type='text/html' if file.suffix=='.html' else 'application/javascript',
                                    headers={'Cache-Control':'no-store'})
            return asset
        module.app.add_api_route(path, asset_handler(guard/name), methods=['GET'], include_in_schema=False)
    if not hasattr(module, '_voice_caller_ok'):
        # A pre-fix rollback must not reopen voice credential issuance publicly.
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse
        import hmac
        class LegacyVoiceGuard(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.url.path == '/api/voice/token' and not hmac.compare_digest(request.headers.get('X-Vintos-Secret',''),secret):
                    return JSONResponse({'detail':'Owner enrollment required after legacy rollback'},status_code=401)
                return await call_next(request)
        module.app.add_middleware(LegacyVoiceGuard)
    return module.app


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--server', required=True)
    p.add_argument('--port', type=int, default=8500)
    a = p.parse_args(argv)
    import uvicorn
    uvicorn.run(build(a.server), host='0.0.0.0', port=a.port)


if __name__ == '__main__': main()
