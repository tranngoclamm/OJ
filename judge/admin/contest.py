from datetime import datetime
import json
import os
import tempfile
import zipfile
from adminsortable2.admin import SortableInlineAdminMixin
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.db.models import Q, TextField
from django.forms import ModelForm, ModelMultipleChoiceField
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _, ngettext
from django.views.decorators.http import require_POST
from reversion.admin import VersionAdmin

from django_ace import AceWidget
from judge.models import Contest, ContestAnnouncement, ContestProblem, ContestSubmission, Profile, Rating, Submission
from judge.ratings import rate_contest
from judge.utils.views import NoBatchDeleteMixin
from judge.widgets import AdminHeavySelect2MultipleWidget, AdminHeavySelect2Widget, AdminMartorWidget, \
    AdminSelect2MultipleWidget, AdminSelect2Widget


class AdminHeavySelect2Widget(AdminHeavySelect2Widget):
    @property
    def is_hidden(self):
        return False


class ContestTagForm(ModelForm):
    contests = ModelMultipleChoiceField(
        label=_('Included contests'),
        queryset=Contest.objects.all(),
        required=False,
        widget=AdminHeavySelect2MultipleWidget(data_view='contest_select2'))


class ContestTagAdmin(admin.ModelAdmin):
    fields = ('name', 'color', 'description', 'contests')
    list_display = ('name', 'color')
    actions_on_top = True
    actions_on_bottom = True
    form = ContestTagForm
    formfield_overrides = {
        TextField: {'widget': AdminMartorWidget},
    }

    def save_model(self, request, obj, form, change):
        super(ContestTagAdmin, self).save_model(request, obj, form, change)
        obj.contests.set(form.cleaned_data['contests'])

    def get_form(self, request, obj=None, **kwargs):
        form = super(ContestTagAdmin, self).get_form(request, obj, **kwargs)
        if obj is not None:
            form.base_fields['contests'].initial = obj.contests.all()
        return form


class ContestProblemInlineForm(ModelForm):
    class Meta:
        widgets = {'problem': AdminHeavySelect2Widget(data_view='problem_select2')}


class ContestProblemInline(SortableInlineAdminMixin, admin.TabularInline):
    model = ContestProblem
    verbose_name = _('Problem')
    verbose_name_plural = _('Problems')
    fields = ('problem', 'points', 'partial', 'is_pretested', 'max_submissions', 'output_prefix_override', 'order',
              'rejudge_column', 'rescore_column')
    readonly_fields = ('rejudge_column', 'rescore_column')
    form = ContestProblemInlineForm

    @admin.display(description='')
    def rejudge_column(self, obj):
        if obj.id is None:
            return ''
        return format_html('<a class="button rejudge-link action-link" href="{0}">{1}</a>',
                           reverse('admin:judge_contest_rejudge', args=(obj.contest.id, obj.id)), _('Rejudge'))

    @admin.display(description='')
    def rescore_column(self, obj):
        if obj.id is None:
            return ''
        return format_html('<a class="button rescore-link action-link" href="{}">Rescore</a>',
                           reverse('admin:judge_contest_rescore', args=(obj.contest.id, obj.id)))


class ContestAnnouncementInlineForm(ModelForm):
    class Meta:
        widgets = {'description': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('comment_preview')})}


class ContestAnnouncementInline(admin.StackedInline):
    model = ContestAnnouncement
    fields = ('title', 'description', 'resend')
    readonly_fields = ('resend',)
    form = ContestAnnouncementInlineForm
    extra = 0

    @admin.display(description=_('Resend announcement'))
    def resend(self, obj):
        if obj.id is None:
            return 'Not available'
        return format_html('<a class="button resend-link action-link" href="{}">Resend</a>',
                           reverse('admin:judge_contest_resend', args=(obj.contest.id, obj.id)))


class ContestForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(ContestForm, self).__init__(*args, **kwargs)
        if 'rate_exclude' in self.fields:
            if self.instance and self.instance.id:
                self.fields['rate_exclude'].queryset = \
                    Profile.objects.filter(contest_history__contest=self.instance).distinct()
            else:
                self.fields['rate_exclude'].queryset = Profile.objects.none()
        self.fields['banned_users'].widget.can_add_related = False
        self.fields['view_contest_scoreboard'].widget.can_add_related = False
        self.fields['banned_judges'].widget.can_add_related = False

    def clean(self):
        cleaned_data = super(ContestForm, self).clean()
        cleaned_data['banned_users'].filter(current_contest__contest=self.instance).update(current_contest=None)

    class Meta:
        widgets = {
            'authors': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'curators': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'testers': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'private_contestants': AdminHeavySelect2MultipleWidget(data_view='profile_select2',
                                                                   attrs={'style': 'width: 100%'}),
            'organizations': AdminHeavySelect2MultipleWidget(data_view='organization_select2'),
            'tags': AdminSelect2MultipleWidget,
            'banned_users': AdminHeavySelect2MultipleWidget(data_view='profile_select2',
                                                            attrs={'style': 'width: 100%'}),
            'view_contest_scoreboard': AdminHeavySelect2MultipleWidget(data_view='profile_select2',
                                                                       attrs={'style': 'width: 100%'}),
            'description': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('contest_preview')}),
            'banned_judges': AdminSelect2MultipleWidget(attrs={'style': 'width: 100%'}),
        }


