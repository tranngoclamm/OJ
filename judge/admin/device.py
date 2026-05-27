import csv
from django.http import HttpResponse
from django.contrib import admin
from judge.models.device import Device, Room, ContestSeat
from judge.models.contest import Contest
from judge.admin.runtime import ContestSeatAdminForm
from django.utils.html import format_html
from django.urls import reverse
from django.contrib.admin import RelatedFieldListFilter, SimpleListFilter
from django.contrib import messages
from django.utils import timezone
from django.contrib.sessions.models import Session
from django.core.cache import caches

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "hostname",
        "mac",
        "room",
        "last_ip",
        "is_active",
        "last_seen",
        "created_at",
        "updated_at",
    )

    search_fields = ("hostname", "device_id", "mac")
    list_filter = ("is_active", "room")
    ordering = ("hostname",)

    readonly_fields = ("last_seen",)

    def short_key(self, obj):
        return obj.public_key[:30] + "..."
    short_key.short_description = "Public Key"


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code",)

class ContestRelatedFilter(RelatedFieldListFilter):
    def field_choices(self, field, request, model_admin):
        return field.get_choices(
            include_blank=False,
            ordering=["-id"]  # 👈 quan trọng
        )

class ContestMultiFilter(SimpleListFilter):
    title = "contest"
    parameter_name = "contest__in"

    def lookups(self, request, model_admin):
        contest_ids = ContestSeat.objects.values_list("contest_id", flat=True).distinct()

        contests = Contest.objects.filter(id__in=contest_ids).order_by("-id")

        return [(c.id, c.name) for c in contests]

    def queryset(self, request, queryset):
        values = request.GET.getlist(self.parameter_name)
        if values:
            return queryset.filter(contest__id__in=values)
        return queryset

