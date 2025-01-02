from django.contrib import admin
from .models import InboxItem, SingleTask, Project, ProjectTask, Sprint, Retrospective

@admin.register(InboxItem)
class InboxItemAdmin(admin.ModelAdmin):
    list_display = ('text', 'user', 'created_at', 'processed', 'eliminated')
    list_filter = ('processed', 'eliminated', 'archive_category')
    search_fields = ('text',)
    date_hierarchy = 'created_at'

@admin.register(SingleTask)
class SingleTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'category', 'status', 'archived')
    list_filter = ('status', 'archived', 'category')
    search_fields = ('title', 'description')
    date_hierarchy = 'created_at'

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'category', 'status', 'archived')
    list_filter = ('status', 'archived', 'category')
    search_fields = ('title', 'description')
    date_hierarchy = 'created_at'

@admin.register(ProjectTask)
class ProjectTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'user', 'category', 'status', 'archived')
    list_filter = ('status', 'archived', 'category')
    search_fields = ('title', 'description', 'project__title')
    date_hierarchy = 'created_at'

@admin.register(Sprint)
class SprintAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'start_date', 'end_date', 'status')
    list_filter = ('status',)
    search_fields = ('user__username',)
    date_hierarchy = 'start_date'

@admin.register(Retrospective)
class RetrospectiveAdmin(admin.ModelAdmin):
    list_display = ('sprint', 'completion_rate', 'average_efficiency', 'created_at')
    list_filter = ('sprint__status',)
    search_fields = ('sprint__user__username', 'achievements', 'challenges')
    date_hierarchy = 'created_at'