class ContestAdmin(NoBatchDeleteMixin, VersionAdmin):
    fieldsets = (
        (None, {'fields': ('key', 'name', 'authors', 'curators', 'testers')}),
        (_('Settings'), {'fields': ('is_visible', 'use_clarifications', 'push_announcements', 'disallow_virtual',
                                    'hide_problem_tags', 'hide_problem_authors', 'show_short_display',
                                    'run_pretests_only', 'locked_after', 'scoreboard_visibility',
                                    'ranking_access_code', 'scoreboard_cache_timeout', 'show_submission_list',
                                    'points_precision', 'banned_judges')}),
        (_('Scheduling'), {'fields': ('start_time', 'end_time', 'registration_start', 'registration_end',
                                      'time_limit')}),
        (_('Details'), {'fields': ('description', 'og_image', 'logo_override_image', 'tags', 'summary')}),
        (_('Format'), {'fields': ('format_name', 'frozen_last_minutes', 'format_config', 'problem_label_script')}),
        (_('Rating'), {'fields': ('is_rated', 'rate_all', 'rating_floor', 'rating_ceiling', 'rate_exclude')}),
        (_('Access'), {'fields': ('access_code', 'is_private', 'private_contestants', 'is_organization_private',
                                  'organizations', 'view_contest_scoreboard')}),
        (_('Justice'), {'fields': ('banned_users',)}),
        (_('Ranking'), {'fields': ('csv_ranking',)}),
    )
    list_display = ('key', 'name', 'is_visible', 'is_rated', 'locked_after', 'start_time', 'end_time', 'time_limit',
                    'user_count')
    search_fields = ('key', 'name')
    inlines = [ContestProblemInline, ContestAnnouncementInline]
    actions_on_top = True
    actions_on_bottom = True
    form = ContestForm
    change_list_template = 'admin/judge/contest/change_list.html'
    filter_horizontal = ['rate_exclude']
    date_hierarchy = 'start_time'

    def get_actions(self, request):
        actions = super(ContestAdmin, self).get_actions(request)

        if request.user.has_perm('judge.change_contest_visibility') or \
                request.user.has_perm('judge.create_private_contest'):
            for action in ('make_visible', 'make_hidden'):
                actions[action] = self.get_action(action)

        if request.user.has_perm('judge.lock_contest'):
            for action in ('set_locked', 'set_unlocked'):
                actions[action] = self.get_action(action)

        if request.user.has_perm('judge.export_contest'):
                actions['export_contests'] = (self.export_contests, 'export_contests', _('Export contests'))

        return actions

    def get_queryset(self, request):
        queryset = Contest.objects.all()
        if request.user.has_perm('judge.edit_all_contest'):
            return queryset
        else:
            return queryset.filter(Q(authors=request.profile) | Q(curators=request.profile)).distinct()

    def get_readonly_fields(self, request, obj=None):
        readonly = []
        if not request.user.has_perm('judge.contest_rating'):
            readonly += ['is_rated', 'rate_all', 'rate_exclude']
        if not request.user.has_perm('judge.lock_contest'):
            readonly += ['locked_after']
        if not request.user.has_perm('judge.contest_access_code'):
            readonly += ['access_code']
        if not request.user.has_perm('judge.create_private_contest'):
            readonly += ['is_private', 'private_contestants', 'is_organization_private', 'organizations']
            if not request.user.has_perm('judge.change_contest_visibility'):
                readonly += ['is_visible']
        if not request.user.has_perm('judge.contest_problem_label'):
            readonly += ['problem_label_script']
        return readonly

    def save_model(self, request, obj, form, change):
        # `is_visible` will not appear in `cleaned_data` if user cannot edit it
        if form.cleaned_data.get('is_visible') and not request.user.has_perm('judge.change_contest_visibility'):
            if not form.cleaned_data['is_private'] and not form.cleaned_data['is_organization_private']:
                raise PermissionDenied
            if not request.user.has_perm('judge.create_private_contest'):
                raise PermissionDenied

        super().save_model(request, obj, form, change)
        # We need this flag because `save_related` deals with the inlines, but does not know if we have already rescored
        self._rescored = False
        if form.changed_data and any(
            f in form.changed_data for f in ('frozen_last_minutes', 'format_config', 'format_name')
        ):
            self._rescore(obj.key)
            self._rescored = True

        if form.changed_data and 'locked_after' in form.changed_data:
            self.set_locked_after(obj, form.cleaned_data['locked_after'])

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Only rescored if we did not already do so in `save_model`
        if not self._rescored and any(formset.has_changed() for formset in formsets):
            self._rescore(form.cleaned_data['key'])

    def has_change_permission(self, request, obj=None):
        if not request.user.has_perm('judge.edit_own_contest'):
            return False
        if obj is None:
            return True
        return obj.is_editable_by(request.user)

    def _rescore(self, contest_key):
        from judge.tasks import rescore_contest
        transaction.on_commit(rescore_contest.s(contest_key).delay)

    @admin.display(description=_('Mark contests as visible'))
    def make_visible(self, request, queryset):
        if not request.user.has_perm('judge.change_contest_visibility'):
            queryset = queryset.filter(Q(is_private=True) | Q(is_organization_private=True))
        count = queryset.update(is_visible=True)
        self.message_user(request, ngettext('%d contest successfully marked as visible.',
                                            '%d contests successfully marked as visible.',
                                            count) % count)

    @admin.display(description=_('Mark contests as hidden'))
    def make_hidden(self, request, queryset):
        if not request.user.has_perm('judge.change_contest_visibility'):
            queryset = queryset.filter(Q(is_private=True) | Q(is_organization_private=True))
        count = queryset.update(is_visible=False)
        self.message_user(request, ngettext('%d contest successfully marked as hidden.',
                                            '%d contests successfully marked as hidden.',
                                            count) % count)

    @admin.display(description=_('Lock contest submissions'))
    def set_locked(self, request, queryset):
        for row in queryset:
            self.set_locked_after(row, timezone.now())
        count = queryset.count()
        self.message_user(request, ngettext('%d contest successfully locked.',
                                            '%d contests successfully locked.',
                                            count) % count)

    @admin.display(description=_('Unlock contest submissions'))
    def set_unlocked(self, request, queryset):
        for row in queryset:
            self.set_locked_after(row, None)
        count = queryset.count()
        self.message_user(request, ngettext('%d contest successfully unlocked.',
                                            '%d contests successfully unlocked.',
                                            count) % count)
    @admin.action(description=_('Export contests'))
    def export_contests(self, modeladmin, request, queryset):
        import os, tempfile, subprocess, io, zipfile, re
        from django.http import FileResponse
        from django.conf import settings
        from django.db import connection
        from django.contrib import messages

        db_settings = settings.DATABASES['default']
        db_user = db_settings['USER']
        db_password = db_settings.get('PASSWORD', '')
        db_name = db_settings['NAME']
        db_host = db_settings.get('HOST', 'localhost')
        db_port = db_settings.get('PORT', '3306')  

        with tempfile.TemporaryDirectory() as tmpdir:
            sql_paths = []
            for contest in queryset:
                contest_id = contest.id
                
                sql_filename = f'contest_{contest_id}.sql'
                sql_filepath = os.path.join(tmpdir, sql_filename)
                
                tables = [
                    'judge_contest',
                    'judge_contestproblem',
                    'judge_contestannouncement',
                    'judge_contestmoss',
                    'judge_contestparticipation',
                    'judge_contestsubmission',
                    'judge_submission',
                    'judge_submissionsource',
                    'judge_submissiontestcase',
                    'auth_user',         
                    'judge_profile',     
                    'judge_problem',
                    # Các bảng many-to-many
                    'judge_problem_allowed_languages',
                    'judge_languagelimit',
                    'judge_problem_authors',
                    'judge_problem_banned_users',
                    'judge_problem_curators',
                    'judge_problem_organizations',
                    'judge_problem_testers',
                    'judge_problem_types',
                    'judge_problemclarification',
                    'judge_problemdata',
                    'judge_problemgroup',
                    'judge_problemtestcase',
                    'judge_problemtranslation',
                    'judge_problemtype',
                    'judge_contest_authors',
                    'judge_contest_curators',
                    'judge_contest_testers',
                    'judge_contest_tags',
                    'judge_contest_private_contestants',
                    'judge_contest_organizations',
                    'judge_contest_banned_users',
                    'judge_contest_banned_judges',
                    'judge_contest_view_contest_scoreboard',
                    'judge_contest_rate_exclude',
                ]
                
                with open(sql_filepath, 'w') as f:
                    f.write(f"-- SQL dump for contest {contest_id} (data only)\n")
                    f.write("-- This file contains only INSERT statements without table structure\n")
                    f.write("SET FOREIGN_KEY_CHECKS=0;\n\n")
                
                if 'mysql' in db_settings.get('ENGINE', '').lower():
                    dump_env = os.environ.copy()
                    if db_password:
                        dump_env['MYSQL_PWD'] = db_password  
                    
                    success = True
                    has_data = False
                    
                    for table in tables:
                        base_cmd = [
                            'mysqldump',
                            f'--host={db_host}',
                            f'--port={db_port}',
                            f'--user={db_user}',
                            '--skip-extended-insert',  
                            '--no-create-info',        
                            '--no-create-db',          
                            '--skip-triggers',         
                            '--single-transaction',    
                            db_name
                        ]
                        
                        if table == 'judge_contest':
                            condition = f"id={contest_id}"
                        elif table == 'judge_contestproblem':
                            condition = f"contest_id={contest_id}"
                        elif table == 'judge_contestannouncement':
                            condition = f"contest_id={contest_id}"
                        elif table == 'judge_contestmoss':
                            condition = f"contest_id={contest_id}"
                        elif table == 'judge_contestparticipation':
                            condition = f"contest_id={contest_id}"
                        elif table == 'judge_contestsubmission':
                            condition = f"participation_id IN (SELECT id FROM judge_contestparticipation WHERE contest_id={contest_id})"
                        elif table == 'judge_submission':
                            condition = f"id IN (SELECT submission_id FROM judge_contestsubmission WHERE participation_id IN (SELECT id FROM judge_contestparticipation WHERE contest_id={contest_id}))"
                        elif table == 'judge_submissionsource':
                            condition = f"submission_id IN (SELECT submission_id FROM judge_contestsubmission WHERE participation_id IN (SELECT id FROM judge_contestparticipation WHERE contest_id={contest_id}))"
                        elif table == 'judge_submissiontestcase':
                            condition = f"submission_id IN (SELECT submission_id FROM judge_contestsubmission WHERE participation_id IN (SELECT id FROM judge_contestparticipation WHERE contest_id={contest_id}))"  
                        elif table == 'auth_user':
                            condition = f"id IN (SELECT user_id FROM judge_profile WHERE id IN (SELECT profile_id FROM judge_contest_private_contestants WHERE contest_id={contest_id}))"
                        elif table == 'judge_profile':
                            condition = f"id IN (SELECT profile_id FROM judge_contest_private_contestants WHERE contest_id={contest_id})"
                        elif table == 'judge_problem':
                            condition = f"id IN (SELECT problem_id FROM judge_contestproblem WHERE contest_id={contest_id})"
                        elif table == 'judge_problemdata':
                            condition = f"problem_id IN (SELECT problem_id FROM judge_contestproblem WHERE contest_id={contest_id})"
                        elif table == 'judge_problemtestcase':
                            condition = f"dataset_id IN (SELECT problem_id FROM judge_contestproblem WHERE contest_id={contest_id})"
                        elif table == 'judge_languagelimit':
                            condition = f"problem_id IN (SELECT problem_id FROM judge_contestproblem WHERE contest_id={contest_id})"
                        elif table.startswith('judge_problem_'):
                            condition = f"problem_id IN (SELECT problem_id FROM judge_contestproblem WHERE contest_id={contest_id})"
                        elif table.startswith('judge_contest_'):
                            condition = f"contest_id={contest_id}"
                        else:
                            continue  
                        
                        table_cmd = base_cmd + ['--where', condition, table]
                        
                        try:
                            temp_table_file = os.path.join(tmpdir, f"{table}_{contest_id}_temp.sql")
                            
                            with open(temp_table_file, 'w') as temp_f:
                                result = subprocess.run(
                                    table_cmd, 
                                    stdout=temp_f, 
                                    stderr=subprocess.PIPE, 
                                    env=dump_env, 
                                    text=True,
                                    check=False  # Không dừng khi lỗi
                                )
                                
                                if result.returncode != 0:
                                    messages.warning(
                                        request, 
                                        f"Lỗi khi export bảng {table} cho contest {contest_id}: {result.stderr}"
                                    )
                                    success = False
                                    continue
                            
                            with open(temp_table_file, 'r') as temp_f:
                                content = temp_f.read()
                                if re.search(r'INSERT\s+INTO', content, re.IGNORECASE):
                                    with open(sql_filepath, 'a') as main_f:
                                        main_f.write(content)
                                        main_f.write('\n')
                                    has_data = True
                            
                            os.remove(temp_table_file)
                            
                        except Exception as e:
                            messages.error(request, f"Lỗi khi thực thi mysqldump: {str(e)}")
                            success = False
                    
                    with open(sql_filepath, 'a') as f:
                        f.write("\nSET FOREIGN_KEY_CHECKS=1;\n")
                    
                    if success and has_data:
                        sql_paths.append(sql_filepath)
                        
            if not sql_paths:
                messages.error(request, "Không có dữ liệu nào được xuất.")
                return None
            
            date_str = datetime.now().strftime('%Y%m%d')

            contest_ids_str = '_'.join([f"{contest}" for contest in queryset])

            zip_filename = f"{date_str}_{contest_ids_str}.zip"
            zip_filepath = os.path.join(tmpdir, zip_filename)
            
            with zipfile.ZipFile(zip_filepath, 'w') as zipf:
                for file in sql_paths:
                    zipf.write(file, arcname=os.path.basename(file))
            
            buffer = io.BytesIO()
            with open(zip_filepath, 'rb') as f:
                buffer.write(f.read())
            
            buffer.seek(0)
            return FileResponse(buffer, as_attachment=True, filename=zip_filename)
        
    def set_locked_after(self, contest, locked_after):
        with transaction.atomic():
            contest.locked_after = locked_after
            contest.save()
            Submission.objects.filter(contest_object=contest,
                                    contest__participation__virtual=0).update(locked_after=locked_after)

    def get_urls(self):
        return [
            path('rate/all/', self.rate_all_view, name='judge_contest_rate_all'),
            path('<int:id>/rate/', self.rate_view, name='judge_contest_rate'),
            path('<int:contest_id>/rejudge/<int:problem_id>/', self.rejudge_view, name='judge_contest_rejudge'),
            path('<int:contest_id>/rescore/<int:problem_id>/', self.rescore_view, name='judge_contest_rescore'),
            path('<int:contest_id>/resend/<int:announcement_id>/', self.resend_view, name='judge_contest_resend'),
            path('import/', self.import_contests_view, name='judge_contest_import'),
        ] + super(ContestAdmin, self).get_urls()

    @method_decorator(require_POST)
    def rejudge_view(self, request, contest_id, problem_id):
        contest = get_object_or_404(Contest, id=contest_id)
        if not request.user.is_staff or not self.has_change_permission(request, contest):
            raise PermissionDenied()
        queryset = ContestSubmission.objects.filter(participation__contest_id=contest_id,
                                                    problem_id=problem_id).select_related('submission')
        for model in queryset:
            model.submission.judge(rejudge=True, rejudge_user=request.user)

        self.message_user(request, ngettext('%d submission was successfully scheduled for rejudging.',
                                            '%d submissions were successfully scheduled for rejudging.',
                                            len(queryset)) % len(queryset))
        return HttpResponseRedirect(reverse('admin:judge_contest_change', args=(contest_id,)))

    @method_decorator(require_POST)
    def rescore_view(self, request, contest_id, problem_id):
        contest = get_object_or_404(Contest, id=contest_id)
        if not request.user.is_staff or not self.has_change_permission(request, contest):
            raise PermissionDenied()
        queryset = ContestSubmission.objects.filter(participation__contest_id=contest_id,
                                                    problem_id=problem_id).select_related('submission')
        for model in queryset:
            model.submission.update_contest()

        self.message_user(request, ngettext('%d submission was successfully rescored.',
                                            '%d submissions were successfully rescored.',
                                            len(queryset)) % len(queryset))
        return HttpResponseRedirect(reverse('admin:judge_contest_change', args=(contest_id,)))

    @method_decorator(require_POST)
    def resend_view(self, request, contest_id, announcement_id):
        contest = get_object_or_404(Contest, id=contest_id)
        if not request.user.is_staff or not self.has_change_permission(request, contest):
            raise PermissionDenied()
        announcement = get_object_or_404(ContestAnnouncement, id=announcement_id)
        announcement.send()
        return HttpResponseRedirect(reverse('admin:judge_contest_change', args=(contest_id,)))

    @method_decorator(require_POST)
    def rate_all_view(self, request):
        if not request.user.has_perm('judge.contest_rating'):
            raise PermissionDenied()
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('TRUNCATE TABLE `%s`' % Rating._meta.db_table)
            Profile.objects.update(rating=None)
            for contest in Contest.objects.filter(is_rated=True, end_time__lte=timezone.now()).order_by('end_time'):
                rate_contest(contest)
        return HttpResponseRedirect(reverse('admin:judge_contest_changelist'))

    @method_decorator(require_POST)
    def rate_view(self, request, id):
        if not request.user.has_perm('judge.contest_rating'):
            raise PermissionDenied()
        contest = get_object_or_404(Contest, id=id)
        if not contest.is_rated or not contest.ended:
            raise Http404()
        with transaction.atomic():
            contest.rate()
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', reverse('admin:judge_contest_changelist')))

    def import_contests_view(self, request):
        if request.method == 'POST':
            zip_file = request.FILES['zip_file']
            imported_names = self.import_contests(zip_file)
            if imported_names:
                name_list = ', '.join(imported_names)
                self.message_user(request, f'Contests: {name_list} imported successfully.')

            else:
                self.message_user(request, 'Import contest failed.', level='warning')
            return HttpResponseRedirect('/admin/judge/contest/')
        return self.render_change_form(
            request,
            context={
                **self.admin_site.each_context(request),
                'opts': self.model._meta,
                'action_form': None,
            }
        )

    def import_contests(self, zip_file):
        overwrite = True
        import os, tempfile, zipfile, re
        from django.db import connection, transaction
        from django.contrib import messages
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_zip_path = os.path.join(tmpdir, 'contests.zip')
            with open(temp_zip_path, 'wb') as f:
                for chunk in zip_file.chunks():
                    f.write(chunk)
            
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir)
            
            sql_files = [f for f in os.listdir(tmpdir) if f.endswith('.sql') and f.startswith('contest_')]
            
            if not sql_files:
                raise ValueError("No SQL files found in the ZIP archive")
            
            sql_files.sort()
            
            cursor = connection.cursor()
            contest_name_list = []
            for sql_file in sql_files:
                match = re.match(r'contest_(\d+)\.sql', sql_file)
                if not match:
                    continue
                    
                contest_id = match.group(1)
                sql_path = os.path.join(tmpdir, sql_file)
                
                with open(sql_path, 'r', encoding='utf-8') as f:
                    sql_content = f.read()
                
                with transaction.atomic():
                    try:
                        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
                        
                        sql_statements = []
                        current_statement = ""
                        
                        for line in sql_content.split('\n'):
                            if line.strip().startswith('--') or not line.strip():
                                continue
                            
                            if line.strip().upper().startswith('SET '):
                                if current_statement:
                                    sql_statements.append(current_statement)
                                    current_statement = ""
                                sql_statements.append(line)
                                continue
                                
                            current_statement += line + "\n"
                            
                            if line.strip().endswith(';'):
                                sql_statements.append(current_statement)
                                current_statement = ""
                        
                        if current_statement.strip():
                            sql_statements.append(current_statement)
                        

                        temp_contest_name = None
                        for statement in sql_statements:
                            modified_statement = statement

                            if modified_statement.strip().startswith("INSERT INTO `judge_contest`"):
                                match = re.search(r"INSERT INTO `judge_contest` VALUES\s*\(\s*(\d+)\s*,\s*'([^']*)'\s*,\s*'([^']*)'", modified_statement)
                                if match:
                                    temp_contest_name = match.group(3)
                            if "LOCK TABLES" in modified_statement.upper() or "UNLOCK TABLES" in modified_statement.upper():
                                continue
                                
                            if modified_statement.strip().upper().startswith('INSERT INTO'):
                                table_match = re.search(r'INSERT INTO\s+`?(\w+)`?', modified_statement)
                                table_name = table_match.group(1).strip('`') if table_match else None
                                
                                sensitive_tables = ['django_migrations']
                                
                                if table_name and table_name not in sensitive_tables:
                                    if overwrite:
                                        modified_statement = modified_statement.replace('INSERT INTO', 'REPLACE INTO', 1)
                                    else:
                                        modified_statement = modified_statement.replace('INSERT INTO', 'INSERT IGNORE INTO', 1)
                                        
                            
                            if modified_statement.strip():
                                try:
                                    cursor.execute(modified_statement)
                                except Exception as e:
                                    print(f"Error executing statement: {modified_statement[:100]}...")
                                    print(f"Error details: {str(e)}")
                                    if "SET " not in modified_statement.upper() and "LOCK" not in modified_statement.upper():
                                        raise
                        
                        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        
                        if temp_contest_name:
                            contest_name_list.append(temp_contest_name)
                    except Exception as e:
                        raise Exception(f"Error importing contest {contest_id}: {str(e)}")
            return contest_name_list  
                                    
    def get_form(self, request, obj=None, **kwargs):
        form = super(ContestAdmin, self).get_form(request, obj, **kwargs)
        if 'problem_label_script' in form.base_fields:
            # form.base_fields['problem_label_script'] does not exist when the user has only view permission
            # on the model.
            form.base_fields['problem_label_script'].widget = AceWidget(
                mode='lua', theme=request.profile.resolved_ace_theme,
            )

        perms = ('edit_own_contest', 'edit_all_contest')
        form.base_fields['curators'].queryset = Profile.objects.filter(
            Q(user__is_superuser=True) |
            Q(user__groups__permissions__codename__in=perms) |
            Q(user__user_permissions__codename__in=perms),
        ).distinct()
        return form


