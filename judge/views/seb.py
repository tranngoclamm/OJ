from django.conf import settings
from django.utils import timezone
from django.shortcuts import render
import hashlib

class SEBRequiredMixin:
    def seb_check(self, request, contest):
        user = request.user
        now = timezone.now()

        if not (contest.start_time <= now <= contest.end_time):
            return None

        if contest.is_editable_by(user):
            return None

        is_exam = contest.tags.filter(name="exam").exists()
        if not is_exam:
            return None

        seb_hash = request.headers.get('X-SafeExamBrowser-ConfigKeyHash')
        if not seb_hash:
            return render(request, 'errors/seb_forbidden.html', status=403)

        absolute_url = request.build_absolute_uri()

        config_keys = getattr(settings, 'SEB_CONFIG_KEYS', [])

        for key in config_keys:
            expected = hashlib.sha256((absolute_url + key).encode()).hexdigest()
            if expected == seb_hash:
                return None

        for key in config_keys:
            expected = hashlib.sha256((absolute_url + key).encode()).hexdigest()

        return render(request, 'errors/seb_forbidden.html', status=403)
