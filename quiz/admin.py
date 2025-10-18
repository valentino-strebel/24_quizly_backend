from django.contrib import admin
from django.db import models
from django import forms

from .models import Quiz, Question


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    show_change_link = True
    fields = ("question_title", "question_options", "answer", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")

    formfield_overrides = {
        models.JSONField: {"widget": forms.Textarea(attrs={"rows": 4})},
    }


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("title", "description", "owner__username", "owner__email")
    readonly_fields = ("created_at", "updated_at")
    fields = ("owner", "title", "description", "video_url", "created_at", "updated_at")
    ordering = ("-created_at",)
    inlines = [QuestionInline]

    def save_model(self, request, obj, form, change):
        """
        On create, if no owner set, default to the current user.
        """
        if not change and not obj.owner_id:
            obj.owner = request.user
        super().save_model(request, obj, form, change)



@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "quiz", "created_at", "updated_at")
    list_filter = ("quiz", "created_at", "updated_at")
    search_fields = ("question_title", "answer", "quiz__title")
    readonly_fields = ("created_at", "updated_at")
    fields = ("quiz", "question_title", "question_options", "answer", "created_at", "updated_at")
    ordering = ("quiz", "id")
    autocomplete_fields = ("quiz",)

    formfield_overrides = {
        models.JSONField: {"widget": forms.Textarea(attrs={"rows": 4})},
    }