class ContestParticipationForm(ModelForm):
    class Meta:
        widgets = {
            'contest': AdminSelect2Widget(),
            'user': AdminHeavySelect2Widget(data_view='profile_select2'),
        }


class ContestParticipationAdmin(admin.ModelAdmin):
    fields = ('contest', 'user', 'real_start', 'virtual', 'is_disqualified')
    list_display = ('contest', 'username', 'show_virtual', 'real_start', 'score', 'cumtime', 'tiebreaker')
    actions = ['recalculate_results']
    actions_on_bottom = actions_on_top = True
    search_fields = ('contest__key', 'contest__name', 'user__user__username')
    form = ContestParticipationForm
    date_hierarchy = 'real_start'

    def get_queryset(self, request):
        return super(ContestParticipationAdmin, self).get_queryset(request).only(
            'contest__name', 'contest__format_name', 'contest__format_config',
            'user__user__username', 'real_start', 'score', 'cumtime', 'tiebreaker', 'virtual',
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if form.changed_data and 'is_disqualified' in form.changed_data:
            obj.set_disqualified(obj.is_disqualified)

    @admin.display(description=_('Recalculate results'))
    def recalculate_results(self, request, queryset):
        count = 0
        for participation in queryset:
            participation.recompute_results()
            count += 1
        self.message_user(request, ngettext('%d participation recalculated.',
                                            '%d participations recalculated.',
                                            count) % count)

    @admin.display(description=_('username'), ordering='user__user__username')
    def username(self, obj):
        return obj.user.username

    @admin.display(description=_('virtual'), ordering='virtual')
    def show_virtual(self, obj):
        return obj.virtual or '-'
