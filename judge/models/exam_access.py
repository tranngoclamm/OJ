from django.conf import settings
from django.db import models

from django.utils.translation import gettext_lazy as _

from judge.models.problem import Problem
from judge.models.profile import Organization
from judge.models.contest import Contest
from django.contrib.auth.models import User

class ExamAccess(models.Model):
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE)
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        db_table = 'judge_examaccess' 
        unique_together = ('contest', 'problem', 'organization', 'user')