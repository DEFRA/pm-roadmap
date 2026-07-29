from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.contrib import messages

from .models import Tag, Roadmap, Item, Organisation
from .importers import import_items, build_template_workbook


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ['name', 'abbreviation', 'created_at']
    search_fields = ['name', 'abbreviation']
    fields = ['name', 'abbreviation', 'description']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'tag_type', 'roadmap', 'colour']
    list_filter = ['tag_type', 'roadmap']
    search_fields = ['name']
    fields = ['name', 'tag_type', 'roadmap', 'colour', 'description', 'link']


class ItemInline(admin.TabularInline):
    model = Item
    extra = 1
    fields = ['item_type', 'title', 'priority', 'size', 'start_date', 'end_date']
    show_change_link = True


@admin.register(Roadmap)
class RoadmapAdmin(admin.ModelAdmin):
    list_display = ['name', 'team', 'roadmap_type', 'created_at']
    list_filter = ['roadmap_type']
    search_fields = ['name', 'team']
    filter_horizontal = ['tags', 'organisations']
    change_list_template = 'admin/roadmap/roadmap/change_list.html'
    fieldsets = [
        (None, {
            'fields': ['name', 'roadmap_type', 'team', 'organisations', 'description'],
        }),
        ('Mission & Vision', {
            'fields': ['mission', 'vision'],
        }),
        ('Tags', {
            'fields': ['tags'],
            'description': 'Assign Outcome / Gov Objective / Team / Objective tags directly to this roadmap.',
        }),
    ]
    inlines = [ItemInline]

    def get_urls(self):
        custom = [
            path(
                'upload-items/',
                self.admin_site.admin_view(self._upload_view),
                name='roadmap_upload_items',
            ),
            path(
                'upload-items/template/',
                self.admin_site.admin_view(self._template_download_view),
                name='roadmap_upload_template',
            ),
        ]
        return custom + super().get_urls()

    # ── Upload view ───────────────────────────────────────────────────────────

    def _upload_view(self, request):
        context = {
            **self.admin_site.each_context(request),
            'title': 'Upload items from spreadsheet',
            'template_url': reverse('admin:roadmap_upload_template'),
            'result': None,
        }

        if request.method == 'POST':
            upload = request.FILES.get('spreadsheet')
            if not upload:
                messages.error(request, 'Please choose a file to upload.')
            else:
                result = import_items(upload)
                context['result'] = result

                if not result['errors']:
                    roadmap = result.get('roadmap')
                    messages.success(
                        request,
                        f"Import complete — "
                        f"{result['created']} created, "
                        f"{result['updated']} updated, "
                        f"{result['skipped']} skipped"
                        + (f" on \"{roadmap}\"." if roadmap else "."),
                    )

        return render(request, 'admin/roadmap/upload_items.html', context)

    # ── Template download ─────────────────────────────────────────────────────

    def _template_download_view(self, request):
        wb = build_template_workbook()
        response = HttpResponse(
            content_type=(
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        )
        response['Content-Disposition'] = (
            'attachment; filename="roadmap_items_template.xlsx"'
        )
        wb.save(response)
        return response


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['title', 'item_type', 'roadmap', 'priority', 'size', 'start_date', 'end_date']
    list_filter = ['item_type', 'priority', 'size', 'roadmap', 'tags']
    search_fields = ['title', 'description']
    filter_horizontal = ['tags', 'linked_activities']
    fieldsets = [
        (None, {
            'fields': ['roadmap', 'item_type', 'title', 'description', 'tags'],
        }),
        ('Activity Details', {
            'fields': ['priority', 'size', 'prd_link', 'backlog_link'],
            'classes': ['collapse'],
        }),
        ('Timeline', {
            'fields': ['start_date', 'end_date'],
        }),
        ('Linked Activities', {
            'fields': ['linked_activities'],
            'classes': ['collapse'],
            'description': 'For milestones and key results: link to related activities.',
        }),
    ]
