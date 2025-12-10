from django.contrib import admin
from .models import Users

# Register your models here.

@admin.register(Users)
class UsersAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'username')
    search_fields = ('email', 'username')