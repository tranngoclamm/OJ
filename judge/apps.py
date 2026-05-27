from django.apps import AppConfig
from django.db import DatabaseError
from django.utils.translation import gettext_lazy


class JudgeAppConfig(AppConfig):
    name = 'judge'
    verbose_name = gettext_lazy('Online Judge')

    def ready(self):
        # WARNING: AS THIS IS NOT A FUNCTIONAL PROGRAMMING LANGUAGE,
        #          OPERATIONS MAY HAVE SIDE EFFECTS.
        #          DO NOT REMOVE THINKING THE IMPORT IS UNUSED.
        # noinspection PyUnresolvedReferences
        from . import signals, jinja2  # noqa: F401, imported for side effects

        from judge.models import Language, Profile
        from django.contrib.auth.models import User

        try:
            lang = Language.get_default_language()
            for user in User.objects.filter(profile=None):
                # These poor profileless users
                profile = Profile(user=user, language=lang)
                profile.save()
        except DatabaseError:
            pass

        def _patch_impersonate():
            from impersonate import views as impersonate_views
            from django.contrib.sessions.middleware import SessionMiddleware
            from django.contrib.sessions.exceptions import SessionInterrupted

            _original_impersonate = impersonate_views.impersonate
            _original_process_response = SessionMiddleware.process_response
            _original_stop = impersonate_views.stop_impersonate

            def safe_impersonate(request, uid):
                try:
                    request.session.save()
                except Exception:
                    # Flush và tạo session mới, giữ lại auth data
                    from django.contrib.auth import login
                    user = request.user
                    request.session.flush()
                    # Ghi lại thông tin auth vào session mới
                    login(request, user, 
                        backend='django.contrib.auth.backends.ModelBackend')
                return _original_impersonate(request, uid)

            def safe_stop_impersonate(request):
                try:
                    request.session.save()
                except Exception:
                    # Session không còn trong DB → flush + login lại admin
                    from django.contrib.auth import login
                    # request.impersonator là admin thật
                    user = request.impersonator or request.user
                    request.session.flush()
                    login(request, user,
                        backend='django.contrib.auth.backends.ModelBackend')
                return _original_stop(request)
            
            def _safe_process_response(self, request, response):
                try:
                    return _original_process_response(self, request, response)
                except SessionInterrupted:
                    return response

            impersonate_views.impersonate = safe_impersonate
            impersonate_views.stop_impersonate = safe_stop_impersonate
            SessionMiddleware.process_response = _safe_process_response

        _patch_impersonate()


        
