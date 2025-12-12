from django.contrib import admin
from .models import Users, OTP

# Register your models here.

@admin.register(Users)
class UsersAdmin(admin.ModelAdmin):
    list_display = ('email', 'username')
    search_fields = ('email', 'username')
    
@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ('user', 'otp_code', 'is_verified')
    
    
admin.site.site_header = 'EKNA Administration'
admin.site.site_title = 'EKNA Admin'
admin.site.index_title = 'Welcome to EKNA Administration'