@admin.register(ContestSeat)
class ContestSeatAdmin(admin.ModelAdmin):
    form = ContestSeatAdminForm
    list_display = ("contest", "user_display", "device_hostname", "assigned_at", "updated_at")
    # list_filter = ("contest",)
    # list_filter = (
    #     ("contest", ContestRelatedFilter),
    # )
    list_filter = (ContestMultiFilter,)
    search_fields = ("user__user__username", "contest__name", "user__user__first_name", "device__hostname")
    autocomplete_fields = ("contest", "user")
    ordering = ("-updated_at", "-assigned_at",)
    # actions = ["clear_device"]
    actions = ["force_logout_users", "clear_device", "redistribute_devices", "export_csv" ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("contest", "user__user", "device")

    def device_hostname(self, obj):
        return obj.device.hostname if obj.device else "-"

    def user_display(self, obj):
        user = obj.user.user

        url = reverse("admin:auth_user_change", args=[user.id])

        return format_html(
            '<a href="{}" style="color:#333">{} ({})</a>',
            url,
            user.username,
            user.first_name or "-"
        )

    user_display.short_description = "User"
    user_display.admin_order_field = "user__user__username"
    device_hostname.short_description = "Device"
    device_hostname.admin_order_field = "device__hostname"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "contest":
            kwargs["queryset"] = db_field.related_model.objects.order_by("-id")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def build_filename(self, queryset):
        contest_keys = set(obj.contest.key for obj in queryset)

        print("contest_keys:", contest_keys)

        prefix_map = {}

        for key in contest_keys:
            if "_" in key:
                prefix, suffix = key.rsplit("_", 1)
            else:
                prefix, suffix = key, ""

            prefix_map.setdefault(prefix, set()).add(suffix)

        print("prefix_map:", prefix_map)

        parts = []

        for prefix, suffixes in prefix_map.items():
            suffixes = sorted(s for s in suffixes if s)
            if suffixes:
                parts.append(prefix + "_" + "_".join(suffixes))
            else:
                parts.append(prefix)

        filename = "__".join(parts)

        print("filename:", filename)

        return filename

    def export_csv(self, request, queryset):
        # response = HttpResponse(content_type='text/csv')
        filename = self.build_filename(queryset)
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response.write('\ufeff')
        # response['Content-Disposition'] = 'attachment; filename=contest_seats.csv'
        response['Content-Disposition'] = f'attachment; filename={filename}.csv'

        writer = csv.writer(response)
        writer.writerow(["Contest", "Username", "Full Name", "Device", "Assigned At", "Update At"])

        for obj in queryset:
            writer.writerow([
                obj.contest,
                obj.user.user.username,
                obj.user.user.first_name,
                obj.device.hostname if obj.device else "",
                obj.assigned_at,
                obj.updated_at
            ])

        return response
    
    def redistribute_devices(self, request, queryset):
        from collections import defaultdict
        from django.utils import timezone as tz

        print("==== REDISTRIBUTE START ====")
        print("Selected seats:", queryset.count())

        if not queryset.exists():
            self.message_user(request, "No seats selected")
            return

        contest = queryset.first().contest
        print("Contest:", contest)

        now_start = contest.start_time
        now_end = contest.end_time

        # 👉 group seats theo room
        seats_by_room = defaultdict(list)

        for seat in queryset.select_related("device__room"):
            if seat.device and seat.device.room:
                seats_by_room[seat.device.room_id].append(seat)
            else:
                print(f"[WARN] Seat {seat.id} has no device or room")

        print("Rooms found:", list(seats_by_room.keys()))

        # 👉 lấy device đang bị chiếm bởi contest khác
        busy_device_ids = set(
            ContestSeat.objects.filter(
                contest__start_time__lt=now_end,
                contest__end_time__gt=now_start,
            ).exclude(
                contest=contest
            ).values_list('device_id', flat=True)
        )

        print("busy_device_ids:", busy_device_ids)

        updated = 0

        # =========================
        # 🔁 XỬ LÝ TỪNG ROOM
        # =========================
        for room_id, seats in seats_by_room.items():
            print("\n---- ROOM", room_id)
            print("Seats:", [s.id for s in seats])

            # 👉 device đang dùng trong queryset
            current_devices = [s.device for s in seats if s.device]
            print("current_devices:", [d.id for d in current_devices])

            # 👉 device available trong room
            available_devices = list(
                Device.objects.filter(
                    room_id=room_id,
                    is_active=True
                ).exclude(
                    id__in=busy_device_ids
                )
            )

            print("available_devices:", [d.id for d in available_devices])

            # 👉 gộp lại (unique)
            all_devices = {d.id: d for d in current_devices + available_devices}
            all_devices = list(all_devices.values())

            print("all_devices:", [d.id for d in all_devices])

            if not all_devices:
                print("[SKIP] No devices")
                continue

            # 👉 sort để ổn định
            all_devices.sort(key=lambda d: (d.room.code, d.hostname))

            # 👉 giãn cách
            step = max(1, len(all_devices) // len(seats))
            selected_devices = all_devices[::step][:len(seats)]

            print("step:", step)
            print("selected_devices:", [d.id for d in selected_devices])

            # 👉 gán lại
            for seat, device in zip(seats, selected_devices):
                print(f"Assign seat {seat.id} -> device {device.hostname}")
                seat.device = device
                seat.save(update_fields=["device", "updated_at"])

                updated += 1

        print("==== DONE ====")

        self.message_user(
            request,
            f"Redistributed devices for {updated} seats",
            level=messages.SUCCESS
        )
    def clear_device(self, request, queryset):
        updated = queryset.update(device=None)

        self.message_user(
            request,
            f"Cleared device for {updated} contest seat(s).",
            level=messages.SUCCESS
        )

    clear_device.short_description = "Remove device"

    def delete_user_sessions(self, user):
        sessions = Session.objects.filter(expire_date__gte=timezone.now())
        count = 0
        cache = caches['default']
        for session in sessions:
            data = session.get_decoded()
            if data.get('_auth_user_id') == str(user.id):
                cache_key = "django.contrib.sessions.cached_db" + session.session_key
                cache.delete(cache_key)
                session.delete()
                count += 1

        return count

    def force_logout_users(self, request, queryset):
        total_sessions = 0
        total_users = 0

        for seat in queryset:
            if seat.user and seat.user.user:
                total_sessions += self.delete_user_sessions(seat.user.user)
                total_users += 1

        self.message_user(
            request,
            f"Successfully force logged out {total_users} user(s). "
            f"Removed {total_sessions} active session(s)."
        )
    force_logout_users.short_description = "Force logout"
